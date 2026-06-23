"""Repository for service credentials operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.encryption import get_encryption_service
from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CredentialsRepository(BaseRepository):
    """Repository for managing encrypted service credentials."""

    def __init__(self, db_manager, encryption_service=None):
        """
        Initialize repository with encryption service.

        Args:
            db_manager: Database manager instance
            encryption_service: Encryption service (auto-created if not provided)
        """
        super().__init__(db_manager)
        self.encryption = encryption_service or get_encryption_service()

    def store(
        self,
        service_name: str,
        credential_type: str,
        credential_data: Dict[str, Any],
        expires_at: Optional[str] = None,
    ) -> bool:
        """
        Store encrypted credentials for a service.

        Args:
            service_name: Service name (google, outlook, etc.)
            credential_type: Credential type (oauth_token, api_key, app_password)
            credential_data: Credential data dictionary (will be encrypted)
            expires_at: Optional expiration timestamp (ISO format)

        Returns:
            True if successful
        """
        # Encrypt credential data
        encrypted_data = self.encryption.encrypt(credential_data)

        # Check if exists
        if self.exists("service_credentials", "service_name = ?", (service_name,)):
            # Update
            data = {
                "credential_type": credential_type,
                "credential_data": encrypted_data,
                "expires_at": expires_at,
                "updated_at": datetime.utcnow().isoformat(),
            }

            affected = self.update("service_credentials", data, "service_name = ?", (service_name,))

            logger.info(f"Updated credentials for service: {service_name}")
            return affected > 0
        else:
            # Insert
            data = {
                "service_name": service_name,
                "credential_type": credential_type,
                "credential_data": encrypted_data,
                "expires_at": expires_at,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            self.insert("service_credentials", data)
            logger.info(f"Stored credentials for service: {service_name}")
            return True

    def get(self, service_name: str) -> Optional[Dict[str, Any]]:
        """
        Get and decrypt credentials for a service.

        Args:
            service_name: Service name

        Returns:
            Dictionary with credential_type and decrypted credential_data, or None
        """
        query = """
            SELECT credential_type, credential_data, expires_at
            FROM service_credentials
            WHERE service_name = ?
        """
        result = self.fetch_one(query, (service_name,))

        if not result:
            return None

        # Decrypt credential data
        try:
            decrypted_data = self.encryption.decrypt(result["credential_data"])
            return {
                "credential_type": result["credential_type"],
                "credential_data": decrypted_data,
                "expires_at": result["expires_at"],
            }
        except Exception as e:
            logger.error(f"Failed to decrypt credentials for {service_name}: {e}")
            return None

    def get_metadata(self, service_name: str) -> Optional[Dict[str, Any]]:
        """
        Get credential metadata without decrypting.

        Args:
            service_name: Service name

        Returns:
            Dictionary with metadata (no credential_data)
        """
        query = """
            SELECT service_name, credential_type, expires_at, created_at, updated_at
            FROM service_credentials
            WHERE service_name = ?
        """
        return self.fetch_one(query, (service_name,))

    def list_services(self) -> List[str]:
        """
        List all services with stored credentials.

        Returns:
            List of service names
        """
        query = "SELECT service_name FROM service_credentials ORDER BY service_name"
        results = self.fetch_all(query)
        return [row["service_name"] for row in results]

    def list_all_metadata(self) -> List[Dict[str, Any]]:
        """
        List metadata for all credentials.

        Returns:
            List of credential metadata dictionaries
        """
        query = """
            SELECT service_name, credential_type, expires_at, created_at, updated_at
            FROM service_credentials
            ORDER BY service_name
        """
        return self.fetch_all(query)

    def delete(self, service_name: str) -> bool:
        """
        Delete credentials for a service.

        Args:
            service_name: Service name

        Returns:
            True if deleted, False otherwise
        """
        affected = super().delete("service_credentials", "service_name = ?", (service_name,))

        if affected > 0:
            logger.info(f"Deleted credentials for service: {service_name}")

        return affected > 0

    def is_expired(self, service_name: str) -> bool:
        """
        Check if credentials are expired.

        Args:
            service_name: Service name

        Returns:
            True if expired, False otherwise (or if no expiration set)
        """
        query = "SELECT expires_at FROM service_credentials WHERE service_name = ?"
        result = self.fetch_one(query, (service_name,))

        if not result or not result["expires_at"]:
            return False

        expires_at = datetime.fromisoformat(result["expires_at"])
        return datetime.utcnow() > expires_at
