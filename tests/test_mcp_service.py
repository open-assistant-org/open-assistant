"""Tests for the MCP server integration (McpService)."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.mcp import (
    McpAuthHeaderInput,
    McpCredentialsRequest,
    McpDiscoveredTool,
    McpOAuthMetadata,
    McpServerConfig,
    McpServerCreateRequest,
)
from src.services.mcp_service import McpService, _describe_exception, _pkce_challenge

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


def _http_config(server_id="cf_gateway", auth_type="header", tools=None) -> McpServerConfig:
    return McpServerConfig(
        id=server_id,
        display_name="CF Gateway",
        url="https://example.com/mcp",
        auth_type=auth_type,
        auth_headers=(
            [{"name": "CF-Access-Client-Id"}, {"name": "CF-Access-Client-Secret"}]
            if auth_type == "header"
            else []
        ),
        intent_keywords=["cloudflare"],
        discovered_tools=tools
        or [McpDiscoveredTool(name="do_thing", description="d", input_schema={})],
    )


def _oauth_config(server_id="openseo", tools=None) -> McpServerConfig:
    return McpServerConfig(
        id=server_id,
        display_name="OpenSEO",
        url="https://openseo.example.com/mcp",
        auth_type="oauth2",
        oauth_scopes=["read", "write"],
        oauth_metadata=McpOAuthMetadata(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            registration_endpoint="https://auth.example.com/register",
            scopes_supported=["read", "write"],
        ),
        discovered_tools=tools or [],
    )


# ---------------------------------------------------------------------------
# Secure multi-header storage (header auth)
# ---------------------------------------------------------------------------


def test_multiple_headers_stored_and_rebuilt(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _http_config()
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
    cfg = _http_config()
    svc._configs[cfg.id] = cfg
    svc._store_header_values(cfg.id, {"CF-Access-Client-Id": "id-123"})
    svc._save_config(cfg)
    saved = (tmp_path / "mcp_servers" / f"{cfg.id}.json").read_text()
    assert "id-123" not in saved  # secret is never persisted to disk
    assert "CF-Access-Client-Id" in saved  # only the header name is


def test_blank_value_does_not_overwrite_existing_secret(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _http_config()
    svc._store_header_values(cfg.id, {"CF-Access-Client-Id": "id-123"})
    svc._store_header_values(cfg.id, {"CF-Access-Client-Id": ""})  # blank on re-save
    assert svc._build_request_headers(cfg)["CF-Access-Client-Id"] == "id-123"


def test_no_auth_returns_empty_headers(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _http_config(auth_type="none")
    headers = svc._build_request_headers(cfg)
    assert headers == {}


# ---------------------------------------------------------------------------
# Tool registration / schema
# ---------------------------------------------------------------------------


def test_create_tool_name_and_schema(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _http_config()
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
    cfg = _http_config()
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


def test_describe_exception_unwraps_task_group():
    # The MCP client wraps real failures (e.g. HTTP 401) in an ExceptionGroup
    # whose str is the unhelpful "unhandled errors in a TaskGroup".
    leaf = ValueError("Client error '401 Unauthorized' for url 'https://x/mcp'")
    grp = ExceptionGroup("unhandled errors in a TaskGroup", [leaf])
    msg = _describe_exception(grp)
    assert "401 Unauthorized" in msg
    assert "TaskGroup" not in msg

    # Nested groups are flattened to the leaf cause.
    nested = ExceptionGroup("outer", [ExceptionGroup("inner", [RuntimeError("boom")])])
    assert _describe_exception(nested) == "RuntimeError: boom"


@pytest.mark.asyncio
async def test_execute_tool_routes_to_session(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _http_config()
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
    cfg = _http_config()
    svc._configs[cfg.id] = cfg
    with pytest.raises(ValueError, match="disabled"):
        await svc.execute_tool("mcp_cf_gateway_do_thing", {})


# ---------------------------------------------------------------------------
# add_server — header variant
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
        auth_type="header",
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
        auth_type="header",
        auth_headers=[McpAuthHeaderInput(name="Authorization", value="Bearer x")],
        intent_keywords=[],
    )

    with patch.object(svc, "_discover", side_effect=_boom):
        with pytest.raises(RuntimeError, match="connection refused"):
            await svc.add_server(request)

    # No orphaned secrets left behind.
    assert svc.credentials_repo.get("mcp_bad_server") is None
    assert "bad_server" not in svc._configs


# ---------------------------------------------------------------------------
# save_credentials
# ---------------------------------------------------------------------------


def test_save_credentials_updates_headers(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _http_config()
    svc._configs[cfg.id] = cfg
    svc._store_header_values(cfg.id, {"CF-Access-Client-Id": "old"})

    req = McpCredentialsRequest(
        headers=[McpAuthHeaderInput(name="CF-Access-Client-Id", value="new")],
    )
    svc.save_credentials(cfg.id, req)
    assert svc._build_request_headers(cfg)["CF-Access-Client-Id"] == "new"


# ---------------------------------------------------------------------------
# OAuth 2.1 helpers
# ---------------------------------------------------------------------------


def test_pkce_challenge_is_s256():
    """_pkce_challenge must produce the S256 code_challenge from the verifier."""
    import base64
    import hashlib

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert _pkce_challenge(verifier) == expected


def test_oauth_build_headers_uses_bearer_token(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    svc._save_oauth_data(cfg.id, {"access_token": "tok123"})
    headers = svc._build_request_headers(cfg)
    assert headers == {"Authorization": "Bearer tok123"}


def test_oauth_build_headers_empty_when_no_token(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    headers = svc._build_request_headers(cfg)
    assert headers == {}


def test_is_oauth_authorized_true_when_token_present(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    assert not svc._is_oauth_authorized(cfg.id)
    svc._save_oauth_data(cfg.id, {"access_token": "tok"})
    assert svc._is_oauth_authorized(cfg.id)


@pytest.mark.asyncio
async def test_ensure_oauth_token_raises_when_no_token(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    with pytest.raises(RuntimeError, match="not yet authorized"):
        await svc._ensure_oauth_token(cfg)


@pytest.mark.asyncio
async def test_ensure_oauth_token_no_refresh_needed_when_fresh(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    # Token that expires far in the future.
    svc._save_oauth_data(
        cfg.id,
        {
            "access_token": "fresh_tok",
            "expires_at": time.time() + 3600,
        },
    )
    # Should return without making any HTTP call.
    await svc._ensure_oauth_token(cfg)  # no error


@pytest.mark.asyncio
async def test_ensure_oauth_token_refreshes_when_expired(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    svc._save_oauth_data(
        cfg.id,
        {
            "access_token": "old_tok",
            "refresh_token": "ref_tok",
            "client_id": "cid",
            "expires_at": time.time() - 10,  # expired
        },
    )

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "access_token": "new_tok",
        "refresh_token": "new_ref",
        "expires_in": 3600,
    }
    fake_response.raise_for_status = MagicMock()

    import httpx

    async def _fake_post(url, **kwargs):
        return fake_response

    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=_fake_post)):
        with patch(
            "httpx.AsyncClient.__aenter__",
            return_value=MagicMock(post=AsyncMock(return_value=fake_response)),
        ):
            with patch("httpx.AsyncClient.__aexit__", return_value=None):
                # Use a simpler mock approach
                pass

    # Directly test by mocking the client at a higher level
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=fake_response)

    with patch("src.services.mcp_service.httpx.AsyncClient", return_value=mock_client):
        await svc._ensure_oauth_token(cfg)

    refreshed = svc._load_oauth_data(cfg.id)
    assert refreshed["access_token"] == "new_tok"
    assert refreshed["refresh_token"] == "new_ref"


@pytest.mark.asyncio
async def test_oauth_start_generates_auth_url(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    # Pre-store a client_id so we skip registration.
    svc._save_oauth_data(cfg.id, {"client_id": "test_client"})

    resp = await svc.oauth_start(cfg.id, "https://app.example.com/api/mcp/oauth/callback")
    assert "https://auth.example.com/authorize" in resp.auth_url
    assert "code_challenge" in resp.auth_url
    assert "state=" in resp.auth_url
    assert resp.state in svc._oauth_states


@pytest.mark.asyncio
async def test_oauth_callback_stores_tokens(tmp_path):
    svc = _make_service(tmp_path)
    cfg = _oauth_config()
    svc._configs[cfg.id] = cfg
    svc._save_oauth_data(cfg.id, {"client_id": "test_client"})

    # Seed the state as if oauth_start was already called.
    state_token = "test_state_xyz"
    svc._oauth_states[state_token] = {
        "server_id": cfg.id,
        "code_verifier": "verifier123",
        "redirect_uri": "https://app.example.com/api/mcp/oauth/callback",
        "client_id": "test_client",
    }

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "access_token": "acc_token",
        "refresh_token": "ref_token",
        "expires_in": 3600,
    }
    fake_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=fake_response)

    with patch("src.services.mcp_service.httpx.AsyncClient", return_value=mock_client):
        server_id = await svc.oauth_callback("auth_code_xyz", state_token)

    assert server_id == cfg.id
    stored = svc._load_oauth_data(cfg.id)
    assert stored["access_token"] == "acc_token"
    assert stored["refresh_token"] == "ref_token"
    assert stored["expires_at"] is not None
    # State is consumed after use.
    assert state_token not in svc._oauth_states


@pytest.mark.asyncio
async def test_oauth_callback_rejects_unknown_state(tmp_path):
    svc = _make_service(tmp_path)
    with pytest.raises(ValueError, match="Unknown or expired"):
        await svc.oauth_callback("code", "nonexistent_state")


@pytest.mark.asyncio
async def test_add_server_oauth_skips_discovery(tmp_path):
    """OAuth servers are added without tool discovery (no token yet)."""
    agent_registry = MagicMock()
    agent_registry.get_agent_by_name.return_value = None
    svc = _make_service(tmp_path, agent_registry=agent_registry)

    async def _fake_discover_meta(url):
        return McpOAuthMetadata(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            registration_endpoint="https://auth.example.com/register",
        )

    request = McpServerCreateRequest(
        id="openseo",
        display_name="OpenSEO",
        url="https://openseo.example.com/mcp",
        auth_type="oauth2",
        oauth_scopes=["read"],
        intent_keywords=["seo"],
    )

    with patch.object(svc, "_discover_oauth_metadata", side_effect=_fake_discover_meta):
        with patch.object(svc, "_discover") as mock_discover:
            cfg = await svc.add_server(request)
            # _discover must NOT be called for OAuth servers.
            mock_discover.assert_not_called()

    assert cfg.auth_type == "oauth2"
    assert cfg.discovered_tools == []
    assert cfg.oauth_metadata is not None
    agent_registry.create_agent.assert_called_once()
