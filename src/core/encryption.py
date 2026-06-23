"""Encryption service for secure credential storage."""

import json
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

from src.utils.logger import get_logger

logger = get_logger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data."""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption service.

        Args:
            encryption_key: Fernet encryption key. If not provided, reads from
                          SECURITY_ENCRYPTION_KEY environment variable.

        Raises:
            ValueError: If no encryption key is provided or found in environment
        """
        key = encryption_key or os.getenv("SECURITY_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")

        if not key:
            raise ValueError(
                "Encryption key not found. Set SECURITY_ENCRYPTION_KEY or ENCRYPTION_KEY "
                "environment variable. Generate with: "
                "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        try:
            self.fernet = Fernet(key.encode())
            logger.info("Encryption service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize encryption service: {e}")
            raise ValueError(f"Invalid encryption key: {e}")

    def encrypt(self, data: Dict[str, Any]) -> str:
        """
        Encrypt a dictionary to an encrypted string.

        Args:
            data: Dictionary to encrypt

        Returns:
            Base64-encoded encrypted string

        Raises:
            ValueError: If encryption fails
        """
        try:
            json_str = json.dumps(data)
            encrypted_bytes = self.fernet.encrypt(json_str.encode())
            encrypted_str = encrypted_bytes.decode()
            logger.debug(f"Successfully encrypted data with {len(data)} keys")
            return encrypted_str
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Failed to encrypt data: {e}")

    def decrypt(self, encrypted_data: str) -> Dict[str, Any]:
        """
        Decrypt an encrypted string back to a dictionary.

        Args:
            encrypted_data: Base64-encoded encrypted string

        Returns:
            Decrypted dictionary

        Raises:
            ValueError: If decryption fails
        """
        try:
            encrypted_bytes = encrypted_data.encode()
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            json_str = decrypted_bytes.decode()
            data = json.loads(json_str)
            logger.debug(f"Successfully decrypted data with {len(data)} keys")
            return data
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Failed to decrypt data: {e}")

    def encrypt_string(self, text: str) -> str:
        """
        Encrypt a plain string.

        Args:
            text: String to encrypt

        Returns:
            Base64-encoded encrypted string
        """
        try:
            encrypted_bytes = self.fernet.encrypt(text.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"String encryption failed: {e}")
            raise ValueError(f"Failed to encrypt string: {e}")

    def decrypt_string(self, encrypted_text: str) -> str:
        """
        Decrypt an encrypted string.

        Args:
            encrypted_text: Base64-encoded encrypted string

        Returns:
            Decrypted plain string
        """
        try:
            encrypted_bytes = encrypted_text.encode()
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"String decryption failed: {e}")
            raise ValueError(f"Failed to decrypt string: {e}")


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        Base64-encoded encryption key

    Example:
        >>> key = generate_encryption_key()
        >>> print(key)
        'xyzabc123...'
    """
    return Fernet.generate_key().decode()


# Global encryption service instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get or create the global encryption service instance.

    Returns:
        EncryptionService instance

    Raises:
        ValueError: If encryption key is not configured
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
