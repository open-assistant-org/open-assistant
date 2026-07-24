"""REST API endpoints for the MCP (Model Context Protocol) server integration."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.models.mcp import (
    McpCredentialsRequest,
    McpEnableRequest,
    McpOAuthStartRequest,
    McpOAuthStartResponse,
    McpServerCreateRequest,
    McpServerListItem,
    McpTestResult,
)
from src.services.mcp_service import McpSdkNotInstalled
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


def _get_mcp_service(request: Request):
    """Retrieve the McpService from app state."""
    mcp_service = getattr(request.app.state, "mcp_service", None)
    if mcp_service is None:
        raise HTTPException(status_code=503, detail="MCP service not available")
    return mcp_service


@router.get("", response_model=list[McpServerListItem])
async def list_servers(request: Request) -> list[McpServerListItem]:
    """List all configured MCP servers with their state."""
    return _get_mcp_service(request).list_servers()


@router.post("", response_model=McpServerListItem, status_code=201)
async def add_server(body: McpServerCreateRequest, request: Request) -> McpServerListItem:
    """Add an MCP server: connect, discover tools, and wire up the agent row."""
    mcp_service = _get_mcp_service(request)
    try:
        cfg = await mcp_service.add_server(body)
    except McpSdkNotInstalled as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add MCP server: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Could not connect to MCP server: {e}")

    for item in mcp_service.list_servers():
        if item.id == cfg.id:
            return item
    raise HTTPException(status_code=500, detail="Server added but not found in listing")


@router.put("/{server_id}/enable")
async def toggle_server(server_id: str, body: McpEnableRequest, request: Request) -> dict:
    """Enable or disable an MCP server (and its generated agent row)."""
    mcp_service = _get_mcp_service(request)
    try:
        await mcp_service.set_enabled(server_id, body.enabled)
        return {"success": True, "server_id": server_id, "enabled": body.enabled}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")


@router.put("/{server_id}/credentials")
async def save_server_credentials(
    server_id: str, body: McpCredentialsRequest, request: Request
) -> dict:
    """Update the stored (encrypted) auth header values for a server."""
    mcp_service = _get_mcp_service(request)
    try:
        mcp_service.save_credentials(server_id, body)
        return {"success": True, "server_id": server_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{server_id}/refresh", response_model=McpServerListItem)
async def refresh_server(server_id: str, request: Request) -> McpServerListItem:
    """Re-discover a server's tools and update the registry + agent row."""
    mcp_service = _get_mcp_service(request)
    try:
        await mcp_service.refresh_tools(server_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")
    except McpSdkNotInstalled as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not refresh MCP server: {e}")

    for item in mcp_service.list_servers():
        if item.id == server_id:
            return item
    raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")


@router.get("/{server_id}/test", response_model=McpTestResult)
async def test_server(server_id: str, request: Request) -> McpTestResult:
    """Test connectivity to an MCP server."""
    mcp_service = _get_mcp_service(request)
    try:
        return await mcp_service.test_server(server_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")


@router.delete("/{server_id}")
async def delete_server(server_id: str, request: Request) -> dict:
    """Delete an MCP server, its tools, credentials, and agent row."""
    mcp_service = _get_mcp_service(request)
    try:
        await mcp_service.delete_server(server_id)
        return {"success": True, "server_id": server_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")


# ============================================================================
# OAuth 2.1 endpoints
# ============================================================================


@router.post("/{server_id}/oauth/start", response_model=McpOAuthStartResponse)
async def oauth_start(
    server_id: str, body: McpOAuthStartRequest, request: Request
) -> McpOAuthStartResponse:
    """Begin the OAuth 2.1 PKCE authorization flow for an MCP server.

    Returns the authorization URL to redirect the user to. The client should
    open this URL in the browser. After authorization, the provider redirects
    to ``redirect_uri`` (which must point to the ``/api/mcp/oauth/callback``
    endpoint on this server).
    """
    mcp_service = _get_mcp_service(request)
    try:
        return await mcp_service.oauth_start(server_id, body.redirect_uri)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"OAuth start failed for '{server_id}': {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"OAuth flow failed: {e}")


@router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
) -> RedirectResponse:
    """OAuth 2.1 redirect callback — exchanges the authorization code for tokens.

    This endpoint is registered as the ``redirect_uri`` during dynamic client
    registration. After a successful exchange, the user is redirected to the
    Settings page with ``?mcp_connected={server_id}`` so the UI can confirm
    success. On failure, ``?mcp_error=...`` is appended instead.
    """
    if error:
        desc = error_description or error
        logger.warning(f"OAuth callback received error: {error} — {desc}")
        return RedirectResponse(f"/settings?mcp_error={desc}", status_code=302)

    if not code or not state:
        return RedirectResponse("/settings?mcp_error=missing+code+or+state", status_code=302)

    mcp_service = _get_mcp_service(request)
    try:
        server_id = await mcp_service.oauth_callback(code, state)
        return RedirectResponse(f"/settings?mcp_connected={server_id}", status_code=302)
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}", exc_info=True)
        return RedirectResponse(f"/settings?mcp_error={str(e)[:200]}", status_code=302)
