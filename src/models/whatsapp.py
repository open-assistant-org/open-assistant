"""WhatsApp API request and response models."""

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    phone_number: str = Field(..., description="Recipient phone number with country code")
    message: str = Field(..., description="Message text")


class WebhookConfigRequest(BaseModel):
    webhook_url: str = Field(..., description="Webhook URL for incoming messages")


class NotifyOwnerRequest(BaseModel):
    """Request model for notifying the owner via WhatsApp or Slack."""

    message: str = Field(..., description="Message text to send to the owner")
    channel: Literal["whatsapp", "slack"] = Field(
        default="whatsapp",
        description=(
            "Channel to use for the notification. "
            "'whatsapp' (default) sends via WhatsApp using the configured phone number; "
            "'slack' sends via Slack using the configured default channel."
        ),
    )


class GetStatusRequest(BaseModel):
    """Request model for getting WhatsApp connection status."""

    pass  # No parameters needed


class IncomingMessageWebhook(BaseModel):
    from_: str = Field(..., alias="from", description="Sender phone number")
    body: str = Field("", description="Message body")
    timestamp: Optional[int] = Field(None, description="Message timestamp")
    hasMedia: bool = Field(False, description="Whether message has media")
    mediaData: Optional[str] = Field(None, description="Base64-encoded media data")
    mimetype: Optional[str] = Field(
        None, description="Media MIME type (e.g. audio/ogg, image/jpeg)"
    )
    filename: Optional[str] = Field(None, description="Original media filename")

    class Config:
        populate_by_name = True


class WhatsAppStatusResponse(BaseModel):
    ready: bool = Field(..., description="Whether WhatsApp is ready")
    has_qr: bool = Field(..., description="Whether QR code is available")
    qr_code: Optional[str] = Field(None, description="QR code for authentication")


class WhatsAppConnectionTestResponse(BaseModel):
    service_name: str = Field(..., description="Service name")
    status: str = Field(..., description="Status")
    message: str = Field(..., description="Message")
