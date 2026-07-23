"""Service for managing MCP (Model Context Protocol) servers.

Phase 1: connect to remote MCP servers over Streamable HTTP, discover their
tools, register each tool in the global ToolRegistry as ``mcp_{id}_{tool}``, and
execute tool calls by opening a short-lived session per call.

Design notes
------------
* This mirrors :class:`~src.services.plugin_service.PluginService`: dynamic tools
  with ``service_name=f"mcp_{id}"`` and ``executor=None``; execution is routed
  through :meth:`execute_tool` by :class:`~src.core.tools.executor.ToolExecutor`.
* The ``mcp`` SDK is imported lazily inside the methods that actually talk to a
  server, so the application still boots (and can register cached tools) even if
  the package is not installed yet.
* Auth is static headers only (no OAuth). Header *values* are stored encrypted in
  ``service_credentials`` under ``mcp_{id}``; the config JSON holds only names.
  Several headers are supported per server (e.g. Cloudflare Access).
* Adding a server also creates an agent/skill row so the server's tools are
  triggered by the user's chosen intent keywords — see ``docs/mcp-servers.md``
  and ``src/models/skill.py`` for why agents == skills.
"""

import asyncio
import json
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
    # Credentials (secure, multi-header)
    # ------------------------------------------------------------------

    def _load_header_values(self, server_id: str) -> Dict[str, str]:
        """Return the decrypted {header_name: value} map for a server."""
        raw = self.credentials_repo.get(f"mcp_{server_id}") or {}
        data = raw.get("credential_data", raw)
        headers = data.get("headers") if isinstance(data, dict) else None
        return {str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {}

    def _store_header_values(self, server_id: str, headers: Dict[str, str]) -> None:
        """Encrypt and persist the {header_name: value} map for a server."""
        # Drop empty values so a blank field doesn't wipe an existing secret.
        clean = {k: v for k, v in headers.items() if v}
        if not clean:
            return
        existing = self._load_header_values(server_id)
        existing.update(clean)
        self.credentials_repo.store(
            service_name=f"mcp_{server_id}",
            credential_type="api_key",
            credential_data={"headers": existing},
        )

    def _build_request_headers(self, cfg: McpServerConfig) -> Dict[str, str]:
        """Assemble the auth headers to send, from stored secret values."""
        stored = self._load_header_values(cfg.id)
        headers: Dict[str, str] = {}
        for h in cfg.auth_headers:
            if h.name in stored:
                headers[h.name] = stored[h.name]
        return headers

    # ------------------------------------------------------------------
    # MCP client (lazy import)
    # ------------------------------------------------------------------

    async def _run_with_session(
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
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"Timed out after {int(_MCP_TIMEOUT_SECONDS)}s connecting to {cfg.url}"
            ) from e
        except Exception as e:
            # The MCP client runs its transport inside an anyio task group, so a
            # real failure (connection refused, HTTP 401, DNS, OAuth challenge…)
            # arrives wrapped in an ExceptionGroup whose default message is the
            # unhelpful "unhandled errors in a TaskGroup". Surface the leaf cause.
            raise RuntimeError(_describe_exception(e)) from e

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
            endpoint=cfg.url,
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

    def set_enabled(self, server_id: str, enabled: bool) -> None:
        if server_id not in self._configs:
            raise KeyError(f"MCP server '{server_id}' not found")
        self.settings_repo.set(f"mcp.{server_id}.enabled", enabled, value_type="bool")
        # Keep the generated agent/skill row in lockstep so disabling a server
        # also stops its tools from being selected.
        if self.agent_registry:
            agent = self.agent_registry.get_agent_by_name(f"mcp_{server_id}")
            if agent:
                self.agent_registry.toggle_agent(agent.id, enabled)

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
                    enabled=self._is_enabled(server_id),
                    has_credentials=bool(self.credentials_repo.get(f"mcp_{server_id}")),
                    header_names=[h.name for h in cfg.auth_headers],
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
            transport="http",
            url=request.url,
            auth_headers=[{"name": h.name} for h in request.auth_headers],
            intent_keywords=[k.strip() for k in request.intent_keywords if k.strip()],
        )

        # Store secret header values BEFORE discovery so authenticated servers
        # can be reached during the initial tools/list call.
        self._store_header_values(request.id, {h.name: h.value for h in request.auth_headers})

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
        """Update stored header values (and add any new header names)."""
        cfg = self._configs.get(server_id)
        if not cfg:
            raise KeyError(f"MCP server '{server_id}' not found")

        known = {h.name for h in cfg.auth_headers}
        new_names = [h.name for h in request.headers if h.name not in known]
        if new_names:
            # Rebuild the config through the model so the new header names are
            # validated, rather than mutating the typed list in place.
            data = cfg.model_dump()
            data["auth_headers"] = list(data["auth_headers"]) + [{"name": n} for n in new_names]
            cfg = McpServerConfig.model_validate(data)
            self._configs[server_id] = cfg
            self._save_config(cfg)

        self._store_header_values(server_id, {h.name: h.value for h in request.headers})

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

    def delete_server(self, server_id: str) -> None:
        """Remove a server: unregister tools, drop the agent row, creds, config."""
        if server_id not in self._configs:
            raise KeyError(f"MCP server '{server_id}' not found")

        get_tool_registry().unregister_by_prefix(f"mcp_{server_id}_")
        if self.agent_registry:
            self.agent_registry.delete_agent(f"mcp_{server_id}")
        self.credentials_repo.delete(f"mcp_{server_id}")
        self.settings_repo.set(f"mcp.{server_id}.enabled", False, value_type="bool")

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
