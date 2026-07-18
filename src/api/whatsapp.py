"""WhatsApp API endpoints with skills-based message handling."""

from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from src.core.dependencies import (
    get_credentials_repo,
    get_message_handler,
    get_settings_repo,
    get_settings_service,
    get_whatsapp_media_handler,
    get_whatsapp_service as _get_whatsapp_service,
)
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.core.tools.definitions import initialize_all_tools
from src.models.whatsapp import *
from src.services.message_handler import MessageHandler
from src.services.settings import SettingsService
from src.services.whatsapp import WhatsAppService
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# Ensure tools are registered
initialize_all_tools()


def get_whatsapp_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> WhatsAppService:
    return WhatsAppService(settings_repo, credentials_repo)


@router.get("/status", response_model=WhatsAppStatusResponse)
async def get_status(
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> WhatsAppStatusResponse:
    """Get WhatsApp connection status and QR code if available."""
    try:
        status = whatsapp_service.get_status()
        return WhatsAppStatusResponse(**status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send")
async def send_message(
    request: SendMessageRequest, whatsapp_service: WhatsAppService = Depends(get_whatsapp_service)
) -> Dict[str, Any]:
    """Send WhatsApp message."""
    try:
        result = whatsapp_service.send_message(
            phone_number=request.phone_number, message=request.message
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-connection")
async def test_connection(
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> Dict[str, Any]:
    """Test WhatsApp bridge connectivity and authentication status."""
    return whatsapp_service.test_connection()


@router.post("/webhook/configure")
async def configure_webhook(
    request: WebhookConfigRequest, whatsapp_service: WhatsAppService = Depends(get_whatsapp_service)
) -> Dict[str, Any]:
    """Configure webhook for incoming messages."""
    try:
        result = whatsapp_service.configure_webhook(webhook_url=request.webhook_url)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/incoming")
async def handle_incoming_message(
    webhook: IncomingMessageWebhook,
    background_tasks: BackgroundTasks,
    message_handler: MessageHandler = Depends(get_message_handler),
    settings_service: SettingsService = Depends(get_settings_service),
    whatsapp_service: WhatsAppService = Depends(_get_whatsapp_service),
    media_handler=Depends(get_whatsapp_media_handler),
) -> Dict[str, Any]:
    """Handle incoming WhatsApp message from bridge.

    Processes the message through the MessageHandler and sends the
    reply back via WhatsApp in a background task so the webhook returns
    quickly to the bridge.
    """
    from_number = webhook.from_
    message_body = webhook.body
    has_media = webhook.hasMedia and webhook.mediaData is not None
    media_mimetype = webhook.mimetype

    logger.info(
        f"Received WhatsApp message from {from_number}: "
        f"{message_body[:100] if message_body else '(no text)'}"
        f"{' [has media: ' + (media_mimetype or 'unknown') + ']' if has_media else ''}"
    )

    # Only respond to the owner's configured phone number
    owner_number = settings_service.get_config_with_fallback("whatsapp.phone_number", "")
    if owner_number:
        # Normalise both sides: strip +, spaces, dashes, and WhatsApp suffixes (@c.us, @lid)
        normalise = (
            lambda n: n.replace("+", "")
            .replace(" ", "")
            .replace("-", "")
            .replace("@c.us", "")
            .replace("@lid", "")
        )
        normalized_from = normalise(from_number)
        normalized_owner = normalise(owner_number)
        logger.info(
            f"Phone number comparison - From: '{normalized_from}' vs Owner: '{normalized_owner}'"
        )
        if normalized_from != normalized_owner:
            logger.info(f"Ignoring message from non-owner number {from_number}")
            return {"success": True, "message": "Ignored (not owner)"}

    async def process_and_reply():
        try:
            # Verify LLM configuration
            api_key = settings_service.get_config_with_fallback("llm.api_key")
            if not api_key:
                logger.error("LLM API key not configured, cannot reply to WhatsApp message")
                return

            # Preserve the full WhatsApp ID (with @c.us or @lid suffix) for replies
            contact_id = from_number

            # -----------------------------------------------------------------
            # Media processing using modular handler
            # -----------------------------------------------------------------
            effective_message = message_body
            pdf_note_url = None
            image_base64 = None
            image_mimetype = None

            if has_media and media_mimetype:
                # Use modular media handler
                result = media_handler.process_media(
                    media_data=webhook.mediaData,
                    mimetype=media_mimetype,
                    filename=webhook.filename,
                    caption=message_body,
                    contact_id=contact_id,
                )

                # Extract results
                effective_message = result.effective_message
                pdf_note_url = result.note_url
                image_base64 = result.image_base64
                image_mimetype = result.image_mimetype

            logger.info(
                f"[WhatsApp] Processing message for contact: {contact_id}, "
                f"message length: {len(effective_message)} chars, "
                f"has_image: {image_base64 is not None}"
            )
            logger.debug(f"[WhatsApp] Effective message: {effective_message[:200]}")

            # WhatsApp has no "new chat" button, so treat a conversation as
            # new when the last message is older than 5 hours.
            WHATSAPP_NEW_CHAT_IDLE_SECONDS = 5 * 60 * 60  # 5 hours

            # Process message through MessageHandler
            result = await message_handler.handle_message(
                message=effective_message,
                conversation_id=None,  # Let it find/create based on contact
                channel="whatsapp",
                contact_identifier=contact_id,
                max_idle_seconds=WHATSAPP_NEW_CHAT_IDLE_SECONDS,
                metadata={"source": "whatsapp_webhook", "has_media": has_media},
                image_base64=image_base64,
                image_mimetype=image_mimetype,
            )

            response_text = result["response"] or ""

            # If PDF was processed, append note URL to response
            if pdf_note_url:
                if message_body:
                    # User asked a question - add note URL at the end
                    response_text += f"\n\n📄 Document saved: {pdf_note_url}"
                else:
                    # No question - prepend document info before note URL
                    response_text = (
                        f"Document processed and saved: {pdf_note_url}\n\n{response_text}"
                    )

            # Send reply back via WhatsApp (bridge rejects empty messages)
            if not response_text.strip():
                response_text = (
                    "I processed your message but couldn't generate a response. Please try again."
                )

            whatsapp_service.send_message(
                phone_number=contact_id,
                message=response_text,
            )

            logger.info(
                f"[WhatsApp] Replied to {contact_id}: "
                f"skills={result['skills_used']}, "
                f"tools={len(result['tools_executed'])}, "
                f"iterations={result['iterations']}"
            )

        except Exception as e:
            logger.error(f"Failed to process WhatsApp message: {e}", exc_info=True)
            # Try to send error message to user
            try:
                whatsapp_service.send_message(
                    phone_number=contact_id,
                    message=f"Sorry, I encountered an error processing your message: {str(e)}",
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")

    background_tasks.add_task(process_and_reply)

    return {"success": True, "message": "Message received, processing in background"}
