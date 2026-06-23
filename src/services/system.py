"""System operations service for LLM tools."""

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.llm_client import LLMClient, LLMConfig
from src.services.embedding import EmbeddingService
from src.utils.logger import get_logger
from src.utils.token_counter import count_tokens

logger = get_logger(__name__)


class SystemService:
    """Service for system-level operations accessible to the LLM."""

    # Maximum tokens of conversation text to return from get_conversation_text.
    # Keeps the payload sent to the LLM for nightly updates manageable.
    MAX_CONVERSATION_TOKENS = int(os.getenv("SYSTEM_AGENT_MAX_CONVERSATION_TOKENS", "6000"))

    def __init__(
        self, db_manager=None, embedding_service=None, search_service=None, settings_service=None
    ):
        """Initialize system service.

        Args:
            db_manager: Optional DatabaseManager for conversation/prompt access.
            embedding_service: Optional EmbeddingService for generating embeddings.
            search_service: Optional UnifiedSearchService for memory index search.
            settings_service: Optional SettingsService for reading LLM config from DB.
        """
        self.log_dir = os.getenv("LOG_DIR", "logs")
        self.log_file = Path(self.log_dir) / "assistant.log"
        from src.utils.tmp import get_tmp_dir

        self.tmp_dir = get_tmp_dir()
        self._db_manager = db_manager
        self._embedding_service = embedding_service
        self._search_service = search_service
        self._settings_service = settings_service

    def fetch_logs(self, lines: int = 500, level: Optional[str] = None) -> Dict:
        """
        Fetch recent application log lines.

        This allows the LLM to review recent logs to help diagnose issues,
        understand recent activity, or answer questions about system behavior.

        Args:
            lines: Number of log lines to fetch (default 500, max 2000)
            level: Optional log level filter (ERROR, WARNING, INFO, DEBUG)

        Returns:
            Dictionary with log entries and metadata
        """
        try:
            if not self.log_file.exists():
                return {
                    "success": False,
                    "error": f"Log file not found: {self.log_file}",
                    "logs": [],
                }

            # Clamp lines to max
            lines = min(lines, 2000)

            # Read log lines using tail for efficiency
            result = subprocess.run(
                ["tail", "-n", str(lines * 2), str(self.log_file)],
                capture_output=True,
                text=True,
                check=True,
            )

            log_lines = result.stdout.strip().split("\n")
            parsed_logs = []

            # Parse and filter logs
            for line in reversed(log_lines):  # Newest first
                if not line.strip():
                    continue

                try:
                    # Parse format: "2024-01-01 12:00:00,123 - LEVEL - module - message"
                    parts = line.split(" - ", 3)
                    if len(parts) >= 4:
                        timestamp, log_level, module, message = parts

                        # Filter by level if specified
                        if level and log_level != level:
                            continue

                        parsed_logs.append(
                            {
                                "timestamp": timestamp,
                                "level": log_level,
                                "module": module,
                                "message": message,
                            }
                        )

                        if len(parsed_logs) >= lines:
                            break
                except Exception as e:
                    # Skip malformed lines
                    logger.debug(f"Failed to parse log line: {e}")
                    continue

            return {
                "success": True,
                "log_file": str(self.log_file),
                "total_lines": len(parsed_logs),
                "filter": {"level": level} if level else None,
                "logs": parsed_logs,
            }

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to read log file: {e}")
            return {"success": False, "error": f"Failed to read log file: {str(e)}", "logs": []}
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            return {"success": False, "error": str(e), "logs": []}

    def clean_tmp_dir(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Remove files from the temporary directory that are older than max_age_hours.

        Args:
            max_age_hours: Delete files older than this many hours (default 24)

        Returns:
            Dictionary with cleanup results
        """
        try:
            if not self.tmp_dir.exists():
                return {
                    "success": True,
                    "message": f"Tmp directory does not exist: {self.tmp_dir}",
                    "deleted": 0,
                    "errors": 0,
                }

            max_age_hours = min(max(max_age_hours, 1), 720)
            cutoff = time.time() - (max_age_hours * 3600)
            deleted = 0
            errors = 0
            freed_bytes = 0

            for entry in self.tmp_dir.iterdir():
                try:
                    if entry.is_file() or entry.is_symlink():
                        if entry.stat().st_mtime < cutoff:
                            size = entry.stat().st_size
                            entry.unlink()
                            deleted += 1
                            freed_bytes += size
                    elif entry.is_dir():
                        # Recursively remove old directories
                        dir_mtime = entry.stat().st_mtime
                        if dir_mtime < cutoff:
                            import shutil

                            size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                            shutil.rmtree(entry)
                            deleted += 1
                            freed_bytes += size
                except Exception as e:
                    logger.warning(f"Failed to remove {entry}: {e}")
                    errors += 1

            logger.info(
                f"Tmp cleanup: deleted {deleted} items, freed {freed_bytes} bytes, "
                f"{errors} errors"
            )

            return {
                "success": True,
                "tmp_dir": str(self.tmp_dir),
                "max_age_hours": max_age_hours,
                "deleted": deleted,
                "freed_bytes": freed_bytes,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"Error cleaning tmp directory: {e}", exc_info=True)
            return {"success": False, "error": str(e), "deleted": 0, "errors": 1}

    # ---- Conversation text retrieval ----

    def get_conversation_text(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """Return conversation message text within a time window.

        Args:
            since: ISO-8601 start timestamp (inclusive). Defaults to start of today (UTC).
            until: ISO-8601 end timestamp (inclusive). Defaults to now.
            channel: Optional channel filter (e.g. 'webui', 'whatsapp').
            limit: Max number of messages to return (default 200, max 1000).

        Returns:
            Dict with messages list, metadata, and success flag.
        """
        if not self._db_manager:
            return {"success": False, "error": "Database not available", "messages": []}

        try:
            if not since:
                since = (
                    datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                )
            if not until:
                until = datetime.utcnow().isoformat()

            limit = min(limit, 1000)

            # Single SQL query: join messages with conversations, filter by
            # timestamp range and role directly in the database.
            conn = self._db_manager.get_connection()
            cursor = conn.cursor()

            if channel:
                cursor.execute(
                    """
                    SELECT m.conversation_id,
                           c.channel,
                           m.role,
                           m.content,
                           m.timestamp
                    FROM messages m
                    JOIN conversations c ON c.conversation_id = m.conversation_id
                    WHERE m.timestamp >= ?
                      AND m.timestamp <= ?
                      AND m.role IN ('user', 'assistant')
                      AND c.channel = ?
                    ORDER BY m.timestamp ASC
                    LIMIT ?
                    """,
                    (since, until, channel, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT m.conversation_id,
                           c.channel,
                           m.role,
                           m.content,
                           m.timestamp
                    FROM messages m
                    JOIN conversations c ON c.conversation_id = m.conversation_id
                    WHERE m.timestamp >= ?
                      AND m.timestamp <= ?
                      AND m.role IN ('user', 'assistant')
                    ORDER BY m.timestamp ASC
                    LIMIT ?
                    """,
                    (since, until, limit),
                )

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()

            all_messages: List[Dict[str, Any]] = [dict(zip(columns, row)) for row in rows]

            # --- Token-budget trimming ---
            # Serialize to the text the LLM will actually see, then trim
            # from the *oldest* end so the most recent info is preserved.
            total_before = len(all_messages)
            trimmed = False

            if all_messages:
                combined = self._serialize_messages(all_messages)
                token_count = count_tokens(combined)

                if token_count > self.MAX_CONVERSATION_TOKENS:
                    logger.info(
                        f"Conversation text ({token_count} tokens) exceeds budget "
                        f"({self.MAX_CONVERSATION_TOKENS}), trimming oldest messages"
                    )
                    # Drop from the front (oldest) until within budget
                    while all_messages and token_count > self.MAX_CONVERSATION_TOKENS:
                        all_messages.pop(0)
                        combined = self._serialize_messages(all_messages)
                        token_count = count_tokens(combined)
                    trimmed = True
                    logger.info(f"Trimmed to {len(all_messages)} messages ({token_count} tokens)")

            return {
                "success": True,
                "since": since,
                "until": until,
                "total_messages": len(all_messages),
                "trimmed": trimmed,
                "trimmed_from": total_before if trimmed else None,
                "token_count": (
                    count_tokens(self._serialize_messages(all_messages)) if all_messages else 0
                ),
                "token_budget": self.MAX_CONVERSATION_TOKENS,
                "messages": all_messages,
            }
        except Exception as e:
            logger.error(f"Error getting conversation text: {e}", exc_info=True)
            return {"success": False, "error": str(e), "messages": []}

    @staticmethod
    def _serialize_messages(messages: List[Dict[str, Any]]) -> str:
        """Serialize messages to the text format the LLM will process."""
        return "\n".join(f"[{m['timestamp']}] {m['role']}: {m['content']}" for m in messages)

    # ---- Prompt read helpers ----

    def get_prompt(self, key: str) -> Dict[str, Any]:
        """Read a prompt value by key.

        Args:
            key: One of 'system_prompt_default', 'system_prompt_custom', 'memory', 'soul'.

        Returns:
            Dict with the prompt value and metadata.
        """
        if not self._db_manager:
            return {"success": False, "error": "Database not available"}
        try:
            from src.core.repositories.prompts import PromptsRepository

            repo = PromptsRepository(self._db_manager)
            record = repo.get(key)
            if not record:
                return {"success": False, "error": f"Prompt '{key}' not found"}
            return {
                "success": True,
                "key": key,
                "value": record.get("value", ""),
                "updated_at": record.get("updated_at"),
            }
        except Exception as e:
            logger.error(f"Error reading prompt {key}: {e}")
            return {"success": False, "error": str(e)}

    # ---- Prompt update helpers ----

    def update_memory_prompt(self, updated_memory: str) -> Dict[str, Any]:
        """Update the memory prompt.

        The caller (system agent) is responsible for merging / appending to the
        existing content – this method simply persists the new value.

        Args:
            updated_memory: The full new memory prompt text.

        Returns:
            Dict with success flag.
        """
        if not self._db_manager:
            return {"success": False, "error": "Database not available"}
        try:
            from src.core.repositories.prompts import PromptsRepository

            repo = PromptsRepository(self._db_manager)
            repo.set("memory", updated_memory)
            logger.info("Memory prompt updated by system agent")
            return {"success": True, "message": "Memory prompt updated"}
        except Exception as e:
            logger.error(f"Error updating memory prompt: {e}")
            return {"success": False, "error": str(e)}

    def index_memory_facts(self, date: str, facts: str) -> Dict[str, Any]:
        """Index general/contextual memory facts into the search_index table.

        These are background facts that don't need to live in the system prompt
        on every request — e.g. interests, project context, relationship details.
        They are stored with a date-based source_id and can be recalled later
        via unified search with source 'memory'.

        Args:
            date: ISO date string (YYYY-MM-DD) identifying when the facts were recorded.
            facts: Text containing the general facts to index.

        Returns:
            Dict with success flag and indexing details.
        """
        if not self._db_manager:
            return {"success": False, "error": "Database not available"}
        try:
            source_id = f"memory_facts_{date}"
            title = f"Memory Facts – {date}"
            full_content = f"{title}\n\n{facts}"
            content_hash = hashlib.sha256(full_content.encode()).hexdigest()
            metadata_json = json.dumps({"date": date, "type": "memory_facts"})

            conn = self._db_manager.get_connection()
            try:
                # Generate embedding if embedding service is available
                embedding_blob = None
                if self._embedding_service and self._embedding_service.is_available():
                    try:
                        embedding = self._embedding_service.embed_single(full_content)
                        if embedding is not None:
                            embedding_blob = EmbeddingService.serialize_embedding(embedding)
                    except Exception as emb_err:
                        logger.debug(f"Embedding generation failed: {emb_err}")

                conn.execute(
                    """INSERT INTO search_index
                       (source, source_id, title, content, content_hash,
                        embedding, metadata, indexed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(source, source_id) DO UPDATE SET
                           title = excluded.title,
                           content = excluded.content,
                           content_hash = excluded.content_hash,
                           embedding = excluded.embedding,
                           metadata = excluded.metadata,
                           indexed_at = CURRENT_TIMESTAMP""",
                    (
                        "memory",
                        source_id,
                        title,
                        full_content[:8000],
                        content_hash,
                        embedding_blob,
                        metadata_json,
                    ),
                )
                conn.commit()
                logger.info(
                    f"Memory facts indexed for {date} (embedding={'yes' if embedding_blob else 'no'})"
                )
                return {
                    "success": True,
                    "source_id": source_id,
                    "date": date,
                    "embedded": embedding_blob is not None,
                    "message": f"General memory facts for {date} stored in search index.",
                }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error indexing memory facts: {e}")
            return {"success": False, "error": str(e)}

    def _get_llm_client(self) -> LLMClient:
        """Build an LLM client from settings (reads worker_model from DB)."""
        if self._settings_service is None:
            raise ValueError("Settings service not provided to SystemService")
        config = LLMConfig.from_settings(self._settings_service)
        return LLMClient(config)

    def recall_conversation_memory(
        self,
        query: List[str],
        question: str,
        max_conversations: int = 3,
        context_window: int = 10,
    ) -> Dict[str, Any]:
        """Search past conversation messages for keywords and synthesize relevant context.

        This tool complements unified_search (which searches indexed memory facts) by
        searching the raw message history. It finds conversations containing the query
        keywords, retrieves surrounding context, and uses a worker LLM to produce a
        focused summary that answers the question.

        Args:
            query: List of search keywords provided by the main LLM.
            question: Specific question to answer from the retrieved context.
            max_conversations: Maximum number of conversations to retrieve context from.
            context_window: Number of messages to include per matched conversation.

        Returns:
            Dict with summary, sources list, and match counts.
        """
        if not self._db_manager:
            return {"success": False, "error": "Database not available"}

        try:
            # Use the keywords directly — the main LLM already chose them.
            keywords = [kw.strip() for kw in query if kw.strip()]

            conn = self._db_manager.get_connection()
            try:
                conditions = " OR ".join(["LOWER(m.content) LIKE LOWER(?)" for _ in keywords])
                params: List[Any] = [f"%{kw}%" for kw in keywords]
                params.append(max_conversations * 5)  # fetch extra candidates, trim below

                cursor = conn.execute(
                    f"""
                    SELECT DISTINCT m.conversation_id,
                           c.created_at,
                           c.channel,
                           MIN(m.timestamp) AS first_match_ts
                    FROM messages m
                    JOIN conversations c ON c.conversation_id = m.conversation_id
                    WHERE m.role IN ('user', 'assistant')
                      AND ({conditions})
                    GROUP BY m.conversation_id
                    ORDER BY first_match_ts DESC
                    LIMIT ?
                    """,
                    params,
                )
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description]
                matched_conversations = [dict(zip(columns, row)) for row in rows]
            finally:
                conn.close()

            if not matched_conversations:
                return {
                    "success": True,
                    "summary": "No past conversations found containing those keywords.",
                    "sources": [],
                    "matched_conversations": 0,
                    "query": ", ".join(query),
                }

            # Retrieve context messages for each matched conversation.
            conversation_contexts: List[str] = []
            sources: List[Dict[str, Any]] = []

            for conv in matched_conversations[:max_conversations]:
                conv_id = conv["conversation_id"]
                conv_date = (conv.get("created_at") or "")[:10]
                channel = conv.get("channel", "unknown")

                conn = self._db_manager.get_connection()
                try:
                    cursor = conn.execute(
                        """
                        SELECT role, content, timestamp
                        FROM messages
                        WHERE conversation_id = ?
                          AND role IN ('user', 'assistant')
                          AND timestamp >= ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                        """,
                        (conv_id, conv["first_match_ts"], context_window),
                    )
                    msg_rows = cursor.fetchall()
                finally:
                    conn.close()

                if not msg_rows:
                    continue

                lines = [f"[Conversation {conv_date} | channel: {channel}]"]
                for role, content, ts in msg_rows:
                    short_ts = (ts or "")[:16]
                    lines.append(f"{short_ts} {role.upper()}: {content}")
                conversation_contexts.append("\n".join(lines))

                sources.append(
                    {
                        "conversation_id": conv_id,
                        "date": conv_date,
                        "channel": channel,
                        "messages_retrieved": len(msg_rows),
                    }
                )

            # Also search the memory index (indexed facts from system_index_memory_facts).
            # Search each keyword individually to avoid phrase-matching failure.
            index_snippets: List[str] = []
            index_sources: List[Dict[str, Any]] = []
            seen_source_ids: set = set()
            if self._search_service:
                try:
                    for keyword in query:
                        index_result = self._search_service.search(
                            query=keyword,
                            sources=["memory"],
                            search_type="hybrid",
                            limit=5,
                        )
                        for hit in index_result.get("results", []):
                            source_id = hit.get("source_id", "")
                            if source_id in seen_source_ids:
                                continue
                            seen_source_ids.add(source_id)
                            snippet = hit.get("snippet") or hit.get("title") or ""
                            if snippet:
                                date = (hit.get("metadata") or {}).get("date", "")
                                label = f"[Indexed memory{' – ' + date if date else ''}]"
                                index_snippets.append(f"{label}\n{snippet}")
                                index_sources.append(
                                    {
                                        "source": "memory_index",
                                        "source_id": source_id,
                                        "date": date,
                                        "score": hit.get("score"),
                                    }
                                )
                except Exception as search_err:
                    logger.warning(f"Memory index search failed: {search_err}")

            has_conversation_context = bool(conversation_contexts)
            has_index_context = bool(index_snippets)

            if not has_conversation_context and not has_index_context:
                return {
                    "success": True,
                    "summary": "No relevant information found in past conversations or memory index.",
                    "sources": sources + index_sources,
                    "matched_conversations": len(matched_conversations),
                    "query": ", ".join(query),
                }

            # Build unified context for the worker LLM.
            context_sections: List[str] = []
            if index_snippets:
                context_sections.append("## Indexed Memory Facts\n\n" + "\n\n".join(index_snippets))
            if conversation_contexts:
                context_sections.append(
                    "## Past Conversation Excerpts\n\n" + "\n\n---\n\n".join(conversation_contexts)
                )
            full_context = "\n\n".join(context_sections)

            # Worker LLM: synthesize a focused answer from the combined context.
            try:
                llm = self._get_llm_client()
                focus = question

                system_msg = (
                    "You are a memory assistant. You have been given indexed memory facts and "
                    "excerpts from past conversations. Your task is to extract and summarise "
                    "information that directly addresses the user's question. Be concise and "
                    "factual. Cite the source (memory fact date or conversation date) for each "
                    "piece of information."
                )
                prompt = (
                    f"{full_context}\n\n"
                    f"Question: {focus}\n\n"
                    "Provide a concise answer based only on the context above, citing sources."
                )

                messages = []
                if system_msg:
                    messages.append({"role": "system", "content": system_msg})
                messages.append({"role": "user", "content": prompt})

                response = llm.complete(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1024,
                    model_override=llm.config.get_worker_model(),
                )
                summary = response.choices[0].message.content
            except Exception as llm_err:
                logger.error(
                    f"recall_conversation_memory LLM call failed: {llm_err}", exc_info=True
                )
                summary = "Worker LLM unavailable. Raw context:\n\n" + full_context

            all_sources = sources + index_sources
            return {
                "success": True,
                "summary": summary,
                "sources": all_sources,
                "matched_conversations": len(matched_conversations),
                "retrieved_conversations": len(sources),
                "memory_index_hits": len(index_sources),
                "query": ", ".join(query),
            }

        except Exception as e:
            logger.error(f"recall_conversation_memory failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def update_soul_prompt(self, updated_soul: str) -> Dict[str, Any]:
        """Update the soul prompt.

        The caller (system agent) is responsible for merging / appending to the
        existing content – this method simply persists the new value.

        Args:
            updated_soul: The full new soul prompt text.

        Returns:
            Dict with success flag.
        """
        if not self._db_manager:
            return {"success": False, "error": "Database not available"}
        try:
            from src.core.repositories.prompts import PromptsRepository

            repo = PromptsRepository(self._db_manager)
            repo.set("soul", updated_soul)
            logger.info("Soul prompt updated by system agent")
            return {"success": True, "message": "Soul prompt updated"}
        except Exception as e:
            logger.error(f"Error updating soul prompt: {e}")
            return {"success": False, "error": str(e)}
