"""Outlook/Microsoft Graph OAuth authentication module using MSAL."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from msal import ConfidentialClientApplication, PublicClientApplication

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AuthenticationRequiredException(Exception):
    """Exception raised when authentication is needed with user-visible instructions."""

    def __init__(self, message: str, auth_url: str, user_code: str, flow: Dict[str, Any]):
        super().__init__(message)
        self.auth_url = auth_url
        self.user_code = user_code
        self.flow = flow


# Default Microsoft Graph scopes
# MSAL expects short format scopes (without https://graph.microsoft.com/ prefix)
# Note: Do NOT include 'offline_access' - MSAL adds it automatically
DEFAULT_SCOPES = [
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.Read",
    "Calendars.ReadWrite",
    "Files.ReadWrite.All",
    "User.Read",
    # OneNote scopes
    "Notes.Read",
    "Notes.ReadWrite",
    # Microsoft To Do scopes
    "Tasks.ReadWrite",
]


def get_outlook_token(
    client_id: str,
    client_secret: Optional[str] = None,
    tenant_id: str = "common",
    scopes: Optional[List[str]] = None,
    token_cache_path: Optional[str] = None,
) -> Dict[str, str]:
    """
    Get Microsoft Graph access token using MSAL.

    Args:
        client_id: Azure application client ID
        client_secret: Client secret (optional, for confidential client)
        tenant_id: Tenant ID (default: "common")
        scopes: OAuth scopes (default: mail, calendar, files)
        token_cache_path: Path to save/load token cache

    Returns:
        Dictionary with access_token and other token info

    Raises:
        ValueError: If authentication fails
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES

    authority = f"https://login.microsoftonline.com/{tenant_id}"

    # Load token cache if available
    cache = _load_token_cache(token_cache_path) if token_cache_path else None

    # Device code flow requires PublicClientApplication.
    # If you have a client_secret configured, you must enable "Allow public client flows"
    # in your Azure app registration (Authentication > Advanced settings).
    # Note: client_secret is ignored for device code flow - it's only useful for
    # confidential clients with authorization code flow (not implemented here).
    app = PublicClientApplication(client_id, authority=authority, token_cache=cache)

    # Try to get token from cache
    accounts = app.get_accounts()
    if accounts:
        logger.info("Found account in cache, attempting silent token acquisition")
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            logger.info("Token acquired silently from cache")
            _save_token_cache(app, token_cache_path)
            return result

    # Need authentication - use device code flow for better UX in chat
    logger.info("No cached token, starting device code authentication")

    # Always use device code flow (better for server/chat apps)
    flow = app.initiate_device_flow(scopes=scopes)

    if "user_code" not in flow:
        raise ValueError("Failed to create device flow")

    # Extract user-friendly auth info
    auth_url = flow.get("verification_uri", "https://microsoft.com/devicelogin")
    user_code = flow.get("user_code", "")
    message = flow.get("message", f"Visit {auth_url} and enter code {user_code}")

    logger.info(f"Device code flow initiated: {message}")

    # Log to console for backup visibility
    print(f"\n{'='*60}")
    print(f"OUTLOOK AUTHENTICATION REQUIRED")
    print(f"{'='*60}")
    print(f"{message}")
    print(f"{'='*60}\n")

    # Prepare authentication message
    auth_message = (
        f"Please authenticate with Microsoft:\n\n"
        f"1. Visit: {auth_url}\n"
        f"2. Enter code: {user_code}\n\n"
        f"After authenticating, wait about 30 seconds then try your request again.\n\n"
        f"Note: If authentication fails with an error about 'client_secret required', enable\n"
        f"'Allow public client flows' in your Azure app registration (Authentication > Advanced settings)."
    )

    # Raise exception with auth instructions - this will be shown in chat
    raise AuthenticationRequiredException(
        message=auth_message, auth_url=auth_url, user_code=user_code, flow=flow
    )


