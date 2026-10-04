"""Slack Socket Mode handler for real-time event processing without public endpoints."""

import asyncio
import base64
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from src.integrations.slack.participants import (
    Action,
    SlackSender,
    format_with_speaker,
    route_message_event,
)
from src.utils.logger import get_logger
from src.utils.settings import settings_truthy

if TYPE_CHECKING:
    from src.services.message_handler import MessageHandler
    from src.services.settings import SettingsService
    from src.services.slack import SlackService
    from src.services.whatsapp_media import MediaHandler

logger = get_logger(__name__)

# Conversation idle timeout for Slack (5 hours)
SLACK_NEW_CHAT_IDLE_SECONDS = 5 * 60 * 60


def _extract_slack_files(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract file metadata from a Slack event payload."""
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


class SlackSocketModeHandler:
    """
    Handles Slack events via Socket Mode.

    Socket Mode establishes an outbound WebSocket connection to Slack's servers,
    allowing the app to receive events without a public HTTP endpoint.
    This is ideal for:
    - Closed networks with no inbound access
    - Development environments
    - Behind-firewall deployments
    """

    def __init__(
        self,
        app_token: str,
        bot_token: str,
        message_handler: "MessageHandler",
        slack_service: "SlackService",
        settings_service: "SettingsService",
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
        media_handler: Optional["MediaHandler"] = None,
    ):
        """
        Initialize Socket Mode handler.

        Args:
            app_token: Slack App-Level Token (xapp-...) for WebSocket connection
            bot_token: Slack Bot Token (xoxb-...) for Web API calls
            message_handler: MessageHandler for processing messages
            slack_service: SlackService for sending replies
            settings_service: SettingsService for configuration
            event_loop: The asyncio event loop from the main thread (required for async processing)
            media_handler: MediaHandler for processing file attachments
        """
        self.app_token = app_token
        self.bot_token = bot_token
        self.message_handler = message_handler
        self.slack_service = slack_service
        self.settings_service = settings_service
        self.event_loop = event_loop
        self.media_handler = media_handler

        # Initialize the Socket Mode client with a WebClient for API calls
        self.client = SocketModeClient(
            app_token=app_token,
            web_client=WebClient(token=bot_token),
        )

        # Register event listener
        self.client.socket_mode_request_listeners.append(self._handle_request)

        # Thread for running the client
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._bot_user_id: Optional[str] = None

        logger.info(
            f"[Slack Socket Mode] Handler initialized (app_token={'configured' if app_token else 'MISSING'}, "
            f"bot_token={'configured' if bot_token else 'MISSING'}, event_loop={'provided' if event_loop else 'None'}, "
            f"media_handler={'configured' if media_handler else 'None'})"
        )

    def start(self) -> None:
        """Start the Socket Mode connection in a background thread."""
        if self._running:
            logger.warning("Socket Mode handler already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_client, daemon=True)
        self._thread.start()
        logger.info("Slack Socket Mode connection started")

    _bot_id: Optional[str] = None

    def _get_bot_user_id(self) -> Optional[str]:
        """Lazily fetch and cache the bot's Slack user ID (and bot ID) via auth.test."""
        if not self._bot_user_id:
            try:
                response = self.client.web_client.auth_test()
                self._bot_user_id = response.get("user_id") or ""
                self._bot_id = response.get("bot_id") or None
                logger.info(
                    f"[Slack Socket Mode] Bot user ID: {self._bot_user_id}, bot ID: {self._bot_id}"
                )
            except Exception as e:
                logger.warning(f"[Slack Socket Mode] Could not fetch bot user ID: {e}")
        return self._bot_user_id or None

    def _run_client(self) -> None:
        """Run the Socket Mode client (blocking)."""
        try:
            logger.info("[Slack Socket Mode] Connecting to Slack WebSocket...")
            self.client.connect()
            logger.info(
                "[Slack Socket Mode] WebSocket connected successfully - listening for events"
            )
        except Exception as e:
            logger.error(f"[Slack Socket Mode] Connection error: {e}", exc_info=True)
            self._running = False

    def close(self) -> None:
        """Close the Socket Mode connection."""
        self._running = False
        try:
            self.client.close()
            logger.info("Slack Socket Mode connection closed")
        except Exception as e:
            logger.error(f"Error closing Socket Mode connection: {e}")

    def _download_and_encode_file(self, file_info: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Download a Slack file and return base64-encoded data with metadata."""
        try:
            client = self.slack_service._get_client()
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
            logger.error(
                f"[Slack Socket Mode] Failed to download file {file_info.get('name')}: {e}"
            )
            return None

    def _handle_request(self, client: SocketModeClient, req: SocketModeRequest) -> None:
        """
        Handle incoming Socket Mode requests.

        This is called by the SocketModeClient for each incoming event.
        """
        # Log all incoming requests for debugging
        logger.debug(
            f"[Slack Socket Mode] Received request type={req.type}, envelope_id={req.envelope_id}"
        )

        # Acknowledge the request immediately
        response = SocketModeResponse(envelope_id=req.envelope_id)
        client.send_socket_mode_response(response)

        # Only process events_api type (not interactive, etc.)
        if req.type != "events_api":
            logger.debug(f"[Slack Socket Mode] Ignoring non-events_api request: {req.type}")
            return

        # Extract the event payload
        payload = req.payload
        event = payload.get("event", {})

        # Log the event type for debugging
        event_type = event.get("type", "unknown")
        event_subtype = event.get("subtype")
        logger.debug(
            f"[Slack Socket Mode] Event: type={event_type}, subtype={event_subtype}, "
            f"user={event.get('user')}, channel={event.get('channel')}, bot_id={event.get('bot_id')}"
        )

        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts", "")
        files = _extract_slack_files(event)

        mention_only = settings_truthy(self.settings_service.get_setting("slack.mention_only"))
        ingest_all = mention_only and settings_truthy(
            self.settings_service.get_setting("slack.thread_ingest_all_messages")
        )
        reply_to_bots = mention_only and settings_truthy(
            self.settings_service.get_setting("slack.reply_to_bots")
        )
        reply_thread_ts = self._resolve_thread_scope_ts(thread_ts)
        contact_identifier = f"{channel_id}:{reply_thread_ts}" if reply_thread_ts else channel_id

        bot_user_id = self._get_bot_user_id() if mention_only or event.get("bot_id") else None

        route = route_message_event(
            event,
            has_files=bool(files),
            own_user_id=bot_user_id,
            own_bot_id=self._bot_id,
            mention_only=mention_only,
            ingest_all=ingest_all,
            reply_to_bots=reply_to_bots,
            thread_scoped=bool(reply_thread_ts),
            conversation_key=contact_identifier,
            is_user_allowed=self.slack_service.is_user_allowed,
            is_bot_allowed=self.slack_service.is_bot_allowed,
        )
        sender = route.sender
        logger.info(
            f"[Slack Socket Mode] Message from {sender.id if sender else user_id}"
            f"{' (bot)' if sender and sender.is_bot else ''} in {channel_id}: "
            f"{route.action.value} ({route.reason})"
        )

        if route.action == Action.IGNORE:
            return

        if self.event_loop is None:
            logger.error(
                "[Slack Socket Mode] No event loop provided - cannot process message. "
                "This is a bug - the event_loop should have been passed during initialization."
            )
            return

        if self.event_loop.is_closed():
            logger.error("[Slack Socket Mode] Event loop is closed - cannot process message")
            return

        # In shared threads, label who is speaking so the model can tell
        # participants apart; ids are included when it may @mention them back.
        label_speakers = bool(sender and (sender.is_bot or ingest_all))

        def _label(body: str) -> str:
            if not (label_speakers and sender and body.strip()):
                return body
            return format_with_speaker(body, sender, self._lookup_user, reply_to_bots)

        if route.action == Action.INGEST:
            asyncio.run_coroutine_threadsafe(
                self._ingest_thread_message(
                    channel_id, sender.id if sender else user_id, _label(text), thread_ts, sender
                ),
                self.event_loop,
            )
            return

        logger.debug(f"[Slack Socket Mode] Submitting coroutine to event loop: {self.event_loop}")

        asyncio.run_coroutine_threadsafe(
            self._process_and_reply(
                channel_id, sender.id if sender else user_id, _label(route.text), files, thread_ts
            ),
            self.event_loop,
        )

    def _lookup_user(self, user_id: str) -> Dict[str, Any]:
        """Look up a Slack user's names (used to label thread participants)."""
        return self.slack_service.get_user_display_info(user_id)

    def _resolve_thread_scope_ts(self, thread_ts: Optional[str]) -> Optional[str]:
        """
        Resolve the thread timestamp that should scope a conversation, or
        None to keep the existing channel-wide conversation.

        A thread is scoped when "Reply in Thread" is on, or when "Reply
        Only on Mention" and "Ingest All Thread Messages" are both on —
        the latter needs thread-scoped conversations too, since it records
        non-mention messages under the same identity the eventual
        @mention reply will use.
        """
        thread_replies = settings_truthy(self.settings_service.get_setting("slack.thread_replies"))
        thread_ingest_all = settings_truthy(
            self.settings_service.get_setting("slack.mention_only")
        ) and settings_truthy(self.settings_service.get_setting("slack.thread_ingest_all_messages"))
        use_thread_scope = thread_replies or thread_ingest_all
        return thread_ts if (use_thread_scope and thread_ts) else None

    async def _ingest_thread_message(
        self,
        channel_id: str,
        user_id: str,
        text: str,
        thread_ts: str,
        sender: Optional[SlackSender] = None,
    ) -> None:
        """
        Passively record a non-mention thread message into that thread's
        conversation history, without triggering a reply.

        Lets other thread participants — including other bots/agents —
        post in the same Slack thread and have their messages available as
        context the next time this bot is @mentioned there.
        """
        if not text or not text.strip():
            return

        reply_thread_ts = self._resolve_thread_scope_ts(thread_ts)
        if not reply_thread_ts:
            return
        contact_identifier = f"{channel_id}:{reply_thread_ts}"

        try:
            await self.message_handler.ingest_passive_message(
                message=text,
                channel="slack",
                contact_identifier=contact_identifier,
                metadata={
                    "source": "slack_socket_mode",
                    "channel": channel_id,
                    "user": user_id,
                    "thread_ts": reply_thread_ts,
                    "passive": True,
                    "is_bot": bool(sender and sender.is_bot),
                },
                max_idle_seconds=SLACK_NEW_CHAT_IDLE_SECONDS,
            )
        except Exception as e:
            logger.error(f"[Slack Socket Mode] Failed to ingest thread message: {e}", exc_info=True)

    async def _process_and_reply(
        self,
        channel_id: str,
        user_id: str,
        text: str,
        files: Optional[List[Dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
    ) -> None:
        """Process the message and send a reply."""
        logger.info(f"[Slack Socket Mode] Processing message from {user_id} in {channel_id}")

        # Resolve the thread scope once, up front, so the reply target, the
        # progress-notification target and the conversation identity can never
        # disagree — and so the error handler below can still reply in-thread.
        #
        # With "Reply in Thread" on, each Slack thread is its own conversation:
        # the contact identifier carries the thread_ts, so context stays inside
        # the thread instead of being shared channel-wide.  With it off the
        # identifier stays the bare channel_id, preserving the existing
        # channel-wide conversation behaviour.
        reply_thread_ts = self._resolve_thread_scope_ts(thread_ts)
        contact_identifier = f"{channel_id}:{reply_thread_ts}" if reply_thread_ts else channel_id

        try:
            # Verify LLM configuration
            api_key = self.settings_service.get_config_with_fallback("llm.api_key")
            if not api_key:
                logger.error(
                    "[Slack Socket Mode] LLM API key not configured, cannot reply to Slack message"
                )
                return

            logger.debug("[Slack Socket Mode] LLM API key found, calling MessageHandler")

            # -----------------------------------------------------------------
            # Media processing
            # -----------------------------------------------------------------
            effective_message = text or ""
            note_url = None
            image_base64 = None
            image_mimetype = None

            if files and self.media_handler:
                # Process the first file
                file_info = files[0]
                logger.info(
                    f"[Slack Socket Mode] Downloading file: {file_info['name']} "
                    f"({file_info['mimetype']}, {file_info.get('size', '?')} bytes)"
                )

                downloaded = self._download_and_encode_file(file_info)
                if downloaded:
                    result = self.media_handler.process_media(
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
            elif files and not self.media_handler:
                logger.warning(
                    "[Slack Socket Mode] Files received but no media handler configured - ignoring files"
                )

            logger.info(
                f"[Slack Socket Mode] Processing: message_length={len(effective_message)}, "
                f"has_image={image_base64 is not None}"
            )

            # Process through MessageHandler
            result = await self.message_handler.handle_message(
                message=effective_message,
                conversation_id=None,
                channel="slack",
                contact_identifier=contact_identifier,
                max_idle_seconds=SLACK_NEW_CHAT_IDLE_SECONDS,
                metadata={
                    "source": "slack_socket_mode",
                    "channel": channel_id,
                    "user": user_id,
                    "thread_ts": reply_thread_ts,
                    "has_media": bool(files),
                },
                image_base64=image_base64,
                image_mimetype=image_mimetype,
                reply_thread_ts=reply_thread_ts,
            )

            response_text = result.get("response") or ""

            # If a document was processed, append the note URL
            if note_url:
                response_text += f"\n\nDocument saved: {note_url}"

            if not response_text.strip():
                response_text = (
                    "I processed your message but couldn't generate a response. Please try again."
                )

            logger.info(
                f"[Slack Socket Mode] Sending reply to {user_id} in {channel_id}: "
                f"{response_text[:20]}..."
            )

            # Send reply (in-thread if configured)
            self.slack_service.send_message(
                channel=channel_id,
                message=response_text,
                thread_ts=reply_thread_ts,
            )

            logger.info(
                f"[Slack Socket Mode] Replied to {user_id} in {channel_id}: "
                f"skills={result.get('skills_used', [])}, "
                f"tools={len(result.get('tools_executed', []))}, "
                f"iterations={result.get('iterations', 0)}"
            )

        except Exception as e:
            logger.error(f"[Slack Socket Mode] Failed to process message: {e}", exc_info=True)
            try:
                self.slack_service.send_message(
                    channel=channel_id,
                    message=f"Sorry, I encountered an error processing your message: {str(e)}",
                    thread_ts=reply_thread_ts,
                )
            except Exception as send_error:
                logger.error(f"[Slack Socket Mode] Failed to send error message: {send_error}")
