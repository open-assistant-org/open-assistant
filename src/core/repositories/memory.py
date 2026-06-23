"""Repository for conversation memory operations."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MemoryRepository(BaseRepository):
    """Repository for managing conversation memory."""

    def store_memory(self, conversation_id: str, memory_type: str, content: Dict[str, Any]) -> int:
        """
        Store a memory entry.

        Args:
            conversation_id: Conversation ID
            memory_type: Type of memory (short_term, long_term, facts, working)
            content: Memory content as dictionary

        Returns:
            Inserted row ID
        """
        data = {
            "conversation_id": conversation_id,
            "memory_type": memory_type,
            "content": json.dumps(content),
            "created_at": datetime.utcnow().isoformat(),
        }

        row_id = self.insert("conversation_memory", data)
        logger.debug(f"Stored {memory_type} memory for conversation: {conversation_id}")

        return row_id

    def get_by_type(
        self, conversation_id: str, memory_type: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get memories by type for a conversation.

        Args:
            conversation_id: Conversation ID
            memory_type: Memory type filter
            limit: Maximum number of entries

        Returns:
            List of memory entries
        """
        if limit:
            query = """
                SELECT * FROM conversation_memory
                WHERE conversation_id = ? AND memory_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = (conversation_id, memory_type, limit)
        else:
            query = """
                SELECT * FROM conversation_memory
                WHERE conversation_id = ? AND memory_type = ?
                ORDER BY created_at DESC
            """
            params = (conversation_id, memory_type)

        results = self.fetch_all(query, params)

        for result in results:
            if result.get("content"):
                result["content"] = json.loads(result["content"])

        return results

    def get_all_memory(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Get all memories for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of all memory entries
        """
        query = """
            SELECT * FROM conversation_memory
            WHERE conversation_id = ?
            ORDER BY memory_type, created_at DESC
        """

        results = self.fetch_all(query, (conversation_id,))

        for result in results:
            if result.get("content"):
                result["content"] = json.loads(result["content"])

        return results

    def delete_by_type(self, conversation_id: str, memory_type: str) -> int:
        """
        Delete all memories of a specific type.

        Args:
            conversation_id: Conversation ID
            memory_type: Memory type to delete

        Returns:
            Number of deleted entries
        """
        affected = self.delete(
            "conversation_memory",
            "conversation_id = ? AND memory_type = ?",
            (conversation_id, memory_type),
        )

        if affected > 0:
            logger.info(
                f"Deleted {affected} {memory_type} memories for " f"conversation: {conversation_id}"
            )

        return affected

    def delete_all_memory(self, conversation_id: str) -> int:
        """
        Delete all memories for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Number of deleted entries
        """
        affected = self.delete("conversation_memory", "conversation_id = ?", (conversation_id,))

        if affected > 0:
            logger.info(f"Deleted all memories for conversation: {conversation_id}")

        return affected
