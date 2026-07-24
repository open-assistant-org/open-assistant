"""Message handler service for skills-based LLM orchestration."""

import asyncio
import json
import os
import re
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.core.llm_client import LLMClient, LLMConfig
from src.core.repositories.skill import SkillRepository
from src.core.tools.executor import ToolExecutor
from src.core.tools.registry import get_tool_registry
from src.models.skill import Skill
from src.services.conversation import ConversationService
from src.services.memory import MemoryService
from src.services.plan_helpers import (
    deserialize_messages,
    handle_revise_plan,
    serialize_messages,
)
from src.services.async_task_dispatcher import AsyncTaskDispatcher
from src.services.planner import Planner, PlanTracker
from src.services.settings import SettingsService
from src.utils.json_utils import try_repair_json
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MessageHandler:
    """
    Core message orchestration service.

    - Single LLM process with full context preservation
    - Skill-based context selection
    - Iterative tool calling loop with stuck detection
    - Direct tool execution
    """

    def __init__(
        self,
        skill_repo: SkillRepository,
        conversation_service: ConversationService,
        memory_service: MemoryService,
        settings_service: SettingsService,
        tool_executor: ToolExecutor,
        max_iterations: int = 15,
        max_skills_per_request: int = 5,
    ):
        self.skill_repo = skill_repo
        self.conversation_service = conversation_service
        self.memory_service = memory_service
        self.settings_service = settings_service
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self.max_skills_per_request = max_skills_per_request
        self.tool_registry = get_tool_registry()

        # Dispatcher for async sub-tasks — bound to this handler instance so
        # sub-tasks share the same services and configuration.
        self.async_task_dispatcher = AsyncTaskDispatcher(self.handle_message)

        logger.info(
            f"MessageHandler initialized (max_iterations={max_iterations}, "
            f"max_skills={max_skills_per_request})"
        )

    # Tool names for adaptive planning — injected when a plan is active.
    # dispatch_task / wait_for_tasks / get_task_result enable parallel sub-task execution.
    PLAN_TOOLS = {
        "revise_plan",
        "ask_user",
        "dispatch_task",
        "get_task_result",
        "wait_for_tasks",
    }

    @staticmethod
    async def _emit(callback: Optional[Callable[[dict], Awaitable[None]]], event: dict) -> None:
        """Fire an SSE progress event, swallowing any callback errors."""
        if callback:
            try:
                await callback(event)
            except Exception:
                pass

    async def handle_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        channel: str = "webui",
        contact_identifier: Optional[str] = None,
        max_idle_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        image_base64: Optional[str] = None,
        image_mimetype: Optional[str] = None,
        event_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Handle a user message through the skills-based LLM system.

        If the conversation has a suspended execution (``awaiting_input``),
        the user's message is treated as the answer and the loop is resumed
        with the full prior context preserved.

        Args:
            message: User message text
            conversation_id: Optional existing conversation ID
            channel: Message channel (webui, whatsapp, system)
            contact_identifier: Contact identifier for conversation lookup
            max_idle_seconds: Max idle time before creating new conversation
            metadata: Optional metadata dict
            image_base64: Optional base64-encoded image data for vision
            image_mimetype: Optional MIME type of the image

        Returns:
            Dictionary with response, conversation_id, skills_used,
            tools_executed, iterations, stuck_detected.
            May also contain ``pending_input`` when ``ask_user`` suspends
            execution.
        """
        logger.info(
            f"Processing message: channel={channel}, length={len(message)}, "
            f"conversation_id={conversation_id}"
        )

        try:
            # Step 1: Get or create conversation
            logger.debug("Step 1: Getting/creating conversation...")
            conversation = self.conversation_service.create_or_get_conversation(
                channel=channel,
                contact_identifier=contact_identifier,
                conversation_id=conversation_id,
                max_idle_seconds=max_idle_seconds,
            )
            conv_id = conversation["conversation_id"]
            logger.debug(f"Conversation ID: {conv_id}")

            # Step 1b: Handle /clear command — start a fresh conversation,
            # leaving the existing one intact as history.
            if message.strip() == "/clear":
                new_conv_id = str(uuid4())
                self.conversation_service.conversation_repo.create(
                    conversation_id=new_conv_id,
                    channel=channel,
                    contact_identifier=contact_identifier,
                )
                logger.info(
                    f"/clear: new conversation {new_conv_id} started "
                    f"(channel={channel}, previous={conv_id})"
                )
                return {
                    "response": "Conversation cleared.",
                    "conversation_id": new_conv_id,
                    "skills_used": [],
                    "tools_executed": [],
                    "iterations": 0,
                    "stuck_detected": False,
                    "cleared": True,
                }

            # Step 1c: Check for suspended execution (ask_user resumption)
            suspended_result = self._get_suspended_state(conv_id)
            if suspended_result:
                suspended_state, suspended_msg_id = suspended_result
                logger.info("Resuming suspended execution with user's answer")
                return await self._resume_suspended_execution(
                    conv_id=conv_id,
                    user_answer=message,
                    suspended_state=suspended_state,
                    suspended_message_id=suspended_msg_id,
                    metadata=metadata,
                    channel=channel,
                    contact_identifier=contact_identifier,
                    event_callback=event_callback,
                )

            # Step 2: Store user message
            logger.debug("Step 2: Storing user message...")
            self.conversation_service.add_message(
                conversation_id=conv_id,
                role="user",
                content=message,
                metadata=metadata,
            )

            # Step 3: Load context (memory, soul, recent messages)
            logger.debug("Step 3: Loading context...")
            context = self._load_context(conv_id)
            logger.debug(
                f"Context loaded: memory={len(context.get('memory', ''))} chars, "
                f"soul={len(context.get('soul', ''))} chars, "
                f"recent_messages={len(context.get('recent_messages', []))}"
            )

            # Step 4: Select relevant skills
            logger.debug("Step 4: Selecting skills...")
            selection_message = self._contextualize_message_for_skill_selection(
                message, context.get("recent_messages", [])
            )
            selected_skills = self._select_skills(selection_message, conversation_id=conv_id)
            logger.debug(
                f"Selected {len(selected_skills)} skills: {[s.name for s in selected_skills]}"
            )

            # Step 5: Build system prompt
            logger.debug("Step 5: Building system prompt...")
            system_prompt = self._build_system_prompt(selected_skills, context)
            logger.debug(f"System prompt: {len(system_prompt)} chars")

            # Step 6: Get tools from selected skills
            logger.debug("Step 6: Getting tools...")
            tools = self._get_tools_from_skills(selected_skills)
            logger.debug(f"Available tools: {len(tools)}")

            # Step 7: Get LLM client
            logger.debug("Step 7: Creating LLM client...")
            llm_client = self._get_llm_client()
            logger.debug("LLM client created")

        except Exception as e:
            logger.error(
                f"Error in message setup (step failed before LLM call): "
                f"{type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise

        # Step 8: Optionally generate a plan for complex requests
        plan: Optional[PlanTracker] = None
        try:
            if tools and Planner.should_plan(message, selected_skills):
                logger.info("Complex request detected — generating plan")

                # Give the planner ALL enabled skills so it can plan across
                # skill boundaries, even when keyword matching selected a subset.
                all_enabled_skills = self.skill_repo.get_enabled_skills()

                # Pre-inject plan tools (including dispatch_task / get_task_result)
                # so the planner is aware of async delegation as an option.
                planner_tools = self._inject_plan_tools(list(tools))

                plan = await Planner.generate_plan(
                    llm_client,
                    message,
                    planner_tools,
                    skills=all_enabled_skills,
                )
                logger.info(f"Plan generated with {plan.total} steps")

                if plan.total > 1:
                    # The plan may reference tools from skills that weren't
                    # selected by keyword matching.  Expand the skill set,
                    # system prompt, and tool list so the execution loop has
                    # every tool and backstory the plan might need.
                    selected_skills, system_prompt, tools = self._expand_skills_for_plan(
                        plan,
                        selected_skills,
                        context,
                    )
        except Exception as e:
            # Planning is best-effort; if it fails we proceed without a plan
            logger.warning(f"Plan generation failed, proceeding without plan: {e}")

        # When a plan is active, inject adaptive planning tools (revise_plan, ask_user)
        if plan and plan.total > 1:
            tools = self._inject_plan_tools(tools)

        # Step 9: Execute conversation loop
        try:
            result = await self._execute_conversation_loop(
                llm_client=llm_client,
                system_prompt=system_prompt,
                user_message=message,
                conversation_id=conv_id,
                tools=tools,
                recent_messages=context.get("recent_messages", []),
                image_base64=image_base64,
                image_mimetype=image_mimetype,
                plan=plan,
                channel=channel,
                contact_identifier=contact_identifier,
                event_callback=event_callback,
            )
        except Exception as e:
            logger.error(f"Error in conversation loop: {type(e).__name__}: {str(e)}", exc_info=True)

            # Detect image/media model mismatch (e.g. OpenRouter 404 for vision)
            error_msg = str(e)
            if "image input" in error_msg.lower() or "vision" in error_msg.lower():
                error_response = (
                    "The current model does not support image input. "
                    "Please configure a vision-capable model in Settings > LLM > Media Model "
                    "(e.g. anthropic/claude-3.5-sonnet)."
                )
            else:
                error_response = (
                    f"I encountered an error while processing your request: {type(e).__name__}: {error_msg}\n\n"
                    "Please try again or rephrase your request."
                )
            self.conversation_service.add_message(
                conversation_id=conv_id,
                role="assistant",
                content=error_response,
                metadata={"error": str(e), "error_type": type(e).__name__},
            )
            return {
                "response": error_response,
                "conversation_id": conv_id,
                "skills_used": [s.name for s in selected_skills],
                "tools_executed": [],
                "iterations": 0,
                "stuck_detected": False,
                "error": str(e),
            }

        # Step 10: Store assistant response (unless suspended for user input)
        if result.get("awaiting_input"):
            # Execution was suspended by ask_user — persist suspended state
            # and return the question to the caller without storing a final
            # assistant message.
            self._save_suspended_state(
                conv_id,
                result["suspended_state"],
                question=result["pending_input"]["question"],
            )
            logger.info(
                f"Execution suspended for user input: {result['pending_input']['question']}"
            )
            return {
                "response": result["response"],
                "conversation_id": conv_id,
                "skills_used": [s.name for s in selected_skills],
                "tools_executed": result["tools_executed"],
                "iterations": result["iterations"],
                "stuck_detected": result["stuck_detected"],
                "pending_input": result["pending_input"],
            }

        response_metadata = {
            "skills_used": [s.name for s in selected_skills],
            "tools_executed": result["tools_executed"],
            "iterations": result["iterations"],
            "stuck_detected": result["stuck_detected"],
        }
        if "plan_steps_total" in result:
            response_metadata["plan_steps_completed"] = result["plan_steps_completed"]
            response_metadata["plan_steps_total"] = result["plan_steps_total"]

        self.conversation_service.add_message(
            conversation_id=conv_id,
            role="assistant",
            content=result["response"],
            metadata=response_metadata,
        )

        # Auto-compaction: fire-and-forget — runs in the background after the response
        # is already stored, so it never adds latency to the user-facing turn.
        try:
            auto_compact = self.settings_service.get_config_with_fallback("llm.auto_compact", True)
            if auto_compact and self.memory_service.should_summarize(conv_id):
                asyncio.create_task(self._run_auto_compaction(conv_id, llm_client.config.model))
                logger.debug(f"Auto-compaction scheduled for conversation: {conv_id}")
        except Exception as e:
            logger.warning(f"Could not schedule auto-compaction: {e}")

        logger.info(
            f"Message processed: conversation_id={conv_id}, "
            f"skills={[s.name for s in selected_skills]}, "
            f"tools_executed={len(result['tools_executed'])}, "
            f"iterations={result['iterations']}, "
            f"stuck={result['stuck_detected']}"
        )

        return {
            "response": result["response"],
            "conversation_id": conv_id,
            "skills_used": [s.name for s in selected_skills],
            "tools_executed": result["tools_executed"],
            "iterations": result["iterations"],
            "stuck_detected": result["stuck_detected"],
        }

    def _load_context(self, conversation_id: str) -> Dict[str, Any]:
        """
        Load conversation context including memory, soul, and recent messages.

        Uses PromptsRepository (via MemoryService) for soul/memory prompts.
        Recent messages are loaded via MemoryService.get_conversation_context() so
        the Context Strategy and Context Max Messages settings are respected on every turn.
        """
        # Get memory prompt from prompts table
        memory = ""
        soul = ""
        try:
            prompts_repo = self.memory_service.prompts_repo
            memory = prompts_repo.get_value("memory") or ""
            soul = prompts_repo.get_value("soul") or ""
        except Exception as e:
            logger.warning(f"Could not load prompts: {e}")

        # Get recent messages using the strategy-aware memory service so that
        # Context Strategy / Context Max Messages settings actually take effect.
        recent_messages = []
        long_term_summaries = []
        try:
            model_name = (
                self.settings_service.get_config_with_fallback("llm.model", "")
                or "anthropic/claude-3.5-sonnet"
            )
            ctx = self.memory_service.get_conversation_context(
                conversation_id=conversation_id,
                model=model_name,
                # System messages (long-term summaries) are injected separately by
                # _build_system_prompt so we exclude them here and pass them alongside.
                include_system_message=False,
            )
            recent_messages = [
                m for m in ctx.get("messages", []) if m.get("role") in ("user", "assistant")
            ]
            # Collect long-term summaries so _build_system_prompt can inject them.
            long_term_summaries = self.memory_service.memory_repo.get_by_type(
                conversation_id, "long_term"
            )
        except Exception as e:
            logger.warning(f"Strategy-aware context load failed, falling back: {e}")
            try:
                history = self.conversation_service.message_repo.get_recent_messages(
                    conversation_id, count=50
                )
                recent_messages = history if isinstance(history, list) else []
            except Exception as e2:
                logger.warning(f"Fallback context load also failed: {e2}")

        return {
            "memory": memory,
            "soul": soul,
            "recent_messages": recent_messages,
            "long_term_summaries": long_term_summaries,
        }

    def _select_skills(self, message: str, conversation_id: Optional[str] = None) -> List[Skill]:
        """
        Select relevant skills based on message intent, augmented with any skills
        that were active in prior turns of this conversation (sticky skills).

        Uses keyword matching against intent_keywords, sorted by priority.
        Falls back to top N skills by priority if no matches.
        """
        skills = self.skill_repo.get_skills_by_keywords(
            message, max_skills=self.max_skills_per_request
        )
        if not skills:
            logger.warning("No skills returned from repository")

        # Merge sticky skills accumulated during this conversation so tools
        # established in earlier messages remain available without re-triggering
        # their intent keywords.
        if conversation_id:
            conv = self.conversation_service.conversation_repo.get_by_id(conversation_id)
            meta = (conv or {}).get("metadata") or {}
            active_names = set(meta.get("active_skills", []))
            if active_names:
                current_names = {s.name for s in skills}
                for skill in self.skill_repo.get_enabled_skills():
                    if skill.name in active_names and skill.name not in current_names:
                        skills.append(skill)
                        logger.debug("Sticky skill re-added: %s", skill.name)

        return skills

    def _find_skill_for_tool(self, tool_name: str) -> Optional[str]:
        """Return the name of the enabled skill that owns tool_name, or None."""
        for skill in self.skill_repo.get_enabled_skills():
            if tool_name in (skill.tools or []):
                return skill.name
        return None

    def _persist_active_skill(self, conversation_id: str, skill_name: str) -> None:
        """Add skill_name to the conversation's active_skills set and persist it."""
        conv = self.conversation_service.conversation_repo.get_by_id(conversation_id)
        meta = dict((conv or {}).get("metadata") or {})
        active = set(meta.get("active_skills", []))
        if skill_name not in active:
            active.add(skill_name)
            meta["active_skills"] = list(active)
            self.conversation_service.conversation_repo.update_metadata(conversation_id, meta)
            logger.debug(
                "Persisted active skill '%s' for conversation %s", skill_name, conversation_id
            )

    _CONTINUATION_PHRASES: frozenset = frozenset(
        {
            "go on",
            "continue",
            "yes",
            "ok",
            "sure",
            "proceed",
            "do it",
            "go ahead",
            "next",
            "and?",
            "more",
            "keep going",
            "alright",
            "sounds good",
            "perfect",
            "great",
            "done",
            "ok then",
            "go on then",
            "carry on",
            "then",
            "and then",
            "what else",
            "yep",
            "yup",
            "please",
            "ok do it",
        }
    )

    def _contextualize_message_for_skill_selection(
        self,
        message: str,
        recent_messages: List[Dict[str, Any]],
    ) -> str:
        """
        Enrich a short continuation message with recent history for skill matching.

        When users send brief follow-ups ("go on then", "yes", "continue") the
        keyword matcher finds no intent signals in the current message and falls
        back to priority ordering.  This method detects those cases and builds
        an enriched string from the last three user messages so that the original
        task's intent keywords are present for matching.  The original message is
        preserved everywhere else (storage, LLM context, display).
        """
        stripped = message.strip()
        if len(stripped) >= 50:
            return message

        msg_lower = stripped.lower()
        is_continuation = any(phrase in msg_lower for phrase in self._CONTINUATION_PHRASES)
        if not is_continuation:
            return message

        prior_user_texts: List[str] = []
        for msg in reversed(recent_messages):
            if msg.get("role") == "user" and msg.get("content", "").strip() != stripped:
                prior_user_texts.append(msg["content"])
                if len(prior_user_texts) == 3:
                    break

        if not prior_user_texts:
            return message

        enriched = " ".join([stripped] + prior_user_texts)
        logger.debug(
            f"Enriched continuation message for skill selection "
            f"({len(stripped)} → {len(enriched)} chars)"
        )
        return enriched

    def _expand_skills_for_plan(
        self,
        plan: PlanTracker,
        already_selected: List[Skill],
        context: Dict[str, Any],
    ) -> Tuple[List[Skill], str, List[Dict[str, Any]]]:
        """Expand the active skill set so the execution loop covers the full plan.

        A generated plan may reference tools from skills that keyword matching
        did not select.  This method loads all enabled skills, merges them with
        the already-selected set (preserving order/priority), then rebuilds the
        system prompt and tool list.

        Args:
            plan: The generated execution plan.
            already_selected: Skills selected by keyword matching.
            context: Conversation context (memory, soul, etc.).

        Returns:
            Tuple of (expanded_skills, new_system_prompt, new_tools).
        """
        all_enabled = self.skill_repo.get_enabled_skills()

        # Merge: start with keyword-selected skills (higher relevance),
        # then append any enabled skills that weren't already selected.
        selected_names = {s.name for s in already_selected}
        expanded = list(already_selected)
        for skill in all_enabled:
            if skill.name not in selected_names:
                expanded.append(skill)

        logger.info(
            f"Expanded skills for plan execution: "
            f"{len(already_selected)} → {len(expanded)} skills"
        )

        new_system_prompt = self._build_system_prompt(expanded, context)
        new_tools = self._get_tools_from_skills(expanded)
        return expanded, new_system_prompt, new_tools

    def _build_system_prompt(self, skills: List[Skill], context: Dict[str, Any]) -> str:
        """Build system prompt from skill contexts and conversation context."""
        base_prompt = """You are a helpful AI assistant with access to various tools and integrations.

        CRITICAL INSTRUCTIONS:
        1. ALWAYS use your tools to answer questions - NEVER guess or make up information
        2. Be thorough and complete - don't stop until the task is fully done
        3. If you need clarification, ask the user directly
        4. Always cite your sources (which email, file, URL, etc.)
        5. For multi-step tasks, follow the plan provided and work through each step in order. After completing each step, move on to the next without stopping early.
        6. When you need to apply the same action to many items (label emails, move files, etc.), use batch_tool with the tool name and list of argument sets — this is much more efficient than calling the tool one-by-one.
        7. When each item needs multiple sequential steps (e.g. fetch an email then create a Notion page for each one), use loop_tool with a list of steps and items — this runs the full pipeline per item without extra round-trips.
        8. If a tool call fails, try alternative approaches or ask for help
        9. When browsing: after browse_url, use browse_action with ref IDs to click/type. The browser session persists between calls so you can navigate across pages.
        10. When a tool returns a result with a "file" key, the full data was too large for context and has been saved to that path. Pass the file path as context to python_agent — do not try to read or process it inline. When asking python_agent to write output files (charts, reports, HTML), tell it to write to the directory containing that file — do NOT use /app/tmp.

        """

        # Add current date/time for temporal context, using the user's timezone
        user_tz_name = self.settings_service.get_config_with_fallback("user.timezone", "UTC")
        try:
            user_tz = ZoneInfo(user_tz_name)
        except Exception:
            logger.warning(f"Invalid timezone '{user_tz_name}', falling back to UTC")
            user_tz = timezone.utc
        current_time = datetime.now(user_tz).strftime("%Y-%m-%d %H:%M:%S")
        first_day = self.settings_service.get_config_with_fallback(
            "user.first_day_of_week", "Monday"
        )
        base_prompt += f"Current date and time: {current_time} (timezone: {user_tz_name})\n"
        base_prompt += f"First day of the week: {first_day}\n\n"

        # Add memory if available
        if context.get("memory"):
            base_prompt += f"# Memory\n{context['memory']}\n\n"

        # Add long-term conversation summaries produced by auto-compaction
        long_term = context.get("long_term_summaries") or []
        if long_term:
            base_prompt += "# Previous Conversation Summaries\n"
            for entry in reversed(long_term):  # oldest first
                summary_text = entry.get("content", {}).get("summary", "")
                if summary_text:
                    base_prompt += f"{summary_text}\n\n"

        # Add soul if available
        if context.get("soul"):
            base_prompt += f"# Personality\n{context['soul']}\n\n"

        # Add skill-specific contexts
        if skills:
            base_prompt += "# Available Skills and Tools\n\n"
            for skill in skills:
                base_prompt += f"## {skill.display_name}\n"
                base_prompt += f"{skill.context_prompt}\n\n"

        return base_prompt

    # Meta-tools that are always available regardless of skill selection.
    # These operate on other tools rather than a specific integration.
    ALWAYS_AVAILABLE_TOOLS = {"batch_tool", "loop_tool"}

    def _inject_plan_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add revise_plan and ask_user tools to the tool list when a plan is active."""
        settings_repo = self.settings_service.settings_repo
        all_tools = self.tool_registry.get_openai_tools(settings_repo)
        plan_tool_defs = [t for t in all_tools if t["function"]["name"] in self.PLAN_TOOLS]
        # Avoid duplicates
        existing_names = {t["function"]["name"] for t in tools}
        for pt in plan_tool_defs:
            if pt["function"]["name"] not in existing_names:
                tools.append(pt)
        return tools

    def _get_tools_from_skills(self, skills: List[Skill]) -> List[Dict[str, Any]]:
        """Get tool definitions from selected skills in OpenAI format."""
        # Collect all unique tool names from skills
        tool_names = set()
        for skill in skills:
            logger.debug(f"Skill '{skill.name}' tools: {skill.tools}")
            tool_names.update(skill.tools)

        logger.debug(f"Total unique tool names: {len(tool_names)}")

        # Get settings repo to filter enabled tools
        settings_repo = self.settings_service.settings_repo

        # Get all available tools in OpenAI format
        all_tools = self.tool_registry.get_openai_tools(settings_repo)
        logger.debug(f"Registry has {len(all_tools)} total tools")

        # Filter to only include tools from selected skills, plus meta-tools
        # that are always available (e.g. batch_tool).
        filtered_tools = [
            tool
            for tool in all_tools
            if tool["function"]["name"] in tool_names
            or tool["function"]["name"] in self.ALWAYS_AVAILABLE_TOOLS
        ]
        logger.debug(f"Filtered to {len(filtered_tools)} tools for selected skills")

        if not filtered_tools and tool_names:
            logger.warning(
                f"No matching tools in registry for skill tool names: {tool_names}. "
                f"Available: {[t['function']['name'] for t in all_tools]}"
            )

        return filtered_tools

    async def _send_progress_notification(
        self,
        channel: str,
        contact_identifier: Optional[str],
        message: str,
    ) -> None:
        """Send a progress notification back to the originating channel.

        - whatsapp: sends directly to the contact's phone number.
        - slack: sends to the channel extracted from the contact_identifier
          (format ``{channel_id}:{user_id}``).
        - webui / subtask / anything else: no-op — the user is watching
          synchronously or it is an internal sub-task.

        Failures are logged at DEBUG level and never propagate, so a
        misconfigured integration cannot break the wait_for_tasks flow.
        """
        try:
            if channel == "whatsapp" and contact_identifier:
                whatsapp_service = self.tool_executor.services.get("whatsapp")
                if whatsapp_service:
                    whatsapp_service.send_message(phone_number=contact_identifier, message=message)
            elif channel == "slack" and contact_identifier:
                slack_service = self.tool_executor.services.get("slack")
                if slack_service:
                    # contact_identifier is "{channel_id}:{user_id}"
                    slack_channel_id = contact_identifier.split(":")[0]
                    slack_service.send_message(channel=slack_channel_id, message=message)
            # webui / subtask: user is watching synchronously — no notification needed
        except Exception as exc:
            logger.debug(f"_send_progress_notification ({channel}): {exc}")

    def _get_llm_client(self) -> LLMClient:
        """Get LLM client configured from settings."""
        llm_config = LLMConfig.from_settings(self.settings_service)

        logger.debug(
            f"LLM config: provider={llm_config.provider}, model={llm_config.model}, "
            f"media_model={llm_config.media_model}, worker_model={llm_config.worker_model}, "
            f"base_url={llm_config.base_url}"
        )

        return LLMClient(llm_config)

    async def _execute_conversation_loop(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        user_message: str,
        conversation_id: str,
        tools: List[Dict[str, Any]],
        recent_messages: Optional[List[Dict[str, Any]]] = None,
        image_base64: Optional[str] = None,
        image_mimetype: Optional[str] = None,
        plan: Optional[PlanTracker] = None,
        # Channel context — used to send progress notifications back to the
        # originating channel (WhatsApp/Slack) during wait_for_tasks.
        channel: str = "webui",
        contact_identifier: Optional[str] = None,
        # Resume parameters — when provided, skip message-building preamble
        resume_messages: Optional[List[Dict[str, Any]]] = None,
        resume_iteration: int = 0,
        resume_tools_executed: Optional[List[str]] = None,
        resume_tool_call_history: Optional[deque] = None,
        resume_plan_nudge_count: int = 0,
        # Optional callback for streaming progress events to the caller
        event_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Execute iterative conversation loop with tool calling.

        If a *plan* is provided the loop injects progress context between
        iterations so the LLM can stay on track across many tool calls.

        When *resume_messages* is provided the message-building preamble is
        skipped and the loop picks up from the given state (used by
        ``_resume_suspended_execution``).

        Returns dict with: response, tools_executed, iterations,
        stuck_detected, plan_steps_completed, plan_steps_total.
        """
        if resume_messages is not None:
            # Resuming from a suspended execution — use provided state directly
            messages = resume_messages
            tools_executed = resume_tools_executed if resume_tools_executed is not None else []
            tool_call_history = (
                resume_tool_call_history
                if resume_tool_call_history is not None
                else deque(maxlen=10)
            )
            iteration = resume_iteration
            plan_nudge_count = resume_plan_nudge_count
            stuck_detected = False
            # Image handling only applies to fresh starts; on resume the media
            # model is irrelevant (and raw image data is already stripped), but
            # the variable must still exist for the loop below.
            model_for_media = None
        else:
            # Fresh start — build messages from scratch
            messages = [{"role": "system", "content": system_prompt}]

            # Include prior conversation history for context
            # recent_messages includes the current user message (stored in step 2)
            added_count = 0
            if recent_messages:
                for msg in recent_messages:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    if role in ("user", "assistant") and content:
                        messages.append({"role": role, "content": content})
                        added_count += 1

            if added_count == 0:
                # No valid history messages found, add the current user message directly
                messages.append({"role": "user", "content": user_message})
                logger.debug("No conversation history, using direct user message")
            else:
                logger.debug(f"Loaded {added_count} messages from conversation history")

            # Safety check: ensure the last message is from the user
            if messages[-1].get("role") != "user":
                logger.warning(
                    f"Last message role is '{messages[-1].get('role')}', expected 'user'. "
                    "Appending current user message."
                )
                messages.append({"role": "user", "content": user_message})

            # If a plan was generated, inject it right after the user message so
            # the LLM knows the intended execution order.
            if plan and plan.total > 1:
                plan.start()
                plan_guidance = (
                    "I've broken this request into a step-by-step plan. "
                    "Please execute each step in order:\n\n"
                    f"{plan.raw_plan}\n\n"
                    "Work through the steps one at a time. After completing "
                    "each step, move to the next.\n\n"
                    "ADAPTIVE PLANNING: If a step fails or returns unexpected results, "
                    "you can use revise_plan to adjust the remaining steps. "
                    "If you need clarification from the user, call ask_user to pause and ask."
                )
                if plan.has_iterative_steps:
                    plan_guidance += (
                        "\n\nIMPORTANT: Some steps need to be applied to multiple items. "
                        "Use batch_tool when each item only needs one tool call (same action, "
                        "different args). Use loop_tool when each item needs multiple sequential "
                        "steps (a pipeline of tools per item). Both avoid unnecessary round-trips."
                    )
                messages.append({"role": "user", "content": plan_guidance})

            # Log message summary for debugging
            logger.debug(
                f"Final message list: {len(messages)} messages. "
                f"Last user msg: {messages[-1].get('content', '')[:80]}..."
            )

            # If image data is provided, convert the last user message to multimodal format
            model_for_media = None
            if image_base64 and image_mimetype:
                messages = self._inject_image_into_messages(messages, image_base64, image_mimetype)
                logger.debug("Injected image data into last user message (multimodal format)")
                model_for_media = llm_client.config.get_media_model()
                if model_for_media != llm_client.config.model:
                    logger.info(f"Using media model {model_for_media} for image processing")

            # Track tool calls for stuck detection
            tool_call_history = deque(maxlen=10)
            tools_executed = []
            iteration = 0
            stuck_detected = False
            plan_nudge_count = 0

        max_plan_nudges = 3
        max_validation_nudges = 2
        validation_nudge_count = 0

        # Give iterative plans more room to finish
        effective_max_iterations = self.max_iterations
        if plan and plan.has_iterative_steps:
            effective_max_iterations = max(self.max_iterations, 25)
            max_plan_nudges = 5
            logger.debug(
                f"Iterative plan detected: max_iterations={effective_max_iterations}, "
                f"max_nudges={max_plan_nudges}"
            )

        while iteration < effective_max_iterations:
            iteration += 1
            logger.debug(f"Iteration {iteration}/{self.max_iterations}")
            await self._emit(event_callback, {"type": "iteration_start", "iteration": iteration})

            # Surface plan variables once they've been populated by the guardrail.
            # Only inject from iteration 2 onward (variables don't exist until tools run).
            if plan and plan.variables and iteration > 1:
                from src.utils.tmp import get_tmp_dir

                _var_lines = "\n".join(f"  {k}: {v}" for k, v in plan.variables.items())
                _var_msg = (
                    "[Plan data — files produced by previous steps]\n"
                    f"{_var_lines}\n"
                    "Pass these paths to python_agent when a step needs to process this data. "
                    f"Tell python_agent to write output files to {get_tmp_dir()} — do NOT use /app/tmp."
                )
                if not any("[Plan data" in m.get("content", "") for m in messages[-4:]):
                    messages.append({"role": "user", "content": _var_msg})

            # Use media model only on the first call when image is present
            media_override = model_for_media if iteration == 1 else None

            # After the vision model handled iteration 1, strip raw image data
            # from messages so the main model (which may not support multimodal
            # input) doesn't choke on image_url content in later iterations.
            if iteration == 2 and model_for_media and model_for_media != llm_client.config.model:
                messages = self._strip_images_from_messages(messages)
                logger.debug("Stripped image data from messages for main-model iterations")

            # Call LLM (with tools if available, without if none)
            logger.debug(f"Calling LLM with {len(messages)} messages and {len(tools)} tools")
            if tools:
                response = await asyncio.to_thread(
                    llm_client.complete_with_tools,
                    messages=messages,
                    tools=tools,
                    model_override=media_override,
                )
            else:
                response = await asyncio.to_thread(
                    llm_client.complete, messages=messages, model_override=media_override
                )

            # Extract response message
            response_message = response.choices[0].message if response.choices else None

            # Check if LLM wants to call tools
            if not response_message or not response_message.tool_calls:
                final_response = (response_message.content if response_message else None) or ""

                # If the current step was iterative, the LLM stopping tool
                # calls means it finished the iteration — advance past it.
                if (
                    plan
                    and plan.current_step
                    and plan.current_step.requires_iteration
                    and plan.current_step.status == "in_progress"
                ):
                    plan.complete_current()
                    logger.debug("Completed iterative plan step (LLM stopped calling tools)")

                # If the plan still has pending steps, nudge the LLM to continue
                # instead of accepting this as the final response.
                if (
                    plan
                    and plan.total > 1
                    and plan.current_step
                    and plan.current_step.status != "completed"
                ):
                    plan_nudge_count += 1
                    if plan_nudge_count > max_plan_nudges:
                        logger.warning(
                            f"Plan nudge limit ({max_plan_nudges}) reached, "
                            "returning response to user"
                        )
                        # Ask the LLM to summarise what was done
                        pending = [s for s in plan.steps if s.status in ("pending", "in_progress")]
                        pending_desc = "; ".join(f"{s.number}. {s.description}" for s in pending)
                        messages.append({"role": "assistant", "content": final_response})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[Internal: the following plan steps were not completed: "
                                    f"{pending_desc}. "
                                    "Provide a concise summary to the user of what was "
                                    "accomplished and mention any steps that could not be "
                                    "finished. Do NOT repeat this message verbatim.]"
                                ),
                            }
                        )
                        summary_resp = await asyncio.to_thread(
                            llm_client.complete,
                            messages=messages,
                            model_override=llm_client.config.get_worker_model(),
                        )
                        final_response = (
                            summary_resp.choices[0].message.content
                            if summary_resp.choices
                            else None
                        ) or final_response
                        return self._build_result(
                            final_response, tools_executed, iteration, stuck_detected, plan
                        )
                    else:
                        pending = [s for s in plan.steps if s.status in ("pending", "in_progress")]
                        pending_desc = "; ".join(f"{s.number}. {s.description}" for s in pending)
                        logger.info(
                            f"LLM stopped with {len(pending)} plan steps remaining, "
                            f"nudging to continue ({plan_nudge_count}/{max_plan_nudges})"
                        )
                        messages.append({"role": "assistant", "content": final_response})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "You still have unfinished steps in the plan: "
                                    f"{pending_desc}. "
                                    "Continue executing the next step now using the available tools. "
                                    "Do not stop until all steps are complete."
                                ),
                            }
                        )
                        continue

                # Safeguard: refuse to return while sub-tasks are still running.
                # Nudge the LLM to call wait_for_tasks to collect all results first.
                running_tasks = self.async_task_dispatcher.get_running_tasks()
                if running_tasks:
                    running_ids = [t["task_id"] for t in running_tasks]
                    logger.info(
                        f"{len(running_tasks)} sub-task(s) still running when LLM tried "
                        f"to return a final response: {running_ids}. Nudging to wait."
                    )
                    messages.append({"role": "assistant", "content": final_response})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"[Internal: {len(running_tasks)} sub-task(s) are still running: "
                                f"{running_ids}. Call wait_for_tasks to collect their results "
                                "before providing the final response to the user. "
                                "Do NOT repeat this message verbatim.]"
                            ),
                        }
                    )
                    continue

                # Self-validation: before accepting the final response, ask the
                # worker model whether the original task is actually complete.
                # Only fires when budget allows a follow-up iteration.
                if (
                    validation_nudge_count < max_validation_nudges
                    and iteration < effective_max_iterations - 1
                ):
                    validation = await self._validate_response(
                        llm_client=llm_client,
                        user_message=user_message,
                        final_response=final_response,
                        messages=messages,
                    )
                    if not validation["complete"]:
                        validation_nudge_count += 1
                        logger.info(
                            f"Response validator flagged incomplete response "
                            f"({validation_nudge_count}/{max_validation_nudges}): "
                            f"{validation['reason']}"
                        )
                        messages.append({"role": "assistant", "content": final_response})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[Internal: A validation check found the response incomplete. "
                                    f"Reason: {validation['reason']} "
                                    "You must provide the actual answer, data, or content directly "
                                    "in your response — do NOT say you have found it or that it is "
                                    "available. State the answer explicitly and completely. "
                                    "Do NOT repeat this message verbatim.]"
                                ),
                            }
                        )
                        continue

                # If the response is still empty after all validation nudges are
                # exhausted, make one explicit fallback call with a summary of
                # completed tools so the LLM can write a meaningful answer.
                if not final_response.strip():
                    logger.warning(
                        "Final response is empty after validation nudges exhausted; "
                        "making explicit completion call"
                    )
                    tools_summary = ", ".join(tools_executed) if tools_executed else "none"
                    messages.append({"role": "assistant", "content": ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[Internal: Your response is empty. "
                                f"The following tools were already executed: {tools_summary}. "
                                "Based on what was accomplished, write a complete summary "
                                "response to the user describing what was done. "
                                "Do NOT call any more tools. Do NOT repeat this message verbatim.]"
                            ),
                        }
                    )
                    fallback_resp = await asyncio.to_thread(
                        llm_client.complete,
                        messages=messages,
                        model_override=llm_client.config.get_worker_model(),
                    )
                    final_response = (
                        fallback_resp.choices[0].message.content if fallback_resp.choices else None
                    ) or final_response

                logger.debug(f"Conversation complete in {iteration} iterations")
                return self._build_result(
                    final_response, tools_executed, iteration, stuck_detected, plan
                )

            # LLM wants to call tools - add its message to conversation.
            # Ensure content is a string (not None) for Gemini compatibility.
            # response_message is guaranteed non-None here (None case handled above).
            assert response_message is not None
            assistant_msg = response_message.model_dump()
            if assistant_msg.get("content") is None:
                assistant_msg["content"] = ""
            messages.append(assistant_msg)

            # Execute all tool calls
            tool_results = []
            ask_user_pending = None  # set if ask_user is called
            for tool_call in response_message.tool_calls:
                tool_name = tool_call.function.name
                tool_call_id = tool_call.id

                # Parse arguments
                raw_args = tool_call.function.arguments or "{}"
                try:
                    arguments = json.loads(raw_args)
                except json.JSONDecodeError as exc:
                    repaired = try_repair_json(raw_args, hint=exc)
                    if repaired is not None:
                        logger.debug(
                            "Repaired malformed JSON arguments for tool '%s' "
                            "(original error: %s)",
                            tool_name,
                            exc,
                        )
                        arguments = repaired
                    else:
                        logger.warning(
                            "Failed to parse arguments for tool '%s' "
                            "(JSONDecodeError at pos %d: %s) — raw: %r",
                            tool_name,
                            exc.pos,
                            exc.msg,
                            raw_args[:200],
                        )
                        hint = (
                            f"JSON parse error at position {exc.pos}: {exc.msg}. "
                            "Ensure all string values are properly JSON-escaped "
                            '(newlines as \\n, backslashes as \\\\, quotes as \\"). '
                            "Re-emit the tool call with valid JSON."
                        )
                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": json.dumps({"success": False, "error": hint}),
                            }
                        )
                        tools_executed.append(tool_name)
                        continue

                # ----------------------------------------------------------
                # Handle ask_user: suspend execution and return to caller
                # ----------------------------------------------------------
                if tool_name == "ask_user":
                    logger.info(f"ask_user called: {arguments.get('question', '')[:100]}")
                    ask_user_pending = {
                        "tool_call_id": tool_call_id,
                        "arguments": arguments,
                    }
                    # Provide a tool result so the message sequence stays valid,
                    # but we'll return early after this loop.
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(
                                {
                                    "status": "awaiting_user_response",
                                    "message": "Execution paused. Waiting for user response.",
                                }
                            ),
                        }
                    )
                    continue

                # ----------------------------------------------------------
                # Handle revise_plan: update the PlanTracker in place
                # ----------------------------------------------------------
                if tool_name == "revise_plan" and plan:
                    logger.info(f"revise_plan called: action={arguments.get('action')}")
                    revision_result = self._handle_revise_plan(plan, arguments)
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(revision_result),
                        }
                    )
                    tools_executed.append(tool_name)
                    continue

                # ----------------------------------------------------------
                # Handle dispatch_task: spawn an async sub-task
                # ----------------------------------------------------------
                if tool_name == "dispatch_task":
                    description = arguments.get("description", "")
                    context = arguments.get("context", "")
                    logger.info(f"dispatch_task called: {description[:100]}")
                    task_id = self.async_task_dispatcher.dispatch(description, context)
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(
                                {
                                    "task_id": task_id,
                                    "status": "running",
                                    "message": (
                                        f"Sub-task dispatched with ID '{task_id}'. "
                                        f"Call get_task_result(task_id='{task_id}') "
                                        "to check progress and retrieve the result."
                                    ),
                                }
                            ),
                        }
                    )
                    tools_executed.append(tool_name)
                    continue

                # ----------------------------------------------------------
                # Handle get_task_result: retrieve sub-task status / result
                # ----------------------------------------------------------
                if tool_name == "get_task_result":
                    task_id = arguments.get("task_id", "")
                    logger.info(f"get_task_result called: task_id={task_id}")
                    status = self.async_task_dispatcher.get_status(task_id)
                    if status is None:
                        content = {
                            "error": f"Unknown task_id '{task_id}'. "
                            "Make sure you use the exact ID returned by dispatch_task."
                        }
                    else:
                        content = status
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(content),
                        }
                    )
                    tools_executed.append(tool_name)
                    continue

                # ----------------------------------------------------------
                # Handle wait_for_tasks: await sub-tasks, notify channel
                # ----------------------------------------------------------
                if tool_name == "wait_for_tasks":
                    requested_ids = arguments.get("task_ids") or []
                    timeout = float(arguments.get("timeout_seconds", 300))
                    progress_message = arguments.get(
                        "progress_message",
                        "Working on background tasks, please wait…",
                    )

                    # Determine which tasks we're waiting for
                    if not requested_ids:
                        requested_ids = [
                            t["task_id"] for t in self.async_task_dispatcher.get_running_tasks()
                        ]

                    logger.info(
                        f"wait_for_tasks: waiting for {len(requested_ids)} task(s): "
                        f"{requested_ids}"
                    )

                    # Notify the originating channel that work is in progress.
                    # Skipped for webui (user is watching) and subtask (internal).
                    if requested_ids:
                        await self._send_progress_notification(
                            channel=channel,
                            contact_identifier=contact_identifier,
                            message=f"⏳ {progress_message}",
                        )

                    # Block until all requested tasks finish (or timeout)
                    results = await self.async_task_dispatcher.wait_for(
                        task_ids=requested_ids,
                        timeout=timeout,
                    )

                    # Build completion summary and notify channel
                    completed = sum(1 for r in results.values() if r.get("status") == "completed")
                    failed = sum(1 for r in results.values() if r.get("status") == "failed")
                    still_running = sum(1 for r in results.values() if r.get("status") == "running")
                    parts = [f"{completed} completed"]
                    if failed:
                        parts.append(f"{failed} failed")
                    if still_running:
                        parts.append(f"{still_running} timed out")
                    summary = "✅ Sub-tasks done: " + ", ".join(parts)

                    if requested_ids:
                        await self._send_progress_notification(
                            channel=channel,
                            contact_identifier=contact_identifier,
                            message=summary,
                        )

                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps({"tasks": results, "summary": summary}),
                        }
                    )
                    tools_executed.append(tool_name)
                    continue

                # Track for stuck detection
                tool_call_history.append((tool_name, json.dumps(arguments, sort_keys=True)))
                tools_executed.append(tool_name)

                # Emit tool_call event before execution — send only the first
                # two args, each truncated, so the stream stays lightweight.
                _args_preview = {
                    k: (str(v)[:120] + "…" if len(str(v)) > 120 else v)
                    for k, v in list(arguments.items())[:2]
                }
                await self._emit(
                    event_callback,
                    {"type": "tool_call", "tool": tool_name, "args": _args_preview},
                )

                # Execute tool
                logger.info(f"Executing tool: {tool_name}")
                result = await self.tool_executor.execute_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                )

                # --- Tool result size guardrail ---
                # Offload oversized payloads to TMP_DIR so they don't clog the context
                # window. The compact pointer includes schema + one sample record so the
                # LLM can instruct python_agent precisely without loading the data inline.
                # Configurable via the "Max Tool Output Chars" setting (llm.tool_output_max_chars),
                # which falls back to the TOOL_RESULT_OFFLOAD_THRESHOLD env var, then to the
                # default ~300K chars (~75K tokens) sized for 200K-context models.
                _OFFLOAD_THRESHOLD = int(
                    self.settings_service.get_config_with_fallback(
                        "llm.tool_output_max_chars", 300000
                    )
                )
                if "file" not in result:
                    _raw = json.dumps(result)
                    if len(_raw) > _OFFLOAD_THRESHOLD:
                        from src.utils.tmp import get_tmp_dir

                        _tmp = get_tmp_dir()
                        _var_key = f"{tool_name}_result"
                        _out = _tmp / f"{_var_key}_{uuid4().hex[:8]}.json"
                        _out.write_text(_raw, encoding="utf-8")
                        _first = next(
                            (v[0] for v in result.values() if isinstance(v, list) and v), None
                        )
                        _record_count = next(
                            (len(v) for v in result.values() if isinstance(v, list)), None
                        )
                        logger.info(
                            "Tool '%s' result offloaded (%d chars) → %s",
                            tool_name,
                            len(_raw),
                            _out,
                        )
                        result = {
                            "file": str(_out),
                            "record_count": _record_count,
                            "schema": list(_first.keys()) if isinstance(_first, dict) else None,
                            "sample": _first,
                            "note": (
                                f"Response too large for context ({len(_raw):,} chars). "
                                f"Full data saved to {_out}. "
                                "Pass this path to python_agent to process the data."
                            ),
                        }
                        if plan is not None:
                            plan.variables[_var_key] = str(_out)

                # Track which skill this tool belongs to and persist it as active
                # so it remains available in subsequent messages without re-matching keywords.
                _skill_owner = self._find_skill_for_tool(tool_name)
                if _skill_owner:
                    self._persist_active_skill(conversation_id, _skill_owner)

                # Emit tool_result event
                _result_summary = json.dumps(result)[:200]
                _tool_success = "error" not in result and result.get("success", True) is not False
                await self._emit(
                    event_callback,
                    {
                        "type": "tool_result",
                        "tool": tool_name,
                        "success": _tool_success,
                        "summary": _result_summary,
                    },
                )

                # Format result as tool response message
                result_content = json.dumps(result)
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_content,
                    }
                )

            # Add tool results to conversation
            messages.extend(tool_results)

            # ----------------------------------------------------------
            # If ask_user was called, suspend the loop
            # ----------------------------------------------------------
            if ask_user_pending:
                suspended_state = {
                    "messages": self._serialize_messages(messages),
                    "tools_executed": tools_executed,
                    "iteration": iteration,
                    "plan": plan.to_dict() if plan else None,
                    "tool_call_history": list(tool_call_history),
                    "plan_nudge_count": plan_nudge_count,
                    "ask_user_tool_call_id": ask_user_pending["tool_call_id"],
                }
                question = ask_user_pending["arguments"].get("question", "")
                options = ask_user_pending["arguments"].get("options")
                context_text = ask_user_pending["arguments"].get("context", "")
                response_text = question
                if context_text:
                    response_text = f"{context_text}\n\n{question}"

                return {
                    "response": response_text,
                    "tools_executed": tools_executed,
                    "iterations": iteration,
                    "stuck_detected": stuck_detected,
                    "awaiting_input": True,
                    "pending_input": {
                        "question": question,
                        "options": options,
                        "context": context_text,
                    },
                    "suspended_state": suspended_state,
                    **(
                        {
                            "plan_steps_completed": plan.completed_count,
                            "plan_steps_total": plan.total,
                        }
                        if plan and plan.total > 1
                        else {}
                    ),
                }

            # Advance plan progress after successful tool execution
            if plan and tool_results:
                advanced = plan.advance()
                if advanced:
                    logger.debug(f"Plan advanced to step {advanced.number}: {advanced.description}")
                elif not plan.current_step:
                    logger.debug("All plan steps completed")

            # ----------------------------------------------------------
            # Adaptive reflection: check if the LLM should re-evaluate
            # the plan based on the latest tool results.
            # ----------------------------------------------------------
            if plan and plan.total > 1 and plan.current_step:
                if Planner.should_reflect(tool_results, plan):
                    reflection_prompt = Planner.build_reflection_prompt(plan, tool_results)
                    messages.append({"role": "user", "content": reflection_prompt})
                    logger.info("Injected plan reflection checkpoint")

            # Check if stuck
            if self._is_stuck(tool_call_history):
                logger.warning(f"Stuck detected at iteration {iteration}")
                stuck_detected = True

                # Force completion with explanation prompt
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You seem to be repeating the same tool calls. "
                            "Please provide a final response based on the information you have gathered, "
                            "or explain what additional information you need from me."
                        ),
                    }
                )

                # Get final response without tools
                final_response_obj = await asyncio.to_thread(
                    llm_client.complete,
                    messages=messages,
                    model_override=llm_client.config.get_worker_model(),
                )
                final_response = (
                    final_response_obj.choices[0].message.content
                    if final_response_obj.choices
                    else None
                ) or ""

                return self._build_result(final_response, tools_executed, iteration, True, plan)

        # Max iterations reached - nudge LLM to wrap up
        logger.warning(f"Max iterations ({effective_max_iterations}) reached")
        remaining_hint = ""
        if plan:
            pending = [s for s in plan.steps if s.status != "completed"]
            if pending:
                remaining_hint = (
                    " The following steps are still pending: "
                    + "; ".join(f"{s.number}. {s.description}" for s in pending)
                    + ". Summarize what was accomplished and what remains."
                )

        messages.append(
            {
                "role": "user",
                "content": (
                    "Please provide a final response based on the information "
                    "you have gathered so far." + remaining_hint
                ),
            }
        )

        final_response_obj = await asyncio.to_thread(
            llm_client.complete,
            messages=messages,
            model_override=llm_client.config.get_worker_model(),
        )
        final_response = (
            final_response_obj.choices[0].message.content if final_response_obj.choices else None
        ) or ""

        return self._build_result(final_response, tools_executed, iteration, False, plan)

    @staticmethod
    def _build_result(
        response: str,
        tools_executed: List[str],
        iterations: int,
        stuck_detected: bool,
        plan: Optional[PlanTracker] = None,
    ) -> Dict[str, Any]:
        """Build the standard result dict, including plan metadata when available."""
        result: Dict[str, Any] = {
            "response": response,
            "tools_executed": tools_executed,
            "iterations": iterations,
            "stuck_detected": stuck_detected,
        }
        if plan and plan.total > 1:
            result["plan_steps_completed"] = plan.completed_count
            result["plan_steps_total"] = plan.total
        return result

    # ------------------------------------------------------------------
    # Response self-validation
    # ------------------------------------------------------------------

    @staticmethod
    async def _validate_response(
        llm_client: LLMClient,
        user_message: str,
        final_response: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Ask the worker model whether the proposed response fully completes the task.

        Returns {"complete": True} or {"complete": False, "reason": "<explanation>"}.
        Defaults to {"complete": True} on any parsing or API failure so a broken
        validator never blocks a legitimate response.
        """
        # Summarise which tools were actually called, to give the validator context.
        tool_names_called: List[str] = []
        for msg in messages:
            for tc in msg.get("tool_calls") or []:
                fn_name = (tc.get("function") or {}).get("name")
                if fn_name:
                    tool_names_called.append(fn_name)
        tools_summary = ", ".join(tool_names_called) if tool_names_called else "none"

        validation_messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict task-completion validator. "
                    "Given an original task and a proposed final response, decide whether "
                    "the task has been fully carried out. "
                    "CRITICAL: The response must contain the actual answer, data, or content "
                    "requested — not merely a statement that the answer was found or is available. "
                    "Mark as incomplete if the response says things like 'I found the answer', "
                    "'I have all the information', 'the result is available', or any similar "
                    "phrasing that references the answer without actually stating it. "
                    "Reply with JSON only — no prose, no markdown:\n"
                    '  {"complete": true}\n'
                    '  {"complete": false, "reason": "<short explanation of what is missing>"}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"ORIGINAL TASK:\n{user_message}\n\n"
                    f"TOOLS CALLED DURING EXECUTION: {tools_summary}\n\n"
                    f"PROPOSED FINAL RESPONSE:\n{final_response}\n\n"
                    "Does the response contain the actual answer/content (not just a claim that "
                    "the answer exists or was found)? Reply with JSON only."
                ),
            },
        ]

        try:
            resp = await asyncio.to_thread(
                llm_client.complete,
                messages=validation_messages,
                model_override=llm_client.config.get_worker_model(),
                max_tokens=120,
            )
            content = (resp.choices[0].message.content or "").strip()
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return {
                    "complete": bool(data.get("complete", True)),
                    "reason": data.get("reason", ""),
                }
        except Exception as exc:
            logger.warning(f"Response validation call failed, assuming complete: {exc}")

        return {"complete": True, "reason": ""}

    # ------------------------------------------------------------------
    # Adaptive planning helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_revise_plan(plan: PlanTracker, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a revise_plan tool call by mutating the PlanTracker."""
        return handle_revise_plan(plan, arguments)

    # ------------------------------------------------------------------
    # ask_user suspension / resumption helpers
    # ------------------------------------------------------------------

    def _get_suspended_state(self, conversation_id: str) -> Optional[Tuple[Dict[str, Any], str]]:
        """Check if a conversation has a suspended execution awaiting user input.

        Returns a tuple of (suspended_state_dict, message_id) or None.
        """
        try:
            history = self.conversation_service.message_repo.get_recent_messages(
                conversation_id, count=5
            )
            if not history:
                return None
            for msg in reversed(history):
                meta = msg.get("metadata")
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = None
                if isinstance(meta, dict) and meta.get("suspended_state"):
                    return meta["suspended_state"], msg.get("message_id", "")
        except Exception as e:
            logger.warning(f"Could not check for suspended state: {e}")
        return None

    def _save_suspended_state(
        self, conversation_id: str, suspended_state: Dict[str, Any], question: str = ""
    ) -> str:
        """Persist suspended execution state as an assistant message with metadata.

        Returns the message_id of the created message so it can be cleared
        after resumption.
        """
        content = question or "I have a question for you..."
        msg = self.conversation_service.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            metadata={"suspended_state": suspended_state},
        )
        return msg.get("message_id", "")

    async def _resume_suspended_execution(
        self,
        conv_id: str,
        user_answer: str,
        suspended_state: Dict[str, Any],
        suspended_message_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        channel: str = "webui",
        contact_identifier: Optional[str] = None,
        event_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Resume a suspended execution with the user's answer.

        Restores the full message history and plan state, injects the
        user's answer as the tool result for the original ``ask_user``
        call, and continues the conversation loop.
        """
        # Store the user's answer as a message
        self.conversation_service.add_message(
            conversation_id=conv_id,
            role="user",
            content=user_answer,
            metadata=metadata,
        )

        # Restore state
        messages = self._deserialize_messages(suspended_state.get("messages", []))
        tools_executed = suspended_state.get("tools_executed", [])
        iteration = suspended_state.get("iteration", 0)
        plan = None
        if suspended_state.get("plan"):
            plan = PlanTracker.from_dict(suspended_state["plan"])
        tool_call_history = deque(
            [tuple(x) for x in suspended_state.get("tool_call_history", [])],
            maxlen=10,
        )
        plan_nudge_count = suspended_state.get("plan_nudge_count", 0)

        # Find and update the ask_user tool result with the user's answer
        ask_user_tc_id = suspended_state.get("ask_user_tool_call_id")
        if ask_user_tc_id:
            for msg in messages:
                if msg.get("role") == "tool" and msg.get("tool_call_id") == ask_user_tc_id:
                    msg["content"] = json.dumps(
                        {
                            "status": "user_responded",
                            "user_answer": user_answer,
                        }
                    )
                    break

        # Rebuild tools and LLM client
        selected_skills = self._select_skills(
            # Use the original user message from the first user message in history
            next(
                (m.get("content", "") for m in messages if m.get("role") == "user"),
                user_answer,
            )
        )
        tools = self._get_tools_from_skills(selected_skills)
        if plan and plan.total > 1:
            tools = self._inject_plan_tools(tools)
        llm_client = self._get_llm_client()

        # Continue the conversation loop from where we left off
        result = await self._execute_conversation_loop(
            llm_client=llm_client,
            system_prompt="",
            user_message=user_answer,
            conversation_id=conv_id,
            tools=tools,
            plan=plan,
            channel=channel,
            contact_identifier=contact_identifier,
            resume_messages=messages,
            resume_iteration=iteration,
            resume_tools_executed=tools_executed,
            resume_tool_call_history=tool_call_history,
            resume_plan_nudge_count=plan_nudge_count,
            event_callback=event_callback,
        )

        # Clear the suspended state from the original message to prevent
        # stale re-detection.
        if suspended_message_id:
            try:
                self.conversation_service.message_repo.update_metadata(
                    suspended_message_id, {"resumed": True}
                )
            except Exception as e:
                logger.warning(f"Could not clear suspended state metadata: {e}")

        # Handle the result (might suspend again)
        if result.get("awaiting_input"):
            self._save_suspended_state(
                conv_id,
                result["suspended_state"],
                question=result["pending_input"]["question"],
            )
            return {
                "response": result["response"],
                "conversation_id": conv_id,
                "skills_used": [s.name for s in selected_skills],
                "tools_executed": result["tools_executed"],
                "iterations": result["iterations"],
                "stuck_detected": result["stuck_detected"],
                "pending_input": result["pending_input"],
            }

        # Store final response
        response_metadata = {
            "skills_used": [s.name for s in selected_skills],
            "tools_executed": result["tools_executed"],
            "iterations": result["iterations"],
            "stuck_detected": result["stuck_detected"],
        }
        if "plan_steps_total" in result:
            response_metadata["plan_steps_completed"] = result["plan_steps_completed"]
            response_metadata["plan_steps_total"] = result["plan_steps_total"]

        self.conversation_service.add_message(
            conversation_id=conv_id,
            role="assistant",
            content=result["response"],
            metadata=response_metadata,
        )

        # Auto-compaction after resumed turn (same pattern as handle_message)
        try:
            auto_compact = self.settings_service.get_config_with_fallback("llm.auto_compact", True)
            if auto_compact and self.memory_service.should_summarize(conv_id):
                asyncio.create_task(self._run_auto_compaction(conv_id, llm_client.config.model))
                logger.debug(f"Auto-compaction scheduled for conversation: {conv_id}")
        except Exception as e:
            logger.warning(f"Could not schedule auto-compaction: {e}")

        return {
            "response": result["response"],
            "conversation_id": conv_id,
            "skills_used": [s.name for s in selected_skills],
            "tools_executed": result["tools_executed"],
            "iterations": result["iterations"],
            "stuck_detected": result["stuck_detected"],
        }

    @staticmethod
    def _serialize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Serialize messages for suspension storage."""
        return serialize_messages(messages)

    @staticmethod
    def _deserialize_messages(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Restore messages from suspension storage."""
        return deserialize_messages(data)

    def _is_stuck(self, tool_call_history: deque) -> bool:
        """
        Detect if the LLM is stuck in a loop.

        Detection criteria:
        1. Same tool + same args called 3+ times consecutively
        2. Same (tool, args) pair appears 5+ times in last 10 calls

        Calling the same tool with *different* arguments (e.g. labelling
        different emails) is legitimate iteration, not a stuck loop.
        """
        if len(tool_call_history) < 3:
            return False

        history = list(tool_call_history)

        # Check for consecutive repeats (same tool + same args)
        if len(history) >= 3:
            last_three = history[-3:]
            if len(set(last_three)) == 1:
                logger.debug(f"Stuck: same call repeated 3 times: {last_three[0][0]}")
                return True

        # Check for same (tool + args) pair called many times.
        # This checks the full tuple, so same tool with different args
        # (legitimate iteration) won't trigger it.
        if len(history) >= 7:
            call_counts = Counter(history[-10:])
            most_common_call, count = call_counts.most_common(1)[0]
            if count >= 5:
                logger.debug(
                    f"Stuck: identical call '{most_common_call[0]}' repeated {count} times"
                )
                return True

        return False

    @staticmethod
    def _strip_images_from_messages(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Strip image_url content parts from messages, keeping only text.

        Called before iteration 2+ when a separate media model handled the
        image on iteration 1, so the main model (which may not support
        multimodal input) receives text-only messages.
        """
        result = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                text = " ".join(t for t in text_parts if t).strip()
                result.append({**msg, "content": text or "[image]"})
            else:
                result.append(msg)
        return result

    @staticmethod
    def _inject_image_into_messages(
        messages: List[Dict[str, Any]],
        image_base64: str,
        image_mimetype: str,
    ) -> List[Dict[str, Any]]:
        """
        Convert the last user message to multimodal format with an image.

        Replaces the simple string content of the final user message with the
        OpenAI vision format so that models with vision capabilities can
        process the image alongside the text.
        """
        result = list(messages)

        # Find the last user message and convert to multimodal
        for i in range(len(result) - 1, -1, -1):
            if result[i].get("role") == "user":
                text_content = result[i].get("content", "")
                if isinstance(text_content, list):
                    # Already multimodal - append the image
                    parts = list(text_content)
                else:
                    parts = [{"type": "text", "text": text_content or "What's in this image?"}]

                # Strip codec params from mime type
                base_mime = image_mimetype.split(";")[0].strip()

                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{base_mime};base64,{image_base64}",
                        },
                    }
                )
                result[i] = {**result[i], "content": parts}
                break

        return result

    async def _run_auto_compaction(self, conversation_id: str, model: str) -> None:
        """Fire-and-forget background task that compresses conversation history.

        Called after a turn completes when should_summarize() returns True.
        Uses the worker model via MemoryService. Failures are swallowed so
        they never surface to the user.
        """
        try:
            logger.info(f"Auto-compaction triggered for conversation: {conversation_id}")
            await asyncio.to_thread(
                self.memory_service.compress_conversation,
                conversation_id,
                None,  # target_tokens: let compress_conversation use its default (70% of max)
                model,
            )
            logger.info(f"Auto-compaction completed for conversation: {conversation_id}")
        except Exception as e:
            logger.warning(f"Auto-compaction failed for {conversation_id}: {e}")
