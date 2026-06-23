"""Slack API endpoints with skills-based message handling."""

import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from src.core.dependencies import (
    get_credentials_repo,
    get_message_handler,
    get_settings_repo,
    get_settings_service,
    get_slack_media_handler,
    get_slack_service as _get_slack_service,
)
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.core.tools.definitions import initialize_all_tools
from src.models.slack import *
from src.services.message_handler import MessageHandler
from src.services.settings import SettingsService
from src.services.slack import SlackService
from src.services.whatsapp_media import MediaHandler
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/slack", tags=["slack"])

# Ensure tools are registered
initialize_all_tools()


def get_slack_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> SlackService:
    return SlackService(settings_repo, credentials_repo)


@router.get("/status", response_model=SlackStatusResponse)
async def get_status(
    slack_service: SlackService = Depends(get_slack_service),
) -> SlackStatusResponse:
    """Get Slack connection status."""
    try:
        status = slack_service.get_status()
        return SlackStatusResponse(**status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send")
async def send_message(
    request: SlackSendMessageRequest,
    slack_service: SlackService = Depends(get_slack_service),
) -> Dict[str, Any]:
    """Send Slack message to a channel."""
    try:
        result = slack_service.send_message(
            channel=request.channel,
            message=request.message,
            thread_ts=request.thread_ts,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-connection")
async def test_connection(
    slack_service: SlackService = Depends(get_slack_service),
) -> Dict[str, Any]:
    """Test Slack connection."""
    return slack_service.test_connection()


def _extract_slack_files(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract file metadata from a Slack event payload.

    Returns a list of file dicts with keys: id, name, mimetype, url_private.
    """
    files = event.get("files") or []
    result = []
    for f in files:
        url = f.get("url_private_download") or f.get("url_private")
        if url:
            result.append(
                {
                    "id": f.get("id", ""),
                    "name": f.get("name", "file"),
                    "mimetype": f.get("mimetype", "application/octet-stream"),
                    "url_private": url,
                    "size": f.get("size", 0),
                }
            )
    return result


def _download_and_encode_slack_file(
    slack_service: SlackService,
    file_info: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    """Download a Slack file and return base64-encoded data with metadata.

    Returns dict with keys: data (base64), mimetype, filename, or None on failure.
    """
    try:
        client = slack_service._get_client()
        file_bytes = client.download_file(
            file_info["url_private"],
            expected_size=file_info.get("size"),
        )
        return {
            "data": base64.b64encode(file_bytes).decode("utf-8"),
            "mimetype": file_info["mimetype"],
            "filename": file_info["name"],
        }
    except Exception as e:
        logger.error(f"[Slack] Failed to download file {file_info.get('name')}: {e}")
        return None


@router.post("/webhook/events")
async def handle_slack_event(
    request: Request,
    background_tasks: BackgroundTasks,
    message_handler: MessageHandler = Depends(get_message_handler),
    settings_service: SettingsService = Depends(get_settings_service),
    slack_service: SlackService = Depends(_get_slack_service),
    media_handler: MediaHandler = Depends(get_slack_media_handler),
) -> Dict[str, Any]:
    """Handle incoming Slack Events API requests.

    Supports URL verification (challenge) and message events.
    Processes user messages (including file uploads) through the MessageHandler
    and replies in the channel.
    """
    body = await request.json()

    # Handle Slack URL verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    event = body.get("event", {})
    event_type = event.get("type")
    event_subtype = event.get("subtype")

    # Only handle actual user messages
    # Allow messages with no subtype (normal text) or with file_share subtype (file uploads)
    if event_type != "message":
        return {"ok": True}
    if event_subtype is not None and event_subtype != "file_share":
        return {"ok": True}

    # Ignore messages from bots (including ourselves)
    if event.get("bot_id"):
        return {"ok": True}

    user_id = event.get("user", "")
    channel_id = event.get("channel", "")
    text = event.get("text", "")
    thread_ts = event.get("thread_ts") or event.get("ts", "")
    files = _extract_slack_files(event)

    # Skip if there's no text and no files
    if not text.strip() and not files:
        return {"ok": True}

    logger.info(
        f"Received Slack message from {user_id} in {channel_id}: "
        f"{text[:100] if text else '(no text)'}"
        f"{f' [{len(files)} file(s)]' if files else ''}"
    )

    # Check if user is allowed
    if not slack_service.is_user_allowed(user_id):
        logger.info(f"Ignoring message from non-allowed Slack user {user_id}")
        return {"ok": True, "message": "Ignored (not allowed)"}

    async def process_and_reply():
        try:
            # Verify LLM configuration
            api_key = settings_service.get_config_with_fallback("llm.api_key")
            if not api_key:
                logger.error("LLM API key not configured, cannot reply to Slack message")
                return

            SLACK_NEW_CHAT_IDLE_SECONDS = 5 * 60 * 60  # 5 hours

            # -----------------------------------------------------------------
            # Media processing
            # -----------------------------------------------------------------
            effective_message = text or ""
            note_url = None
            image_base64 = None
            image_mimetype = None

            if files:
                # Process the first file (consistent with WhatsApp single-file handling)
                file_info = files[0]
                logger.info(
                    f"[Slack] Downloading file: {file_info['name']} "
                    f"({file_info['mimetype']}, {file_info.get('size', '?')} bytes)"
                )

                downloaded = _download_and_encode_slack_file(slack_service, file_info)
                if downloaded:
                    result = media_handler.process_media(
                        media_data=downloaded["data"],
                        mimetype=downloaded["mimetype"],
                        filename=downloaded["filename"],
                        caption=text or None,
                        contact_id=f"{channel_id}:{user_id}",
                    )
                    effective_message = result.effective_message
                    note_url = result.note_url
                    image_base64 = result.image_base64
                    image_mimetype = result.image_mimetype

            logger.info(
                f"[Slack] Processing message for {user_id} in {channel_id}, "
                f"message length: {len(effective_message)} chars, "
                f"has_image: {image_base64 is not None}"
            )

            result = await message_handler.handle_message(
                message=effective_message,
                conversation_id=None,
                channel="slack",
                contact_identifier=channel_id,
                max_idle_seconds=SLACK_NEW_CHAT_IDLE_SECONDS,
                metadata={
                    "source": "slack_event",
                    "channel": channel_id,
                    "user": user_id,
                    "has_media": bool(files),
                },
                image_base64=image_base64,
                image_mimetype=image_mimetype,
            )

            response_text = result["response"] or ""

            # If a document was processed, append the note URL
            if note_url:
                response_text += f"\n\nDocument saved: {note_url}"

            if not response_text.strip():
                response_text = (
                    "I processed your message but couldn't generate a response. Please try again."
                )

            # Send reply
            slack_service.send_message(
                channel=channel_id,
                message=response_text,
            )

            logger.info(
                f"[Slack] Replied to {user_id} in {channel_id}: "
                f"skills={result['skills_used']}, "
                f"tools={len(result['tools_executed'])}, "
                f"iterations={result['iterations']}"
            )

        except Exception as e:
            logger.error(f"Failed to process Slack message: {e}", exc_info=True)
            try:
                slack_service.send_message(
                    channel=channel_id,
                    message=f"Sorry, I encountered an error processing your message: {str(e)}",
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")

    background_tasks.add_task(process_and_reply)

    return {"ok": True, "message": "Message received, processing in background"}
