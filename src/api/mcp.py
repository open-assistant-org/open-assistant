"""REST API endpoints for the MCP (Model Context Protocol) server integration."""

from fastapi import APIRouter, HTTPException, Request

from src.models.mcp import (
    McpCredentialsRequest,
    McpEnableRequest,
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
