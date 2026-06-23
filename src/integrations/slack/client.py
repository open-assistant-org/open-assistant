"""Slack client using the official Slack SDK."""

from typing import Any, Dict, List, Optional

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.utils.logger import get_logger

logger = get_logger(__name__)


class SlackClient:
    """Client for Slack operations via the Slack Web API."""

    def __init__(self, bot_token: str):
        """
        Initialize Slack client.

        Args:
            bot_token: Slack Bot User OAuth Token (xoxb-...)
        """
        self.client = WebClient(token=bot_token)
        logger.info("Slack client initialized")

    def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a Slack channel.

        Args:
            channel: Channel ID or name
            text: Message text
            thread_ts: Optional thread timestamp to reply in a thread

        Returns:
            Response dictionary with message details
        """
        try:
            logger.info(f"Sending Slack message to channel {channel}")
            kwargs: Dict[str, Any] = {"channel": channel, "text": text}
            if thread_ts:
                kwargs["thread_ts"] = thread_ts

            response = self.client.chat_postMessage(**kwargs)
            logger.info(f"Message sent successfully to {channel}")
            return {
                "ok": response["ok"],
                "channel": response["channel"],
                "ts": response["ts"],
            }
        except SlackApiError as e:
            logger.error(f"Failed to send Slack message: {e.response['error']}")
            raise

    def get_channel_info(self, channel: str) -> Dict[str, Any]:
        """
        Get information about a Slack channel.

        Args:
            channel: Channel ID

        Returns:
            Channel info dictionary
        """
        try:
            response = self.client.conversations_info(channel=channel)
            ch = response["channel"]
            return {
                "id": ch["id"],
                "name": ch.get("name", ""),
                "is_channel": ch.get("is_channel", False),
                "is_member": ch.get("is_member", False),
                "topic": ch.get("topic", {}).get("value", ""),
                "purpose": ch.get("purpose", {}).get("value", ""),
            }
        except SlackApiError as e:
            logger.error(f"Failed to get channel info: {e.response['error']}")
            raise

    def list_channels(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List channels the bot is a member of.

        Args:
            limit: Maximum number of channels to return

        Returns:
            List of channel dictionaries
        """
        try:
            response = self.client.conversations_list(
                types="public_channel,private_channel",
                limit=limit,
            )
            return [
                {
                    "id": ch["id"],
                    "name": ch.get("name", ""),
                    "is_member": ch.get("is_member", False),
                    "topic": ch.get("topic", {}).get("value", ""),
                }
                for ch in response.get("channels", [])
            ]
        except SlackApiError as e:
            logger.error(f"Failed to list channels: {e.response['error']}")
            raise

    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get information about a Slack user.

        Args:
            user_id: Slack user ID

        Returns:
            User info dictionary
        """
        try:
            response = self.client.users_info(user=user_id)
            user = response["user"]
            return {
                "id": user["id"],
                "name": user.get("name", ""),
                "real_name": user.get("real_name", ""),
                "display_name": user.get("profile", {}).get("display_name", ""),
                "is_bot": user.get("is_bot", False),
            }
        except SlackApiError as e:
            logger.error(f"Failed to get user info: {e.response['error']}")
            raise

    def test_connection(self) -> bool:
        """
        Test connection to Slack API.

        Returns:
            True if the bot token is valid and API is reachable
        """
        try:
            response = self.client.auth_test()
            logger.info(f"Slack connection test successful: bot={response.get('user', 'unknown')}")
            return response.get("ok", False)
        except SlackApiError as e:
            logger.error(f"Slack connection test failed: {e.response['error']}")
            return False
        except Exception as e:
            logger.error(f"Slack connection test failed: {e}")
            return False

    def get_bot_info(self) -> Dict[str, Any]:
        """
        Get info about the authenticated bot.

        Returns:
            Bot info dictionary
        """
        try:
            response = self.client.auth_test()
            return {
                "ok": response.get("ok", False),
                "user": response.get("user", ""),
                "user_id": response.get("user_id", ""),
                "team": response.get("team", ""),
                "team_id": response.get("team_id", ""),
            }
        except SlackApiError as e:
            logger.error(f"Failed to get bot info: {e.response['error']}")
            raise

    def download_file(self, url_private: str, expected_size: Optional[int] = None) -> bytes:
        """
        Download a file from Slack using the bot token for authentication.

        Slack file URLs (url_private / url_private_download) require a valid
        bot token in the Authorization header.

        Args:
            url_private: The url_private or url_private_download from a Slack file object
            expected_size: Optional expected file size for validation

        Returns:
            File content as bytes

        Raises:
            ValueError: If the download fails or returns unexpected content
        """
        try:
            logger.debug(f"Downloading Slack file from: {url_private}")
            response = requests.get(
                url_private,
                headers={"Authorization": f"Bearer {self.client.token}"},
                timeout=60,
            )
            response.raise_for_status()

            # Check Content-Type to detect HTML error pages
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type:
                # Slack sometimes returns HTML error pages instead of the file
                preview = response.text[:500] if response.text else "(empty)"
                logger.error(
                    f"Slack file download returned HTML instead of file. "
                    f"URL: {url_private[:80]}, Response preview: {preview}"
                )
                raise ValueError(
                    f"Slack returned an HTML page instead of the file. "
                    "This usually means the bot lacks the 'files:read' scope or the file is inaccessible. "
                    "Please verify the 'files:read' scope is added in your Slack app settings."
                )

            # Validate size if expected
            if expected_size and len(response.content) != expected_size:
                logger.warning(
                    f"Downloaded size mismatch: got {len(response.content)} bytes, "
                    f"expected {expected_size} bytes"
                )

            logger.info(
                f"Downloaded Slack file: {len(response.content)} bytes, content-type: {content_type}"
            )
            return response.content
        except requests.RequestException as e:
            logger.error(f"Failed to download Slack file from {url_private[:80]}: {e}")
            raise ValueError(f"Failed to download file from Slack: {e}") from e
