"""Service for managing MCP (Model Context Protocol) servers.

Phase 1: connect to remote MCP servers over Streamable HTTP, discover their
tools, register each tool in the global ToolRegistry as ``mcp_{id}_{tool}``, and
execute tool calls by opening a short-lived session per call.

Phase 2: launch local MCP servers as stdio subprocesses (e.g. ``npx …`` or
``uvx …``) and keep the subprocess alive across calls via a per-server
``_StdioSessionManager``.

Design notes
------------
* This mirrors :class:`~src.services.plugin_service.PluginService`: dynamic tools
  with ``service_name=f"mcp_{id}"`` and ``executor=None``; execution is routed
  through :meth:`execute_tool` by :class:`~src.core.tools.executor.ToolExecutor`.
* The ``mcp`` SDK is imported lazily inside the methods that actually talk to a
  server, so the application still boots (and can register cached tools) even if
  the package is not installed yet.
* Auth/credentials: header *values* (HTTP) and env var *values* (stdio) are
  stored encrypted in ``service_credentials`` under ``mcp_{id}`` as
  ``{"headers": {...}, "env": {...}}``. Config JSON holds only names, never
  secret values.
* Adding a server also creates an agent/skill row so the server's tools are
  triggered by the user's chosen intent keywords — see ``docs/mcp-servers.md``
  and ``src/models/skill.py`` for why agents == skills.
"""

import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.agents.registry import AgentRegistry
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.core.tools.registry import Tool, get_tool_registry
from src.core.tools.schema import ToolSchema, _sanitize_property
from src.models.mcp import (
    McpCredentialsRequest,
    McpDiscoveredTool,
    McpServerConfig,
    McpServerCreateRequest,
    McpServerListItem,
    McpTestResult,
)
from src.services.base import BaseService
from src.utils.logger import get_logger
from src.utils.settings import settings_truthy

logger = get_logger(__name__)

# How long (seconds) to wait when connecting to / calling an MCP server.
_MCP_TIMEOUT_SECONDS = 30.0


class McpSdkNotInstalled(RuntimeError):
    """Raised when an operation needs the ``mcp`` SDK but it is not installed."""


def _describe_exception(exc: BaseException) -> str:
    """Flatten an exception (incl. anyio/TaskGroup ExceptionGroups) to a message.

    The MCP client runs its transport inside a task group, so a genuine failure
    surfaces wrapped in an ``ExceptionGroup`` whose ``str`` is the unhelpful
    "unhandled errors in a TaskGroup (N sub-exceptions)". Recurse into the group
    and report the underlying leaf causes instead.
    """
    leaves: List[str] = []

    def _collect(e: BaseException) -> None:
        sub_exceptions = getattr(e, "exceptions", None)
        if sub_exceptions:
            for child in sub_exceptions:
                _collect(child)
        else:
            text = str(e).strip()
            leaves.append(f"{type(e).__name__}: {text}" if text else type(e).__name__)

    _collect(exc)
    # De-duplicate while preserving order.
    seen: set = set()
    unique = [x for x in leaves if not (x in seen or seen.add(x))]
    return "; ".join(unique) or str(exc) or type(exc).__name__


class _StdioSessionManager:
    """Manages a persistent stdio subprocess connection to one MCP server.

    The subprocess is started lazily on the first call and kept alive across
    subsequent calls. If the process dies, the next call reconnects. Thread
    safety is provided by an ``asyncio.Lock``.
    """

    def __init__(self, server_id: str, command: str, args: List[str], env: Dict[str, str]):
        self._server_id = server_id
        self._command = command
        self._args = args
        self._env = env
        self._lock = asyncio.Lock()
        self._session: Any = None
        self._exit_stack: Optional[AsyncExitStack] = None

    async def run(self, fn: Callable[[Any], Awaitable[Any]]) -> Any:
        """Ensure the subprocess session is alive, then run ``fn(session)``."""
        async with self._lock:
            if self._session is None:
                await self._connect()
        try:
            return await fn(self._session)
        except Exception:
            # Session may be dead (process exited, pipe broken…); invalidate
            # it so the next call reconnects cleanly.
            async with self._lock:
                await self._close_nolock()
            raise

    async def _connect(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env or None,
        )
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=_MCP_TIMEOUT_SECONDS)
        except Exception:
            await stack.aclose()
            raise
        self._exit_stack = stack
        self._session = session

    async def close(self) -> None:
        async with self._lock:
            await self._close_nolock()

    async def _close_nolock(self) -> None:
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass  # best-effort teardown; process may already be dead
            self._exit_stack = None
            self._session = None


