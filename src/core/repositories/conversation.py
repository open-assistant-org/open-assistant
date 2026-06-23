"""Repository for conversation operations."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
        self, channel: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List conversations with pagination.

        Args:
            channel: Filter by channel (optional)
            limit: Number of conversations to return
            offset: Pagination offset

        Returns:
            List of conversation dictionaries
        """
        if channel:
            query = """
                SELECT * FROM conversations
                WHERE channel = ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """
            params = (channel, limit, offset)
        else:
            query = """
                SELECT * FROM conversations
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """
            params = (limit, offset)

        results = self.fetch_all(query, params)

        for result in results:
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])

        return results

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

    def count_conversations(self, channel: Optional[str] = None) -> int:
        """
        Count total conversations.

        Args:
            channel: Filter by channel (optional)

        Returns:
            Total conversation count
        """
        if channel:
            query = "SELECT COUNT(*) FROM conversations WHERE channel = ?"
            params = (channel,)
        else:
            query = "SELECT COUNT(*) FROM conversations"
            params = None

        return self.fetch_scalar(query, params) or 0

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
