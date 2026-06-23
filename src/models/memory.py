"""Pydantic models for memory operations."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MemoryStoreRequest(BaseModel):
    """Memory store request model."""

    memory_type: str = Field(..., description="Memory type (short_term, long_term, facts, working)")
    content: Dict[str, Any] = Field(..., description="Memory content dictionary")


class MemoryResponse(BaseModel):
    """Memory response model."""

    id: int = Field(..., description="Memory entry ID")
    conversation_id: str = Field(..., description="Conversation ID")
    memory_type: str = Field(..., description="Memory type")
    content: Dict[str, Any] = Field(..., description="Memory content")
    created_at: str = Field(..., description="Creation timestamp")


class CompressionStatsResponse(BaseModel):
    """Compression statistics response model."""

    compressed: bool = Field(..., description="Whether compression was performed")
    original_tokens: Optional[int] = Field(None, description="Original token count")
    compressed_tokens: Optional[int] = Field(None, description="Compressed token count")
    tokens_saved: Optional[int] = Field(None, description="Tokens saved")
    messages_summarized: Optional[int] = Field(None, description="Messages summarized")
    messages_kept: Optional[int] = Field(None, description="Messages kept")
    summary_created: Optional[bool] = Field(None, description="Whether summary was created")
    reason: Optional[str] = Field(None, description="Reason if not compressed")
