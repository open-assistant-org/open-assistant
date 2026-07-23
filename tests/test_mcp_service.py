"""Tests for the MCP server integration (McpService)."""

from unittest.mock import MagicMock, patch

import pytest

from src.models.mcp import (
    McpAuthHeaderInput,
    McpDiscoveredTool,
    McpServerConfig,
    McpServerCreateRequest,
)
from src.services.mcp_service import McpService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCredentials:
    """In-memory stand-in for CredentialsRepository (encryption is transparent)."""

    def __init__(self):
        self._store = {}

    def store(self, service_name, credential_type, credential_data, expires_at=None):
        self._store[service_name] = {
            "credential_type": credential_type,
            "credential_data": credential_data,
        }
        return True

    def get(self, service_name):
        return self._store.get(service_name)

    def delete(self, service_name):
        return self._store.pop(service_name, None) is not None


def _make_service(tmp_path, agent_registry=None) -> McpService:
    settings_repo = MagicMock()
    settings_repo.get.return_value = "true"  # servers appear enabled by default
    with patch.object(McpService, "_load_all_configs"):
        svc = McpService(
            settings_repo=settings_repo,
            credentials_repo=_FakeCredentials(),
            data_dir=str(tmp_path),
            agent_registry=agent_registry,
        )
    svc._configs = {}
    return svc


def _config(server_id="cf_gateway", tools=None) -> McpServerConfig:
    return McpServerConfig(
        id=server_id,
        display_name="CF Gateway",
        url="https://example.com/mcp",
        auth_headers=[{"name": "CF-Access-Client-Id"}, {"name": "CF-Access-Client-Secret"}],
        intent_keywords=["cloudflare"],
        discovered_tools=tools
        or [McpDiscoveredTool(name="do_thing", description="d", input_schema={})],
    )


# ---------------------------------------------------------------------------
# Secure multi-header storage (the key requirement)
# ---------------------------------------------------------------------------


