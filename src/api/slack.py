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
from src.integrations.slack.participants import Action, format_with_speaker, route_message_event
from src.models.slack import *
from src.services.message_handler import MessageHandler
from src.utils.settings import settings_truthy
from src.services.settings import SettingsService
from src.services.slack import SlackService
from src.services.whatsapp_media import MediaHandler
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/slack", tags=["slack"])

# Conversation idle timeout for Slack (5 hours)
SLACK_NEW_CHAT_IDLE_SECONDS = 5 * 60 * 60

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

    user_id = event.get("user", "")
    channel_id = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts", "")
    files = _extract_slack_files(event)

    # Resolve the thread scope once, up front, so the reply target, the
    # progress-notification target and the conversation identity can never
    # disagree — and so the error handler below can still reply in-thread.
    #
    # With "Reply in Thread" on, each Slack thread is its own conversation: the
    # contact identifier carries the thread_ts, so context stays inside the
    # thread instead of being shared channel-wide.  With it off the identifier
    # stays the bare channel_id, preserving the existing channel-wide
    # conversation behaviour. "Reply Only on Mention" + "Ingest All Thread
    # Messages" also needs thread scoping, since it records non-mention
    # messages under the same identity the eventual @mention reply will use.
    thread_replies = settings_truthy(settings_service.get_setting("slack.thread_replies"))
    mention_only = settings_truthy(settings_service.get_setting("slack.mention_only"))
    thread_ingest_all = mention_only and settings_truthy(
        settings_service.get_setting("slack.thread_ingest_all_messages")
    )
    reply_to_bots = mention_only and settings_truthy(
        settings_service.get_setting("slack.reply_to_bots")
    )
    use_thread_scope = thread_replies or thread_ingest_all
    reply_thread_ts = thread_ts if (use_thread_scope and thread_ts) else None
    contact_identifier = f"{channel_id}:{reply_thread_ts}" if reply_thread_ts else channel_id

    own_ids = (
        slack_service.get_own_ids()
        if (mention_only or event.get("bot_id"))
        else {"user_id": None, "bot_id": None}
    )

    route = route_message_event(
        event,
        has_files=bool(files),
        own_user_id=own_ids.get("user_id"),
        own_bot_id=own_ids.get("bot_id"),
        mention_only=mention_only,
        ingest_all=thread_ingest_all,
        reply_to_bots=reply_to_bots,
        thread_scoped=bool(reply_thread_ts),
        conversation_key=contact_identifier,
        is_user_allowed=slack_service.is_user_allowed,
        is_bot_allowed=slack_service.is_bot_allowed,
    )
    sender = route.sender
    if route.action == Action.IGNORE:
        logger.debug(f"Slack message ignored: {route.reason}")
        return {"ok": True}
    if sender:
        user_id = sender.id

    logger.info(
        f"Received Slack message from {user_id} in {channel_id} ({route.action.value}): "
        f"{(event.get('text') or '(no text)')[:100]}"
        f"{f' [{len(files)} file(s)]' if files else ''}"
    )

    # In shared threads, label who is speaking so the model can tell
    # participants apart; ids are included when it may @mention them back.
    def _label(body: str) -> str:
        if not (sender and (sender.is_bot or thread_ingest_all) and body.strip()):
            return body
        return format_with_speaker(body, sender, slack_service.get_user_display_info, reply_to_bots)

    if route.action == Action.INGEST:
        background_tasks.add_task(
            message_handler.ingest_passive_message,
            message=_label(event.get("text") or ""),
            channel="slack",
            contact_identifier=contact_identifier,
            metadata={
                "source": "slack_event",
                "channel": channel_id,
                "user": user_id,
                "thread_ts": reply_thread_ts,
                "passive": True,
                "is_bot": bool(sender and sender.is_bot),
            },
            max_idle_seconds=SLACK_NEW_CHAT_IDLE_SECONDS,
        )
        return {"ok": True}

    text = _label(route.text)

    async def process_and_reply():
        try:
            # Verify LLM configuration
            api_key = settings_service.get_config_with_fallback("llm.api_key")
            if not api_key:
                logger.error("LLM API key not configured, cannot reply to Slack message")
                return

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
                contact_identifier=contact_identifier,
                max_idle_seconds=SLACK_NEW_CHAT_IDLE_SECONDS,
                metadata={
                    "source": "slack_event",
                    "channel": channel_id,
                    "user": user_id,
                    "thread_ts": reply_thread_ts,
                    "has_media": bool(files),
                },
                image_base64=image_base64,
                image_mimetype=image_mimetype,
                reply_thread_ts=reply_thread_ts,
            )

            response_text = result["response"] or ""

            # If a document was processed, append the note URL
            if note_url:
                response_text += f"\n\nDocument saved: {note_url}"

            if not response_text.strip():
                response_text = (
                    "I processed your message but couldn't generate a response. Please try again."
                )

            # Send reply (in-thread if configured)
            slack_service.send_message(
                channel=channel_id,
                message=response_text,
                thread_ts=reply_thread_ts,
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
                    thread_ts=reply_thread_ts,
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")

    background_tasks.add_task(process_and_reply)

    return {"ok": True, "message": "Message received, processing in background"}
