"""Google OAuth 2.0 authentication module."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

from src.core.config import get_app_config
from src.core.repositories.credentials import CredentialsRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default Google API scopes (Gmail + Calendar + Drive + Docs + Sheets + Slides)
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
]


def get_google_credentials(
    client_id: str,
    client_secret: str,
    credentials_repo: CredentialsRepository,
    scopes: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    use_console_flow: bool = False,
    redirect_uri: Optional[str] = None,
) -> Credentials:
    """
    Get Google OAuth credentials with automatic refresh using client_id and client_secret.

    This function handles the OAuth 2.0 flow for Google services:
    1. Checks if a valid token exists in database
    2. Refreshes expired tokens
    3. Runs OAuth flow for new authentication
    4. Saves tokens to database (encrypted)

    Args:
        client_id: Google OAuth 2.0 Client ID
        client_secret: Google OAuth 2.0 Client Secret
        credentials_repo: Credentials repository for encrypted storage
        scopes: List of OAuth scopes (default: Gmail + Calendar)
        project_id: Optional Google Cloud Project ID
        use_console_flow: If True, prints URL for manual authorization (for chat integration)
        redirect_uri: OAuth redirect URI for web app flow

    Returns:
        Credentials object for Google APIs

    Raises:
        ValueError: If credentials are invalid or authentication fails
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES

    if not client_id or not client_secret:
        raise ValueError("Client ID and Client Secret are required")

    creds = None

    # Check if token exists in database
    stored_cred = credentials_repo.get("google")
    if stored_cred and stored_cred.get("credential_type") == "oauth_token":
        try:
            logger.info("Loading Google token from database")
            # credential_data is already decrypted by the repository
            creds = Credentials.from_authorized_user_info(stored_cred["credential_data"], scopes)
        except Exception as e:
            logger.warning(f"Failed to load token from database: {e}")
            creds = None

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            try:
                logger.info("Refreshing expired Google token")
                creds.refresh(Request())
                logger.info("Token refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                creds = None

        if not creds:
            # Run OAuth flow using client config
            try:
                logger.info("Starting Google OAuth flow")

                # Determine redirect URI
                # Priority: function param > env var > APP_URL from config
                if redirect_uri:
                    app_redirect_uri = redirect_uri
                elif os.environ.get("GOOGLE_REDIRECT_URI"):
                    app_redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI")
                else:
                    try:
                        config = get_app_config()
                        app_redirect_uri = f"{config.general.app_url}/auth/google/callback"
                    except RuntimeError:
                        # Fallback if config not initialized
                        app_redirect_uri = "http://localhost:8080/auth/google/callback"

                # Construct client config for web app
                client_config = {
                    "web": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": [app_redirect_uri],
                    }
                }

                if project_id:
                    client_config["web"]["project_id"] = project_id

                if use_console_flow:
                    flow = Flow.from_client_config(
                        client_config,
                        scopes,
                        redirect_uri=app_redirect_uri,
                    )
                    auth_url, _ = flow.authorization_url(
                        prompt="consent",
                        access_type="offline",
                    )
                    raise OAuthFlowRequired(auth_url, flow)
                else:
                    # Run local server for OAuth callback
                    # Fall back to InstalledAppFlow for local dev
                    installed_config = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://localhost"],
                        }
                    }
                    if project_id:
                        installed_config["installed"]["project_id"] = project_id

                    local_flow = InstalledAppFlow.from_client_config(
                        installed_config,
                        scopes,
                    )
                    creds = local_flow.run_local_server(port=0)
                    logger.info("OAuth flow completed successfully")

            except OAuthFlowRequired:
                raise
            except Exception as e:
                logger.error(f"OAuth flow failed: {e}")
                raise ValueError(f"Failed to authenticate with Google: {str(e)}")

        # Save credentials to database (encrypted)
        try:
            credentials_repo.store(
                service_name="google",
                credential_type="oauth_token",
                credential_data=json.loads(creds.to_json()),
            )
            logger.info("Saved Google token to database")

        except Exception as e:
            logger.warning(f"Failed to save token to database: {e}")

    return creds


class OAuthFlowRequired(Exception):
    """Exception raised when OAuth flow needs user interaction."""

    def __init__(self, auth_url: str, flow):
        self.auth_url = auth_url
        self.flow = flow
        super().__init__(f"OAuth authorization required. Visit: {auth_url}")


def complete_google_oauth_flow(
    flow, authorization_code: str, credentials_repo: CredentialsRepository
) -> Credentials:
    """
    Complete Google OAuth flow with authorization code from user.

    Args:
        flow: The OAuth flow object from the initial attempt
        authorization_code: Authorization code from user after visiting auth URL
        credentials_repo: Credentials repository for encrypted storage

    Returns:
        Credentials object

    Raises:
        ValueError: If code is invalid
    """
    try:
        # Exchange code for credentials
        flow.fetch_token(code=authorization_code)
        creds = flow.credentials

        # Save credentials to database (encrypted)
        credentials_repo.store(
            service_name="google",
            credential_type="oauth_token",
            credential_data=json.loads(creds.to_json()),
        )

        logger.info("OAuth flow completed and saved token to database")
        return creds

    except Exception as e:
        logger.error(f"Failed to complete OAuth flow: {e}")
        raise ValueError(f"Invalid authorization code: {str(e)}")


def revoke_google_credentials(credentials_repo: CredentialsRepository) -> bool:
    """
    Revoke Google OAuth credentials and delete token from database.

    Args:
        credentials_repo: Credentials repository for encrypted storage

    Returns:
        True if revocation successful, False otherwise
    """
    try:
        # Load credentials from database
        stored_cred = credentials_repo.get("google")

        if stored_cred and stored_cred.get("credential_type") == "oauth_token":
            # Load credentials - credential_data is already decrypted
            creds = Credentials.from_authorized_user_info(
                stored_cred["credential_data"], DEFAULT_SCOPES
            )

            # Revoke credentials with Google
            if creds and creds.valid:
                creds.revoke(Request())
                logger.info("Google credentials revoked with Google")

            # Delete token from database
            credentials_repo.delete("google")
            logger.info("Deleted Google token from database")

            return True

        else:
            logger.warning("Google token not found in database")
            return False

    except Exception as e:
        logger.error(f"Failed to revoke credentials: {e}")
        return False


def validate_credentials_file(credentials_path: str) -> bool:
    """
    Validate Google OAuth credentials file.

    Args:
        credentials_path: Path to credentials JSON file

    Returns:
        True if valid, False otherwise
    """
    try:
        if not os.path.exists(credentials_path):
            return False

        with open(credentials_path, "r") as f:
            data = json.load(f)

        # Check for required OAuth fields (supports both web and installed types)
        if "web" in data or "installed" in data:
            client_config = data.get("web") or data.get("installed")
            required_fields = ["client_id", "client_secret"]

            return all(field in client_config for field in required_fields)

        return False

    except Exception as e:
        logger.error(f"Failed to validate credentials file: {e}")
        return False
