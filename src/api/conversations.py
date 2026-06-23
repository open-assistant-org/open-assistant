"""Conversations API for managing conversation history."""

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import (
    get_conversation_repo,
    get_db_manager,
    get_memory_repo,
    get_message_repo,
    get_prompts_repo,
    get_settings_repo,
)
from src.core.database import DatabaseManager
from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.memory import MemoryRepository
from src.core.repositories.message import MessageRepository
from src.core.repositories.prompts import PromptsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.conversation import (
    ConversationListResponse,
    ConversationResponse,
    ConversationStatsResponse,
    MessageListResponse,
    MessageResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from src.services.conversation import ConversationService
from src.services.memory import MemoryService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/search", response_model=ConversationListResponse)
async def search_conversations(
    q: str = "",
    date_filter: str = "all",
    limit: int = 20,
    offset: int = 0,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> ConversationListResponse:
    """
    Search conversations with optional query and date filtering.

    Args:
        q: Search query for message content (optional)
        date_filter: Date filter (all, today, week, month, older)
        limit: Page size (default: 20)
        offset: Page offset (default: 0)
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)

    Returns:
        ConversationListResponse with filtered conversations
    """
    memory_service = MemoryService(
        message_repo, memory_repo, conversation_repo, prompts_repo, settings_repo, db_manager
    )
    conversation_service = ConversationService(conversation_repo, message_repo, memory_service)

    result = conversation_service.search_conversations(
        query=q if q else None, date_filter=date_filter, limit=limit, offset=offset
    )

    conversations = [ConversationResponse(**conv) for conv in result["conversations"]]

    return ConversationListResponse(
        conversations=conversations,
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
        has_more=result["has_more"],
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    channel: str = None,
    limit: int = 20,
    offset: int = 0,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> ConversationListResponse:
    """
    List conversations with pagination.

    Args:
        channel: Filter by channel (optional)
        limit: Page size (default: 20)
        offset: Page offset (default: 0)
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)

    Returns:
        ConversationListResponse with paginated conversations
    """
    memory_service = MemoryService(
        message_repo, memory_repo, conversation_repo, prompts_repo, settings_repo, db_manager
    )
    conversation_service = ConversationService(conversation_repo, message_repo, memory_service)

    result = conversation_service.list_conversations(channel=channel, limit=limit, offset=offset)

    conversations = [ConversationResponse(**conv) for conv in result["conversations"]]

    return ConversationListResponse(
        conversations=conversations,
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
        has_more=result["has_more"],
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
) -> ConversationResponse:
    """
    Get conversation details.

    Args:
        conversation_id: Conversation ID
        conversation_repo: Conversation repository (injected)

    Returns:
        ConversationResponse with conversation details

    Raises:
        HTTPException: If conversation not found
    """
    conversation = conversation_repo.get_by_id(conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(**conversation)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    message_repo: MessageRepository = Depends(get_message_repo),
) -> MessageListResponse:
    """
    Get messages for a conversation.

    Args:
        conversation_id: Conversation ID
        limit: Page size (default: 50)
        offset: Page offset (default: 0)
        message_repo: Message repository (injected)

    Returns:
        MessageListResponse with paginated messages
    """
    messages = message_repo.get_by_conversation(conversation_id, limit=limit, offset=offset)

    total = message_repo.count_messages(conversation_id)
    has_more = (offset + limit) < total

    message_responses = [MessageResponse(**msg) for msg in messages]

    return MessageListResponse(
        messages=message_responses,
        conversation_id=conversation_id,
        total=total,
        has_more=has_more,
    )


@router.get("/{conversation_id}/stats", response_model=ConversationStatsResponse)
async def get_conversation_stats(
    conversation_id: str,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> ConversationStatsResponse:
    """
    Get conversation statistics.

    Args:
        conversation_id: Conversation ID
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)

    Returns:
        ConversationStatsResponse with statistics

    Raises:
        HTTPException: If conversation not found
    """
    memory_service = MemoryService(
        message_repo, memory_repo, conversation_repo, prompts_repo, settings_repo, db_manager
    )
    conversation_service = ConversationService(conversation_repo, message_repo, memory_service)

    stats = conversation_service.get_conversation_stats(conversation_id)

    if not stats:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationStatsResponse(**stats)


@router.post("/{conversation_id}/summarize", response_model=SummarizeResponse)
async def summarize_conversation(
    conversation_id: str,
    request: SummarizeRequest,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> SummarizeResponse:
    """
    Trigger conversation summarization.

    Args:
        conversation_id: Conversation ID
        request: Summarization request with parameters
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)

    Returns:
        SummarizeResponse with summary and statistics

    Raises:
        HTTPException: If summarization fails
    """
    try:
        memory_service = MemoryService(
            message_repo, memory_repo, conversation_repo, prompts_repo, settings_repo, db_manager
        )

        # Get message count before summarization
        message_count_before = message_repo.count_messages(conversation_id)

        # Perform summarization
        summary = memory_service.summarize_old_messages(
            conversation_id=conversation_id,
            max_messages=request.max_messages,
        )

        if not summary:
            raise HTTPException(
                status_code=400,
                detail="No messages to summarize or summarization failed",
            )

        # Get message count after
        message_count_after = message_repo.count_messages(conversation_id)
        messages_summarized = message_count_before - message_count_after

        return SummarizeResponse(
            summary=summary,
            messages_summarized=messages_summarized,
            tokens_saved=None,  # Could calculate if needed
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summarization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> dict:
    """
    Delete a conversation and its messages.

    Args:
        conversation_id: Conversation ID
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)

    Returns:
        Success message

    Raises:
        HTTPException: If conversation not found
    """
    memory_service = MemoryService(
        message_repo, memory_repo, conversation_repo, prompts_repo, settings_repo, db_manager
    )
    conversation_service = ConversationService(conversation_repo, message_repo, memory_service)

    success = conversation_service.delete_conversation(conversation_id)

    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"message": "Conversation deleted successfully"}


@router.post("/{conversation_id}/pin")
async def toggle_pin_conversation(
    conversation_id: str,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> ConversationResponse:
    """
    Toggle pin status for a conversation.

    Args:
        conversation_id: Conversation ID
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)

    Returns:
        Updated conversation

    Raises:
        HTTPException: If conversation not found
    """
    memory_service = MemoryService(
        message_repo, memory_repo, conversation_repo, prompts_repo, settings_repo, db_manager
    )
    conversation_service = ConversationService(conversation_repo, message_repo, memory_service)

    updated = conversation_service.toggle_pin_conversation(conversation_id)

    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(**updated)


@router.post("/{conversation_id}/generate-title")
async def generate_conversation_title(
    conversation_id: str,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> dict:
    """
    Generate a title for a conversation.

    Args:
        conversation_id: Conversation ID
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)

    Returns:
        Dictionary with generated title

    Raises:
        HTTPException: If conversation not found or title generation fails
    """
    memory_service = MemoryService(
        message_repo, memory_repo, conversation_repo, prompts_repo, settings_repo, db_manager
    )
    conversation_service = ConversationService(conversation_repo, message_repo, memory_service)

    # Check if conversation exists
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    title = conversation_service.generate_conversation_title(conversation_id)

    if not title:
        raise HTTPException(status_code=400, detail="Could not generate title (no messages found)")

    return {"title": title}
