"""Plugin service — loads JSON plugin definitions and executes their endpoints as LLM tools."""

import base64
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.core.tools.registry import Tool, get_tool_registry
from src.core.tools.schema import ToolSchema
from src.models.plugin import (
    PluginAuth,
    PluginCredentialsRequest,
    PluginDefinition,
    PluginListItem,
)
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)

BUILTIN_PLUGINS_DIR = Path(__file__).parent.parent / "plugins" / "builtins"


class PluginService(BaseService):
    """
    Manages plugin definitions and executes their HTTP endpoints.

    Plugins are JSON files that define REST API endpoints.  Built-in plugins
    live in ``src/plugins/builtins/``; user-installed ones in ``data/plugins/``.
    Each endpoint is registered as an LLM tool named ``plugin_{id}_{endpoint}``.
    """

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
        data_dir: str = "data",
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)
        self.user_plugins_dir = Path(data_dir) / "plugins"
        self.user_plugins_dir.mkdir(parents=True, exist_ok=True)

        self._definitions: Dict[str, PluginDefinition] = {}
        self._builtin_ids: set = set()
        # plugin_id → (jwt_token, expires_at) for api_key_with_jwt auth type
        self._jwt_cache: Dict[str, Tuple[str, datetime]] = {}

        self._load_all_definitions()
        self._migrate_legacy_toggl()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all_definitions(self) -> None:
        """Load all plugin definitions from built-in and user directories."""
        for path in sorted(BUILTIN_PLUGINS_DIR.glob("*.json")):
            try:
                defn = PluginDefinition.model_validate_json(path.read_text())
                self._definitions[defn.id] = defn
                self._builtin_ids.add(defn.id)
                logger.debug(f"Loaded built-in plugin: {defn.id}")
            except Exception as e:
                logger.error(f"Failed to load built-in plugin {path.name}: {e}")

        for path in sorted(self.user_plugins_dir.glob("*.json")):
            try:
                defn = PluginDefinition.model_validate_json(path.read_text())
                self._definitions[defn.id] = defn
                logger.debug(f"Loaded user plugin: {defn.id}")
            except Exception as e:
                logger.error(f"Failed to load user plugin {path.name}: {e}")

        logger.info(
            f"Plugin system loaded {len(self._definitions)} plugins "
            f"({len(self._builtin_ids)} built-in, "
            f"{len(self._definitions) - len(self._builtin_ids)} user-installed)"
        )

    def _migrate_legacy_toggl(self) -> None:
        """
        One-time migration: copy old toggl credentials (service_name='toggl')
        to the plugin namespace (service_name='plugin_toggl').
        """
        try:
            old_creds = self.credentials_repo.get("toggl")
            new_creds = self.credentials_repo.get("plugin_toggl")
            if old_creds and not new_creds:
                # Old credentials stored {"value": "<api_token>"}
                token = old_creds.get("value") or old_creds.get("api_token", "")
                if token:
                    self.credentials_repo.store(
                        service_name="plugin_toggl",
                        credential_type="api_key",
                        credential_data={"token": token},
                    )
                    logger.info("Migrated legacy Toggl credentials to plugin namespace")
        except Exception as e:
            logger.warning(f"Legacy Toggl credential migration skipped: {e}")

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register_plugin_tools(self) -> None:
        """Register all plugin endpoints as tools in the global ToolRegistry."""
        registry = get_tool_registry()
        count = 0
        for plugin_id, defn in self._definitions.items():
            for endpoint in defn.endpoints:
                tool = self._create_tool(plugin_id, defn, endpoint)
                registry.register(tool)
                count += 1
        logger.info(f"Registered {count} plugin tools in ToolRegistry")

    def _create_tool(self, plugin_id: str, defn: PluginDefinition, endpoint) -> Tool:
        """Build a Tool object for a single plugin endpoint."""
        tool_name = f"plugin_{plugin_id}_{endpoint.name}"

        # Build JSON Schema for the endpoint's parameters
        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param in endpoint.parameters:
            prop: Dict[str, Any] = {"description": param.description}
            if param.type == "integer":
                prop["type"] = "integer"
            elif param.type == "number":
                prop["type"] = "number"
            elif param.type == "boolean":
                prop["type"] = "boolean"
            else:
                prop["type"] = "string"

            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        schema = ToolSchema(
            name=tool_name,
            description=f"[{defn.display_name}] {endpoint.description}",
            parameters={
                "type": "object",
                "properties": properties,
                "required": required,
            },
        )

        return Tool(
            schema=schema,
            executor=None,  # execution is routed through PluginService.execute_tool
            service_name=f"plugin_{plugin_id}",
            requires_auth=True,
        )

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a plugin tool call.

        tool_name format: ``plugin_{plugin_id}_{endpoint_name}``
        """
        # Strip the leading "plugin_" prefix, then split on the first underscore
        # sequence that matches a known plugin id.
        without_prefix = tool_name[len("plugin_") :]

        plugin_id = None
        endpoint_name = None
        for pid in self._definitions:
            if without_prefix.startswith(pid + "_"):
                plugin_id = pid
                endpoint_name = without_prefix[len(pid) + 1 :]
                break

        if not plugin_id or not endpoint_name:
            raise ValueError(f"Cannot resolve plugin tool: {tool_name}")

        if not self._is_plugin_enabled(plugin_id):
            raise ValueError(f"Plugin '{plugin_id}' is disabled")

        return await self._execute_endpoint(plugin_id, endpoint_name, arguments)

    async def _execute_endpoint(
        self, plugin_id: str, endpoint_name: str, params: Dict[str, Any]
    ) -> Any:
        """Make the HTTP call for a plugin endpoint."""
        defn = self._definitions[plugin_id]
        endpoint = next((e for e in defn.endpoints if e.name == endpoint_name), None)
        if not endpoint:
            raise ValueError(f"Endpoint '{endpoint_name}' not found in plugin '{plugin_id}'")

        # Load non-sensitive config values (e.g. organization, site_url)
        config_values = self._load_config_values(plugin_id, defn)

        # Load credentials
        raw_creds = self.credentials_repo.get(f"plugin_{plugin_id}") or {}
        # Credentials are stored as {"credential_type": ..., "credential_data": {...}, ...}
        creds = raw_creds.get("credential_data", raw_creds)

        # Build auth headers (may perform an async JWT fetch for api_key_with_jwt)
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        headers.update(await self._resolve_auth_headers(plugin_id, defn, creds, defn.base_url))

        # Resolve base URL (may contain {config_field} placeholders)
        base_url = defn.base_url.rstrip("/")
        # For plugins with a site_url config field, override base_url
        if "site_url" in config_values:
            base_url = config_values["site_url"].rstrip("/")
        else:
            try:
                base_url = base_url.format(**config_values)
            except KeyError:
                pass  # unresolved placeholders stay as-is

        # Build path params from endpoint parameters + config values
        path_params: Dict[str, Any] = {**config_values}
        query_params: Dict[str, Any] = {}
        body_params: Dict[str, Any] = {}
        header_params: Dict[str, str] = {}

        for param in endpoint.parameters:
            value = params.get(param.name)
            if value is None and param.default is not None:
                value = param.default
            if value is None:
                continue
            loc = param.in_
            if loc == "path":
                path_params[param.name] = value
            elif loc == "query":
                query_params[param.name] = value
            elif loc == "body":
                body_params[param.name] = value
            elif loc == "header":
                header_params[param.name] = str(value)

        headers.update(header_params)

        # Substitute path params into the URL
        path = endpoint.path
        try:
            path = path.format(**path_params)
        except KeyError as e:
            raise ValueError(f"Missing path parameter {e} for endpoint '{endpoint_name}'")

        url = base_url + path

        # For body endpoints, wrap body params in the expected structure
        json_body: Optional[Dict[str, Any]] = None
        if body_params:
            # Special case: Jira create_issue needs a specific structure
            if plugin_id == "jira_cloud" and endpoint_name == "create_issue":
                json_body = _build_jira_create_issue_body(body_params)
            # Special case: Jira add_comment
            elif plugin_id == "jira_cloud" and endpoint_name == "add_comment":
                json_body = _build_jira_comment_body(body_params)
            # Azure DevOps create_work_item uses JSON Patch format
            elif plugin_id == "azure_devops" and endpoint_name == "create_work_item":
                json_body = _build_ado_work_item_body(body_params)
            elif plugin_id == "azure_devops" and endpoint_name == "update_work_item":
                json_body = _build_ado_update_work_item_body(body_params)
            elif plugin_id == "azure_devops" and endpoint_name == "move_work_item":
                json_body = _build_ado_move_work_item_body(
                    body_params, path_params.get("organization", "")
                )
            elif plugin_id == "azure_devops" and endpoint_name == "add_work_item_comment":
                json_body = _build_ado_add_comment_body(body_params)
            else:
                json_body = body_params

        # ADO JSON Patch operations require application/json-patch+json.
        # httpx's json= always sends application/json, so for these endpoints
        # we override the header and pass pre-serialised bytes via content=.
        use_ado_patch_content_type = (
            plugin_id == "azure_devops"
            and endpoint_name in _ADO_JSON_PATCH_ENDPOINTS
            and json_body is not None
        )
        if use_ado_patch_content_type:
            headers["Content-Type"] = "application/json-patch+json"

        self._log_web_request(
            service_name=f"plugin_{plugin_id}",
            action=endpoint_name,
            endpoint=url,
            method=endpoint.method,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=endpoint.method,
                url=url,
                headers=headers,
                params=query_params if query_params else None,
                content=json.dumps(json_body) if use_ado_patch_content_type else None,
                json=json_body if not use_ado_patch_content_type else None,
            )

            if response.status_code == 401 and defn.auth.type == "api_key_with_jwt":
                # Token was rejected — evict the stale cache entry and retry once
                self._jwt_cache.pop(plugin_id, None)
                retry_headers: Dict[str, str] = {"Content-Type": "application/json"}
                retry_headers.update(
                    await self._resolve_auth_headers(plugin_id, defn, creds, defn.base_url)
                )
                if use_ado_patch_content_type:
                    retry_headers["Content-Type"] = "application/json-patch+json"
                retry_headers.update(header_params)
                response = await client.request(
                    method=endpoint.method,
                    url=url,
                    headers=retry_headers,
                    params=query_params if query_params else None,
                    content=json.dumps(json_body) if use_ado_patch_content_type else None,
                    json=json_body if not use_ado_patch_content_type else None,
                )

        response.raise_for_status()

        # Return None body as empty dict
        if not response.content:
            return {}

        try:
            return response.json()
        except Exception:
            return {"raw": response.text}

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def _resolve_auth_headers(
        self,
        plugin_id: str,
        defn: PluginDefinition,
        creds: Dict[str, Any],
        base_url: str,
    ) -> Dict[str, str]:
        """Dispatch to the correct auth header builder (sync or async)."""
        if defn.auth.type == "api_key_with_jwt":
            return await self._build_api_key_with_jwt_headers(plugin_id, defn.auth, creds, base_url)
        return self._build_auth_headers(defn.auth, creds)

    def _build_auth_headers(self, auth: PluginAuth, credentials: Dict[str, Any]) -> Dict[str, str]:
        """Build HTTP authentication headers for the three simple auth types."""
        auth_type = auth.type

        if auth_type == "bearer":
            token = credentials.get("token", "")
            return {"Authorization": f"Bearer {token}"}

        elif auth_type == "header":
            header_name = auth.header_name or "X-API-Key"
            token = credentials.get("token", "")
            return {header_name: token}

        elif auth_type == "basic":
            if auth.fixed_password is not None:
                # e.g. Toggl: username=token, password="api_token"
                username = credentials.get("token", "")
                password = auth.fixed_password
            else:
                username = credentials.get("username", "")
                password = credentials.get("password", "")

            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}

        return {}

    async def _build_api_key_with_jwt_headers(
        self,
        plugin_id: str,
        auth: PluginAuth,
        creds: Dict[str, Any],
        base_url: str,
    ) -> Dict[str, str]:
        """Build headers for api_key_with_jwt: optional static API key header + JWT from login."""
        token_prefix = auth.token_prefix or "Bearer"
        jwt = await self._get_jwt(plugin_id, auth, creds, base_url)
        headers: Dict[str, str] = {"Authorization": f"{token_prefix} {jwt}"}
        api_key = creds.get("api_key", "")
        if api_key and auth.api_key_header:
            headers[auth.api_key_header] = api_key
        return headers

    async def _get_jwt(
        self,
        plugin_id: str,
        auth: PluginAuth,
        creds: Dict[str, Any],
        base_url: str,
    ) -> str:
        """Return a valid JWT for the plugin, fetching a new one if the cached one is stale."""
        now = datetime.now(timezone.utc)
        cached = self._jwt_cache.get(plugin_id)
        if cached:
            jwt_token, expires_at = cached
            if expires_at > now + timedelta(seconds=60):
                return jwt_token

        token_endpoint = auth.token_endpoint or "/token"
        url = base_url.rstrip("/") + token_endpoint

        login_headers: Dict[str, str] = {"Content-Type": "application/json"}
        api_key = creds.get("api_key", "")
        if api_key and auth.api_key_header:
            login_headers[auth.api_key_header] = api_key

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers=login_headers,
                json={"username": creds.get("username", ""), "password": creds.get("password", "")},
            )
        response.raise_for_status()

        data = response.json()
        token_field = auth.token_field or "access_token"
        jwt_token = data.get(token_field, "")
        if not jwt_token:
            raise ValueError(f"Field '{token_field}' not found in login response from {url}")

        expires_at = self._parse_jwt_expiry(jwt_token, default_ttl_minutes=55)
        self._jwt_cache[plugin_id] = (jwt_token, expires_at)
        logger.debug(
            f"Fetched new JWT for plugin '{plugin_id}', expires at {expires_at.isoformat()}"
        )
        return jwt_token

    @staticmethod
    def _parse_jwt_expiry(jwt_token: str, default_ttl_minutes: int = 55) -> datetime:
        """Extract exp from a JWT payload; fall back to default TTL if unparseable."""
        now = datetime.now(timezone.utc)
        try:
            payload_b64 = jwt_token.split(".")[1]
            # Restore standard base64 padding
            padding = (4 - len(payload_b64) % 4) % 4
            payload = json.loads(base64.b64decode(payload_b64 + "=" * padding))
            if "exp" in payload:
                return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        except Exception:
            pass
        return now + timedelta(minutes=default_ttl_minutes)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_plugin_enabled(self, plugin_id: str) -> bool:
        """Check if a plugin is enabled, handling both bool and string storage."""
        value = self.settings_repo.get(f"plugin.{plugin_id}.enabled")
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        # Backwards compat: value stored as string before the fix
        return str(value).lower() == "true"

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _load_config_values(self, plugin_id: str, defn: PluginDefinition) -> Dict[str, str]:
        """Load non-sensitive config field values from the settings table."""
        config: Dict[str, str] = {}
        for field in defn.config_fields:
            if not field.sensitive:
                value = self.settings_repo.get(f"plugin.{plugin_id}.{field.key}")
                if value:
                    config[field.key] = str(value)
        return config

    # ------------------------------------------------------------------
    # Plugin management (CRUD)
    # ------------------------------------------------------------------

    def list_plugins(self) -> List[PluginListItem]:
        """Return all plugins with their current enable state."""
        result = []
        for plugin_id, defn in self._definitions.items():
            enabled = self._is_plugin_enabled(plugin_id)
            has_creds = bool(self.credentials_repo.get(f"plugin_{plugin_id}"))
            result.append(
                PluginListItem(
                    id=plugin_id,
                    display_name=defn.display_name,
                    description=defn.description,
                    icon=defn.icon,
                    enabled=enabled,
                    is_builtin=plugin_id in self._builtin_ids,
                    has_credentials=has_creds,
                    auth_type=defn.auth.type,
                    has_fixed_password=bool(defn.auth.fixed_password),
                    endpoint_count=len(defn.endpoints),
                    config_fields=[
                        {
                            "key": f.key,
                            "display_name": f.display_name,
                            "description": f.description,
                            "required": f.required,
                            "sensitive": f.sensitive,
                            "placeholder": f.placeholder,
                        }
                        for f in defn.config_fields
                    ],
                )
            )
        return result

    def get_plugin(self, plugin_id: str) -> Optional[PluginDefinition]:
        return self._definitions.get(plugin_id)

    def get_plugin_config(self, plugin_id: str) -> Dict[str, Any]:
        """Return current non-sensitive config values + credential presence for a plugin."""
        defn = self._definitions.get(plugin_id)
        if not defn:
            raise KeyError(f"Plugin '{plugin_id}' not found")

        config_values: Dict[str, str] = {}
        for field in defn.config_fields:
            if not field.sensitive:
                value = self.settings_repo.get(f"plugin.{plugin_id}.{field.key}") or ""
                config_values[field.key] = value

        return {
            "id": plugin_id,
            "config_values": config_values,
            "has_credentials": bool(self.credentials_repo.get(f"plugin_{plugin_id}")),
        }

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        """Enable or disable a plugin."""
        if plugin_id not in self._definitions:
            raise KeyError(f"Plugin '{plugin_id}' not found")
        self.settings_repo.set(f"plugin.{plugin_id}.enabled", enabled, value_type="bool")

    def save_credentials(self, plugin_id: str, request: PluginCredentialsRequest) -> None:
        """Save credentials and config values for a plugin."""
        defn = self._definitions.get(plugin_id)
        if not defn:
            raise KeyError(f"Plugin '{plugin_id}' not found")

        # Build credential blob
        cred_data: Dict[str, str] = {}
        auth_type = defn.auth.type

        if auth_type == "bearer" or auth_type == "header":
            if request.token:
                cred_data["token"] = request.token
        elif auth_type == "basic":
            if defn.auth.fixed_password is not None:
                # Only token (username) is needed
                if request.token:
                    cred_data["token"] = request.token
            else:
                if request.username:
                    cred_data["username"] = request.username
                if request.password:
                    cred_data["password"] = request.password
        elif auth_type == "api_key_with_jwt":
            if request.api_key:
                cred_data["api_key"] = request.api_key
            if request.username:
                cred_data["username"] = request.username
            if request.password:
                cred_data["password"] = request.password
            # Invalidate cached JWT whenever credentials change
            self._jwt_cache.pop(plugin_id, None)

        # Sensitive config fields also go into credentials
        for field in defn.config_fields:
            if field.sensitive and field.key in request.config:
                cred_data[field.key] = request.config[field.key]

        if cred_data:
            self.credentials_repo.store(
                service_name=f"plugin_{plugin_id}",
                credential_type="api_key",
                credential_data=cred_data,
            )

        # Non-sensitive config fields go into settings
        for field in defn.config_fields:
            if not field.sensitive and field.key in request.config:
                self.settings_repo.set(f"plugin.{plugin_id}.{field.key}", request.config[field.key])

    def install_user_plugin(self, plugin_json: Dict[str, Any]) -> PluginDefinition:
        """Validate and install a user-provided plugin definition."""
        defn = PluginDefinition.model_validate(plugin_json)

        if defn.id in self._builtin_ids:
            raise ValueError(
                f"Plugin id '{defn.id}' conflicts with a built-in plugin. Choose a different id."
            )

        path = self.user_plugins_dir / f"{defn.id}.json"
        path.write_text(json.dumps(plugin_json, indent=2, ensure_ascii=False))

        self._definitions[defn.id] = defn

        # Register tools dynamically
        for endpoint in defn.endpoints:
            tool = self._create_tool(defn.id, defn, endpoint)
            get_tool_registry().register(tool)

        logger.info(f"Installed user plugin: {defn.id} ({len(defn.endpoints)} endpoints)")
        return defn

    def get_user_plugin_definition(self, plugin_id: str) -> Dict[str, Any]:
        """Return the raw JSON dict for a user-installed plugin."""
        if plugin_id not in self._definitions:
            raise KeyError(f"Plugin '{plugin_id}' not found")
        if plugin_id in self._builtin_ids:
            raise PermissionError(f"Built-in plugin '{plugin_id}' cannot be edited")
        path = self.user_plugins_dir / f"{plugin_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def update_user_plugin(self, plugin_id: str, plugin_json: Dict[str, Any]) -> PluginDefinition:
        """Validate and overwrite an existing user-installed plugin definition."""
        if plugin_id not in self._definitions:
            raise KeyError(f"Plugin '{plugin_id}' not found")
        if plugin_id in self._builtin_ids:
            raise PermissionError(f"Built-in plugin '{plugin_id}' cannot be edited")

        defn = PluginDefinition.model_validate(plugin_json)
        if defn.id != plugin_id:
            raise ValueError(
                f"Plugin id in JSON ('{defn.id}') must match the existing id ('{plugin_id}'). "
                "To change a plugin's id, delete it and re-install."
            )

        # Unregister old tools, register new ones
        get_tool_registry().unregister_by_prefix(f"plugin_{plugin_id}_")
        for endpoint in defn.endpoints:
            get_tool_registry().register(self._create_tool(plugin_id, defn, endpoint))

        path = self.user_plugins_dir / f"{plugin_id}.json"
        path.write_text(json.dumps(plugin_json, indent=2, ensure_ascii=False))
        self._definitions[plugin_id] = defn

        logger.info(f"Updated user plugin: {plugin_id} ({len(defn.endpoints)} endpoints)")
        return defn

    def delete_user_plugin(self, plugin_id: str) -> None:
        """Delete a user-installed plugin. Built-in plugins cannot be deleted."""
        if plugin_id not in self._definitions:
            raise KeyError(f"Plugin '{plugin_id}' not found")
        if plugin_id in self._builtin_ids:
            raise PermissionError(f"Built-in plugin '{plugin_id}' cannot be deleted")

        path = self.user_plugins_dir / f"{plugin_id}.json"
        if path.exists():
            path.unlink()

        del self._definitions[plugin_id]

        # Clean up settings and credentials
        self.settings_repo.set(f"plugin.{plugin_id}.enabled", False, value_type="bool")
        logger.info(f"Deleted user plugin: {plugin_id}")

    async def test_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """Test connectivity to a plugin's base URL."""
        defn = self._definitions.get(plugin_id)
        if not defn:
            raise KeyError(f"Plugin '{plugin_id}' not found")

        raw_creds = self.credentials_repo.get(f"plugin_{plugin_id}") or {}
        creds = raw_creds.get("credential_data", raw_creds)

        config_values = self._load_config_values(plugin_id, defn)
        base_url = defn.base_url
        if "site_url" in config_values:
            base_url = config_values["site_url"]
        else:
            try:
                base_url = base_url.format(**config_values)
            except KeyError:
                pass

        try:
            headers = await self._resolve_auth_headers(plugin_id, defn, creds, base_url)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.head(base_url, headers=headers, follow_redirects=True)
            # HEAD returning 4xx may still mean the server is reachable
            if response.status_code < 500:
                return {"success": True, "message": f"Connected ({response.status_code})"}
            return {"success": False, "message": f"Server error {response.status_code}"}
        except httpx.ConnectError:
            return {"success": False, "message": f"Could not connect to {base_url}"}
        except httpx.TimeoutException:
            return {"success": False, "message": "Connection timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ------------------------------------------------------------------
    # Metadata for Tools assignment screen
    # ------------------------------------------------------------------

    def get_tool_metadata(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return tool metadata grouped by plugin, for the Tools assignment screen.
        Only includes enabled plugins.
        """
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for plugin_id, defn in self._definitions.items():
            enabled = self._is_plugin_enabled(plugin_id)
            if not enabled:
                continue

            group_key = f"plugin_{plugin_id}"
            groups[group_key] = [
                {
                    "name": f"plugin_{plugin_id}_{ep.name}",
                    "display_name": ep.display_name,
                    "description": ep.description,
                    "category": "plugin",
                    "service": group_key,
                }
                for ep in defn.endpoints
            ]

        return groups


# ------------------------------------------------------------------
# Helpers for API-specific body formats
# ------------------------------------------------------------------

# ADO work item endpoints that use JSON Patch format and therefore require
# Content-Type: application/json-patch+json rather than application/json.
_ADO_JSON_PATCH_ENDPOINTS = {"create_work_item", "update_work_item", "move_work_item"}


def _build_jira_create_issue_body(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build the Jira create-issue request body from flat parameters."""
    fields: Dict[str, Any] = {
        "project": {"key": params.get("project_key", "")},
        "summary": params.get("summary", ""),
        "issuetype": {"name": params.get("issue_type", "Task")},
    }
    if "description" in params:
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": params["description"]}],
                }
            ],
        }
    if "priority" in params:
        fields["priority"] = {"name": params["priority"]}
    return {"fields": fields}


