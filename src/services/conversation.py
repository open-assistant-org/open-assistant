"""Conversation service for high-level conversation management."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.message import MessageRepository
from src.services.memory import MemoryService
from src.utils.logger import get_logger
from src.utils.token_counter import count_tokens

logger = get_logger(__name__)


class ConversationService:
    """Service for managing conversations and messages."""

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        memory_service: MemoryService,
    ):
        """
        Initialize conversation service.

        Args:
            conversation_repo: Conversation repository
            message_repo: Message repository
            memory_service: Memory service
        """
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.memory_service = memory_service

    def create_or_get_conversation(
        self,
        channel: str = "webui",
        contact_identifier: Optional[str] = None,
        conversation_id: Optional[str] = None,
        max_idle_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a new conversation or get existing one.

        Args:
            channel: Communication channel
            contact_identifier: Contact identifier
            conversation_id: Specific conversation ID (optional)
            max_idle_seconds: If set, treat an existing conversation as stale
                and create a new one when the last message is older than this
                many seconds.  Useful for channels without an explicit
                "new chat" action (e.g. WhatsApp).

        Returns:
            Conversation dictionary
        """
        # If conversation_id provided, try to get it
        if conversation_id:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if conversation:
                # Update last accessed
                self.conversation_repo.update_last_accessed(conversation_id)
                return conversation

        # If contact_identifier provided, try to get recent conversation
        if contact_identifier:
            conversation = self.conversation_repo.get_by_contact(channel, contact_identifier)
            if conversation:
                # Check if the conversation has gone idle beyond the threshold
                if max_idle_seconds is not None and self._is_conversation_stale(
                    conversation["conversation_id"], max_idle_seconds
                ):
                    logger.info(
                        f"Conversation {conversation['conversation_id']} is stale "
                        f"(idle >{max_idle_seconds}s), starting new conversation "
                        f"for {channel}/{contact_identifier}"
                    )
                else:
                    # Conversation is still active — reuse it
                    self.conversation_repo.update_last_accessed(conversation["conversation_id"])
                    return conversation

        # Create new conversation
        new_id = conversation_id or str(uuid4())
        conversation = self.conversation_repo.create(
            conversation_id=new_id, channel=channel, contact_identifier=contact_identifier
        )

        logger.info(f"Created new conversation: {new_id}")
        return conversation

    def _is_conversation_stale(self, conversation_id: str, max_idle_seconds: int) -> bool:
        """
        Check whether a conversation's last message is older than the given
        idle threshold.

        Returns True if the conversation should be considered stale (i.e. a
        new conversation should be started).
        """
        recent = self.message_repo.get_recent_messages(conversation_id, count=1)
        if not recent:
            # No messages yet — conversation is empty, reuse it
            return False

        last_msg_time = datetime.fromisoformat(recent[0]["timestamp"])
        idle_seconds = (datetime.utcnow() - last_msg_time).total_seconds()
        logger.debug(
            f"Conversation {conversation_id} idle for {idle_seconds:.0f}s "
            f"(threshold: {max_idle_seconds}s)"
        )
        return idle_seconds > max_idle_seconds

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a message to a conversation.

        Args:
            conversation_id: Conversation ID
            role: Message role (user, assistant, system)
            content: Message content
            model: Model name for token counting
            metadata: Additional metadata

        Returns:
            Created message dictionary
        """
        # Count tokens
        token_count = count_tokens(content, model)

        # Create message
        message = self.message_repo.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
            token_count=token_count,
        )

        # Update conversation last accessed
        self.conversation_repo.update_last_accessed(conversation_id)

        # Check if summarization is needed
        if self.memory_service.should_summarize(conversation_id):
            logger.info(f"Conversation {conversation_id} ready for summarization")
            # Note: Actual summarization can be triggered separately or in background

        return message

    def get_conversation_history(
        self, conversation_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get conversation message history.

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages
            offset: Pagination offset

        Returns:
            List of message dictionaries
        """
        return self.message_repo.get_by_conversation(conversation_id, limit=limit, offset=offset)

    def list_conversations(
        self, channel: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> Dict[str, Any]:
        """
        List conversations with pagination.

        Args:
            channel: Filter by channel (optional)
            limit: Number of conversations per page
            offset: Pagination offset

        Returns:
            Dictionary with conversations and pagination info
        """
        conversations = self.conversation_repo.list_conversations(
            channel=channel, limit=limit, offset=offset
        )

        # Enrich with message counts and previews
        for conv in conversations:
            conv_id = conv["conversation_id"]

            # Get message count
            conv["message_count"] = self.message_repo.count_messages(conv_id)

            # Get last message preview
            recent = self.message_repo.get_recent_messages(conv_id, count=1)
            if recent:
                conv["last_message_preview"] = recent[0]["content"][:100]
            else:
                conv["last_message_preview"] = None

        total = self.conversation_repo.count_conversations(channel)

        return {
            "conversations": conversations,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }

    def get_conversation_stats(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get statistics for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Dictionary with conversation statistics
        """
        conversation = self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            return {}

        message_count = self.message_repo.count_messages(conversation_id)
        total_tokens = self.message_repo.sum_token_count(conversation_id)

        # Count by role
        user_count = self.message_repo.count_messages(conversation_id, role="user")
        assistant_count = self.message_repo.count_messages(conversation_id, role="assistant")

        return {
            "conversation_id": conversation_id,
            "channel": conversation["channel"],
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"],
            "message_count": message_count,
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "total_tokens": total_tokens,
            "context_version": conversation.get("context_version", 1),
        }

    def delete_conversation(self, conversation_id: str, delete_messages: bool = True) -> bool:
        """
        Delete a conversation.

        Args:
            conversation_id: Conversation ID
            delete_messages: Whether to also delete messages (cascade)

        Returns:
            True if deleted successfully
        """
        # Note: Database has CASCADE configured, so messages will be deleted
        # automatically when conversation is deleted

        success = self.conversation_repo.delete_conversation(conversation_id)

        if success:
            logger.info(f"Deleted conversation: {conversation_id}")

        return success

    def search_conversations(
        self,
        query: Optional[str] = None,
        date_filter: str = "all",
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Search conversations with optional query and date filtering.

        Args:
            query: Search query for message content (optional)
            date_filter: Date filter (all, today, week, month, older)
            limit: Number of conversations per page
            offset: Pagination offset

        Returns:
            Dictionary with conversations and pagination info
        """
        # Get conversations with date filtering
        now = datetime.utcnow()
        date_threshold = None

        if date_filter == "today":
            date_threshold = (now - timedelta(days=1)).isoformat()
        elif date_filter == "week":
            date_threshold = (now - timedelta(days=7)).isoformat()
        elif date_filter == "month":
            date_threshold = (now - timedelta(days=30)).isoformat()
        elif date_filter == "older":
            # Older than 30 days - we'll filter after fetching
            date_threshold = (now - timedelta(days=30)).isoformat()

        # If query provided, search messages first
        matching_conversation_ids = None
        if query and query.strip():
            matching_conversation_ids = self.message_repo.search_messages(query.strip())
            if not matching_conversation_ids:
                # No matches found
                return {
                    "conversations": [],
                    "total": 0,
                    "limit": limit,
                    "offset": offset,
                    "has_more": False,
                }

        # Get all conversations (we'll filter in memory for complex logic)
        all_conversations = self.conversation_repo.list_conversations(
            channel=None, limit=1000, offset=0  # Get enough to filter
        )

        # Filter by search results
        if matching_conversation_ids:
            all_conversations = [
                conv
                for conv in all_conversations
                if conv["conversation_id"] in matching_conversation_ids
            ]

        # Filter by date
        if date_threshold:
            if date_filter == "older":
                # Older than threshold
                all_conversations = [
                    conv for conv in all_conversations if conv["updated_at"] < date_threshold
                ]
            else:
                # Newer than threshold
                all_conversations = [
                    conv for conv in all_conversations if conv["updated_at"] >= date_threshold
                ]

        # Sort: pinned first, then by updated_at DESC
        def sort_key(conv):
            metadata = conv.get("metadata", {})
            if metadata is None:
                metadata = {}
            elif isinstance(metadata, str):
                import json

                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            is_pinned = metadata.get("pinned", False)
            return (not is_pinned, conv["updated_at"])

        all_conversations.sort(key=sort_key, reverse=True)

        # Paginate
        total = len(all_conversations)
        conversations = all_conversations[offset : offset + limit]

        # Enrich with message counts, previews, and titles
        for conv in conversations:
            conv_id = conv["conversation_id"]

            # Get message count
            conv["message_count"] = self.message_repo.count_messages(conv_id)

            # Get last message preview (last assistant message)
            recent = self.message_repo.get_recent_messages(conv_id, count=5)
            last_assistant_msg = None
            for msg in reversed(recent):
                if msg["role"] == "assistant":
                    last_assistant_msg = msg
                    break

            if last_assistant_msg:
                conv["last_message_preview"] = last_assistant_msg["content"][:40]
            else:
                conv["last_message_preview"] = None

            # Get title from metadata or generate fallback
            metadata = conv.get("metadata", {})
            if metadata is None:
                metadata = {}
            elif isinstance(metadata, str):
                import json

                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}

            conv["title"] = metadata.get("title")
            if not conv["title"] and recent:
                # Fallback to first user message
                for msg in recent:
                    if msg["role"] == "user":
                        conv["title"] = msg["content"][:50]
                        break

            # Add pinned status
            conv["pinned"] = metadata.get("pinned", False)

        return {
            "conversations": conversations,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }

    def toggle_pin_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Toggle pin status for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Updated conversation dictionary or None if not found
        """
        conversation = self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            return None

        # Get current metadata
        metadata = conversation.get("metadata", {})
        if metadata is None:
            metadata = {}
        elif isinstance(metadata, str):
            import json

            try:
                metadata = json.loads(metadata) if metadata else {}
            except:
                metadata = {}

        # Toggle pinned status
        current_pinned = metadata.get("pinned", False)
        metadata["pinned"] = not current_pinned

        # Update metadata
        success = self.conversation_repo.update_metadata(conversation_id, metadata)

        if success:
            logger.info(f"Toggled pin for conversation {conversation_id}: {not current_pinned}")
            return self.conversation_repo.get_by_id(conversation_id)

        return None

    def generate_conversation_title(self, conversation_id: str, llm_client=None) -> Optional[str]:
        """
        Generate a concise title for a conversation using LLM.

        Args:
            conversation_id: Conversation ID
            llm_client: LLM client for title generation (optional)

        Returns:
            Generated title string or None if failed
        """
        # Get first few messages
        messages = self.message_repo.get_by_conversation(conversation_id, limit=5, offset=0)

        if not messages:
            return None

        # Build context from first messages
        context_parts = []
        for msg in messages[:5]:
            role = msg["role"]
            content = msg["content"][:200]  # Limit length
            context_parts.append(f"{role}: {content}")

        context = "\n".join(context_parts)

        # Generate title using LLM (if client provided)
        if llm_client:
            try:
                prompt = f"""Generate a concise, descriptive title (5-10 words) for this conversation:

{context}

Title:"""
                # Note: This would need actual LLM integration
                # For now, return a fallback
                title = None
            except Exception as e:
                logger.error(f"Failed to generate title: {e}")
                title = None
        else:
            title = None

        # Fallback: Use first user message
        if not title:
            for msg in messages:
                if msg["role"] == "user":
                    title = msg["content"][:50]
                    if len(msg["content"]) > 50:
                        title += "..."
                    break

        # Store title in metadata
        if title:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if conversation:
                metadata = conversation.get("metadata", {})
                if metadata is None:
                    metadata = {}
                elif isinstance(metadata, str):
                    import json

                    try:
                        metadata = json.loads(metadata) if metadata else {}
                    except:
                        metadata = {}

                metadata["title"] = title
                self.conversation_repo.update_metadata(conversation_id, metadata)

        return title