def test_multiple_headers_stored_and_rebuilt(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _config()
    svc._store_header_values(
        cfg.id,
        {"CF-Access-Client-Id": "id-123", "CF-Access-Client-Secret": "secret-456"},
    )
    headers = svc._build_request_headers(cfg)
    assert headers == {
        "CF-Access-Client-Id": "id-123",
        "CF-Access-Client-Secret": "secret-456",
    }


def test_header_values_never_in_config_json(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _config()
    svc._configs[cfg.id] = cfg
    svc._store_header_values(cfg.id, {"CF-Access-Client-Id": "id-123"})
    svc._save_config(cfg)
    saved = (tmp_path / "mcp_servers" / f"{cfg.id}.json").read_text()
    assert "id-123" not in saved  # secret is never persisted to disk
    assert "CF-Access-Client-Id" in saved  # only the header name is


def test_blank_value_does_not_overwrite_existing_secret(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _config()
    svc._store_header_values(cfg.id, {"CF-Access-Client-Id": "id-123"})
    svc._store_header_values(cfg.id, {"CF-Access-Client-Id": ""})  # blank on re-save
    assert svc._build_request_headers(cfg)["CF-Access-Client-Id"] == "id-123"


# ---------------------------------------------------------------------------
# Tool registration / schema
# ---------------------------------------------------------------------------


def test_create_tool_name_and_schema(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _config()
    tool = McpDiscoveredTool(
        name="do_thing",
        description="Does a thing",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "string", "title": "X"}},
            "required": ["x"],
        },
    )
    built = svc._create_tool(cfg.id, cfg, tool)
    assert built.schema.name == "mcp_cf_gateway_do_thing"
    assert built.service_name == "mcp_cf_gateway"
    assert built.executor is None
    # Sanitized: provider-noise like "title" is stripped.
    assert "title" not in built.schema.parameters["properties"]["x"]
    assert built.schema.parameters["required"] == ["x"]


# ---------------------------------------------------------------------------
# Resolution / serialization / execution
# ---------------------------------------------------------------------------


def test_resolve_tool(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _config()
    svc._configs[cfg.id] = cfg
    assert svc._resolve_tool("mcp_cf_gateway_do_thing") == ("cf_gateway", "do_thing")
    assert svc._resolve_tool("mcp_cf_gateway_unknown") == (None, None)


def test_serialize_result_text_and_error():
    class _Block:
        type = "text"
        text = "hello"

    class _Result:
        content = [_Block()]
        isError = True
        structuredContent = {"k": "v"}

    out = McpService._serialize_result(_Result())
    assert out["text"] == "hello"
    assert out["isError"] is True
    assert out["structured"] == {"k": "v"}


@pytest.mark.asyncio
async def test_execute_tool_routes_to_session(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _config()
    svc._configs[cfg.id] = cfg

    class _Block:
        type = "text"
        text = "ok"

    class _Result:
        content = [_Block()]
        isError = False
        structuredContent = None

    async def _fake_run(config, fn):
        # Simulate a live session that returns a CallToolResult.
        class _Session:
            async def call_tool(self, name, args):
                assert name == "do_thing"
                assert args == {"x": "1"}
                return _Result()

        return await fn(_Session())

    with patch.object(svc, "_run_with_session", side_effect=_fake_run):
        result = await svc.execute_tool("mcp_cf_gateway_do_thing", {"x": "1"})
    assert result["text"] == "ok"


@pytest.mark.asyncio
async def test_execute_tool_disabled_raises(tmp_path):
    svc = _make_service(tmp_path)
    svc.settings_repo.get.return_value = "false"  # disabled
    cfg = _config()
    svc._configs[cfg.id] = cfg
    with pytest.raises(ValueError, match="disabled"):
        await svc.execute_tool("mcp_cf_gateway_do_thing", {})


# ---------------------------------------------------------------------------
# add_server wires up the agent/skill row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_server_creates_agent_row_with_keywords(tmp_path):
    agent_registry = MagicMock()
    agent_registry.get_agent_by_name.return_value = None
    svc = _make_service(tmp_path, agent_registry=agent_registry)

    async def _fake_discover(cfg):
        return [McpDiscoveredTool(name="do_thing", description="d", input_schema={})]

    request = McpServerCreateRequest(
        id="cf_gateway",
        display_name="CF Gateway",
        url="https://example.com/mcp",
        auth_headers=[
            McpAuthHeaderInput(name="CF-Access-Client-Id", value="id-1"),
            McpAuthHeaderInput(name="CF-Access-Client-Secret", value="sec-1"),
        ],
        intent_keywords=["cloudflare", "gateway"],
    )

    with patch.object(svc, "_discover", side_effect=_fake_discover):
        with patch.object(svc, "_register_server_tools"):
            cfg = await svc.add_server(request)

    # Secrets stored securely, config persisted, enabled flag set.
    assert svc._build_request_headers(cfg) == {
        "CF-Access-Client-Id": "id-1",
        "CF-Access-Client-Secret": "sec-1",
    }
    svc.settings_repo.set.assert_any_call("mcp.cf_gateway.enabled", True, value_type="bool")

    # The agent/skill row is created with the tools + the user's keywords.
    agent_registry.create_agent.assert_called_once()
    kwargs = agent_registry.create_agent.call_args.kwargs
    assert kwargs["name"] == "mcp_cf_gateway"
    assert kwargs["tools"] == ["mcp_cf_gateway_do_thing"]
    assert kwargs["intent_keywords"] == ["cloudflare", "gateway"]


@pytest.mark.asyncio
async def test_add_server_rolls_back_credentials_on_discovery_failure(tmp_path):
    svc = _make_service(tmp_path)

    async def _boom(cfg):
        raise RuntimeError("connection refused")

    request = McpServerCreateRequest(
        id="bad_server",
        display_name="Bad",
        url="https://example.com/mcp",
        auth_headers=[McpAuthHeaderInput(name="Authorization", value="Bearer x")],
        intent_keywords=[],
    )

    with patch.object(svc, "_discover", side_effect=_boom):
        with pytest.raises(RuntimeError, match="connection refused"):
            await svc.add_server(request)

    # No orphaned secrets left behind.
    assert svc.credentials_repo.get("mcp_bad_server") is None
    assert "bad_server" not in svc._configs
