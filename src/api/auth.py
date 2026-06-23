"""OAuth authentication callback endpoints."""

import json
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow
from msal import PublicClientApplication, ConfidentialClientApplication, SerializableTokenCache

from src.core.config import get_app_config
from src.core.dependencies import get_settings_repo, get_credentials_repo
from src.core.jwt import create_oauth_state, verify_oauth_state
from src.integrations.outlook.auth import _save_token_cache
from src.integrations.google.auth import DEFAULT_SCOPES
from src.integrations.google_ads.auth import (
    build_google_ads_auth_flow,
    get_google_ads_redirect_uri,
    store_google_ads_token,
)
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.settings import OAuthInitiateResponse, DeviceCodeResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory storage for device flow state (per device_code)
# In production, consider using Redis or database for multi-instance deployments
_device_flows: Dict[str, Dict[str, Any]] = {}

# In-memory storage for Google OAuth flow state (per state param)
# Needed to preserve the PKCE code_verifier between initiate and callback
_google_oauth_flows: Dict[str, Flow] = {}

# In-memory storage for Google Ads OAuth flow state (per state param)
_google_ads_oauth_flows: Dict[str, Dict[str, Any]] = {}


@router.post("/google/initiate")
async def google_oauth_initiate(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> OAuthInitiateResponse:
    """
    Initiate Google OAuth flow and return authorization URL.

    This endpoint generates the authorization URL that users will visit
    to authenticate with Google. Designed for use with popup windows.

    Args:
        settings_repo: Settings repository (injected)

    Returns:
        OAuthInitiateResponse with auth_url and state

    Raises:
        HTTPException: If Google credentials are not configured
    """
    try:
        logger.info("Initiating Google OAuth flow")

        # Get Google settings
        # Sensitive settings (client_id, client_secret) are stored in credentials repo when set via UI
        client_id = settings_repo.get("google.client_id")
        client_secret = settings_repo.get("google.client_secret")

        # Fall back to credentials repo for sensitive values
        if not client_id or not client_secret:
            cred = credentials_repo.get("google")
            if cred:
                cred_data = cred.get("credential_data", {})
                if not client_id:
                    client_id = cred_data.get("client_id")
                if not client_secret:
                    client_secret = cred_data.get("client_secret")

        project_id = settings_repo.get("google.project_id")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=400,
                detail="Google OAuth credentials not configured. Please configure client_id and client_secret in Settings.",
            )

        # Determine redirect URI
        redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI")
        if not redirect_uri:
            try:
                config = get_app_config()
                redirect_uri = f"{config.general.app_url}/auth/google/callback"
            except RuntimeError:
                redirect_uri = "http://localhost:8080/auth/google/callback"

        # Create Flow object with same config as auth flow
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

        # Create flow and generate authorization URL
        flow = Flow.from_client_config(
            client_config,
            scopes=DEFAULT_SCOPES,
            redirect_uri=redirect_uri,
        )

        # Generate state: use custom JWT in managed mode, otherwise library default
        if os.getenv("MANAGED_API_KEY"):
            # Managed mode: create signed state with instance_id for relay routing
            instance_id = os.getenv("INSTANCE_ID")
            custom_state = create_oauth_state(instance_id=instance_id)
            auth_url, _ = flow.authorization_url(
                state=custom_state,
                prompt="consent",
                access_type="offline",
            )
            state = custom_state
        else:
            # Standalone mode: use library's default random state
            auth_url, state = flow.authorization_url(
                prompt="consent",
                access_type="offline",
            )

        # Persist the flow so the callback can reuse it with its code_verifier
        _google_oauth_flows[state] = flow

        logger.info("Generated Google OAuth authorization URL")

        return OAuthInitiateResponse(auth_url=auth_url, state=state)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate Google OAuth: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}")


