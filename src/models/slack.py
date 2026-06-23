"""Slack API request and response models."""

from typing import Optional

from pydantic import BaseModel, Field


class SlackSendMessageRequest(BaseModel):
    channel: str = Field(..., description="Channel ID to send the message to")
    message: str = Field(..., description="Message text")
    thread_ts: Optional[str] = Field(None, description="Thread timestamp for replying in a thread")


class SlackSendMessageToDefaultChannelRequest(BaseModel):
    """Request model for sending a message to the default channel configured in settings."""

    message: str = Field(..., description="Message text to send")


class SlackIncomingEvent(BaseModel):
    """Model for Slack Events API incoming payloads (URL verification and event callbacks)."""

    type: str = Field(..., description="Event type: url_verification or event_callback")
    token: Optional[str] = Field(None, description="Deprecated verification token")
    challenge: Optional[str] = Field(None, description="Challenge string for URL verification")
    team_id: Optional[str] = Field(None, description="Team ID")
    event: Optional[dict] = Field(None, description="Event payload")
    event_id: Optional[str] = Field(None, description="Unique event ID")
    event_time: Optional[int] = Field(None, description="Event timestamp")


class SlackStatusResponse(BaseModel):
    connected: bool = Field(..., description="Whether the bot is connected to Slack")
    bot_user: Optional[str] = Field(None, description="Bot username")
    team: Optional[str] = Field(None, description="Team/workspace name")