def complete_device_flow_background(
    client_id: str,
    client_secret: Optional[str],
    tenant_id: str,
    flow: Dict[str, Any],
    token_cache_path: Optional[str],
):
    """
    Complete device flow in background and save token.

    This allows the user to see auth instructions immediately while
    we wait for them to complete authentication.
    """
    try:
        logger.info(f"Background task: Waiting for device flow completion...")
        logger.info(
            f"Background task: client_secret present: {bool(client_secret)}, tenant: {tenant_id}"
        )

        # Create new app instance with token cache
        # Always use PublicClientApplication for device code flow
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        cache = _load_token_cache(token_cache_path) if token_cache_path else None
        app = PublicClientApplication(client_id, authority=authority, token_cache=cache)

        # Complete the device flow
        result = app.acquire_token_by_device_flow(flow)

        if "access_token" in result:
            logger.info("Background task: Token acquired successfully")
            _save_token_cache(app, token_cache_path)
        else:
            error = result.get("error_description", result.get("error", "Unknown"))
            error_code = result.get("error", "")

            # Detect common configuration issues
            if "AADSTS7000218" in str(error) or "client_secret" in str(error).lower():
                logger.error(
                    f"Background task: Authentication failed - {error}\n\n"
                    "This error means your Azure app is registered as a confidential client but device code flow\n"
                    "requires public client settings. Fix in Azure Portal:\n"
                    "  - Go to App registrations -> Your app -> Authentication -> Advanced settings\n"
                    "  - Set 'Allow public client flows' to Yes"
                )
            else:
                logger.error(f"Background task: Failed to acquire token: {error}")
    except Exception as e:
        logger.error(f"Background task: Error completing device flow: {e}")


def _load_token_cache(cache_path: str):
    """Load token cache from file."""
    from msal import SerializableTokenCache

    cache = SerializableTokenCache()

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cache.deserialize(f.read())
            logger.info(f"Loaded token cache from {cache_path}")
        except Exception as e:
            logger.warning(f"Failed to load token cache: {e}")

    return cache


def _save_token_cache(app, cache_path: Optional[str]):
    """Save token cache to file."""
    if not cache_path or not app.token_cache:
        return

    try:
        cache_file = Path(cache_path)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, "w") as f:
            f.write(app.token_cache.serialize())

        logger.info(f"Saved token cache to {cache_path}")

    except Exception as e:
        logger.warning(f"Failed to save token cache: {e}")


def refresh_outlook_token_proactively(
    client_id: str,
    client_secret: Optional[str] = None,
    tenant_id: str = "common",
    scopes: Optional[List[str]] = None,
    token_cache_path: Optional[str] = None,
) -> bool:
    """
    Proactively refresh the Outlook access token to keep the MSAL token cache alive.

    This should be called periodically (e.g., every few hours) to prevent the refresh
    token from expiring due to inactivity. MSAL refresh tokens can expire after 90 days
    of inactivity, so regular silent acquisition keeps them active.

    Args:
        client_id: Azure application client ID
        client_secret: Client secret (optional, for confidential client)
        tenant_id: Tenant ID (default: "common")
        scopes: OAuth scopes (default: mail, calendar, files)
        token_cache_path: Path to save/load token cache

    Returns:
        True if token was refreshed successfully, False otherwise
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES

    authority = f"https://login.microsoftonline.com/{tenant_id}"

    cache = _load_token_cache(token_cache_path) if token_cache_path else None

    if client_secret:
        app = ConfidentialClientApplication(
            client_id, authority=authority, client_credential=client_secret, token_cache=cache
        )
    else:
        app = PublicClientApplication(client_id, authority=authority, token_cache=cache)

    accounts = app.get_accounts()
    if not accounts:
        logger.warning("Proactive token refresh: no cached accounts found, skipping")
        return False

    result = app.acquire_token_silent(scopes, account=accounts[0])
    if result and "access_token" in result:
        _save_token_cache(app, token_cache_path)
        logger.info("Proactive token refresh: token refreshed successfully")
        return True

    logger.warning(
        "Proactive token refresh: silent acquisition failed — "
        "refresh token may be expired. Re-authentication required."
    )
    return False


def revoke_outlook_token(client_id: str, token_cache_path: Optional[str] = None) -> bool:
    """
    Revoke Outlook token and clear cache.

    Args:
        client_id: Azure application client ID
        token_cache_path: Path to token cache file

    Returns:
        True if revocation successful
    """
    try:
        if token_cache_path and os.path.exists(token_cache_path):
            os.remove(token_cache_path)
            logger.info(f"Deleted token cache: {token_cache_path}")

        return True

    except Exception as e:
        logger.error(f"Failed to revoke token: {e}")
        return False
