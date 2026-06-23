"""Google Ads OAuth 2.0 authentication module.

Reuses the Google OAuth 2.0 infrastructure but with the adwords scope,
storing tokens under the 'google_ads' service name to keep them separate
from the regular Google (Gmail/Calendar/Drive) tokens.

Both standalone and managed (multi-tenant) OAuth flows are supported,
mirroring the behaviour of the regular Google integration.
"""

import json
import os
from typing import Dict, Optional

from google_auth_oauthlib.flow import Flow

from src.core.config import get_app_config
from src.core.repositories.credentials import CredentialsRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Google Ads requires the adwords scope
GOOGLE_ADS_SCOPES = [
    "https://www.googleapis.com/auth/adwords",
]


class GoogleAdsOAuthFlowRequired(Exception):
    """Exception raised when Google Ads OAuth flow needs user interaction."""

    def __init__(self, auth_url: str, flow):
        self.auth_url = auth_url
        self.flow = flow
        super().__init__(f"Google Ads OAuth authorization required. Visit: {auth_url}")


def get_google_ads_redirect_uri() -> str:
    """Resolve the redirect URI for Google Ads OAuth."""
    if os.environ.get("GOOGLE_ADS_REDIRECT_URI"):
        return os.environ.get("GOOGLE_ADS_REDIRECT_URI")
    try:
        config = get_app_config()
        return f"{config.general.app_url}/auth/google_ads/callback"
    except RuntimeError:
        return "http://localhost:8080/auth/google_ads/callback"


def get_google_ads_credentials_config(
    credentials_repo: CredentialsRepository,
    settings_repo=None,
) -> Dict:
    """
    Build the configuration dict required by GoogleAdsClient.load_from_dict().

    Pulls OAuth tokens from the database ('google_ads' service) and the
    developer token / login customer ID from settings.

    Args:
        credentials_repo: Credentials repository for encrypted token storage.
        settings_repo: Settings repository for developer_token etc. (optional).

    Returns:
        Dict suitable for GoogleAdsClient.load_from_dict().

    Raises:
        GoogleAdsOAuthFlowRequired: When no valid OAuth token is stored yet.
        ValueError: When required settings (developer_token) are missing.
    """
    stored = credentials_repo.get("google_ads")

    if not stored or stored.get("credential_type") != "oauth_token":
        raise GoogleAdsOAuthFlowRequired(
            auth_url="",
            flow=None,
        )

    cred_data: Dict = stored.get("credential_data", {})
    refresh_token = cred_data.get("refresh_token")

    if not refresh_token:
        raise GoogleAdsOAuthFlowRequired(
            auth_url="",
            flow=None,
        )

    client_id = cred_data.get("client_id")
    client_secret = cred_data.get("client_secret")

    developer_token = None
    login_customer_id = None

    if settings_repo:
        developer_token = settings_repo.get("google_ads.developer_token")
        login_customer_id = settings_repo.get("google_ads.login_customer_id")
        # Fall back to credential_data for sensitive values set via UI
        if not client_id:
            client_id = settings_repo.get("google_ads.client_id")
        if not client_secret:
            client_secret = settings_repo.get("google_ads.client_secret")

    if not developer_token:
        raise ValueError(
            "Google Ads developer token not configured. "
            "Please add it in Settings under Google Ads integration."
        )

    if not client_id or not client_secret:
        raise ValueError(
            "Google Ads OAuth client credentials not configured. "
            "Please add client_id and client_secret in Settings."
        )

    config = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }

    if login_customer_id:
        # Strip any dashes so the library receives a plain numeric string
        config["login_customer_id"] = login_customer_id.replace("-", "")

    return config


def build_google_ads_auth_flow(
    client_id: str,
    client_secret: str,
    redirect_uri: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Flow:
    """
    Construct a google_auth_oauthlib Flow configured for the adwords scope.

    Args:
        client_id: Google OAuth 2.0 Client ID.
        client_secret: Google OAuth 2.0 Client Secret.
        redirect_uri: Redirect URI (defaults to app URL + /auth/google_ads/callback).
        project_id: Optional Google Cloud project ID.

    Returns:
        Configured Flow object.
    """
    if redirect_uri is None:
        redirect_uri = get_google_ads_redirect_uri()

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [redirect_uri],
        }
    }

    if project_id:
        client_config["web"]["project_id"] = project_id

    return Flow.from_client_config(
        client_config,
        scopes=GOOGLE_ADS_SCOPES,
        redirect_uri=redirect_uri,
    )


def store_google_ads_token(
    flow: Flow,
    credentials_repo: CredentialsRepository,
    client_id: str,
    client_secret: str,
) -> None:
    """
    Exchange the authorisation code already fetched by *flow* and persist the
    resulting token (including refresh_token) to the credentials store.

    Call this after ``flow.fetch_token(code=code)``.

    Args:
        flow: Completed Flow object (fetch_token already called).
        credentials_repo: Credentials repository for encrypted storage.
        client_id: OAuth client ID (stored alongside the token for later use).
        client_secret: OAuth client secret (stored alongside the token).
    """
    creds = flow.credentials
    token_data = json.loads(creds.to_json())

    # Persist client_id and client_secret alongside the token so the Ads
    # client can be reconstructed without additional settings lookups.
    token_data["client_id"] = client_id
    token_data["client_secret"] = client_secret

    credentials_repo.store(
        service_name="google_ads",
        credential_type="oauth_token",
        credential_data=token_data,
    )
    logger.info("Saved Google Ads OAuth token to database")


def revoke_google_ads_credentials(credentials_repo: CredentialsRepository) -> bool:
    """
    Delete the stored Google Ads token from the database.

    Note: this does not revoke the token on Google's servers; for a full
    revocation the caller should use the token's revoke endpoint beforehand.

    Args:
        credentials_repo: Credentials repository.

    Returns:
        True if a token was found and deleted, False otherwise.
    """
    stored = credentials_repo.get("google_ads")
    if stored:
        credentials_repo.delete("google_ads")
        logger.info("Deleted Google Ads token from database")
        return True
    logger.warning("Google Ads token not found in database")
    return False
