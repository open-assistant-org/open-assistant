"""Repository for conversation operations."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 1 when the conversation's metadata has ``"archived": true``, else 0. Guarded
# with json_valid so a row with malformed metadata counts as not archived
# instead of failing the whole query.
ARCHIVED_SQL = (
    "(CASE WHEN json_valid(metadata) "
    "THEN COALESCE(json_extract(metadata, '$.archived'), 0) ELSE 0 END)"
)


class ConversationRepository(BaseRepository):
    """Repository for managing conversations."""

    def create(
        self,
        conversation_id: Optional[str] = None,
        channel: str = "webui",
        contact_identifier: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new conversation.

        Args:
            conversation_id: Unique conversation ID (auto-generated if not provided)
            channel: Communication channel (webui, whatsapp, etc.)
            contact_identifier: Contact identifier (email, phone, etc.)
            metadata: Additional metadata

        Returns:
            Created conversation dictionary
        """
        if conversation_id is None:
            conversation_id = str(uuid4())

        data = {
            "conversation_id": conversation_id,
            "channel": channel,
            "contact_identifier": contact_identifier,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": json.dumps(metadata) if metadata else None,
            "context_version": 1,
            "last_accessed": datetime.utcnow().isoformat(),
        }

        self.insert("conversations", data)
        logger.info(f"Created conversation: {conversation_id}")

        return self.get_by_id(conversation_id)

    def get_by_id(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation by ID.

        Args:
            conversation_id: Conversation ID

        Returns:
            Conversation dictionary or None
        """
        query = "SELECT * FROM conversations WHERE conversation_id = ?"
        result = self.fetch_one(query, (conversation_id,))

        if result and result.get("metadata"):
            result["metadata"] = json.loads(result["metadata"])

        return result

    def get_by_contact(self, channel: str, contact_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Get most recent conversation by contact.

        Args:
            channel: Communication channel
            contact_identifier: Contact identifier

        Returns:
            Conversation dictionary or None
        """
        query = """
            SELECT * FROM conversations
            WHERE channel = ? AND contact_identifier = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """
        result = self.fetch_one(query, (channel, contact_identifier))

        if result and result.get("metadata"):
            result["metadata"] = json.loads(result["metadata"])

        return result

    def list_conversations(
        self,
        channel: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        archived: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        List conversations with pagination.

        Args:
            channel: Filter by channel (optional)
            limit: Number of conversations to return
            offset: Pagination offset
            archived: True for only archived conversations, False for only
                unarchived ones, None (default) for both

        Returns:
            List of conversation dictionaries
        """
        where, params = self._filters(channel, archived)
        query = f"""
            SELECT * FROM conversations
            {where}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """

        results = self.fetch_all(query, (*params, limit, offset))

        for result in results:
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])

        return results

    @staticmethod
    def _filters(channel: Optional[str], archived: Optional[bool]) -> Tuple[str, Tuple[Any, ...]]:
        """Build the WHERE clause shared by list_conversations and count_conversations."""
        clauses: List[str] = []
        params: List[Any] = []
        if channel:
            clauses.append("channel = ?")
            params.append(channel)
        if archived is not None:
            clauses.append(f"{ARCHIVED_SQL} = ?")
            params.append(1 if archived else 0)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, tuple(params)

    def update_metadata(self, conversation_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update conversation metadata.

        Args:
            conversation_id: Conversation ID
            metadata: New metadata dictionary

        Returns:
            True if updated, False otherwise
        """
        data = {"metadata": json.dumps(metadata), "updated_at": datetime.utcnow().isoformat()}

        affected = self.update("conversations", data, "conversation_id = ?", (conversation_id,))

        logger.info(f"Updated metadata for conversation: {conversation_id}")
        return affected > 0

    def update_last_accessed(self, conversation_id: str) -> bool:
        """
        Update last accessed timestamp.

        Args:
            conversation_id: Conversation ID

        Returns:
            True if updated, False otherwise
        """
        data = {
            "last_accessed": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        affected = self.update("conversations", data, "conversation_id = ?", (conversation_id,))

        return affected > 0

    def increment_context_version(self, conversation_id: str) -> bool:
        """
        Increment context version (for cache invalidation).

        Args:
            conversation_id: Conversation ID

        Returns:
            True if updated, False otherwise
        """
        query = """
            UPDATE conversations
            SET context_version = context_version + 1,
                updated_at = ?
            WHERE conversation_id = ?
        """

        cursor = self.execute_query(query, (datetime.utcnow().isoformat(), conversation_id))

        logger.info(f"Incremented context version for conversation: {conversation_id}")
        return cursor.rowcount > 0

    def count_conversations(
        self, channel: Optional[str] = None, archived: Optional[bool] = None
    ) -> int:
        """
        Count total conversations.

        Args:
            channel: Filter by channel (optional)
            archived: True for only archived conversations, False for only
                unarchived ones, None (default) for both

        Returns:
            Total conversation count
        """
        where, params = self._filters(channel, archived)
        query = f"SELECT COUNT(*) FROM conversations {where}"

        return self.fetch_scalar(query, params or None) or 0

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation (and cascade to messages).

        Args:
            conversation_id: Conversation ID

        Returns:
            True if deleted, False otherwise
        """
        affected = self.delete("conversations", "conversation_id = ?", (conversation_id,))

        if affected > 0:
            logger.info(f"Deleted conversation: {conversation_id}")

        return affected > 0
