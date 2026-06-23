"""WhatsApp service for messaging operations."""

from typing import Any, Dict, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.whatsapp.client import WhatsAppClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WhatsAppService(BaseService):
    """Service for WhatsApp integration operations."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_client(self) -> WhatsAppClient:
        """Get configured WhatsApp client."""
        enabled = self.settings_repo.get("whatsapp.enabled")
        if not enabled:
            raise ValueError("WhatsApp integration is not enabled")

        # Get bridge URL from settings (default: localhost:3001)
        bridge_url = self.settings_repo.get("whatsapp.bridge_url") or "http://localhost:3001"

        return WhatsAppClient(bridge_url=bridge_url)

    def get_status(self) -> Dict[str, Any]:
        """Get WhatsApp connection status."""
        client = self._get_client()
        return client.get_status()

    def send_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Send WhatsApp message. Only the configured owner number may be texted."""
        owner_number = self.settings_repo.get("whatsapp.phone_number")
        if not owner_number:
            raise ValueError(
                "Owner phone number not configured. Set 'whatsapp.phone_number' in settings."
            )

        # Reject any attempt to send to a number that is not the owner
        if not self._is_owner_number(phone_number, owner_number):
            raise ValueError(
                f"Outbound messages are restricted to the owner's number. "
                f"Attempted to send to: {phone_number}"
            )

        client = self._get_client()
        phone_number = self._format_phone_number(phone_number)
        return client.send_message(phone_number=phone_number, message=message)

    def send_message_to_owner(self, message: str) -> Dict[str, Any]:
        """Send a WhatsApp message to the owner whose number is stored in settings."""
        owner_number = self.settings_repo.get("whatsapp.phone_number")
        if not owner_number:
            raise ValueError(
                "Owner phone number not configured. Set 'whatsapp.phone_number' in settings."
            )

        return self.send_message(phone_number=owner_number, message=message)

    def configure_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """Configure webhook for incoming messages."""
        client = self._get_client()
        return client.configure_webhook(webhook_url=webhook_url)

    def test_connection(self) -> Dict[str, Any]:
        """Test WhatsApp connection."""
        try:
            client = self._get_client()

            if client.test_connection():
                return {
                    "service_name": "whatsapp",
                    "status": "success",
                    "message": "Connection successful",
                }
            else:
                return {
                    "service_name": "whatsapp",
                    "status": "warning",
                    "message": "Bridge reachable but WhatsApp not authenticated",
                }

        except ValueError as e:
            return {"service_name": "whatsapp", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"WhatsApp connection test failed: {e}")
            return {
                "service_name": "whatsapp",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }

    def _normalise_number(self, number: str) -> str:
        """Strip formatting so two representations of the same number compare equal."""
        return (
            number.replace("+", "")
            .replace(" ", "")
            .replace("-", "")
            .replace("@c.us", "")
            .replace("@lid", "")
        )

    def _is_owner_number(self, phone_number: str, owner_number: str) -> bool:
        """Return True only when phone_number resolves to the owner's number."""
        return self._normalise_number(phone_number) == self._normalise_number(owner_number)

    def _format_phone_number(self, phone_number: str) -> str:
        """Format phone number to include country code."""
        # If it's already a full WhatsApp ID (has @ suffix), return as-is
        if "@" in phone_number:
            return phone_number

        # Remove spaces and dashes
        formatted = phone_number.replace(" ", "").replace("-", "")

        # Ensure it starts with +
        if not formatted.startswith("+"):
            formatted = "+" + formatted

        return formatted