class McpService(BaseService):
    """Manages MCP server definitions and executes their tools."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
        data_dir: str = "data",
        agent_registry: Optional[AgentRegistry] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)
        self.servers_dir = Path(data_dir) / "mcp_servers"
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        self.agent_registry = agent_registry

        self._configs: Dict[str, McpServerConfig] = {}
        # Persistent stdio subprocess managers, keyed by server_id.
        self._stdio_conns: Dict[str, _StdioSessionManager] = {}
        self._load_all_configs()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all_configs(self) -> None:
        """Load all MCP server configs from ``data/mcp_servers``."""
        for path in sorted(self.servers_dir.glob("*.json")):
            try:
                cfg = McpServerConfig.model_validate_json(path.read_text())
                self._configs[cfg.id] = cfg
                logger.debug(f"Loaded MCP server: {cfg.id}")
            except Exception as e:
                logger.error(f"Failed to load MCP server {path.name}: {e}")
        logger.info(f"MCP system loaded {len(self._configs)} server(s)")

    def _config_path(self, server_id: str) -> Path:
        return self.servers_dir / f"{server_id}.json"

    def _save_config(self, cfg: McpServerConfig) -> None:
        self._config_path(cfg.id).write_text(
            json.dumps(cfg.model_dump(), indent=2, ensure_ascii=False)
        )

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register_mcp_tools(self) -> None:
        """Register all cached MCP tools in the global ToolRegistry."""
        registry = get_tool_registry()
        count = 0
        for server_id, cfg in self._configs.items():
            for tool in cfg.discovered_tools:
                registry.register(self._create_tool(server_id, cfg, tool))
                count += 1
        logger.info(f"Registered {count} MCP tool(s) in ToolRegistry")

    def _register_server_tools(self, cfg: McpServerConfig) -> None:
        """(Re)register the tools for a single server."""
        registry = get_tool_registry()
        registry.unregister_by_prefix(f"mcp_{cfg.id}_")
        for tool in cfg.discovered_tools:
            registry.register(self._create_tool(cfg.id, cfg, tool))

    def _create_tool(self, server_id: str, cfg: McpServerConfig, tool: McpDiscoveredTool) -> Tool:
        """Build a Tool object for a single discovered MCP tool."""
        tool_name = f"mcp_{server_id}_{tool.name}"
        schema = ToolSchema(
            name=tool_name,
            description=f"[{cfg.display_name}] {tool.description}".strip(),
            parameters=self._sanitize_input_schema(tool.input_schema),
        )
        return Tool(
            schema=schema,
            executor=None,  # execution is routed through McpService.execute_tool
            service_name=f"mcp_{server_id}",
            requires_auth=True,
        )

    @staticmethod
    def _sanitize_input_schema(input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise an MCP tool ``inputSchema`` into a provider-safe JSON schema.

        MCP tools may return arbitrary JSON Schema (``$ref``/``$defs``/``anyOf``);
        reuse the same sanitizer the plugin/tool system uses for LLM
        compatibility (notably Gemini).
        """
        if not isinstance(input_schema, dict):
            return {"type": "object", "properties": {}}
        defs = input_schema.get("$defs", {}) or input_schema.get("definitions", {}) or {}
        properties = {
            k: _sanitize_property(v, defs)
            for k, v in (input_schema.get("properties", {}) or {}).items()
        }
        return {
            "type": "object",
            "properties": properties,
            "required": input_schema.get("required", []) or [],
        }

    # ------------------------------------------------------------------
    # Credentials (secure, multi-header + env vars)
    # ------------------------------------------------------------------

    def _load_credentials(self, server_id: str) -> Dict[str, Any]:
        """Return the raw decrypted credential blob for a server."""
        raw = self.credentials_repo.get(f"mcp_{server_id}") or {}
        data = raw.get("credential_data", raw)
        return data if isinstance(data, dict) else {}

    def _save_credentials(self, server_id: str, data: Dict[str, Any]) -> None:
        self.credentials_repo.store(
            service_name=f"mcp_{server_id}",
            credential_type="api_key",
            credential_data=data,
        )

    def _load_header_values(self, server_id: str) -> Dict[str, str]:
        """Return the decrypted {header_name: value} map for a server."""
        creds = self._load_credentials(server_id)
        headers = creds.get("headers")
        return {str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {}

    def _store_header_values(self, server_id: str, headers: Dict[str, str]) -> None:
        """Encrypt and persist the {header_name: value} map for a server."""
        # Drop empty values so a blank field doesn't wipe an existing secret.
        clean = {k: v for k, v in headers.items() if v}
        if not clean:
            return
        creds = self._load_credentials(server_id)
        existing = creds.get("headers") or {}
        if not isinstance(existing, dict):
            existing = {}
        existing.update(clean)
        creds["headers"] = existing
        self._save_credentials(server_id, creds)

    def _load_env_values(self, server_id: str) -> Dict[str, str]:
        """Return the decrypted {env_var_name: value} map for a server."""
        creds = self._load_credentials(server_id)
        env = creds.get("env")
        return {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {}

    def _store_env_values(self, server_id: str, env: Dict[str, str]) -> None:
        """Encrypt and persist the {env_var_name: value} map for a server."""
        clean = {k: v for k, v in env.items() if v}
        if not clean:
            return
        creds = self._load_credentials(server_id)
        existing = creds.get("env") or {}
        if not isinstance(existing, dict):
            existing = {}
        existing.update(clean)
        creds["env"] = existing
        self._save_credentials(server_id, creds)

    def _build_request_headers(self, cfg: McpServerConfig) -> Dict[str, str]:
        """Assemble the auth headers to send, from stored secret values."""
        stored = self._load_header_values(cfg.id)
        headers: Dict[str, str] = {}
        for h in cfg.auth_headers:
            if h.name in stored:
                headers[h.name] = stored[h.name]
        return headers

    def _build_stdio_env(self, cfg: McpServerConfig) -> Dict[str, str]:
        """Assemble the env vars to pass to the subprocess, from stored values."""
        stored = self._load_env_values(cfg.id)
        env: Dict[str, str] = {}
        for ev in cfg.env_vars:
            if ev.name in stored:
                env[ev.name] = stored[ev.name]
        return env

    # ------------------------------------------------------------------
    # MCP client (lazy import, transport-aware)
    # ------------------------------------------------------------------

    def _get_stdio_conn(self, cfg: McpServerConfig) -> _StdioSessionManager:
        """Return the persistent stdio session manager for a server, creating it
        lazily. Call this each time (not once at startup) because credentials
        may have changed after the manager was last created."""
        existing = self._stdio_conns.get(cfg.id)
        env = self._build_stdio_env(cfg)
        if existing is None:
            mgr = _StdioSessionManager(
                cfg.id,
                cfg.command,  # type: ignore[arg-type]
                cfg.args,
                env,
            )
            self._stdio_conns[cfg.id] = mgr
            return mgr
        # If env has changed (e.g. credentials were updated), rebuild the manager
        # so the next call reconnects with the new values.
        if existing._env != env:
            self._stdio_conns.pop(cfg.id)
            mgr = _StdioSessionManager(cfg.id, cfg.command, cfg.args, env)  # type: ignore[arg-type]
            self._stdio_conns[cfg.id] = mgr
            return mgr
        return existing

    async def _run_with_session(
        self, cfg: McpServerConfig, fn: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """Dispatch to the appropriate transport and run ``fn(session)``."""
        if cfg.transport == "stdio":
            return await self._run_with_stdio_session(cfg, fn)
        return await self._run_with_http_session(cfg, fn)

    async def _run_with_http_session(
        self, cfg: McpServerConfig, fn: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """Open a short-lived Streamable-HTTP session and run ``fn(session)``."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as e:  # pragma: no cover - depends on optional dep
            raise McpSdkNotInstalled(
                "The 'mcp' Python SDK is not installed. Install it (pip install mcp) "
                "to connect to MCP servers."
            ) from e

        headers = self._build_request_headers(cfg)

        async def _do() -> Any:
            async with streamablehttp_client(cfg.url, headers=headers or None) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)

        try:
            return await asyncio.wait_for(_do(), timeout=_MCP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Timed out after {int(_MCP_TIMEOUT_SECONDS)}s connecting to {cfg.url}"
            )
        except Exception as e:
            # The MCP client runs its transport inside an anyio task group, so a
            # real failure (connection refused, HTTP 401, DNS, OAuth challenge…)
            # arrives wrapped in an ExceptionGroup whose default message is the
            # unhelpful "unhandled errors in a TaskGroup". Surface the leaf cause.
            raise RuntimeError(_describe_exception(e)) from None

    async def _run_with_stdio_session(
        self, cfg: McpServerConfig, fn: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """Run ``fn(session)`` against a persistent stdio subprocess."""
        try:
            from mcp import ClientSession  # noqa: F401 – presence check
            from mcp.client.stdio import stdio_client  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise McpSdkNotInstalled(
                "The 'mcp' Python SDK is not installed. Install it (pip install mcp) "
                "to connect to MCP servers."
            ) from e

        conn = self._get_stdio_conn(cfg)

        try:
            return await asyncio.wait_for(conn.run(fn), timeout=_MCP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            # Invalidate the session: the subprocess may be hanging.
            await conn.close()
            self._stdio_conns.pop(cfg.id, None)
            raise RuntimeError(
                f"Timed out after {int(_MCP_TIMEOUT_SECONDS)}s communicating with "
                f"stdio server '{cfg.id}' (command: {cfg.command})"
            )
        except Exception as e:
            raise RuntimeError(_describe_exception(e)) from None

    async def _discover(self, cfg: McpServerConfig) -> List[McpDiscoveredTool]:
        """Connect and list the server's tools."""

        async def _list(session: Any) -> List[McpDiscoveredTool]:
            result = await session.list_tools()
            tools: List[McpDiscoveredTool] = []
            for t in getattr(result, "tools", []) or []:
                tools.append(
                    McpDiscoveredTool(
                        name=t.name,
                        description=getattr(t, "description", "") or "",
                        input_schema=getattr(t, "inputSchema", {}) or {},
                    )
                )
            return tools

        return await self._run_with_session(cfg, _list)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute an MCP tool call.

        ``tool_name`` format: ``mcp_{server_id}_{tool_name}``. Resolution matches
        against known (server_id, tool) pairs so server ids or tool names
        containing underscores are handled unambiguously.
        """
        server_id, mcp_tool_name = self._resolve_tool(tool_name)
        if server_id is None:
            raise ValueError(f"Cannot resolve MCP tool: {tool_name}")

        if not self._is_enabled(server_id):
            raise ValueError(f"MCP server '{server_id}' is disabled")

        cfg = self._configs[server_id]

        self._log_web_request(
            service_name=f"mcp_{server_id}",
            action=mcp_tool_name,
            endpoint=cfg.url or f"stdio:{cfg.command}",
            method="POST",
        )

        async def _call(session: Any) -> Any:
            return await session.call_tool(mcp_tool_name, arguments or {})

        result = await self._run_with_session(cfg, _call)
        return self._serialize_result(result)

    def _resolve_tool(self, tool_name: str):
        """Return (server_id, mcp_tool_name) for a registered mcp tool name."""
        for server_id, cfg in self._configs.items():
            for tool in cfg.discovered_tools:
                if tool_name == f"mcp_{server_id}_{tool.name}":
                    return server_id, tool.name
        return None, None

    @staticmethod
    def _serialize_result(result: Any) -> Dict[str, Any]:
        """Convert an MCP ``CallToolResult`` into a JSON-serializable dict."""
        out: Dict[str, Any] = {}
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            out["structured"] = structured

        texts: List[str] = []
        blocks: List[Any] = []
        for block in getattr(result, "content", []) or []:
            if getattr(block, "type", None) == "text":
                texts.append(getattr(block, "text", "") or "")
            elif hasattr(block, "model_dump"):
                blocks.append(block.model_dump())
            else:
                blocks.append(str(block))
        if texts:
            out["text"] = "\n".join(texts)
        if blocks:
            out["content"] = blocks
        if getattr(result, "isError", False):
            out["isError"] = True
        return out or {"text": ""}

    # ------------------------------------------------------------------
    # Enable state
    # ------------------------------------------------------------------

    def _is_enabled(self, server_id: str) -> bool:
        return settings_truthy(self.settings_repo.get(f"mcp.{server_id}.enabled"))

    async def set_enabled(self, server_id: str, enabled: bool) -> None:
        if server_id not in self._configs:
            raise KeyError(f"MCP server '{server_id}' not found")
        self.settings_repo.set(f"mcp.{server_id}.enabled", enabled, value_type="bool")
        # Keep the generated agent/skill row in lockstep so disabling a server
        # also stops its tools from being selected.
        if self.agent_registry:
            agent = self.agent_registry.get_agent_by_name(f"mcp_{server_id}")
            if agent:
                self.agent_registry.toggle_agent(agent.id, enabled)
        # Close the stdio subprocess when a server is disabled so it doesn't
        # linger in the background.
        if not enabled and server_id in self._stdio_conns:
            conn = self._stdio_conns.pop(server_id)
            try:
                await conn.close()
            except Exception as e:
                logger.warning(f"Error closing stdio conn for '{server_id}': {e}")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_servers(self) -> List[McpServerListItem]:
        result: List[McpServerListItem] = []
        for server_id, cfg in self._configs.items():
            result.append(
                McpServerListItem(
                    id=server_id,
                    display_name=cfg.display_name,
                    description=cfg.description,
                    icon=cfg.icon,
                    transport=cfg.transport,
                    url=cfg.url,
                    header_names=[h.name for h in cfg.auth_headers],
                    command=cfg.command,
                    args=cfg.args,
                    env_var_names=[ev.name for ev in cfg.env_vars],
                    enabled=self._is_enabled(server_id),
                    has_credentials=bool(self.credentials_repo.get(f"mcp_{server_id}")),
                    intent_keywords=cfg.intent_keywords,
                    tool_count=len(cfg.discovered_tools),
                    tool_names=[t.name for t in cfg.discovered_tools],
                )
            )
        return result

    def get_server(self, server_id: str) -> Optional[McpServerConfig]:
        return self._configs.get(server_id)

    async def add_server(self, request: McpServerCreateRequest) -> McpServerConfig:
        """Add a new MCP server: connect, discover tools, persist, and wire up
        the agent/skill row that triggers those tools.
        """
        if request.id in self._configs:
            raise ValueError(f"MCP server id '{request.id}' already exists")

        cfg = McpServerConfig(
            id=request.id,
            display_name=request.display_name,
            description=request.description,
            icon=request.icon or "🔌",
            transport=request.transport,
            url=request.url,
            auth_headers=[{"name": h.name} for h in request.auth_headers],
            command=request.command,
            args=request.args,
            env_vars=[{"name": ev.name} for ev in request.env_vars],
            intent_keywords=[k.strip() for k in request.intent_keywords if k.strip()],
        )

        # Store secret values BEFORE discovery so authenticated servers can be
        # reached during the initial tools/list call.
        if request.auth_headers:
            self._store_header_values(request.id, {h.name: h.value for h in request.auth_headers})
        if request.env_vars:
            self._store_env_values(request.id, {ev.name: ev.value for ev in request.env_vars})

        # Connect and discover tools (raises on failure — nothing is persisted).
        try:
            cfg.discovered_tools = await self._discover(cfg)
        except Exception:
            # Roll back the credentials we just stored so a failed add leaves no
            # orphaned secrets behind.
            self.credentials_repo.delete(f"mcp_{request.id}")
            raise

        # Persist config, register tools, create the agent/skill row, enable it.
        self._configs[cfg.id] = cfg
        self._save_config(cfg)
        self._register_server_tools(cfg)
        self._sync_agent_row(cfg)
        self.settings_repo.set(f"mcp.{cfg.id}.enabled", True, value_type="bool")

        logger.info(f"Added MCP server '{cfg.id}' with {len(cfg.discovered_tools)} tool(s)")
        return cfg

    async def refresh_tools(self, server_id: str) -> McpServerConfig:
        """Re-discover a server's tools and update the registry + agent row."""
        cfg = self._configs.get(server_id)
        if not cfg:
            raise KeyError(f"MCP server '{server_id}' not found")
        cfg.discovered_tools = await self._discover(cfg)
        self._save_config(cfg)
        self._register_server_tools(cfg)
        self._sync_agent_row(cfg)
        return cfg

    def save_credentials(self, server_id: str, request: McpCredentialsRequest) -> None:
        """Update stored header values and/or env var values."""
        cfg = self._configs.get(server_id)
        if not cfg:
            raise KeyError(f"MCP server '{server_id}' not found")

        if request.headers:
            # Add any new header names to the config.
            known_headers = {h.name for h in cfg.auth_headers}
            new_header_names = [h.name for h in request.headers if h.name not in known_headers]
            if new_header_names:
                data = cfg.model_dump()
                data["auth_headers"] = list(data["auth_headers"]) + [
                    {"name": n} for n in new_header_names
                ]
                cfg = McpServerConfig.model_validate(data)
                self._configs[server_id] = cfg
                self._save_config(cfg)
            self._store_header_values(server_id, {h.name: h.value for h in request.headers})

        if request.env_vars:
            # Add any new env var names to the config.
            known_env = {ev.name for ev in cfg.env_vars}
            new_env_names = [ev.name for ev in request.env_vars if ev.name not in known_env]
            if new_env_names:
                data = cfg.model_dump()
                data["env_vars"] = list(data["env_vars"]) + [{"name": n} for n in new_env_names]
                cfg = McpServerConfig.model_validate(data)
                self._configs[server_id] = cfg
                self._save_config(cfg)
            self._store_env_values(server_id, {ev.name: ev.value for ev in request.env_vars})
            # Invalidate the stdio session so the next call picks up new env values.
            if server_id in self._stdio_conns:
                self._stdio_conns.pop(server_id)

    async def test_server(self, server_id: str) -> McpTestResult:
        """Connect to a server and report reachability + tool count."""
        cfg = self._configs.get(server_id)
        if not cfg:
            raise KeyError(f"MCP server '{server_id}' not found")
        try:
            tools = await self._discover(cfg)
            return McpTestResult(
                success=True,
                message=f"Connected — discovered {len(tools)} tool(s).",
                tool_count=len(tools),
                tool_names=[t.name for t in tools],
            )
        except McpSdkNotInstalled as e:
            return McpTestResult(success=False, message=str(e))
        except Exception as e:  # pragma: no cover - network dependent
            return McpTestResult(success=False, message=f"Connection failed: {e}")

    async def delete_server(self, server_id: str) -> None:
        """Remove a server: unregister tools, drop the agent row, creds, config."""
        if server_id not in self._configs:
            raise KeyError(f"MCP server '{server_id}' not found")

        get_tool_registry().unregister_by_prefix(f"mcp_{server_id}_")
        if self.agent_registry:
            self.agent_registry.delete_agent(f"mcp_{server_id}")
        self.credentials_repo.delete(f"mcp_{server_id}")
        self.settings_repo.set(f"mcp.{server_id}.enabled", False, value_type="bool")

        # Close any lingering stdio subprocess.
        if server_id in self._stdio_conns:
            conn = self._stdio_conns.pop(server_id)
            try:
                await conn.close()
            except Exception as e:
                logger.warning(f"Error closing stdio conn for '{server_id}': {e}")

        path = self._config_path(server_id)
        if path.exists():
            path.unlink()
        self._configs.pop(server_id, None)
        logger.info(f"Deleted MCP server '{server_id}'")

    # ------------------------------------------------------------------
    # Agent/skill row synchronisation
    # ------------------------------------------------------------------

    def _sync_agent_row(self, cfg: McpServerConfig) -> None:
        """Create or update the agent/skill row that exposes this server.

        The row's ``tools`` list holds the server's ``mcp_{id}_*`` tool names and
        its ``intent_keywords`` are the user's chosen trigger words, so the
        skills selector activates these tools on a keyword match — no separate
        routing needed (agents and skills are the same table).
        """
        if not self.agent_registry:
            return

        agent_name = f"mcp_{cfg.id}"
        tool_names = [f"mcp_{cfg.id}_{t.name}" for t in cfg.discovered_tools]
        role = f"{cfg.display_name} (MCP server)"
        goal = cfg.description or f"Use the {cfg.display_name} MCP server's tools."
        backstory = (
            f"You have access to the '{cfg.display_name}' MCP server. "
            f"Use its tools to fulfil requests related to it."
        )

        existing = self.agent_registry.get_agent_by_name(agent_name)
        if existing:
            self.agent_registry.update_agent(
                existing.id,
                {
                    "display_name": cfg.display_name,
                    "role": role,
                    "goal": goal,
                    "backstory": backstory,
                    "tools": tool_names,
                    "intent_keywords": cfg.intent_keywords,
                },
            )
        else:
            self.agent_registry.create_agent(
                name=agent_name,
                display_name=cfg.display_name,
                role=role,
                goal=goal,
                backstory=backstory,
                tools=tool_names,
                priority=5,
                enabled=True,
                allow_delegation=False,
                intent_keywords=cfg.intent_keywords,
            )
