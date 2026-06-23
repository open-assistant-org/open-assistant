"""WhatsApp client that communicates with Node.js bridge."""

import requests
from typing import Any, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class WhatsAppClient:
    """Client for WhatsApp operations via Node.js bridge."""

    def __init__(self, bridge_url: str = "http://localhost:3001"):
        """
        Initialize WhatsApp client.

        Args:
            bridge_url: URL of the Node.js bridge service
        """
        self.bridge_url = bridge_url.rstrip("/")
        logger.info(f"WhatsApp client initialized with bridge: {bridge_url}")

    def get_status(self) -> Dict[str, Any]:
        """
        Get WhatsApp connection status.

        Returns:
            Status dictionary with ready state and QR code if available
        """
        try:
            response = requests.get(f"{self.bridge_url}/status", timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get WhatsApp status: {e}")
            raise

    def is_ready(self) -> bool:
        """Check if WhatsApp is ready to send messages."""
        try:
            status = self.get_status()
            return status.get("ready", False)
        except Exception:
            return False

    def send_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        """
        Send WhatsApp message.

        Args:
            phone_number: Recipient phone number (with country code, e.g., +1234567890)
            message: Message text

        Returns:
            Response dictionary with success status

        Raises:
            requests.RequestException: If sending fails
        """
        try:
            logger.info(f"Sending WhatsApp message to {phone_number}")

            payload = {"phone_number": phone_number, "message": message}

            response = requests.post(f"{self.bridge_url}/send", json=payload, timeout=10)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Message sent successfully to {phone_number}")
            return result

        except requests.RequestException as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            raise

    def configure_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """
        Configure webhook for incoming messages.

        Args:
            webhook_url: URL to receive incoming message notifications

        Returns:
            Response dictionary
        """
        try:
            logger.info(f"Configuring WhatsApp webhook: {webhook_url}")

            payload = {"url": webhook_url}

            response = requests.post(f"{self.bridge_url}/webhook", json=payload, timeout=5)
            response.raise_for_status()

            result = response.json()
            logger.info("Webhook configured successfully")
            return result

        except requests.RequestException as e:
            logger.error(f"Failed to configure webhook: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Test connection to WhatsApp bridge.

        Returns:
            True if bridge is reachable and WhatsApp is ready
        """
        try:
            response = requests.get(f"{self.bridge_url}/health", timeout=5)
            response.raise_for_status()

            health = response.json()
            return health.get("ready", False)

        except Exception as e:
            logger.error(f"WhatsApp bridge connection test failed: {e}")
            return False
