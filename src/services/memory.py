"""Memory service for conversation context management and summarization."""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.core.database import DatabaseManager
from src.core.llm_client import SINGLE_MODEL_PROVIDERS, LLMClient, get_llm_client
from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.memory import MemoryRepository
from src.core.repositories.message import MessageRepository
from src.core.repositories.prompts import PromptsRepository
from src.core.repositories.settings import SettingsRepository
from src.core.transparency_logger import transparency_logger
from src.utils.logger import get_logger
from src.utils.token_counter import count_message_tokens, count_tokens

logger = get_logger(__name__)


class MemoryService:
    """Service for managing conversation memory and context."""

    def __init__(
        self,
        message_repo: MessageRepository,
        memory_repo: MemoryRepository,
        conversation_repo: ConversationRepository,
        prompts_repo: PromptsRepository,
        settings_repo: SettingsRepository,
        db_manager: DatabaseManager,
        llm_client: Optional[LLMClient] = None,
        max_tokens: Optional[int] = None,
        summarization_threshold: Optional[int] = None,
    ):
        """
        Initialize memory service.

        Args:
            message_repo: Message repository
            memory_repo: Memory repository
            conversation_repo: Conversation repository
            prompts_repo: Prompts repository
            settings_repo: Settings repository
            db_manager: Database manager
            llm_client: LLM client for summarization (created if not provided)
            max_tokens: Maximum tokens for context (uses setting or ENV if not provided)
            summarization_threshold: Message threshold for summarization (uses setting or ENV if not provided)
        """
        self.message_repo = message_repo
        self.memory_repo = memory_repo
        self.conversation_repo = conversation_repo
        self.prompts_repo = prompts_repo
        self.settings_repo = settings_repo
        self.db_manager = db_manager
        self.llm_client = llm_client

        # Configuration from parameters or environment (with fallback)
        # Note: These can be configured in the Settings UI or via ENV variables
        self.max_tokens = max_tokens or int(os.getenv("MEMORY_MAX_TOKENS", "100000"))
        self.summarization_threshold = summarization_threshold or int(
            os.getenv("MEMORY_SUMMARIZATION_THRESHOLD", "50")
        )

    def _get_context_strategy(self) -> str:
        """Get the configured context strategy ('summarization' or 'last_messages')."""
        db_value = self.settings_repo.get("llm.context_strategy")
        if db_value:
            return db_value
        return os.getenv("LLM_CONTEXT_STRATEGY", "summarization")

    def _get_max_tokens(self) -> int:
        """Get the conversation context token budget (DB setting → ENV → init default).

        Read on each turn so the "Max Context Tokens" setting takes effect at
        runtime without a restart, matching the context-strategy settings.
        """
        db_value = self.settings_repo.get("memory.max_tokens")
        if db_value is not None:
            return int(db_value)
        return self.max_tokens

    def _get_context_max_messages(self) -> int:
        """Get the max messages limit for the 'last_messages' context strategy."""
        db_value = self.settings_repo.get("llm.context_max_messages")
        if db_value is not None:
            return int(db_value)
        return int(os.getenv("LLM_CONTEXT_MAX_MESSAGES", "20"))

    def _get_llm_client(self) -> LLMClient:
        """Get or create the main-model LLM client, reading config from settings first."""
        if self.llm_client is None:
            api_key = self.settings_repo.get("llm.api_key") or os.getenv("LLM_API_KEY")
            if not api_key:
                raise ValueError("LLM_API_KEY not configured")
            provider = self.settings_repo.get("llm.provider") or os.getenv(
                "LLM_PROVIDER", "openrouter"
            )
            model = self.settings_repo.get("llm.model") or os.getenv(
                "LLM_MODEL", "anthropic/claude-3.5-sonnet"
            )
            base_url = self.settings_repo.get("llm.base_url") or os.getenv("LLM_BASE_URL")
            self.llm_client = get_llm_client(
                api_key=api_key, provider=provider, model=model, base_url=base_url
            )
        return self.llm_client

    def _get_worker_llm_client(self) -> LLMClient:
        """Get an LLM client using the worker model for cheap background tasks.

        Falls back to the main model if no worker model is configured.
        Not cached — called rarely, and the setting can change at runtime.
        """
        api_key = self.settings_repo.get("llm.api_key") or os.getenv("LLM_API_KEY")
        if not api_key:
            return self._get_llm_client()
        provider = self.settings_repo.get("llm.provider") or os.getenv("LLM_PROVIDER", "openrouter")
        main_model = self.settings_repo.get("llm.model") or os.getenv(
            "LLM_MODEL", "anthropic/claude-3.5-sonnet"
        )
        # Single-model providers (Ollama, vLLM) serve one model per endpoint, so
        # the worker role always reuses the main model.
        if provider in SINGLE_MODEL_PROVIDERS:
            model = main_model
        else:
            model = (
                self.settings_repo.get("llm.worker_model")
                or os.getenv("LLM_WORKER_MODEL")
                or main_model
            )
        base_url = self.settings_repo.get("llm.base_url") or os.getenv("LLM_BASE_URL")
        return get_llm_client(api_key=api_key, provider=provider, model=model, base_url=base_url)

    def get_conversation_context(
        self,
        conversation_id: str,
        model: str,
        max_tokens: Optional[int] = None,
        include_system_message: bool = True,
    ) -> Dict[str, Any]:
        """
        Get conversation context within token limits.

        Args:
            conversation_id: Conversation ID
            model: Model name for token counting
            max_tokens: Maximum tokens (defaults to MEMORY_MAX_TOKENS)
            include_system_message: Whether to include system message

        Returns:
            Dictionary with messages, memories, and metadata
        """
        max_tokens = max_tokens or self._get_max_tokens()
        strategy = self._get_context_strategy()

        # Get all messages
        messages = self.message_repo.get_by_conversation(conversation_id)

        # Get facts (used by both strategies)
        facts = self.memory_repo.get_by_type(conversation_id, "facts", limit=10)

        if strategy == "last_messages":
            return self._get_context_last_messages(
                conversation_id=conversation_id,
                messages=messages,
                facts=facts,
                model=model,
                max_tokens=max_tokens,
                include_system_message=include_system_message,
            )

        # Default: summarization strategy
        # Get long-term memories (summaries)
        long_term_memories = self.memory_repo.get_by_type(conversation_id, "long_term")

        # Build context
        context_messages = []

        # Add system message
        if include_system_message:
            system_message = {"role": "system", "content": self._build_system_message(facts)}
            context_messages.append(system_message)

        # Add long-term memories as system context
        if long_term_memories:
            for memory in reversed(long_term_memories):  # Oldest first
                context_messages.append(
                    {
                        "role": "system",
                        "content": f"[Previous conversation summary]: {memory['content'].get('summary', '')}",
                    }
                )

        # Add recent messages
        context_messages.extend(
            [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        )

        # Calculate total tokens
        total_tokens = count_message_tokens(context_messages, model)

        # If over limit, compress
        if total_tokens > max_tokens:
            logger.info(f"Context exceeds {max_tokens} tokens ({total_tokens}), compressing...")
            context_messages = self._compress_context(context_messages, max_tokens, model)
            total_tokens = count_message_tokens(context_messages, model)

        return {
            "messages": context_messages,
            "total_tokens": total_tokens,
            "message_count": len(messages),
            "long_term_memory_count": len(long_term_memories),
            "facts_count": len(facts),
        }

    def _get_context_last_messages(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        facts: List[Dict[str, Any]],
        model: str,
        max_tokens: int,
        include_system_message: bool,
    ) -> Dict[str, Any]:
        """
        Build context using the 'last_messages' strategy: keep only the most recent
        N messages (bounded by llm.context_max_messages) that fit within max_tokens.
        """
        max_messages = self._get_context_max_messages()

        # Limit to most recent N messages first
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages

        context_messages = []

        if include_system_message:
            context_messages.append(
                {"role": "system", "content": self._build_system_message(facts)}
            )

        # Calculate tokens used by system message
        system_tokens = count_message_tokens(context_messages, model)
        available_tokens = max_tokens - system_tokens

        # Fit as many recent messages as possible within token budget (from newest back)
        fitting_messages: List[Dict[str, str]] = []
        current_tokens = 0
        for msg in reversed(recent_messages):
            msg_dict = {"role": msg["role"], "content": msg["content"]}
            msg_tokens = count_message_tokens([msg_dict], model)
            if current_tokens + msg_tokens > available_tokens:
                break
            fitting_messages.insert(0, msg_dict)
            current_tokens += msg_tokens

        context_messages.extend(fitting_messages)
        total_tokens = system_tokens + current_tokens

        logger.info(
            f"last_messages strategy: kept {len(fitting_messages)}/{len(messages)} messages "
            f"({total_tokens} tokens, limit {max_tokens})"
        )

        return {
            "messages": context_messages,
            "total_tokens": total_tokens,
            "message_count": len(messages),
            "long_term_memory_count": 0,
            "facts_count": len(facts),
        }

    def _build_system_message(self, facts: List[Dict[str, Any]]) -> str:
        """Build system message with facts."""
        # Load system prompt from database
        system_prompt_default = self.prompts_repo.get("system_prompt_default")
        system_prompt_custom = self.prompts_repo.get("system_prompt_custom")
        memory_prompt = self.prompts_repo.get("memory")
        soul_prompt = self.prompts_repo.get("soul")

        # Start with default system prompt
        base_message = system_prompt_default.get("value", "") if system_prompt_default else ""

        # Add custom system prompt if provided
        if system_prompt_custom and system_prompt_custom.get("value"):
            base_message += "\n\n" + system_prompt_custom.get("value")

        # Add memory if provided
        if memory_prompt and memory_prompt.get("value"):
            base_message += "\n\nUser Context & Memory:\n" + memory_prompt.get("value")

        # Add soul/personality if provided
        if soul_prompt and soul_prompt.get("value"):
            base_message += "\n\nPersonality & Communication Style:\n" + soul_prompt.get("value")

        # Add conversation facts
        if facts:
            facts_text = "\n".join(
                [
                    f"- {fact['content'].get('fact', '')}"
                    for fact in facts
                    if "fact" in fact["content"]
                ]
            )
            if facts_text:
                base_message += f"\n\nKnown facts from this conversation:\n{facts_text}"

        # Add enabled tools information
        try:
            from src.core.tools.registry import get_tool_registry

            tool_registry = get_tool_registry()
            enabled_tools = tool_registry.list_tools(self.settings_repo, enabled_only=True)

            if enabled_tools:
                tools_by_service = {}
                for tool in enabled_tools:
                    service = getattr(tool, "service_name", "system")
                    if service not in tools_by_service:
                        tools_by_service[service] = []
                    tools_by_service[service].append(tool.name)

                tools_info = "\n\n=== Available Tools ===\n"
                for service, tool_names in sorted(tools_by_service.items()):
                    tools_info += f"\n{service.capitalize()}: {', '.join(tool_names)}"

                base_message += tools_info
        except Exception as e:
            logger.error(f"Failed to load tools info: {e}")

        # Add enabled agents information
        try:
            from src.agents.registry import AgentRegistry

            agent_registry = AgentRegistry(self.db_manager)
            enabled_agents = agent_registry.get_enabled_agents()

            if enabled_agents:
                agents_info = "\n\n=== Available Agents ===\n"
                for agent in enabled_agents:
                    agents_info += f"\n- {agent.display_name} ({agent.name}): {agent.role}"

                base_message += agents_info
        except Exception as e:
            logger.error(f"Failed to load agents info: {e}")

        return base_message

    def _compress_context(
        self, messages: List[Dict[str, str]], max_tokens: int, model: str
    ) -> List[Dict[str, str]]:
        """
        Compress context to fit token limit.

        Strategy:
        1. Keep system messages
        2. Keep most recent N messages
        3. Summarize older messages

        Args:
            messages: List of messages
            max_tokens: Maximum tokens allowed
            model: Model name

        Returns:
            Compressed message list
        """
        # Reserve 20% of tokens for system messages and overhead
        available_tokens = int(max_tokens * 0.8)

        # Separate system messages and conversation messages
        system_messages = [msg for msg in messages if msg["role"] == "system"]
        conversation_messages = [msg for msg in messages if msg["role"] != "system"]

        # Calculate system message tokens
        system_tokens = count_message_tokens(system_messages, model)

        # Remaining tokens for conversation
        conversation_tokens = available_tokens - system_tokens

        # Keep recent messages that fit
        recent_messages = []
        current_tokens = 0

        for msg in reversed(conversation_messages):
            msg_tokens = count_message_tokens([msg], model)

            if current_tokens + msg_tokens <= conversation_tokens:
                recent_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break

        # Combine system + recent messages
        compressed = system_messages + recent_messages

        logger.info(
            f"Compressed context: kept {len(recent_messages)}/{len(conversation_messages)} messages"
        )

        return compressed

    def summarize_old_messages(
        self, conversation_id: str, before_timestamp: Optional[str] = None, max_messages: int = 50
    ) -> Optional[str]:
        """
        Summarize old messages and store as long-term memory.

        Args:
            conversation_id: Conversation ID
            before_timestamp: Summarize messages before this timestamp
            max_messages: Maximum number of messages to summarize

        Returns:
            Summary text or None if no messages to summarize
        """
        # Get messages to summarize
        if before_timestamp:
            messages = self.message_repo.get_messages_before(
                conversation_id, before_timestamp, limit=max_messages
            )
        else:
            # Get all but last 10 messages
            all_messages = self.message_repo.get_by_conversation(conversation_id)
            if len(all_messages) <= 10:
                return None
            messages = all_messages[:-10][:max_messages]

        if not messages:
            return None

        # Build conversation text
        conversation_text = "\n\n".join(
            [f"{msg['role'].upper()}: {msg['content']}" for msg in messages]
        )

        # Generate summary using the worker model (anchored to prior summary if one exists)
        try:
            llm = self._get_worker_llm_client()

            # Fetch the most recent prior summary to anchor the new one — this prevents
            # information loss when compaction runs multiple times on the same conversation.
            prior_summaries = self.memory_repo.get_by_type(conversation_id, "long_term", limit=1)
            prior_context = ""
            if prior_summaries:
                prev = prior_summaries[0]["content"].get("summary", "")
                if prev:
                    prior_context = f"Previous conversation summary:\n{prev}\n\n"

            summary_prompt = f"""You are creating a running summary of a conversation.
{prior_context}New conversation segment to integrate:
{conversation_text}

Write an updated coherent summary in 2-4 paragraphs that merges the prior context \
(if any) with the new segment. Preserve all key facts, decisions, and action items."""

            summary = llm.complete_text(summary_prompt)

            # Persist the summary as an internal transparency row (visibility
            # only; billing reads llm_consumption). Billing-neutral.
            transparency_logger.log(
                conversation_id, "memory_summary", summary, role="assistant"
            )

            # Store as long-term memory
            self.memory_repo.store_memory(
                conversation_id,
                "long_term",
                {
                    "summary": summary,
                    "message_count": len(messages),
                    "timestamp_range": {
                        "start": messages[0]["timestamp"],
                        "end": messages[-1]["timestamp"],
                    },
                },
            )

            # Mark messages as summarized
            for msg in messages:
                self.message_repo.mark_as_summary(msg["message_id"])

            # Increment context version
            self.conversation_repo.increment_context_version(conversation_id)

            logger.info(f"Summarized {len(messages)} messages for conversation: {conversation_id}")

            return summary

        except Exception as e:
            logger.error(f"Failed to summarize messages: {e}")
            return None

    def extract_facts(self, conversation_id: str, recent_message_count: int = 20) -> List[str]:
        """
        Extract key facts from recent conversation.

        Args:
            conversation_id: Conversation ID
            recent_message_count: Number of recent messages to analyze

        Returns:
            List of extracted facts
        """
        # Get recent messages
        messages = self.message_repo.get_recent_messages(conversation_id, recent_message_count)

        if not messages:
            return []

        # Build conversation text
        conversation_text = "\n\n".join(
            [f"{msg['role'].upper()}: {msg['content']}" for msg in messages]
        )

        # Extract facts using the worker model
        try:
            llm = self._get_worker_llm_client()

            extract_prompt = f"""Extract key facts, preferences, and important information from this conversation.
Focus on:
- User's name, location, occupation
- Preferences and interests
- Important dates or events
- Action items or commitments
- Recurring themes

Conversation:
{conversation_text}

List each fact as a single concise sentence, one per line."""

            facts_text = llm.complete_text(extract_prompt)

            # Persist the extracted facts as an internal transparency row
            # (visibility only; billing-neutral).
            transparency_logger.log(
                conversation_id, "memory_facts", facts_text, role="assistant"
            )

            # Parse facts (one per line)
            facts = [
                fact.strip()
                for fact in facts_text.split("\n")
                if fact.strip() and not fact.strip().startswith(("#", "-"))
            ]

            # Store facts
            for fact in facts:
                self.memory_repo.store_memory(conversation_id, "facts", {"fact": fact})

            logger.info(f"Extracted {len(facts)} facts from conversation: {conversation_id}")

            return facts

        except Exception as e:
            logger.error(f"Failed to extract facts: {e}")
            return []

    def should_summarize(self, conversation_id: str) -> bool:
        """
        Check if conversation should be summarized.

        Args:
            conversation_id: Conversation ID

        Returns:
            True if summarization is recommended
        """
        # Respect the auto_compact toggle — None means setting not set, treat as default True
        auto_compact_raw = self.settings_repo.get("llm.auto_compact")
        if auto_compact_raw is not None and not auto_compact_raw:
            return False
        if self._get_context_strategy() == "last_messages":
            return False
        message_count = self.message_repo.count_messages(conversation_id)
        return message_count >= self.summarization_threshold

    def compress_conversation(
        self, conversation_id: str, target_tokens: Optional[int] = None, model: str = "default"
    ) -> Dict[str, Any]:
        """
        Compress conversation to target token count.

        Args:
            conversation_id: Conversation ID
            target_tokens: Target token count (uses 70% of max if not specified)
            model: Model name for token counting

        Returns:
            Dictionary with compression statistics
        """
        target_tokens = target_tokens or int(self._get_max_tokens() * 0.7)

        # Get current token count
        messages = self.message_repo.get_by_conversation(conversation_id)
        message_dicts = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        current_tokens = count_message_tokens(message_dicts, model)

        if current_tokens <= target_tokens:
            return {
                "compressed": False,
                "reason": "Already within target",
                "current_tokens": current_tokens,
                "target_tokens": target_tokens,
            }

        # Keep recent messages
        recent_count = 10
        recent_messages = messages[-recent_count:]

        # Summarize older messages
        old_messages = messages[:-recent_count]

        if old_messages:
            summary = self.summarize_old_messages(
                conversation_id, before_timestamp=recent_messages[0]["timestamp"]
            )
        else:
            summary = None

        # Calculate new token count
        new_context = self.get_conversation_context(conversation_id, model, target_tokens)

        return {
            "compressed": True,
            "original_tokens": current_tokens,
            "compressed_tokens": new_context["total_tokens"],
            "tokens_saved": current_tokens - new_context["total_tokens"],
            "messages_summarized": len(old_messages),
            "messages_kept": len(recent_messages),
            "summary_created": summary is not None,
        }
