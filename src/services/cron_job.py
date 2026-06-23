"""Cron job service with APScheduler integration and async task execution."""

import asyncio
import json
import logging
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.repositories.cron_job import CronJobRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CronJobService:
    """Service for managing recurring scheduled tasks with APScheduler."""

    def __init__(
        self,
        cron_job_repo: CronJobRepository,
        tool_executor: Optional[Any] = None,
        crew: Optional[Any] = None,
        message_handler: Optional[Any] = None,
        whatsapp_service: Optional[Any] = None,
        slack_service: Optional[Any] = None,
        settings_service: Optional[Any] = None,
    ):
        """Initialize cron job service.

        Args:
            cron_job_repo: Cron job repository instance
            tool_executor: ToolExecutor instance for direct tool execution
            crew: PersonalAssistantCrew instance for prompt jobs (legacy)
            message_handler: MessageHandler instance for skills-based execution
            whatsapp_service: WhatsAppService for proactive message delivery
            slack_service: SlackService for proactive message delivery
        """
        self.repo = cron_job_repo
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._tool_executor = tool_executor
        self._crew = crew
        self._message_handler = message_handler
        self._whatsapp_service = whatsapp_service
        self._slack_service = slack_service
        self._settings_service = settings_service

        # Concurrency control
        self._job_semaphore: Optional[asyncio.Semaphore] = None
        self._active_tasks: Dict[int, asyncio.Task] = {}  # execution_id -> task

        # Configuration from environment
        self.max_concurrent_jobs = int(os.getenv("CRON_MAX_CONCURRENT_JOBS", "5"))
        self.max_job_timeout = int(os.getenv("CRON_JOB_TIMEOUT_SECONDS", "1200"))  # 20 minutes

        logger.info(
            f"CronJobService initialized: max_concurrent={self.max_concurrent_jobs}, "
            f"timeout={self.max_job_timeout}s"
        )

    def start_scheduler(self) -> None:
        """Start the APScheduler and load persisted jobs."""
        if self.scheduler and self.scheduler.running:
            logger.warning("Scheduler is already running")
            return

        # Initialize semaphore for concurrency control
        self._job_semaphore = asyncio.Semaphore(self.max_concurrent_jobs)

        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        logger.info(
            f"APScheduler started with max_concurrent={self.max_concurrent_jobs}, "
            f"timeout={self.max_job_timeout}s"
        )

        # Load enabled jobs from database
        self._load_persisted_jobs()

    def shutdown_scheduler(self) -> None:
        """Shutdown the APScheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("APScheduler shut down")

    def _load_persisted_jobs(self) -> None:
        """Load all enabled jobs from the database into the scheduler."""
        jobs = self.repo.list_jobs(enabled_only=True)
        loaded = 0
        for job in jobs:
            try:
                self._schedule_job(job)
                loaded += 1
            except Exception as e:
                logger.error(f"Failed to load job {job['job_id']}: {e}")

        logger.info(f"Loaded {loaded} persisted cron jobs into scheduler")

    def _schedule_job(self, job: Dict[str, Any]) -> None:
        """Add a job to the APScheduler.

        Args:
            job: Job record from database
        """
        if not self.scheduler:
            logger.warning("Scheduler not initialized, cannot schedule job")
            return

        user_tz = "UTC"
        if self._settings_service:
            user_tz = self._settings_service.get_config_with_fallback("user.timezone", "UTC")

        try:
            trigger = CronTrigger.from_crontab(job["cron_expression"], timezone=user_tz)
        except ValueError as e:
            logger.error(f"Invalid cron expression for job {job['job_id']}: {e}")
            return

        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job["job_id"],
            name=job["name"],
            kwargs={"job_id": job["job_id"]},
            replace_existing=True,
        )

        # Update next_run_at in database
        scheduler_job = self.scheduler.get_job(job["job_id"])
        if scheduler_job and scheduler_job.next_run_time:
            self.repo.update_next_run(
                job["job_id"],
                scheduler_job.next_run_time.isoformat(),
            )

        logger.info(
            f"Scheduled job {job['job_id']} ({job['name']}) " f"with cron: {job['cron_expression']}"
        )

    def reschedule_all_jobs(self) -> int:
        """Re-evaluate every enabled job's trigger against the current settings.

        Called when a schedule-affecting global setting changes (e.g. the user's
        timezone) so existing jobs immediately pick up the new value instead of
        waiting for a restart. Each job is unscheduled and re-scheduled, which
        re-reads the current timezone in ``_schedule_job``.

        Returns:
            Number of jobs rescheduled.
        """
        if not self.scheduler or not self.scheduler.running:
            logger.debug("Scheduler not running, skipping reschedule_all_jobs")
            return 0

        rescheduled = 0
        for job in self.repo.list_jobs(enabled_only=True):
            try:
                self._unschedule_job(job["job_id"])
                self._schedule_job(job)
                rescheduled += 1
            except Exception as e:
                logger.error(f"Failed to reschedule job {job['job_id']}: {e}")

        logger.info(f"Rescheduled {rescheduled} cron jobs after settings change")
        return rescheduled

    def _unschedule_job(self, job_id: str) -> None:
        """Remove a job from the APScheduler.

        Args:
            job_id: Job identifier
        """
        if not self.scheduler:
            return

        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Unscheduled job {job_id}")
        except Exception:
            # Job may not be in scheduler
            pass

    async def _execute_job(self, job_id: str) -> None:
        """Execute a scheduled job with instance locking and async task management.

        Args:
            job_id: Job identifier
        """
        # Try to acquire execution lock for horizontal scaling
        instance_id = os.getenv("INSTANCE_ID", socket.gethostname())

        if not self.repo.try_acquire_execution_lock(job_id, instance_id):
            logger.debug(f"Job {job_id} already running on another instance")
            return

        try:
            job = self.repo.get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found for execution")
                return

            if not job["enabled"]:
                logger.info(f"Job {job_id} is disabled, skipping execution")
                return

            # Create execution record
            execution_id = self.repo.create_execution(
                job_id=job_id,
                job_type="cron",
            )

            # Update last_run_at
            self.repo.update_last_run(job_id, datetime.utcnow().isoformat())

            # Update next_run_at
            if self.scheduler:
                scheduler_job = self.scheduler.get_job(job_id)
                if scheduler_job and scheduler_job.next_run_time:
                    self.repo.update_next_run(
                        job_id,
                        scheduler_job.next_run_time.isoformat(),
                    )

            # Create async task (fire and forget, but wait for completion to release lock)
            task = asyncio.create_task(self._execute_job_logic(job, execution_id))
            self._active_tasks[execution_id] = task

            # Cleanup callback
            task.add_done_callback(lambda t: self._active_tasks.pop(execution_id, None))

            # Wait for task completion before releasing lock
            await task

        finally:
            # Always release lock
            self.repo.release_execution_lock(job_id, instance_id)

    async def _execute_job_logic(self, job: Dict[str, Any], execution_id: int) -> None:
        """Execute job with resource management and logging.

        Args:
            job: Job record from database
            execution_id: Execution record ID
        """
        # Setup logging context
        job_logger = logging.LoggerAdapter(
            logger, {"job_id": job["job_id"], "execution_id": execution_id, "job_name": job["name"]}
        )

        job_logger.info("Starting job execution")

        try:
            # Acquire semaphore (limits concurrency)
            async with self._job_semaphore:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self._run_job(job, execution_id, job_logger), timeout=self.max_job_timeout
                )

                self.repo.complete_execution(
                    execution_id=execution_id, status="success", result=result
                )
                job_logger.info("Job completed successfully")

        except asyncio.TimeoutError:
            error_msg = f"Job exceeded timeout of {self.max_job_timeout}s"
            job_logger.error(error_msg)
            self.repo.complete_execution(
                execution_id=execution_id, status="cancelled", error_message=error_msg
            )
        except asyncio.CancelledError:
            job_logger.warning("Job cancelled")
            self.repo.complete_execution(
                execution_id=execution_id, status="cancelled", error_message="Job cancelled"
            )
            raise
        except Exception as e:
            job_logger.error(f"Job failed: {e}", exc_info=True)
            self.repo.complete_execution(
                execution_id=execution_id, status="failed", error_message=str(e)
            )

    async def _run_job(
        self, job: Dict[str, Any], execution_id: int, job_logger: logging.LoggerAdapter
    ) -> Dict[str, Any]:
        """Route job to appropriate execution method.

        Args:
            job: Job record
            execution_id: Execution record ID
            job_logger: Logger with job context

        Returns:
            Execution result
        """
        # Multi-step recipe: steps column is populated (always the case after migration 048)
        if job.get("steps"):
            return await self._run_recipe_job(job, job_logger)

        # Legacy single-action fallback (pre-migration rows or manually created)
        if job["job_type"] == "tool":
            return await self._run_tool_job(job, job_logger)

        if self._message_handler:
            return await self._run_message_handler_job(job, job_logger)

        raise RuntimeError(
            "Cannot execute prompt job: MessageHandler not initialized. "
            f"Job: {job.get('name', 'unknown')}"
        )

    async def _run_recipe_job(
        self, job: Dict[str, Any], job_logger: logging.LoggerAdapter
    ) -> Dict[str, Any]:
        """Execute a multi-step recipe in order, wiring variables between steps.

        Pinned-tool steps call ToolExecutor directly (no LLM, fully deterministic).
        Prompt steps call MessageHandler with required_skills pre-loaded so tools
        are always available regardless of the prompt wording.
        """
        steps = sorted(job["steps"], key=lambda s: s.get("order", 0))
        required_skills: List[str] = job.get("required_skills") or []
        plan_variables: Dict[str, Any] = {}
        results = []

        job_logger.info("Running recipe with %d steps", len(steps))

        for step in steps:
            order = step.get("order", "?")
            description = step.get("description", "")
            tool_name = step.get("tool_name")
            stores_as = step.get("stores_as")
            uses_variable = step.get("uses_variable")

            job_logger.info("Step %s: %s", order, description[:80])

            try:
                if tool_name and not uses_variable:
                    # Pinned-tool step — call directly, zero LLM involvement.
                    # Only valid when no variable injection is needed; a pinned tool
                    # cannot accept arbitrary keyword args like 'context'.
                    if not self._tool_executor:
                        raise RuntimeError("ToolExecutor not initialised for pinned-tool step")
                    params = dict(step.get("tool_parameters") or {})
                    result = await self._tool_executor.execute_tool(
                        tool_name=tool_name,
                        arguments=params,
                        tool_call_id=f"recipe_{job['job_id']}_step{order}",
                        iteration=order if isinstance(order, int) else 1,
                    )
                else:
                    # Prompt-based step — or pinned tool that needs variable data.
                    # Variable-dependent steps must go through the LLM so it can
                    # read the data and call the tool with the correct parameters.
                    if not self._message_handler:
                        raise RuntimeError("MessageHandler not initialised for prompt step")
                    prompt = step.get("prompt_template") or description
                    if tool_name:
                        prompt = f"Use the tool {tool_name} to accomplish: {prompt}"
                    if uses_variable and uses_variable in plan_variables:
                        # Resolve {{variable_name}} placeholders in the template,
                        # then append the raw data as a fallback so the LLM always
                        # has the full context even if the template didn't reference it.
                        var_val = plan_variables[uses_variable]
                        import re

                        prompt = re.sub(
                            r"\{\{" + re.escape(uses_variable) + r"\}\}",
                            str(var_val) if len(str(var_val)) < 4000 else f"[see data below]",
                            prompt,
                        )
                        prompt = f"{prompt}\n\nData from previous step: {var_val}"
                    result = await self._run_message_handler_job(
                        job, job_logger, prompt=prompt, initial_active_skills=required_skills
                    )

                # Store output as named variable for downstream steps
                if stores_as:
                    # Prefer an offloaded file path; fall back to serialised summary
                    plan_variables[stores_as] = result.get("file") or str(result)
                    job_logger.debug(
                        "Stored variable '%s' = %s", stores_as, plan_variables[stores_as]
                    )

                results.append({"step": order, "status": "success", "result": result})

            except Exception as exc:
                job_logger.error("Step %s failed: %s", order, exc)
                results.append({"step": order, "status": "failed", "error": str(exc)})
                # Continue remaining steps; partial success is better than a full abort

        return {"steps_executed": len(results), "results": results}

    async def _run_tool_job(
        self, job: Dict[str, Any], job_logger: logging.LoggerAdapter
    ) -> Dict[str, Any]:
        """Execute a tool job directly via ToolExecutor.

        Args:
            job: Job record
            job_logger: Logger with job context

        Returns:
            Execution result

        Raises:
            RuntimeError: If ToolExecutor not initialized or tool execution fails
        """
        if not self._tool_executor:
            raise RuntimeError("ToolExecutor not initialized - cannot execute tool jobs")

        tool_name = job["tool_name"]
        tool_params = job["tool_parameters"] or {}

        job_logger.info(f"Executing tool: {tool_name}")

        try:
            result = await self._tool_executor.execute_tool(
                tool_name=tool_name,
                arguments=tool_params,
                tool_call_id=f"cron_{job['job_id']}",
                iteration=1,
            )

            if result.get("success"):
                return {"status": "success", "result": result["result"]}
            else:
                raise RuntimeError(result.get("error", "Tool execution failed"))

        except Exception as e:
            job_logger.error(f"Tool execution failed: {e}")
            raise

    async def _run_message_handler_job(
        self,
        job: Dict[str, Any],
        job_logger: logging.LoggerAdapter,
        prompt: Optional[str] = None,
        initial_active_skills: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute a job (or one recipe step) via MessageHandler.

        When delivery_channel is set on the job, the LLM response is also
        sent to the user via WhatsApp or Slack and a fresh conversation is
        created so the scheduled question never appends to an ongoing chat.

        Args:
            job: Job record
            job_logger: Logger with job context
            prompt: Override prompt (used by recipe steps)
            initial_active_skills: Skills to pre-load before keyword matching

        Returns:
            Execution result

        Raises:
            RuntimeError: If MessageHandler not initialized
        """
        if not self._message_handler:
            raise RuntimeError(
                "MessageHandler not initialized - cannot execute message handler jobs"
            )

        prompt = prompt or job.get("prompt", "")
        if not prompt:
            raise ValueError("Prompt is required for message handler jobs")

        job_logger.info(f"Executing via MessageHandler: {prompt[:100]}...")

        delivery_channel = job.get("delivery_channel")

        # Resolve delivery contact from job config or fall back to settings default.
        delivery_contact = job.get("delivery_contact_identifier") or ""
        if delivery_channel and not delivery_contact:
            if delivery_channel == "whatsapp" and self._whatsapp_service:
                delivery_contact = (
                    self._whatsapp_service.settings_repo.get("whatsapp.phone_number") or ""
                )
            elif delivery_channel == "slack" and self._slack_service:
                delivery_contact = (
                    self._slack_service.settings_repo.get("slack.default_channel") or ""
                )

        if delivery_channel and not delivery_contact:
            job_logger.warning(
                f"delivery_channel='{delivery_channel}' set but no contact configured — "
                "falling back to silent system execution"
            )
            delivery_channel = None

        # Choose conversation routing.
        # Delivery jobs get a fresh conversation_id so the scheduled question
        # never appends to an ongoing user conversation.
        if delivery_channel and delivery_contact:
            channel = delivery_channel
            contact_identifier = delivery_contact
            conversation_id = f"sched-{uuid4().hex[:12]}"
            job_logger.info(
                f"Delivery routing: channel={channel}, contact={contact_identifier}, "
                f"conversation={conversation_id}"
            )
        else:
            channel = "system"
            contact_identifier = f"cron_{job['job_id']}"
            conversation_id = None

        # Pre-populate active_skills in conversation metadata so the handler
        # starts with the right tools loaded regardless of keyword matching.
        meta: Dict[str, Any] = {
            "job_id": job["job_id"],
            "job_name": job["name"],
            "source": "cron_job",
        }
        if initial_active_skills:
            meta["active_skills"] = list(initial_active_skills)

        try:
            result = await self._message_handler.handle_message(
                message=prompt,
                conversation_id=conversation_id,
                channel=channel,
                contact_identifier=contact_identifier,
                metadata=meta,
            )

            response = result["response"] or ""

            if delivery_channel and delivery_contact and response:
                await self._deliver_response(
                    delivery_channel, delivery_contact, response, job_logger
                )

            return {
                "status": "success",
                "response": response,
                "skills_used": result["skills_used"],
                "tools_executed": result["tools_executed"],
                "iterations": result["iterations"],
                "stuck_detected": result["stuck_detected"],
            }

        except Exception as e:
            job_logger.error(f"MessageHandler execution failed: {e}")
            raise

    async def _deliver_response(
        self,
        delivery_channel: str,
        delivery_contact: str,
        response: str,
        job_logger: logging.LoggerAdapter,
    ) -> None:
        """Send the LLM response to the user via the configured messaging channel.

        Uses send_message_to_owner / send_message_to_default_channel when a
        contact was resolved from settings, or send_message when an explicit
        contact was provided.  Delivery failures are logged but never propagate
        — the job result is still recorded as successful.
        """
        loop = asyncio.get_event_loop()
        try:
            if delivery_channel == "whatsapp":
                if not self._whatsapp_service:
                    job_logger.error("delivery_channel='whatsapp' but WhatsAppService not injected")
                    return
                await loop.run_in_executor(
                    None,
                    lambda: self._whatsapp_service.send_message(
                        phone_number=delivery_contact, message=response
                    ),
                )
                job_logger.info(f"Delivered response via WhatsApp to {delivery_contact}")

            elif delivery_channel == "slack":
                if not self._slack_service:
                    job_logger.error("delivery_channel='slack' but SlackService not injected")
                    return
                await loop.run_in_executor(
                    None,
                    lambda: self._slack_service.send_message(
                        channel=delivery_contact, message=response
                    ),
                )
                job_logger.info(f"Delivered response via Slack to {delivery_contact}")

            else:
                job_logger.warning(f"Unknown delivery_channel '{delivery_channel}', skipping")

        except Exception as e:
            job_logger.error(f"Failed to deliver via {delivery_channel}: {e}", exc_info=True)

    # --- Public CRUD Methods ---

    def create_job(
        self,
        name: str,
        cron_expression: str,
        job_type: str,
        description: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_parameters: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        required_skills: Optional[List[str]] = None,
        delivery_channel: Optional[str] = None,
        delivery_contact_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new cron job / recipe and schedule it.

        When steps are provided they define a multi-step recipe. required_skills
        is derived automatically from pinned tool_names when not supplied.

        Args:
            name: Human-readable job name
            cron_expression: Cron expression
            job_type: 'tool' or 'prompt'
            description: Optional description
            tool_name: Tool to execute (legacy single-tool jobs)
            tool_parameters: Tool parameters (legacy)
            prompt: Prompt for coordinator (legacy)
            steps: Ordered recipe steps
            required_skills: Skills pre-loaded at execution time
            delivery_channel: 'whatsapp' or 'slack' to proactively deliver output
            delivery_contact_identifier: Override contact; resolved from settings when omitted

        Returns:
            Created job record

        Raises:
            ValueError: If validation fails
        """
        # Ensure steps is a list, not a double-encoded JSON string
        if steps and isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except (json.JSONDecodeError, TypeError):
                steps = None

        if not steps:
            # Legacy validation
            if job_type not in ("tool", "prompt"):
                raise ValueError("job_type must be 'tool' or 'prompt'")
            if job_type == "tool" and not tool_name:
                raise ValueError("tool_name is required for tool jobs")
            if job_type == "prompt" and not prompt:
                raise ValueError("prompt is required for prompt jobs")

        try:
            CronTrigger.from_crontab(cron_expression)
        except ValueError as e:
            raise ValueError(f"Invalid cron expression: {e}")

        # Auto-derive required_skills from pinned tool_names when not supplied
        if steps and required_skills is None:
            required_skills = self._derive_skills_from_steps(steps)

        job_id = f"cron-{uuid4().hex[:12]}"

        job = self.repo.create_job(
            job_id=job_id,
            name=name,
            cron_expression=cron_expression,
            job_type=job_type,
            description=description,
            tool_name=tool_name,
            tool_parameters=tool_parameters,
            prompt=prompt,
            steps=steps,
            required_skills=required_skills,
            delivery_channel=delivery_channel,
            delivery_contact_identifier=delivery_contact_identifier,
        )

        self._schedule_job(job)

        return job

    def _derive_skills_from_steps(self, steps: List[Dict[str, Any]]) -> List[str]:
        """Return the unique skill names that own each pinned tool_name in steps."""
        if not self._tool_executor:
            return []
        skill_names: List[str] = []
        try:
            registry = (
                self._tool_executor.tool_registry
                if hasattr(self._tool_executor, "tool_registry")
                else None
            )
            # Fall back to looking up via message_handler's skill_repo if available
            skill_repo = (
                getattr(self._message_handler, "skill_repo", None)
                if self._message_handler
                else None
            )
            if skill_repo:
                for step in steps:
                    t = step.get("tool_name")
                    if t:
                        for skill in skill_repo.get_enabled_skills():
                            if t in (skill.tools or []) and skill.name not in skill_names:
                                skill_names.append(skill.name)
        except Exception:
            pass
        return skill_names

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a cron job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job record or None
        """
        return self.repo.get_job(job_id)

    def list_jobs(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all cron jobs.

        Args:
            enabled_only: If True, only return enabled jobs

        Returns:
            List of job records
        """
        return self.repo.list_jobs(enabled_only=enabled_only)

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a cron job and reschedule if needed.

        Args:
            job_id: Job identifier
            updates: Fields to update

        Returns:
            Updated job record, or None if not found

        Raises:
            ValueError: If validation fails
        """
        job = self.repo.get_job(job_id)
        if not job:
            return None

        # Validate cron expression if being updated
        if "cron_expression" in updates:
            try:
                CronTrigger.from_crontab(updates["cron_expression"])
            except ValueError as e:
                raise ValueError(f"Invalid cron expression: {e}")

        # Filter out None values
        filtered_updates = {k: v for k, v in updates.items() if v is not None}

        if not filtered_updates:
            return job

        self.repo.update_job(job_id, filtered_updates)

        # Reschedule if schedule-affecting fields changed
        reschedule_fields = {"cron_expression", "enabled"}
        if reschedule_fields & set(filtered_updates.keys()):
            updated_job = self.repo.get_job(job_id)
            if updated_job:
                self._unschedule_job(job_id)
                if updated_job["enabled"]:
                    self._schedule_job(updated_job)

        return self.repo.get_job(job_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete a cron job and unschedule it.

        Args:
            job_id: Job identifier

        Returns:
            True if deleted
        """
        self._unschedule_job(job_id)
        return self.repo.delete_job(job_id)

    def toggle_job(self, job_id: str, enabled: Optional[bool] = None) -> Optional[bool]:
        """Toggle or set the enabled state and update scheduler.

        Args:
            job_id: Job identifier
            enabled: If provided, set to this value. If None, toggle.

        Returns:
            New enabled state, or None if not found
        """
        new_state = self.repo.toggle_job(job_id, enabled)
        if new_state is None:
            return None

        if new_state:
            # Re-enable: schedule the job
            job = self.repo.get_job(job_id)
            if job:
                self._schedule_job(job)
        else:
            # Disable: remove from scheduler
            self._unschedule_job(job_id)
            self.repo.update_next_run(job_id, None)

        return new_state

    async def run_now(self, job_id: str) -> Dict[str, Any]:
        """Trigger immediate execution of a job.

        Args:
            job_id: Job identifier

        Returns:
            Execution result

        Raises:
            ValueError: If job not found
        """
        job = self.repo.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        logger.info(f"Running job {job_id} ({job['name']}) immediately")

        execution_id = self.repo.create_execution(
            job_id=job_id,
            job_type="cron",
        )

        self.repo.update_last_run(job_id, datetime.utcnow().isoformat())

        # Execute directly (not fire-and-forget like scheduled jobs)
        await self._execute_job_logic(job, execution_id)

        # Fetch final execution status
        executions = self.repo.get_job_executions(job_id, limit=1)
        if executions:
            execution = executions[0]
            return {
                "status": execution["status"],
                "execution_id": execution_id,
                "result": execution.get("result"),
                "error": execution.get("error_message"),
            }

        return {"status": "unknown", "execution_id": execution_id}

    def get_recent_executions(
        self, limit: int = 20, status: Optional[str] = None, job_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent executions across all jobs.

        Args:
            limit: Maximum number of records
            status: Optional status filter
            job_type: Optional job type filter

        Returns:
            List of execution records with job names
        """
        return self.repo.get_recent_executions(limit=limit, status=status, job_type=job_type)

    def get_job_executions(self, job_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get execution history for a job.

        Args:
            job_id: Job identifier
            limit: Maximum number of records

        Returns:
            List of execution records
        """
        return self.repo.get_job_executions(job_id, limit)