def _build_jira_comment_body(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build the Jira add-comment request body."""
    return {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": params.get("body", "")}],
                }
            ],
        }
    }


def _build_ado_work_item_body(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the Azure DevOps JSON Patch body for work item creation."""
    patch: List[Dict[str, Any]] = [
        {"op": "add", "path": "/fields/System.Title", "value": params.get("title", "")},
    ]
    if "description" in params:
        patch.append(
            {
                "op": "add",
                "path": "/fields/System.Description",
                "value": params["description"],
            }
        )
    return patch


def _build_ado_update_work_item_body(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the Azure DevOps JSON Patch body for work item field updates."""
    field_map = {
        "title": "System.Title",
        "description": "System.Description",
        "acceptance_criteria": "Microsoft.VSTS.Common.AcceptanceCriteria",
        "state": "System.State",
        "iteration_path": "System.IterationPath",
        "area_path": "System.AreaPath",
        "priority": "Microsoft.VSTS.Common.Priority",
        "assigned_to": "System.AssignedTo",
        "tags": "System.Tags",
    }
    patch: List[Dict[str, Any]] = [
        {"op": "add", "path": f"/fields/{ado_field}", "value": params[key]}
        for key, ado_field in field_map.items()
        if key in params
    ]
    if not patch:
        raise ValueError("update_work_item requires at least one of: " + ", ".join(field_map))
    return patch


def _build_ado_move_work_item_body(
    body_params: Dict[str, Any], organization: str
) -> List[Dict[str, Any]]:
    """Build the Azure DevOps JSON Patch body for re-parenting a work item."""
    patch: List[Dict[str, Any]] = []
    if "current_parent_relation_index" in body_params:
        patch.append(
            {"op": "remove", "path": f"/relations/{body_params['current_parent_relation_index']}"}
        )
    parent_url = (
        f"https://dev.azure.com/{organization}/_apis/wit/workitems/{body_params['new_parent_id']}"
    )
    patch.append(
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": parent_url,
                "attributes": {"comment": ""},
            },
        }
    )
    return patch


def _build_ado_add_comment_body(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build the Azure DevOps add-comment request body."""
    return {"text": params.get("text", "")}