@router.get("/google/callback")
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="State parameter for CSRF protection"),
    popup: bool = Query(False, description="Whether this is a popup window"),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> HTMLResponse:
    """
    Handle OAuth callback from Google.

    This endpoint is called by Google after the user authorizes the application.
    It exchanges the authorization code for access and refresh tokens.

    Args:
        code: Authorization code from Google
        state: Optional state parameter
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        HTML response indicating success or failure
    """
    try:
        logger.info("Received OAuth callback from Google")

        # Reuse the flow from the initiate step to preserve the PKCE code_verifier.
        # Creating a new Flow here would lose the verifier and cause Google to
        # return invalid_grant: Missing code verifier.
        flow = _google_oauth_flows.pop(state, None)
        if flow is None:
            raise ValueError(
                "OAuth state not found — the flow may have expired or the state parameter is invalid"
            )

        # In managed mode, verify JWT signature for extra security
        if os.getenv("MANAGED_API_KEY") and not verify_oauth_state(state):
            raise ValueError("Invalid OAuth state signature")

        # Exchange authorization code for credentials
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Save credentials to database (encrypted)
        import json

        credentials_repo.store(
            service_name="google",
            credential_type="oauth_token",
            credential_data=json.loads(creds.to_json()),
        )

        logger.info("OAuth flow completed and saved token to database")

        # Return success page (different for popup vs full page)
        if popup:
            # Popup mode: send message to parent window and close
            return HTMLResponse(
                content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 1rem;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 500px;
                    }
                    .checkmark {
                        font-size: 4rem;
                        color: #48bb78;
                        margin-bottom: 1rem;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">✓</div>
                    <p>Authentication successful! Closing window...</p>
                </div>
                <script>
                    // Notify parent window of success
                    if (window.opener) {
                        window.opener.postMessage({
                            type: 'oauth_success',
                            service: 'google'
                        }, '*');
                    }
                    // Close popup after a short delay
                    setTimeout(function() {
                        window.close();
                    }, 1000);
                </script>
            </body>
            </html>
            """,
                status_code=200,
            )
        else:
            # Full page mode: show standard success message
            return HTMLResponse(
                content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 1rem;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 500px;
                    }
                    h1 {
                        color: #2d3748;
                        margin-bottom: 1rem;
                    }
                    p {
                        color: #4a5568;
                        line-height: 1.6;
                    }
                    .checkmark {
                        font-size: 4rem;
                        color: #48bb78;
                        margin-bottom: 1rem;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">✓</div>
                    <h1>Authentication Successful!</h1>
                    <p>Your Google account has been connected successfully.</p>
                    <p>You can now close this window and return to the chat to continue.</p>
                </div>
            </body>
            </html>
            """,
                status_code=200,
            )

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")

        # Return error page
        return HTMLResponse(
            content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                }}
                .container {{
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }}
                h1 {{
                    color: #2d3748;
                    margin-bottom: 1rem;
                }}
                p {{
                    color: #4a5568;
                    line-height: 1.6;
                }}
                .error {{
                    font-size: 4rem;
                    color: #f56565;
                    margin-bottom: 1rem;
                }}
                .error-details {{
                    background: #fed7d7;
                    color: #c53030;
                    padding: 1rem;
                    border-radius: 0.5rem;
                    margin-top: 1rem;
                    font-family: monospace;
                    font-size: 0.875rem;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error">✗</div>
                <h1>Authentication Failed</h1>
                <p>There was an error connecting your Google account.</p>
                <p>Please try again or contact support if the problem persists.</p>
                <div class="error-details">{str(e)}</div>
            </div>
        </body>
        </html>
        """,
            status_code=500,
        )


@router.post("/outlook/initiate")
async def outlook_oauth_initiate(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> DeviceCodeResponse:
    """
    Initiate Outlook/Microsoft OAuth device code flow.

    This endpoint starts the device code flow for Microsoft authentication,
    where users visit a URL and enter a code to authenticate.

    Args:
        settings_repo: Settings repository (injected)

    Returns:
        DeviceCodeResponse with user_code, verification_uri, and device_code

    Raises:
        HTTPException: If Outlook credentials are not configured or flow fails
    """
    try:
        logger.info("Initiating Outlook device code flow")

        # Get Outlook settings
        # Sensitive settings (client_id, client_secret) are stored in credentials repo when set via UI
        client_id = settings_repo.get("outlook.client_id")
        client_secret = settings_repo.get("outlook.client_secret")

        # Fall back to credentials repo for sensitive values
        if not client_id or not client_secret:
            cred = credentials_repo.get("outlook")
            if cred:
                cred_data = cred.get("credential_data", {})
                if not client_id:
                    client_id = cred_data.get("client_id")
                if not client_secret:
                    client_secret = cred_data.get("client_secret")

        tenant_id = settings_repo.get("outlook.tenant_id") or "common"

        if not client_id:
            raise HTTPException(
                status_code=400,
                detail="Outlook OAuth credentials not configured. Please configure client_id in Settings.",
            )

        # Create MSAL application with a serializable token cache so the acquired
        # token can be persisted to disk after the device flow completes.
        # Device code flow requires PublicClientApplication. If you have a client_secret
        # configured, you must enable "Allow public client flows" in your Azure app
        # registration (Authentication > Advanced settings).
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        token_cache_path = "data/outlook_token_cache.json"
        cache = SerializableTokenCache()

        app = PublicClientApplication(client_id, authority=authority, token_cache=cache)

        # Initiate device code flow
        scopes = [
            "Mail.Read",
            "Mail.ReadWrite",
            "Mail.Send",  # Required for sending emails
            "Calendars.Read",
            "Calendars.ReadWrite",
            "Files.ReadWrite.All",  # Required for OneDrive upload (changed from Files.Read.All)
            "User.Read",
        ]

        flow = app.initiate_device_flow(scopes=scopes)

        if "user_code" not in flow:
            raise HTTPException(status_code=500, detail="Failed to initiate device code flow")

        # Extract flow information
        user_code = flow.get("user_code", "")
        verification_uri = flow.get("verification_uri", "https://microsoft.com/devicelogin")
        device_code = flow.get("device_code", "")
        expires_in = flow.get("expires_in", 900)  # Default 15 minutes
        interval = flow.get("interval", 5)

        # Store flow state temporarily for polling
        _device_flows[device_code] = {
            "flow": flow,
            "app": app,
            "client_id": client_id,
            "tenant_id": tenant_id,
            "token_cache_path": token_cache_path,
        }

        logger.info(f"Device code flow initiated: {user_code}")

        return DeviceCodeResponse(
            user_code=user_code,
            verification_uri=verification_uri,
            device_code=device_code,
            expires_in=expires_in,
            interval=interval,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate Outlook OAuth: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}")


@router.get("/outlook/status")
async def outlook_oauth_status(
    device_code: str = Query(..., description="Device code from initiation"),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> Dict[str, str]:
    """
    Poll device code flow status for Outlook OAuth.

    This endpoint is called repeatedly by the frontend to check if the user
    has completed authentication.

    Args:
        device_code: Device code from initiation endpoint
        credentials_repo: Credentials repository (injected)

    Returns:
        Status dictionary with status (pending/success/expired/error) and message

    Raises:
        HTTPException: If device_code is invalid or flow fails
    """
    try:
        # Check if device code exists in storage
        if device_code not in _device_flows:
            raise HTTPException(
                status_code=404,
                detail="Device code not found or expired. Please restart authentication.",
            )

        flow_data = _device_flows[device_code]
        app = flow_data["app"]
        flow = flow_data["flow"]

        # Try to acquire token — single non-blocking attempt.
        # Without exit_condition MSAL would poll internally until the 15-minute device code
        # expires, blocking the server thread. Passing a callable that returns True makes it
        # exit after the first attempt so the frontend's own polling loop stays in control.
        result = app.acquire_token_by_device_flow(flow, exit_condition=lambda f: True)

        if "access_token" in result:
            # Success! Persist token to the MSAL cache file so OutlookService can use it.
            logger.info("Outlook OAuth completed successfully")
            _save_token_cache(app, flow_data.get("token_cache_path"))

            # Store credentials in database
            credentials_repo.store(
                service_name="outlook",
                credential_type="oauth_token",
                credential_data={
                    "access_token": result["access_token"],
                    "refresh_token": result.get("refresh_token"),
                    "token_type": result.get("token_type", "Bearer"),
                    "expires_in": result.get("expires_in"),
                    "scope": result.get("scope", ""),
                },
            )

            # Clean up flow state
            del _device_flows[device_code]

            return {"status": "success", "message": "Authentication successful"}

        elif "error" in result:
            error = result.get("error", "")

            # Check if authorization is still pending
            if error == "authorization_pending":
                return {
                    "status": "pending",
                    "message": "Waiting for user to complete authentication",
                }

            # Check if code expired
            elif error == "expired_token" or error == "code_expired":
                # Clean up flow state
                if device_code in _device_flows:
                    del _device_flows[device_code]

                return {
                    "status": "expired",
                    "message": "Device code expired. Please restart authentication.",
                }

            # Other errors
            else:
                error_desc = result.get("error_description", str(error))
                logger.error(f"Outlook OAuth error: {error_desc}")

                # Clean up flow state
                if device_code in _device_flows:
                    del _device_flows[device_code]

                return {"status": "error", "message": f"Authentication failed: {error_desc}"}

        else:
            # Still pending
            return {"status": "pending", "message": "Waiting for user to complete authentication"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to poll device flow status: {e}")

        # Clean up flow state on error
        if device_code in _device_flows:
            del _device_flows[device_code]

        raise HTTPException(status_code=500, detail=f"Failed to check status: {str(e)}")


# ============================================================================
# GOOGLE ADS OAuth
# ============================================================================


@router.post("/google_ads/initiate")
async def google_ads_oauth_initiate(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> OAuthInitiateResponse:
    """
    Initiate Google Ads OAuth flow and return the authorization URL.

    Google Ads uses the same OAuth 2.0 infrastructure as the regular Google
    integration but with the ``https://www.googleapis.com/auth/adwords`` scope
    and stores its tokens separately under the ``google_ads`` service name.

    Returns:
        OAuthInitiateResponse with auth_url and state.

    Raises:
        HTTPException: If Google Ads credentials are not configured.
    """
    try:
        logger.info("Initiating Google Ads OAuth flow")

        client_id = settings_repo.get("google_ads.client_id")
        client_secret = settings_repo.get("google_ads.client_secret")

        # Sensitive values may have been stored in the credentials repo via the UI
        if not client_id or not client_secret:
            cred = credentials_repo.get("google_ads")
            if cred:
                cred_data = cred.get("credential_data", {})
                client_id = client_id or cred_data.get("client_id")
                client_secret = client_secret or cred_data.get("client_secret")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Google Ads OAuth credentials not configured. "
                    "Please add google_ads.client_id and google_ads.client_secret in Settings. "
                    "See docs/integrations/google_ads.md for setup instructions."
                ),
            )

        project_id = settings_repo.get("google_ads.project_id")
        redirect_uri = get_google_ads_redirect_uri()

        flow = build_google_ads_auth_flow(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            project_id=project_id,
        )

        # Generate state: JWT-signed in managed mode, random otherwise
        if os.getenv("MANAGED_API_KEY"):
            instance_id = os.getenv("INSTANCE_ID")
            custom_state = create_oauth_state(instance_id=instance_id)
            auth_url, _ = flow.authorization_url(
                state=custom_state,
                prompt="consent",
                access_type="offline",
            )
            state = custom_state
        else:
            auth_url, state = flow.authorization_url(
                prompt="consent",
                access_type="offline",
            )

        # Persist flow + credentials needed by the callback
        _google_ads_oauth_flows[state] = {
            "flow": flow,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        logger.info("Generated Google Ads OAuth authorization URL")
        return OAuthInitiateResponse(auth_url=auth_url, state=state)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate Google Ads OAuth: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}")


@router.get("/google_ads/callback")
async def google_ads_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="State parameter for CSRF protection"),
    popup: bool = Query(False, description="Whether this is a popup window"),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> HTMLResponse:
    """
    Handle OAuth callback from Google for the Google Ads scope.

    Exchanges the authorization code for access and refresh tokens and
    stores them under the ``google_ads`` service name.
    """
    try:
        logger.info("Received OAuth callback for Google Ads")

        flow_data = _google_ads_oauth_flows.pop(state, None)
        if flow_data is None:
            raise ValueError(
                "OAuth state not found — the flow may have expired or the state parameter is invalid"
            )

        flow: Flow = flow_data["flow"]
        client_id: str = flow_data["client_id"]
        client_secret: str = flow_data["client_secret"]

        # In managed mode, verify the JWT signature
        if os.getenv("MANAGED_API_KEY") and not verify_oauth_state(state):
            raise ValueError("Invalid OAuth state signature")

        flow.fetch_token(code=code)
        store_google_ads_token(flow, credentials_repo, client_id, client_secret)

        logger.info("Google Ads OAuth flow completed successfully")

        if popup:
            return HTMLResponse(
                content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 1rem;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 500px;
                    }
                    .checkmark { font-size: 4rem; color: #48bb78; margin-bottom: 1rem; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">✓</div>
                    <p>Google Ads authentication successful! Closing window...</p>
                </div>
                <script>
                    if (window.opener) {
                        window.opener.postMessage({ type: 'oauth_success', service: 'google_ads' }, '*');
                    }
                    setTimeout(function() { window.close(); }, 1000);
                </script>
            </body>
            </html>
            """,
                status_code=200,
            )
        else:
            return HTMLResponse(
                content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 1rem;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 500px;
                    }
                    h1 { color: #2d3748; margin-bottom: 1rem; }
                    p { color: #4a5568; line-height: 1.6; }
                    .checkmark { font-size: 4rem; color: #48bb78; margin-bottom: 1rem; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">✓</div>
                    <h1>Authentication Successful!</h1>
                    <p>Your Google Ads account has been connected successfully.</p>
                    <p>You can now close this window and return to the chat to continue.</p>
                </div>
            </body>
            </html>
            """,
                status_code=200,
            )

    except Exception as e:
        logger.error(f"Google Ads OAuth callback failed: {e}")
        return HTMLResponse(
            content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                }}
                .container {{
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }}
                h1 {{ color: #2d3748; margin-bottom: 1rem; }}
                p {{ color: #4a5568; line-height: 1.6; }}
                .error {{ font-size: 4rem; color: #f56565; margin-bottom: 1rem; }}
                .error-details {{
                    background: #fed7d7;
                    color: #c53030;
                    padding: 1rem;
                    border-radius: 0.5rem;
                    margin-top: 1rem;
                    font-family: monospace;
                    font-size: 0.875rem;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error">✗</div>
                <h1>Authentication Failed</h1>
                <p>There was an error connecting your Google Ads account.</p>
                <p>Please try again or contact support if the problem persists.</p>
                <div class="error-details">{str(e)}</div>
            </div>
        </body>
        </html>
        """,
            status_code=500,
        )
