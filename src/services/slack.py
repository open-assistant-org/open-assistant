"""Slack service for messaging operations."""

from typing import Any, Dict, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.slack.client import SlackClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SlackService(BaseService):
    """Service for Slack integration operations."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_sensitive_setting(self, key: str) -> Optional[str]:
        """
        Get a sensitive setting value from credentials table.

        Sensitive settings (bot_token, signing_secret, app_token) are stored
        in the credentials table, not the settings table.

        Args:
            key: Full setting key (e.g., "slack.bot_token")

        Returns:
            The setting value or None if not found
        """
        # First check settings table (for backward compatibility)
        value = self.settings_repo.get(key)
        if value:
            return value

        # Then check credentials table
        service_name = key.split(".")[0]
        setting_key = key.split(".", 1)[1] if "." in key else "value"

        cred = self.credentials_repo.get(service_name)
        if cred:
            # Look up by specific setting key
            cred_value = cred.get("credential_data", {}).get(setting_key)
            if cred_value:
                return cred_value
            # Fallback to "value" key for old format
            return cred.get("credential_data", {}).get("value")

        return None

    def _get_client(self) -> SlackClient:
        """Get configured Slack client."""
        enabled = self.settings_repo.get("slack.enabled")
        if not enabled:
            raise ValueError("Slack integration is not enabled")

        bot_token = self._get_sensitive_setting("slack.bot_token") or ""
        if not bot_token:
            raise ValueError("Slack bot token not configured. Set 'slack.bot_token' in settings.")

        return SlackClient(bot_token=bot_token)

    def get_status(self) -> Dict[str, Any]:
        """Get Slack connection status."""
        try:
            client = self._get_client()
            info = client.get_bot_info()
            return {
                "connected": info.get("ok", False),
                "bot_user": info.get("user"),
                "team": info.get("team"),
            }
        except ValueError:
            return {"connected": False, "bot_user": None, "team": None}
        except Exception as e:
            logger.error(f"Failed to get Slack status: {e}")
            return {"connected": False, "bot_user": None, "team": None}

    def send_message(
        self,
        channel: str,
        message: str,
        thread_ts: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a Slack message to a channel."""
        client = self._get_client()
        return client.send_message(channel=channel, text=message, thread_ts=thread_ts)

    def send_message_to_default_channel(self, message: str) -> Dict[str, Any]:
        """Send a Slack message to the default channel configured in settings."""
        default_channel = self.settings_repo.get("slack.default_channel")
        if not default_channel:
            raise ValueError(
                "Default Slack channel not configured. Set 'slack.default_channel' in settings."
            )

        return self.send_message(channel=default_channel, message=message)

    def test_connection(self) -> Dict[str, Any]:
        """Test Slack connection."""
        try:
            client = self._get_client()

            if client.test_connection():
                info = client.get_bot_info()
                return {
                    "service_name": "slack",
                    "status": "success",
                    "message": f"Connected as @{info.get('user', 'unknown')} in {info.get('team', 'unknown')}",
                }
            else:
                return {
                    "service_name": "slack",
                    "status": "error",
                    "message": "Bot token is invalid or API is unreachable",
                }

        except ValueError as e:
            return {"service_name": "slack", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Slack connection test failed: {e}")
            return {
                "service_name": "slack",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }

    def is_user_allowed(self, user_id: str) -> bool:
        """Check if a Slack user is allowed to interact with the bot."""
        allowed_ids_str = self.settings_repo.get("slack.allowed_user_ids") or ""

        if not allowed_ids_str:
            logger.debug(f"[Slack] No allowed_user_ids configured - user {user_id} is allowed")
            return True  # No restriction — all users allowed

        allowed_ids = [uid.strip() for uid in allowed_ids_str.split(",") if uid.strip()]
        is_allowed = user_id in allowed_ids

        if is_allowed:
            logger.info(f"[Slack] User {user_id} is in allowed list")
        else:
            logger.warning(
                f"[Slack] User {user_id} is NOT in allowed list. "
                f"Configured allowed IDs: {allowed_ids}"
            )

        return is_allowed
