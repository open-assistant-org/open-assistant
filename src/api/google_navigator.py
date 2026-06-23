"""Google Navigator API endpoints for Places, Directions, and Geocoding."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.core.dependencies import get_credentials_repo, get_settings_repo
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.services.google import GoogleService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/google_navigator", tags=["google_navigator"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


def get_google_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> GoogleService:
    """Get Google service instance."""
    return GoogleService(settings_repo, credentials_repo)


# ============================================================================
# CONNECTION TESTING
# ============================================================================


@router.post("/test-connection")
async def test_connection(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> Dict[str, Any]:
    """
    Test Google Navigator connection by checking if API key is configured.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        Connection test result
    """
    try:
        # Check if integration is enabled
        enabled = settings_repo.get("google_navigator.enabled")
        if not enabled:
            return {
                "status": "error",
                "message": "Google Navigator integration is not enabled. Please enable it first.",
            }

        # Check if API key is configured in credentials table
        # API key should be stored under service_name='google_navigator', credential_type='api_key'
        # The key is stored as 'places_api_key' in credential_data (from validate_and_set)
        api_key = None
        credentials = credentials_repo.get("google_navigator")

        if credentials:
            if credentials.get("credential_type") == "api_key":
                credential_data = credentials.get("credential_data", {})
                # Check both 'places_api_key' (correct key name) and 'value' (legacy/broken)
                api_key = credential_data.get("places_api_key") or credential_data.get("value")
                if not api_key:
                    return {
                        "status": "error",
                        "message": "Google Places API key found but is empty.",
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Found google_navigator credentials but wrong type: {credentials.get('credential_type')} (expected 'api_key')",
                }
        else:
            # Fall back to checking settings table
            api_key = settings_repo.get("google_navigator.places_api_key")
            # Legacy key support
            if not api_key:
                api_key = settings_repo.get("google.places_api_key")
            if not api_key:
                return {
                    "status": "error",
                    "message": "Google Places API key not found in credentials (service_name='google_navigator') or settings. Please save the API key in the Google Navigator settings.",
                }

        # Basic validation - check if it looks like a Google API key
        if not api_key.startswith("AIza"):
            return {
                "status": "warning",
                "message": "API key format looks unusual. Google API keys typically start with 'AIza'.",
            }

        # TODO: Make an actual API call to test the key
        # For now, just check that it's configured
        return {
            "status": "success",
            "message": "Google Navigator is configured. API key found.",
        }

    except Exception as e:
        logger.error(f"Failed to test Google Navigator connection: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to test connection: {str(e)}",
        }
