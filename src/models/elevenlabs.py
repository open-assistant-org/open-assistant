"""Request/response models for the ElevenLabs voice channel."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AskAssistantRequest(BaseModel):
    """Body of the ``ask_assistant`` client tool."""

    request: str = Field(..., min_length=1, description="Self-contained request to hand over")
    conversation_id: str = Field(
        ..., min_length=1, description="ElevenLabs conversation id of the running call"
    )


class CheckResultRequest(BaseModel):
    """Body of the ``check_assistant_result`` client tool."""

    job_id: str = Field(..., min_length=1)


class EndCallRequest(BaseModel):
    conversation_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,128}$")


class ToolResponse(BaseModel):
    """What the voice agent receives back from a tool call."""

    status: Literal["done", "working", "error"]
    answer: Optional[str] = None
    question: Optional[str] = Field(
        default=None, description="Set when the assistant needs input from the caller"
    )
    job_id: Optional[str] = None
    note: Optional[str] = None


class StatusResponse(BaseModel):
    enabled: bool
    configured: bool


class SessionResponse(BaseModel):
    signed_url: str
