"""Repository for message operations."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MessageRepository(BaseRepository):
    """Repository for managing messages."""

    def create(
        self,
        conversation_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        token_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Create a new message.

        Args:
            conversation_id: Conversation ID this message belongs to
            role: Message role (user, assistant, system)
            content: Message content
            message_id: Unique message ID (auto-generated if not provided)
            metadata: Additional metadata
            token_count: Number of tokens in the message

        Returns:
            Created message dictionary
        """
        if message_id is None:
            message_id = str(uuid4())

        data = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": json.dumps(metadata) if metadata else None,
            "token_count": token_count,
            "is_summary": False,
        }

        self.insert("messages", data)
        logger.debug(f"Created message: {message_id} in conversation: {conversation_id}")

        return self.get_by_id(message_id)

    def get_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get message by ID.

        Args:
            message_id: Message ID

        Returns:
            Message dictionary or None
        """
        query = "SELECT * FROM messages WHERE message_id = ?"
        result = self.fetch_one(query, (message_id,))

        if result and result.get("metadata"):
            result["metadata"] = json.loads(result["metadata"])

        return result

    def get_by_conversation(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
        include_summaries: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get messages for a conversation.

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages to return
            offset: Pagination offset
            include_summaries: Whether to include summary messages

        Returns:
            List of message dictionaries ordered by timestamp
        """
        if include_summaries:
            query = """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """
            params = [conversation_id]
        else:
            query = """
                SELECT * FROM messages
                WHERE conversation_id = ? AND is_summary = 0
                ORDER BY timestamp ASC
            """
            params = [conversation_id]

        if limit:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        results = self.fetch_all(query, tuple(params))

        for result in results:
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])

        return results

    def get_recent_messages(self, conversation_id: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent N messages.

        Args:
            conversation_id: Conversation ID
            count: Number of recent messages to retrieve

        Returns:
            List of recent messages ordered by timestamp DESC
        """
        query = """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """

        results = self.fetch_all(query, (conversation_id, count))

        # Reverse to get chronological order
        results.reverse()

        for result in results:
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])

        return results

    def count_messages(self, conversation_id: str, role: Optional[str] = None) -> int:
        """
        Count messages in a conversation.

        Args:
            conversation_id: Conversation ID
            role: Filter by role (optional)

        Returns:
            Message count
        """
        if role:
            query = """
                SELECT COUNT(*) FROM messages
                WHERE conversation_id = ? AND role = ?
            """
            params = (conversation_id, role)
        else:
            query = "SELECT COUNT(*) FROM messages WHERE conversation_id = ?"
            params = (conversation_id,)

        return self.fetch_scalar(query, params) or 0

    def sum_token_count(self, conversation_id: str) -> int:
        """
        Calculate total token count for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Total token count
        """
        query = """
            SELECT SUM(token_count) FROM messages
            WHERE conversation_id = ?
        """

        return self.fetch_scalar(query, (conversation_id,)) or 0

    def get_messages_before(
        self, conversation_id: str, before_timestamp: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get messages before a specific timestamp.

        Args:
            conversation_id: Conversation ID
            before_timestamp: ISO timestamp
            limit: Maximum number of messages

        Returns:
            List of messages
        """
        if limit:
            query = """
                SELECT * FROM messages
                WHERE conversation_id = ? AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (conversation_id, before_timestamp, limit)
        else:
            query = """
                SELECT * FROM messages
                WHERE conversation_id = ? AND timestamp < ?
                ORDER BY timestamp DESC
            """
            params = (conversation_id, before_timestamp)

        results = self.fetch_all(query, params)

        for result in results:
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])

        return results

    def update_metadata(self, message_id: str, new_metadata: Dict[str, Any]) -> bool:
        """Replace the metadata JSON for a message.

        Args:
            message_id: Message ID
            new_metadata: New metadata dict (completely replaces old metadata)

        Returns:
            True if updated, False otherwise
        """
        data = {"metadata": json.dumps(new_metadata) if new_metadata else None}
        affected = self.update("messages", data, "message_id = ?", (message_id,))
        return affected > 0

    def mark_as_summary(self, message_id: str) -> bool:
        """
        Mark a message as a summary.

        Args:
            message_id: Message ID

        Returns:
            True if updated, False otherwise
        """
        data = {"is_summary": True}

        affected = self.update("messages", data, "message_id = ?", (message_id,))

        return affected > 0

    def update_token_count(self, message_id: str, token_count: int) -> bool:
        """
        Update token count for a message.

        Args:
            message_id: Message ID
            token_count: Token count

        Returns:
            True if updated, False otherwise
        """
        data = {"token_count": token_count}

        affected = self.update("messages", data, "message_id = ?", (message_id,))

        return affected > 0

    def delete_old_messages(self, conversation_id: str, before_timestamp: str) -> int:
        """
        Delete old messages before a timestamp.

        Args:
            conversation_id: Conversation ID
            before_timestamp: ISO timestamp

        Returns:
            Number of deleted messages
        """
        affected = self.delete(
            "messages", "conversation_id = ? AND timestamp < ?", (conversation_id, before_timestamp)
        )

        if affected > 0:
            logger.info(f"Deleted {affected} old messages from conversation: {conversation_id}")

        return affected

    def get_monthly_token_totals(self, months: int = 12) -> List[Dict[str, Any]]:
        """Return token counts grouped by calendar month for the last N months.

        Used by the managed usage API to report billing data to the platform.
        Returns months in ascending order; current month is always included.

        Returns:
            List of dicts with keys: year, month, tokens_total
        """
        query = """
            SELECT
                CAST(strftime('%Y', timestamp) AS INTEGER) AS year,
                CAST(strftime('%m', timestamp) AS INTEGER) AS month,
                SUM(token_count) AS tokens_total
            FROM messages
            WHERE timestamp >= datetime('now', ? || ' months')
            GROUP BY year, month
            ORDER BY year ASC, month ASC
        """
        offset = f"-{months}"
        return self.fetch_all(query, (offset,))

    def search_messages(self, query: str) -> List[str]:
        """
        Search for messages containing a query string.

        Args:
            query: Search query string

        Returns:
            List of unique conversation IDs with matching messages
        """
        sql = """
            SELECT DISTINCT conversation_id
            FROM messages
            WHERE LOWER(content) LIKE LOWER(?)
        """

        search_pattern = f"%{query}%"
        results = self.fetch_all(sql, (search_pattern,))

        return [row["conversation_id"] for row in results]
