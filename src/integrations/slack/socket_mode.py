"""Slack Socket Mode handler for real-time event processing without public endpoints."""

import asyncio
import base64
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from src.utils.logger import get_logger

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

        # Only handle actual user messages
        # Allow messages with no subtype (normal text) or file_share subtype (file uploads)
        if event_type != "message":
            logger.debug(f"[Slack Socket Mode] Ignoring non-message event: {event_type}")
            return

        if event_subtype is not None and event_subtype != "file_share":
            logger.debug(f"[Slack Socket Mode] Ignoring message with subtype: {event_subtype}")
            return

        # Ignore messages from bots (including ourselves)
        if event.get("bot_id"):
            logger.debug(f"[Slack Socket Mode] Ignoring bot message: bot_id={event.get('bot_id')}")
            return

        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        text = event.get("text", "")
        files = _extract_slack_files(event)

        logger.info(
            f"[Slack Socket Mode] Message received: user_id={user_id}, channel={channel_id}, "
            f"text='{text[:100] if text else ''}...'"
            f"{f', files={len(files)}' if files else ''}"
        )

        # Skip if there's no text and no files
        if (not text or not text.strip()) and not files:
            logger.debug("[Slack Socket Mode] Ignoring empty message with no files")
            return

        # Check if user is allowed
        if not self.slack_service.is_user_allowed(user_id):
            logger.warning(
                f"[Slack Socket Mode] User {user_id} NOT in allowed list - ignoring message. "
                f"Configure slack.allowed_user_ids to allow this user."
            )
            return

        logger.info(f"[Slack Socket Mode] User {user_id} is allowed - processing message")

        # Process message in background using the main event loop
        if self.event_loop is None:
            logger.error(
                "[Slack Socket Mode] No event loop provided - cannot process message. "
                "This is a bug - the event_loop should have been passed during initialization."
            )
            return

        if self.event_loop.is_closed():
            logger.error("[Slack Socket Mode] Event loop is closed - cannot process message")
            return

        logger.debug(f"[Slack Socket Mode] Submitting coroutine to event loop: {self.event_loop}")

        asyncio.run_coroutine_threadsafe(
            self._process_and_reply(channel_id, user_id, text, files),
            self.event_loop,
        )

    async def _process_and_reply(
        self,
        channel_id: str,
        user_id: str,
        text: str,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Process the message and send a reply."""
        logger.info(f"[Slack Socket Mode] Processing message from {user_id} in {channel_id}")

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
                contact_identifier=channel_id,
                max_idle_seconds=SLACK_NEW_CHAT_IDLE_SECONDS,
                metadata={
                    "source": "slack_socket_mode",
                    "channel": channel_id,
                    "user": user_id,
                    "has_media": bool(files),
                },
                image_base64=image_base64,
                image_mimetype=image_mimetype,
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

            # Send reply directly to channel
            self.slack_service.send_message(
                channel=channel_id,
                message=response_text,
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
                )
            except Exception as send_error:
                logger.error(f"[Slack Socket Mode] Failed to send error message: {send_error}")
