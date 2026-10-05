"""Request/response models for the ElevenLabs voice agent channel."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AskAssistantRequest(BaseModel):
    """Body of the ``ask_assistant`` server tool."""

    request: str = Field(..., min_length=1, description="Self-contained request to hand over")
    conversation_id: str = Field(
        ..., min_length=1, description="ElevenLabs conversation id ({{system__conversation_id}})"
    )


class CheckResultRequest(BaseModel):
    """Body of the ``check_assistant_result`` server tool."""

    job_id: str = Field(..., min_length=1)


class ToolResponse(BaseModel):
    """What the voice agent receives back from a tool call."""

    status: Literal["done", "working", "error"]
    answer: Optional[str] = None
    question: Optional[str] = Field(
        default=None, description="Set when the assistant needs input from the caller"
    )
    job_id: Optional[str] = None
    note: Optional[str] = None


class TranscriptTurn(BaseModel):
    role: str
    message: Optional[str] = None


class PostCallData(BaseModel):
    conversation_id: str
    transcript: List[TranscriptTurn] = Field(default_factory=list)


class PostCallPayload(BaseModel):
    """ElevenLabs post-call webhook payload (only the fields we use)."""

    type: str
    data: Optional[PostCallData] = None
    model_config = {"extra": "allow"}


WebhookAck = Dict[str, Any]
