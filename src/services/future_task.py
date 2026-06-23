"""Future task service with APScheduler integration for one-time scheduled tasks."""

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from apscheduler.triggers.date import DateTrigger
from dateutil import parser as dateutil_parser

from src.core.repositories.future_task import FutureTaskRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FutureTaskService:
    """Service for managing one-time scheduled tasks."""

    def __init__(
        self,
        future_task_repo: FutureTaskRepository,
        scheduler: Optional[Any] = None,
        tool_executor: Optional[Any] = None,
        crew: Optional[Any] = None,
        message_handler: Optional[Any] = None,
        whatsapp_service: Optional[Any] = None,
        slack_service: Optional[Any] = None,
    ):
        """Initialize future task service.

        Args:
            future_task_repo: Future task repository instance
            scheduler: Shared APScheduler instance (AsyncIOScheduler)
            tool_executor: ToolExecutor instance for direct tool execution
            crew: PersonalAssistantCrew instance for prompt jobs (legacy)
            message_handler: MessageHandler instance for skills-based execution
            whatsapp_service: WhatsAppService for proactive message delivery
            slack_service: SlackService for proactive message delivery
        """
        self.repo = future_task_repo
        self.scheduler = scheduler
        self._tool_executor = tool_executor
        self._crew = crew
        self._message_handler = message_handler
        self._whatsapp_service = whatsapp_service
        self._slack_service = slack_service

        # Reuse concurrency control from shared scheduler
        self._job_semaphore: Optional[asyncio.Semaphore] = None
        self._active_tasks: Dict[int, asyncio.Task] = {}  # execution_id -> task

        # Inherit configuration from environment (same as cron jobs)
        import os

        self.max_concurrent_jobs = int(os.getenv("CRON_MAX_CONCURRENT_JOBS", "5"))
        self.max_job_timeout = int(os.getenv("CRON_JOB_TIMEOUT_SECONDS", "600"))  # 10 minutes

        logger.info(
            f"FutureTaskService initialized: max_concurrent={self.max_concurrent_jobs}, "
            f"timeout={self.max_job_timeout}s"
        )

    def load_pending_tasks(self) -> None:
        """Load pending tasks into scheduler (call on startup).

        This method:
        1. Gets all pending tasks from database
        2. Checks if tasks are missed (scheduled_time < now)
        3. Executes missed tasks immediately
        4. Schedules future tasks
        """
        if not self.scheduler:
            logger.warning("Scheduler not initialized, cannot load pending tasks")
            return

        # Initialize semaphore if not already set
        if self._job_semaphore is None:
            self._job_semaphore = asyncio.Semaphore(self.max_concurrent_jobs)

        pending_tasks = self.repo.get_pending_tasks()
        logger.info(f"Loading {len(pending_tasks)} pending future tasks")

        now = datetime.utcnow()
        missed_count = 0
        scheduled_count = 0

        for task in pending_tasks:
            try:
                scheduled_time = datetime.fromisoformat(
                    task["scheduled_time"].replace("Z", "+00:00")
                )

                if scheduled_time < now:
                    # Task is missed - execute immediately
                    logger.warning(
                        f"Task {task['task_id']} missed scheduled time {task['scheduled_time']}, "
                        f"executing immediately"
                    )
                    asyncio.create_task(self._execute_task(task["task_id"]))
                    missed_count += 1
                else:
                    # Task is in future - schedule it
                    self._schedule_task(task)
                    scheduled_count += 1

            except Exception as e:
                logger.error(f"Failed to load task {task['task_id']}: {e}")

        logger.info(
            f"Loaded {scheduled_count} future tasks, executing {missed_count} missed tasks immediately"
        )

    def create_task(
        self,
        name: str,
        scheduled_time: str,
        job_type: str,
        description: Optional[str] = None,
        conversation_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_parameters: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        delivery_channel: Optional[str] = None,
        delivery_contact_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and schedule a future task.

        Args:
            name: Human-readable task name
            scheduled_time: When to execute (ISO 8601, natural language, or relative)
            job_type: 'tool' or 'prompt'
            description: Optional description
            conversation_id: Conversation context ID
            tool_name: Tool to execute
            tool_parameters: Tool parameters
            prompt: Prompt for coordinator
            delivery_channel: 'whatsapp' or 'slack' to proactively deliver output
            delivery_contact_identifier: Override contact; resolved from settings when omitted

        Returns:
            Created task record

        Raises:
            ValueError: If validation fails or time is in past
        """
        # Validate job_type
        if job_type not in ("tool", "prompt"):
            raise ValueError("job_type must be 'tool' or 'prompt'")

        if job_type == "tool" and not tool_name:
            raise ValueError("tool_name is required for tool jobs")

        if job_type == "prompt" and not prompt:
            raise ValueError("prompt is required for prompt jobs")

        # Parse scheduled_time
        try:
            parsed_time = self._parse_scheduled_time(scheduled_time)
        except ValueError as e:
            raise ValueError(f"Invalid scheduled_time: {e}")

        # Validate time is in future
        now = datetime.utcnow()
        if parsed_time <= now:
            raise ValueError(
                f"scheduled_time must be in the future (got {parsed_time}, now is {now})"
            )

        # Generate task_id
        task_id = f"future-{uuid4().hex[:12]}"

        # Convert to ISO format for storage
        scheduled_time_iso = parsed_time.isoformat()

        # Create task in database
        task = self.repo.create_task(
            task_id=task_id,
            name=name,
            scheduled_time=scheduled_time_iso,
            job_type=job_type,
            description=description,
            conversation_id=conversation_id,
            tool_name=tool_name,
            tool_parameters=tool_parameters,
            prompt=prompt,
            delivery_channel=delivery_channel,
            delivery_contact_identifier=delivery_contact_identifier,
        )

        # Schedule with APScheduler
        if self.scheduler:
            self._schedule_task(task)
        else:
            logger.warning(f"Scheduler not initialized, task {task_id} created but not scheduled")

        return task

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task with execution history.

        Args:
            task_id: Task identifier

        Returns:
            Task record with executions, or None if not found
        """
        task = self.repo.get_task(task_id)
        if not task:
            return None

        # Get execution history from shared job_executions table
        executions = self.repo.get_job_executions(task_id, limit=20)
        task["recent_executions"] = executions

        return task

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tasks with optional status filter.

        Args:
            status: Filter by status (pending/completed/failed/cancelled/all)

        Returns:
            List of task records
        """
        return self.repo.list_tasks(status=status)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task.

        Args:
            task_id: Task identifier

        Returns:
            True if cancelled, False if not found or not pending

        Raises:
            ValueError: If task is not pending
        """
        task = self.repo.get_task(task_id)
        if not task:
            return False

        if task["status"] != "pending":
            raise ValueError(
                f"Cannot cancel task with status '{task['status']}' (only pending tasks can be cancelled)"
            )

        # Remove from scheduler
        if self.scheduler:
            self._unschedule_task(task_id)

        # Update status in database
        return self.repo.update_status(
            task_id=task_id,
            status="cancelled",
            completed_at=datetime.utcnow().isoformat(),
        )

    # === Scheduling ===

    def _schedule_task(self, task: Dict[str, Any]) -> None:
        """Add task to APScheduler with DateTrigger.

        Args:
            task: Task record from database
        """
        if not self.scheduler:
            logger.warning("Scheduler not initialized, cannot schedule task")
            return

        try:
            run_date = datetime.fromisoformat(task["scheduled_time"].replace("Z", "+00:00"))
            trigger = DateTrigger(run_date=run_date)

            self.scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=task["task_id"],
                name=task["name"],
                kwargs={"task_id": task["task_id"]},
                replace_existing=True,
            )

            logger.info(
                f"Scheduled future task {task['task_id']} ({task['name']}) "
                f"for {task['scheduled_time']}"
            )

        except Exception as e:
            logger.error(f"Failed to schedule task {task['task_id']}: {e}")

    def _unschedule_task(self, task_id: str) -> None:
        """Remove task from scheduler.

        Args:
            task_id: Task identifier
        """
        if not self.scheduler:
            return

        try:
            self.scheduler.remove_job(task_id)
            logger.info(f"Unscheduled future task {task_id}")
        except Exception:
            # Task may not be in scheduler
            pass

    # === Execution ===

    async def _execute_task(self, task_id: str) -> None:
        """Execute task (called by APScheduler).

        This is the entry point for task execution. Unlike cron jobs,
        future tasks don't need distributed locking since they're one-time.

        Args:
            task_id: Task identifier
        """
        task = self.repo.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found for execution")
            return

        if task["status"] != "pending":
            logger.info(f"Task {task_id} status is '{task['status']}', skipping execution")
            return

        # Create execution record in shared job_executions table
        execution_id = self.repo.create_execution(
            job_id=task_id,
            job_type="future_task",
        )

        # Create async task for execution
        task_obj = asyncio.create_task(self._execute_task_logic(task, execution_id))
        self._active_tasks[execution_id] = task_obj

        # Cleanup callback
        task_obj.add_done_callback(lambda t: self._active_tasks.pop(execution_id, None))

        # Wait for completion
        await task_obj

    async def _execute_task_logic(self, task: Dict[str, Any], execution_id: int) -> None:
        """Execute task with timeout, semaphore, and error handling.

        Args:
            task: Task record from database
            execution_id: Execution record ID
        """
        # Setup logging context
        task_logger = logging.LoggerAdapter(
            logger,
            {"task_id": task["task_id"], "execution_id": execution_id, "task_name": task["name"]},
        )

        task_logger.info("Starting task execution")

        try:
            # Acquire semaphore (limits concurrency)
            async with self._job_semaphore:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self._run_job(task, execution_id, task_logger), timeout=self.max_job_timeout
                )

                # Update execution record
                self.repo.complete_execution(
                    execution_id=execution_id, status="success", result=result
                )

                # Update task status
                self.repo.update_status(
                    task_id=task["task_id"],
                    status="completed",
                    completed_at=datetime.utcnow().isoformat(),
                    result=result,
                )

                task_logger.info("Task completed successfully")

        except asyncio.TimeoutError:
            error_msg = f"Task exceeded timeout of {self.max_job_timeout}s"
            task_logger.error(error_msg)
            self.repo.complete_execution(
                execution_id=execution_id, status="failed", error_message=error_msg
            )
            self.repo.update_status(
                task_id=task["task_id"],
                status="failed",
                completed_at=datetime.utcnow().isoformat(),
                error_message=error_msg,
            )
        except asyncio.CancelledError:
            task_logger.warning("Task cancelled")
            self.repo.complete_execution(
                execution_id=execution_id, status="cancelled", error_message="Task cancelled"
            )
            self.repo.update_status(
                task_id=task["task_id"],
                status="cancelled",
                completed_at=datetime.utcnow().isoformat(),
                error_message="Task cancelled",
            )
            raise
        except Exception as e:
            task_logger.error(f"Task failed: {e}", exc_info=True)
            self.repo.complete_execution(
                execution_id=execution_id, status="failed", error_message=str(e)
            )
            self.repo.update_status(
                task_id=task["task_id"],
                status="failed",
                completed_at=datetime.utcnow().isoformat(),
                error_message=str(e),
            )

    async def _run_job(
        self, task: Dict[str, Any], execution_id: int, task_logger: logging.LoggerAdapter
    ) -> Dict[str, Any]:
        """Route task to appropriate execution method.

        Args:
            task: Task record
            execution_id: Execution record ID
            task_logger: Logger with task context

        Returns:
            Execution result
        """
        if task["job_type"] == "tool":
            return await self._run_tool_job(task, task_logger)

        # Prompt-type tasks: use MessageHandler (skills-based system)
        if self._message_handler:
            return await self._run_message_handler_task(task, task_logger)

        raise RuntimeError(
            "Cannot execute prompt task: MessageHandler not initialized. "
            f"Task: {task.get('name', 'unknown')}"
        )

    async def _run_tool_job(
        self, task: Dict[str, Any], task_logger: logging.LoggerAdapter
    ) -> Dict[str, Any]:
        """Execute a tool job directly via ToolExecutor.

        Args:
            task: Task record
            task_logger: Logger with task context

        Returns:
            Execution result

        Raises:
            RuntimeError: If ToolExecutor not initialized or tool execution fails
        """
        if not self._tool_executor:
            raise RuntimeError("ToolExecutor not initialized - cannot execute tool jobs")

        tool_name = task["tool_name"]
        tool_params = task["tool_parameters"] or {}

        task_logger.info(f"Executing tool: {tool_name}")

        try:
            result = await self._tool_executor.execute_tool(
                tool_name=tool_name,
                arguments=tool_params,
                tool_call_id=f"future_{task['task_id']}",
                iteration=1,
            )

            if result.get("success"):
                return {"status": "success", "result": result["result"]}
            else:
                raise RuntimeError(result.get("error", "Tool execution failed"))

        except Exception as e:
            task_logger.error(f"Tool execution failed: {e}")
            raise

    async def _run_message_handler_task(
        self, task: Dict[str, Any], task_logger: logging.LoggerAdapter
    ) -> Dict[str, Any]:
        """Execute a task via MessageHandler (skills-based system).

        When delivery_channel is set on the task, the LLM response is also
        sent to the user via WhatsApp or Slack and a fresh conversation is
        created so the scheduled question never appends to an ongoing chat.

        Args:
            task: Task record
            task_logger: Logger with task context

        Returns:
            Execution result

        Raises:
            RuntimeError: If MessageHandler not initialized
        """
        if not self._message_handler:
            raise RuntimeError(
                "MessageHandler not initialized - cannot execute message handler tasks"
            )

        prompt = task.get("prompt", "")
        if not prompt:
            raise ValueError("Prompt is required for message handler tasks")

        task_logger.info(f"Executing via MessageHandler: {prompt[:100]}...")

        delivery_channel = task.get("delivery_channel")

        # Resolve delivery contact from task config or fall back to settings default.
        delivery_contact = task.get("delivery_contact_identifier") or ""
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
            task_logger.warning(
                f"delivery_channel='{delivery_channel}' set but no contact configured — "
                "falling back to silent system execution"
            )
            delivery_channel = None

        # Choose conversation routing.
        # Delivery tasks get a fresh conversation_id so the scheduled question
        # never appends to an ongoing user conversation.
        if delivery_channel and delivery_contact:
            channel = delivery_channel
            contact_identifier = delivery_contact
            conversation_id = f"sched-{uuid4().hex[:12]}"
            task_logger.info(
                f"Delivery routing: channel={channel}, contact={contact_identifier}, "
                f"conversation={conversation_id}"
            )
        else:
            channel = "system"
            contact_identifier = f"future_task_{task['task_id']}"
            conversation_id = task.get("conversation_id")

        try:
            result = await self._message_handler.handle_message(
                message=prompt,
                conversation_id=conversation_id,
                channel=channel,
                contact_identifier=contact_identifier,
                metadata={
                    "task_id": task["task_id"],
                    "task_name": task["name"],
                    "source": "future_task",
                },
            )

            response = result["response"] or ""

            if delivery_channel and delivery_contact and response:
                await self._deliver_response(
                    delivery_channel, delivery_contact, response, task_logger
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
            task_logger.error(f"MessageHandler execution failed: {e}")
            raise

    async def _deliver_response(
        self,
        delivery_channel: str,
        delivery_contact: str,
        response: str,
        task_logger: logging.LoggerAdapter,
    ) -> None:
        """Send the LLM response to the user via the configured messaging channel."""
        loop = asyncio.get_event_loop()
        try:
            if delivery_channel == "whatsapp":
                if not self._whatsapp_service:
                    task_logger.error(
                        "delivery_channel='whatsapp' but WhatsAppService not injected"
                    )
                    return
                await loop.run_in_executor(
                    None,
                    lambda: self._whatsapp_service.send_message(
                        phone_number=delivery_contact, message=response
                    ),
                )
                task_logger.info(f"Delivered response via WhatsApp to {delivery_contact}")

            elif delivery_channel == "slack":
                if not self._slack_service:
                    task_logger.error("delivery_channel='slack' but SlackService not injected")
                    return
                await loop.run_in_executor(
                    None,
                    lambda: self._slack_service.send_message(
                        channel=delivery_contact, message=response
                    ),
                )
                task_logger.info(f"Delivered response via Slack to {delivery_contact}")

            else:
                task_logger.warning(f"Unknown delivery_channel '{delivery_channel}', skipping")

        except Exception as e:
            task_logger.error(f"Failed to deliver via {delivery_channel}: {e}", exc_info=True)

    # === Time Parsing ===

    def _parse_scheduled_time(self, time_str: str) -> datetime:
        """Parse scheduled time from various formats.

        Supports:
        1. ISO 8601: "2024-01-16T15:00:00" or "2024-01-16T15:00:00Z"
        2. Natural language (via dateutil): "tomorrow at 3pm", "next Monday at 10am"
        3. Relative time: "in 2 hours", "in 30 minutes", "in 3 days"

        Args:
            time_str: Time string in various formats

        Returns:
            Parsed datetime (UTC)

        Raises:
            ValueError: If time string cannot be parsed
        """
        time_str = time_str.strip()

        # Try ISO 8601 first
        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            # Convert to UTC if timezone-aware
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)  # Assume UTC storage
            return dt
        except (ValueError, AttributeError):
            pass

        # Try relative time patterns: "in X hours/minutes/days/weeks"
        relative_pattern = r"^in\s+(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks)$"
        match = re.match(relative_pattern, time_str.lower())
        if match:
            amount = int(match.group(1))
            unit = match.group(2).rstrip("s")  # Remove plural 's'

            now = datetime.utcnow()
            if unit == "minute":
                return now + timedelta(minutes=amount)
            elif unit == "hour":
                return now + timedelta(hours=amount)
            elif unit == "day":
                return now + timedelta(days=amount)
            elif unit == "week":
                return now + timedelta(weeks=amount)

        # Try natural language via dateutil
        try:
            dt = dateutil_parser.parse(time_str, fuzzy=True)
            # dateutil returns local time, assume UTC for simplicity
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except (ValueError, TypeError):
            pass

        raise ValueError(
            f"Could not parse '{time_str}'. Supported formats: "
            f"ISO 8601 ('2024-01-16T15:00:00'), "
            f"natural language ('tomorrow at 3pm'), "
            f"relative time ('in 2 hours')"
        )
