"""Tests for the api_key_with_jwt plugin auth type."""

import base64
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.plugin import PluginAuth, PluginCredentialsRequest, PluginDefinition
from src.services.plugin_service import PluginService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jwt(exp_offset_seconds: int = 3600) -> str:
    """Build a minimal signed-looking JWT with a real exp claim."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    exp = int(time.time()) + exp_offset_seconds
    payload_bytes = json.dumps({"sub": "user1", "exp": exp}).encode()
    payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


def _make_plugin_service() -> PluginService:
    """Create a minimal PluginService with all repos mocked out."""
    settings_repo = MagicMock()
    settings_repo.get.return_value = None
    credentials_repo = MagicMock()
    credentials_repo.get.return_value = None
    with (
        patch.object(PluginService, "_load_all_definitions"),
        patch.object(PluginService, "_migrate_legacy_toggl"),
    ):
        svc = PluginService(
            settings_repo=settings_repo,
            credentials_repo=credentials_repo,
            data_dir="/tmp",
        )
    svc._definitions = {}
    svc._builtin_ids = set()
    svc._jwt_cache = {}
    return svc


def _dual_auth_definition() -> PluginDefinition:
    return PluginDefinition.model_validate(
        {
            "id": "my_service",
            "display_name": "My Service",
            "description": "Test dual-auth plugin.",
            "base_url": "https://api.example.com",
            "auth": {
                "type": "api_key_with_jwt",
                "api_key_header": "X-apikey",
                "token_endpoint": "/token",
                "token_field": "access_token",
                "token_prefix": "Access_Token",
            },
            "endpoints": [
                {
                    "name": "list_items",
                    "display_name": "List Items",
                    "description": "List things.",
                    "method": "GET",
                    "path": "/items",
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


class TestPluginAuthModel:
    def test_api_key_with_jwt_accepted(self):
        auth = PluginAuth(type="api_key_with_jwt")
        assert auth.type == "api_key_with_jwt"

    def test_api_key_with_jwt_optional_fields(self):
        auth = PluginAuth(
            type="api_key_with_jwt",
            api_key_header="X-apikey",
            token_endpoint="/token",
            token_field="access_token",
            token_prefix="Access_Token",
        )
        assert auth.api_key_header == "X-apikey"
        assert auth.token_endpoint == "/token"
        assert auth.token_field == "access_token"
        assert auth.token_prefix == "Access_Token"

    def test_existing_types_unchanged(self):
        for t in ("bearer", "header", "basic"):
            auth = PluginAuth(type=t)
            assert auth.type == t

    def test_invalid_type_rejected(self):
        with pytest.raises(Exception):
            PluginAuth(type="magic_auth")


class TestPluginCredentialsRequest:
    def test_api_key_field_accepted(self):
        req = PluginCredentialsRequest(api_key="abc123", username="user", password="pass")
        assert req.api_key == "abc123"
        assert req.username == "user"
        assert req.password == "pass"

    def test_api_key_optional(self):
        req = PluginCredentialsRequest(token="tok")
        assert req.api_key is None


# ---------------------------------------------------------------------------
# JWT parsing
# ---------------------------------------------------------------------------


class TestParseJwtExpiry:
    def test_reads_exp_claim(self):
        future = int(time.time()) + 1800
        jwt = _make_jwt(exp_offset_seconds=1800)
        result = PluginService._parse_jwt_expiry(jwt)
        expected = datetime.fromtimestamp(future, tz=timezone.utc)
        assert abs((result - expected).total_seconds()) < 2

    def test_falls_back_on_bad_jwt(self):
        before = datetime.now(timezone.utc)
        result = PluginService._parse_jwt_expiry("not.a.jwt", default_ttl_minutes=10)
        after = datetime.now(timezone.utc)
        assert before + timedelta(minutes=9) < result < after + timedelta(minutes=11)

    def test_falls_back_on_missing_exp(self):
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(b'{"sub":"x"}').rstrip(b"=").decode()
        jwt = f"{header}.{payload}.sig"
        result = PluginService._parse_jwt_expiry(jwt, default_ttl_minutes=20)
        assert result > datetime.now(timezone.utc) + timedelta(minutes=19)


# ---------------------------------------------------------------------------
# _build_auth_headers (sync, existing types unaffected)
# ---------------------------------------------------------------------------


class TestBuildAuthHeaders:
    def setup_method(self):
        self.svc = _make_plugin_service()

    def test_bearer(self):
        auth = PluginAuth(type="bearer")
        h = self.svc._build_auth_headers(auth, {"token": "tok123"})
        assert h == {"Authorization": "Bearer tok123"}

    def test_header(self):
        auth = PluginAuth(type="header", header_name="X-Custom")
        h = self.svc._build_auth_headers(auth, {"token": "mykey"})
        assert h == {"X-Custom": "mykey"}

    def test_basic_with_credentials(self):
        auth = PluginAuth(type="basic")
        h = self.svc._build_auth_headers(auth, {"username": "u", "password": "p"})
        encoded = base64.b64encode(b"u:p").decode()
        assert h == {"Authorization": f"Basic {encoded}"}

    def test_basic_fixed_password(self):
        auth = PluginAuth(type="basic", fixed_password="api_token")
        h = self.svc._build_auth_headers(auth, {"token": "mytoken"})
        encoded = base64.b64encode(b"mytoken:api_token").decode()
        assert h == {"Authorization": f"Basic {encoded}"}


# ---------------------------------------------------------------------------
# _get_jwt — caching and fetching
# ---------------------------------------------------------------------------


class TestGetJwt:
    def setup_method(self):
        self.svc = _make_plugin_service()
        self.auth = PluginAuth(
            type="api_key_with_jwt",
            api_key_header="X-apikey",
            token_endpoint="/token",
            token_field="access_token",
            token_prefix="Access_Token",
        )
        self.creds = {"api_key": "APIKEY", "username": "user", "password": "pass"}

    @pytest.mark.asyncio
    async def test_fetches_and_caches_jwt(self):
        jwt = _make_jwt(3600)
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": jwt}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await self.svc._get_jwt(
                "my_service", self.auth, self.creds, "https://api.example.com"
            )

        assert result == jwt
        assert "my_service" in self.svc._jwt_cache

    @pytest.mark.asyncio
    async def test_uses_cached_jwt(self):
        jwt = _make_jwt(3600)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        self.svc._jwt_cache["my_service"] = (jwt, expires_at)

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await self.svc._get_jwt(
                "my_service", self.auth, self.creds, "https://api.example.com"
            )
            mock_client_cls.assert_not_called()

        assert result == jwt

    @pytest.mark.asyncio
    async def test_refreshes_expired_jwt(self):
        old_jwt = _make_jwt(-100)  # already expired
        self.svc._jwt_cache["my_service"] = (
            old_jwt,
            datetime.now(timezone.utc) - timedelta(seconds=10),
        )

        new_jwt = _make_jwt(3600)
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": new_jwt}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await self.svc._get_jwt(
                "my_service", self.auth, self.creds, "https://api.example.com"
            )

        assert result == new_jwt

    @pytest.mark.asyncio
    async def test_raises_when_token_field_missing(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"wrong_field": "something"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="access_token"):
                await self.svc._get_jwt(
                    "my_service", self.auth, self.creds, "https://api.example.com"
                )


# ---------------------------------------------------------------------------
# _build_api_key_with_jwt_headers
# ---------------------------------------------------------------------------


class TestBuildApiKeyWithJwtHeaders:
    def setup_method(self):
        self.svc = _make_plugin_service()

    @pytest.mark.asyncio
    async def test_builds_both_headers_when_api_key_present(self):
        jwt = _make_jwt(3600)
        self.svc._jwt_cache["myplugin"] = (jwt, datetime.now(timezone.utc) + timedelta(hours=1))

        auth = PluginAuth(
            type="api_key_with_jwt",
            api_key_header="X-apikey",
            token_endpoint="/token",
            token_field="access_token",
            token_prefix="Access_Token",
        )
        creds = {"api_key": "STATIC_KEY", "username": "u", "password": "p"}

        headers = await self.svc._build_api_key_with_jwt_headers(
            "myplugin", auth, creds, "https://api.example.com"
        )

        assert headers["X-apikey"] == "STATIC_KEY"
        assert headers["Authorization"] == f"Access_Token {jwt}"

    @pytest.mark.asyncio
    async def test_jwt_only_when_no_api_key(self):
        jwt = _make_jwt(3600)
        self.svc._jwt_cache["myplugin"] = (jwt, datetime.now(timezone.utc) + timedelta(hours=1))

        auth = PluginAuth(
            type="api_key_with_jwt",
            token_endpoint="/auth/login",
            token_field="token",
            token_prefix="Bearer",
        )
        creds = {"username": "u", "password": "p"}

        headers = await self.svc._build_api_key_with_jwt_headers(
            "myplugin", auth, creds, "https://api.example.com"
        )

        assert headers == {"Authorization": f"Bearer {jwt}"}
        assert all(not k.lower().startswith("x-") for k in headers)


# ---------------------------------------------------------------------------
# save_credentials — new type
# ---------------------------------------------------------------------------


class TestSaveCredentials:
    def setup_method(self):
        self.svc = _make_plugin_service()
        self.defn = _dual_auth_definition()
        self.svc._definitions["my_service"] = self.defn

    def test_stores_api_key_username_password(self):
        req = PluginCredentialsRequest(api_key="MYKEY", username="bob", password="secret")
        self.svc.save_credentials("my_service", req)

        call_args = self.svc.credentials_repo.store.call_args
        stored = call_args.kwargs["credential_data"]
        assert stored["api_key"] == "MYKEY"
        assert stored["username"] == "bob"
        assert stored["password"] == "secret"

    def test_invalidates_jwt_cache_on_save(self):
        self.svc._jwt_cache["my_service"] = (
            "old_token",
            datetime.now(timezone.utc) + timedelta(hours=1),
        )
        req = PluginCredentialsRequest(api_key="NEWKEY", username="alice", password="newpass")
        self.svc.save_credentials("my_service", req)
        assert "my_service" not in self.svc._jwt_cache


# ---------------------------------------------------------------------------
# _execute_endpoint — reactive 401 retry for api_key_with_jwt
# ---------------------------------------------------------------------------


class TestExecuteEndpoint401Retry:
    def setup_method(self):
        self.svc = _make_plugin_service()
        self.defn = _dual_auth_definition()
        self.svc._definitions["my_service"] = self.defn
        self.svc.credentials_repo.get.side_effect = lambda key: (
            {"credential_data": {"api_key": "K", "username": "u", "password": "p"}}
            if key == "plugin_my_service"
            else None
        )

    def _make_api_client_mock(self, *responses):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(side_effect=list(responses))
        return mock_client

    @pytest.mark.asyncio
    async def test_retries_on_401_and_succeeds(self):
        jwt_v1 = _make_jwt(3600)
        jwt_v2 = _make_jwt(3600)

        self.svc._jwt_cache["my_service"] = (
            jwt_v1, datetime.now(timezone.utc) + timedelta(hours=1)
        )

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.content = b""

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.content = b'{"items": []}'
        resp_200.json.return_value = {"items": []}
        resp_200.raise_for_status = MagicMock()

        mock_client = self._make_api_client_mock(resp_401, resp_200)
        headers_v1 = {"Authorization": f"Access_Token {jwt_v1}", "X-apikey": "K"}
        headers_v2 = {"Authorization": f"Access_Token {jwt_v2}", "X-apikey": "K"}

        with (
            patch("src.services.plugin_service.httpx.AsyncClient", return_value=mock_client),
            patch.object(
                self.svc,
                "_resolve_auth_headers",
                AsyncMock(side_effect=[headers_v1, headers_v2]),
            ),
        ):
            result = await self.svc._execute_endpoint("my_service", "list_items", {})

        assert result == {"items": []}
        assert mock_client.request.call_count == 2
        assert "my_service" not in self.svc._jwt_cache

    @pytest.mark.asyncio
    async def test_raises_when_retry_also_returns_401(self):
        import httpx as real_httpx

        self.svc._jwt_cache["my_service"] = (
            _make_jwt(3600), datetime.now(timezone.utc) + timedelta(hours=1)
        )

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.content = b""
        resp_401.raise_for_status = MagicMock(
            side_effect=real_httpx.HTTPStatusError(
                "401", request=MagicMock(), response=MagicMock(status_code=401)
            )
        )

        mock_client = self._make_api_client_mock(resp_401, resp_401)

        with (
            patch("src.services.plugin_service.httpx.AsyncClient", return_value=mock_client),
            patch.object(
                self.svc,
                "_resolve_auth_headers",
                AsyncMock(return_value={"Authorization": "Access_Token tok"}),
            ),
        ):
            with pytest.raises(real_httpx.HTTPStatusError):
                await self.svc._execute_endpoint("my_service", "list_items", {})

        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_non_jwt_auth_does_not_retry_on_401(self):
        import httpx as real_httpx

        bearer_defn = PluginDefinition.model_validate(
            {
                "id": "bearer_svc",
                "display_name": "Bearer",
                "description": "Bearer auth plugin.",
                "base_url": "https://api.example.com",
                "auth": {"type": "bearer"},
                "endpoints": [
                    {
                        "name": "get_data",
                        "display_name": "Get",
                        "description": ".",
                        "method": "GET",
                        "path": "/data",
                    }
                ],
            }
        )
        self.svc._definitions["bearer_svc"] = bearer_defn

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.content = b""
        resp_401.raise_for_status = MagicMock(
            side_effect=real_httpx.HTTPStatusError(
                "401", request=MagicMock(), response=MagicMock(status_code=401)
            )
        )

        mock_client = self._make_api_client_mock(resp_401)

        with patch("src.services.plugin_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(real_httpx.HTTPStatusError):
                await self.svc._execute_endpoint("bearer_svc", "get_data", {})

        assert mock_client.request.call_count == 1
