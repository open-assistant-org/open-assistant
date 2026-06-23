"""Pydantic models for conversation and message operations."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Message model."""

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")


class MessageResponse(BaseModel):
    """Message response model."""

    message_id: str = Field(..., description="Message ID")
    conversation_id: str = Field(..., description="Conversation ID")
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(..., description="ISO timestamp")
    token_count: int = Field(..., description="Token count")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID (auto-generated if not provided)"
    )
    channel: str = Field(default="webui", description="Communication channel")
    contact_identifier: Optional[str] = Field(
        None, description="Contact identifier (email, phone, etc.)"
    )
    conversation_history: Optional[List[Message]] = Field(
        None, description="DEPRECATED: Conversation history (loaded from DB)"
    )


class PendingInput(BaseModel):
    """Describes a question the assistant needs answered before continuing."""

    question: str = Field(..., description="The question for the user")
    options: Optional[List[str]] = Field(None, description="Suggested answer choices")
    context: Optional[str] = Field(None, description="Why the assistant is asking")


class ChatResponse(BaseModel):
    """Chat response model."""

    response: str = Field(..., description="Assistant response")
    conversation_id: str = Field(..., description="Conversation ID")
    message_id: Optional[str] = Field(None, description="Message ID of the response")
    token_usage: Dict[str, int] = Field(..., description="Token usage statistics")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata (task_id, type, etc.)"
    )
    pending_input: Optional[PendingInput] = Field(
        None,
        description=(
            "Present when the assistant has paused execution to ask the user "
            "a question. The client should display the question and send the "
            "user's answer as the next message in the same conversation."
        ),
    )


class ConversationResponse(BaseModel):
    """Conversation response model."""

    conversation_id: str = Field(..., description="Conversation ID")
    channel: str = Field(..., description="Communication channel")
    contact_identifier: Optional[str] = Field(None, description="Contact identifier")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    message_count: Optional[int] = Field(None, description="Number of messages")
    last_message_preview: Optional[str] = Field(None, description="Last message preview")
    title: Optional[str] = Field(None, description="Conversation title")
    pinned: Optional[bool] = Field(None, description="Whether conversation is pinned")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ConversationListResponse(BaseModel):
    """Conversation list response model."""

    conversations: List[ConversationResponse] = Field(..., description="List of conversations")
    total: int = Field(..., description="Total conversation count")
    limit: int = Field(..., description="Page limit")
    offset: int = Field(..., description="Page offset")
    has_more: bool = Field(..., description="Whether more pages exist")


class MessageListResponse(BaseModel):
    """Message list response model."""

    messages: List[MessageResponse] = Field(..., description="List of messages")
    conversation_id: str = Field(..., description="Conversation ID")
    total: int = Field(..., description="Total message count")
    has_more: bool = Field(..., description="Whether more messages exist")


class SummarizeRequest(BaseModel):
    """Summarization request model."""

    max_messages: int = Field(default=50, description="Maximum number of messages to summarize")


class SummarizeResponse(BaseModel):
    """Summarization response model."""

    summary: str = Field(..., description="Generated summary")
    messages_summarized: int = Field(..., description="Number of messages summarized")
    tokens_saved: Optional[int] = Field(None, description="Estimated tokens saved")


class ConversationStatsResponse(BaseModel):
    """Conversation statistics response model."""

    conversation_id: str = Field(..., description="Conversation ID")
    channel: str = Field(..., description="Communication channel")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    message_count: int = Field(..., description="Total message count")
    user_messages: int = Field(..., description="User message count")
    assistant_messages: int = Field(..., description="Assistant message count")
    total_tokens: int = Field(..., description="Total token count")
    context_version: int = Field(..., description="Context version number")
