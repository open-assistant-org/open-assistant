"""Brave Search API key management."""

from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BraveAuthError(Exception):
    """Raised when Brave Search API authentication fails."""

    pass


def get_api_key(
    settings_repo: SettingsRepository,
    credentials_repo: CredentialsRepository,
) -> str:
    """
    Retrieve the Brave Search API key from credentials store.

    Args:
        settings_repo: Settings repository to check if enabled
        credentials_repo: Credentials repository for API key

    Returns:
        Brave Search API key

    Raises:
        BraveAuthError: If integration is disabled or API key is missing
    """
    enabled = settings_repo.get("brave.enabled")
    if not enabled:
        raise BraveAuthError("Brave Search integration is not enabled")

    creds = credentials_repo.get("brave")
    if not creds:
        raise BraveAuthError("Brave Search API key not found. Please configure it in Settings.")

    api_key = creds.get("credential_data", {}).get("api_key")
    if not api_key:
        raise BraveAuthError("Brave Search API key is empty")

    return api_key
