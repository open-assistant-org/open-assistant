"""REST API endpoints for the plugin system."""

from fastapi import APIRouter, HTTPException, Request

from src.models.plugin import (
    PluginConfigResponse,
    PluginCredentialsRequest,
    PluginEnableRequest,
    PluginListItem,
    PluginTestResult,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def _get_plugin_service(request: Request):
    """Retrieve the PluginService from app state."""
    plugin_service = getattr(request.app.state, "plugin_service", None)
    if plugin_service is None:
        raise HTTPException(status_code=503, detail="Plugin service not available")
    return plugin_service


@router.get("", response_model=list[PluginListItem])
async def list_plugins(request: Request) -> list[PluginListItem]:
    """List all plugins with their current enable/credential state."""
    plugin_service = _get_plugin_service(request)
    return plugin_service.list_plugins()


@router.get("/{plugin_id}/config", response_model=PluginConfigResponse)
async def get_plugin_config(plugin_id: str, request: Request) -> PluginConfigResponse:
    """Get current non-sensitive config values and credential presence for a plugin."""
    plugin_service = _get_plugin_service(request)
    try:
        data = plugin_service.get_plugin_config(plugin_id)
        return PluginConfigResponse(**data)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.put("/{plugin_id}/enable")
async def toggle_plugin(plugin_id: str, body: PluginEnableRequest, request: Request) -> dict:
    """Enable or disable a plugin."""
    plugin_service = _get_plugin_service(request)
    try:
        plugin_service.set_enabled(plugin_id, body.enabled)
        return {"success": True, "plugin_id": plugin_id, "enabled": body.enabled}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.put("/{plugin_id}/credentials")
async def save_plugin_credentials(
    plugin_id: str, body: PluginCredentialsRequest, request: Request
) -> dict:
    """Save credentials and config values for a plugin."""
    plugin_service = _get_plugin_service(request)
    try:
        plugin_service.save_credentials(plugin_id, body)
        return {"success": True, "plugin_id": plugin_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.get("/{plugin_id}/test", response_model=PluginTestResult)
async def test_plugin_connection(plugin_id: str, request: Request) -> PluginTestResult:
    """Test connectivity to a plugin's base URL."""
    plugin_service = _get_plugin_service(request)
    try:
        result = await plugin_service.test_plugin(plugin_id)
        return PluginTestResult(**result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.post("", response_model=PluginListItem, status_code=201)
async def install_plugin(body: dict, request: Request) -> PluginListItem:
    """
    Validate and install a user-provided plugin definition JSON.

    The body must be a valid plugin definition. See ``src/plugins/plugin_schema.json``
    for the full schema.
    """
    plugin_service = _get_plugin_service(request)
    try:
        defn = plugin_service.install_user_plugin(body)
        # Return the list item for the newly installed plugin
        items = plugin_service.list_plugins()
        for item in items:
            if item.id == defn.id:
                return item
        # Fallback
        return PluginListItem(
            id=defn.id,
            display_name=defn.display_name,
            description=defn.description,
            icon=defn.icon,
            enabled=False,
            is_builtin=False,
            has_credentials=False,
            auth_type=defn.auth.type,
            endpoint_count=len(defn.endpoints),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to install plugin: {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Invalid plugin definition: {e}")


@router.get("/{plugin_id}/definition")
async def get_plugin_definition(plugin_id: str, request: Request) -> dict:
    """Return the raw JSON definition for a user-installed plugin."""
    plugin_service = _get_plugin_service(request)
    try:
        return plugin_service.get_user_plugin_definition(plugin_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put("/{plugin_id}/definition", response_model=PluginListItem)
async def update_plugin_definition(plugin_id: str, body: dict, request: Request) -> PluginListItem:
    """Validate and overwrite a user-installed plugin definition."""
    plugin_service = _get_plugin_service(request)
    try:
        defn = plugin_service.update_user_plugin(plugin_id, body)
        items = plugin_service.list_plugins()
        for item in items:
            if item.id == defn.id:
                return item
        return PluginListItem(
            id=defn.id,
            display_name=defn.display_name,
            description=defn.description,
            icon=defn.icon,
            enabled=False,
            is_builtin=False,
            has_credentials=False,
            auth_type=defn.auth.type,
            endpoint_count=len(defn.endpoints),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update plugin: {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Invalid plugin definition: {e}")


@router.delete("/{plugin_id}")
async def delete_plugin(plugin_id: str, request: Request) -> dict:
    """Delete a user-installed plugin. Built-in plugins cannot be deleted."""
    plugin_service = _get_plugin_service(request)
    try:
        plugin_service.delete_user_plugin(plugin_id)
        return {"success": True, "plugin_id": plugin_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
