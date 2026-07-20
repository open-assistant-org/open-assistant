"""Transparency logger — persists auxiliary LLM outputs as internal message rows.

So the system prompt and auxiliary LLM calls (planner, memory summarization/fact
extraction, document composition, the python sub-agent, analysis) become visible
in the conversation view — letting you see the LLM's inner workings — without
polluting the history re-sent to the LLM on subsequent turns.

Rows are written with ``is_internal = 1`` and excluded from
``get_recent_messages`` / ``get_by_conversation`` (see
:meth:`MessageRepository`). They are **billing-neutral**: billing reads the
``llm_consumption`` ledger, not ``messages``.

Like :mod:`usage_recorder`, this is a process-level singleton wired once at
startup. Each call site logs with one line:
``transparency_logger.log(conversation_id, "planner", plan_text)``.
Never raises; no-ops when no DB is wired. Writes delegate to
:class:`MessageRepository` (and thus :class:`BaseRepository`).
"""

from typing import Any, Dict, Optional

from src.core.database import DatabaseManager
from src.core.repositories.base import BaseRepository
from src.core.repositories.message import MessageRepository
from src.utils.logger import get_logger
from src.utils.token_counter import count_tokens

logger = get_logger(__name__)


class TransparencyLogger:
    """Persists internal transparency message rows into the ``messages`` table.

    Process-level singleton — one instance shared app-wide, configured with the
    ``DatabaseManager`` at startup.
    """

    _db: Optional[DatabaseManager] = None
    # Hot-path cache: conversation_ids that already have a system_prompt row,
    # so the once-per-conversation guard avoids a SELECT + connection open on
    # every chat turn after the first.
    _has_system_prompt: set = set()

    @classmethod
    def set_db(cls, db_manager: DatabaseManager) -> None:
        """Wire the database manager. Called once at app startup."""
        cls._db = db_manager
        logger.info("TransparencyLogger wired to database")

    @classmethod
    def clear(cls) -> None:
        """Detach the database manager and cache. Used in tests to reset state."""
        cls._db = None
        cls._has_system_prompt.clear()

    @classmethod
    def has_internal(
        cls, conversation_id: str, kind: Optional[str] = None
    ) -> bool:
        """Return True if an internal row already exists for this conversation.

        When ``kind`` is given, only rows of that kind are considered. Used to
        persist the system prompt once per conversation rather than every turn.
        No-op (returns False) when no DB is wired.
        """
        if cls._db is None:
            return False
        # Hot path: system_prompt existence is cached in memory after first log.
        if kind == "system_prompt" and conversation_id in cls._has_system_prompt:
            return True
        try:
            if kind:
                return BaseRepository(cls._db).exists(
                    "messages",
                    "conversation_id = ? AND is_internal = 1 "
                    "AND json_extract(metadata, '$.kind') = ?",
                    (conversation_id, kind),
                )
            return BaseRepository(cls._db).exists(
                "messages",
                "conversation_id = ? AND is_internal = 1",
                (conversation_id,),
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"TransparencyLogger has_internal failed: {e}")
            return False

    @classmethod
    def log(
        cls,
        conversation_id: Optional[str],
        kind: str,
        content: str,
        *,
        role: str = "assistant",
        model: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        once: bool = False,
    ) -> None:
        """Persist one internal message row.

        Args:
            conversation_id: Conversation this row belongs to. If None, the row
                is skipped (the messages table requires a conversation_id FK and
                orphan transparency rows aren't useful).
            kind: Tag stored in ``metadata.kind`` (e.g. "planner",
                "memory_summary", "document", "system_prompt").
            content: The auxiliary LLM output (or system prompt text).
            role: Message role (default "assistant"; "system" for the prompt).
            model: Optional model name for token counting/display.
            extra_metadata: Optional extra fields merged into metadata.
            once: If True, skip when an internal row of this ``kind`` already
                exists for the conversation (used for the system prompt, which
                is largely stable and need only be logged once).

        Never raises; no-op when no DB is wired or conversation_id is None.
        """
        if cls._db is None or not conversation_id or content is None:
            return

        if once and cls.has_internal(conversation_id, kind=kind):
            return

        try:
            metadata: Dict[str, Any] = {"kind": kind, "internal": True}
            if extra_metadata:
                metadata.update(extra_metadata)

            MessageRepository(cls._db).create(
                conversation_id=conversation_id,
                role=role,
                content=content,
                metadata=metadata,
                token_count=count_tokens(content, model or "default"),
                is_internal=True,
            )
            if kind == "system_prompt":
                cls._has_system_prompt.add(conversation_id)
        except Exception as e:  # noqa: BLE001 - transparency must not break chat
            logger.error(f"TransparencyLogger failed to log '{kind}': {e}")


# Module-level singleton.
transparency_logger = TransparencyLogger
