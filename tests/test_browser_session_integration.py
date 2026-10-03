"""Tests wiring saved browser sessions into the driver, service, fetcher and API.

Cookie *values* are secrets: several tests assert they never appear in anything
the LLM (tool results) or the API/audit log can see.
"""

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.encryption import EncryptionService
from src.core.repositories.credentials import CredentialsRepository
from src.integrations.browser.driver import BrowserDriver, validate_navigation_url
from src.integrations.browser.fetcher import ContentFetcher
from src.integrations.browser.sessions import (
    BrowserSessionStore,
    looks_like_login_url,
    parse_session_export,
)

SECRET = "s3cr3t-cookie-value-XYZ"
ROTATED = "rotated-cookie-value-ABC"
FUTURE = 4_000_000_000  # far-future expiry so the tests never go stale


def _export(domain=".example.com", name="sid", value=SECRET, **extra) -> str:
    cookie = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": "/",
        "expires": FUTURE,
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax",
    }
    cookie.update(extra)
    return json.dumps({"cookies": [cookie], "origins": []})


@pytest.fixture
def credentials_repo(clean_temp_db, test_encryption_key):
    return CredentialsRepository(clean_temp_db, EncryptionService(test_encryption_key))


@pytest.fixture
def store(credentials_repo):
    return BrowserSessionStore(credentials_repo)


# ----------------------------------------------------------------------------
# URL validation
# ----------------------------------------------------------------------------


class TestNavigationUrlValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(document.cookie)",
            "file:///etc/passwd",
            "chrome://settings",
            "about:blank",
            "ftp://example.com/",
            "data:text/html,<script>1</script>",
            "example.com",
            "",
            "https://",
        ],
    )
    def test_rejects_non_http_urls(self, url):
        with pytest.raises(ValueError, match="http"):
            validate_navigation_url(url)

    @pytest.mark.parametrize("url", ["http://example.com", " https://example.com/a?b=1 "])
    def test_accepts_http_urls(self, url):
        assert validate_navigation_url(url) == url.strip()

    @pytest.mark.asyncio
    async def test_navigate_rejects_before_launching_a_browser(self):
        driver = BrowserDriver()
        driver._ensure_browser = AsyncMock()
        with pytest.raises(ValueError):
            await driver.navigate("javascript:alert(1)")
        driver._ensure_browser.assert_not_called()


class TestLoginHeuristic:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/login",
            "https://example.com/users/sign_in",
            "https://example.com/account/login?next=/",
            "https://accounts.example.com/signin/v2/identifier",
            "https://login.example.com/",
            "https://example.com/oauth/authorize",
        ],
    )
    def test_login_urls(self, url):
        assert looks_like_login_url(url)

    @pytest.mark.parametrize(
        "url",
        ["https://example.com/", "https://example.com/inbox", "https://example.com/authors/bob"],
    )
    def test_other_urls(self, url):
        assert not looks_like_login_url(url)


# ----------------------------------------------------------------------------
# Driver: injection and write-back hook (mocked Playwright)
# ----------------------------------------------------------------------------


def _fake_playwright():
    """AsyncMock Playwright stack; returns (async_playwright_factory, context)."""
    context = MagicMock()
    context.new_page = AsyncMock(return_value=MagicMock())
    context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
    context.close = AsyncMock()
    context.add_init_script = AsyncMock()
    context.on = MagicMock()
    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.stop = AsyncMock()
    starter = MagicMock()
    starter.start = AsyncMock(return_value=pw)
    return MagicMock(return_value=starter), browser, context


class TestDriverSessionInjection:
    @pytest.mark.asyncio
    async def test_storage_state_and_user_agent_reach_new_context(self):
        factory, browser, _ = _fake_playwright()
        state = {
            "cookies": [{"name": "sid", "value": SECRET, "domain": "example.com"}],
            "origins": [],
        }
        driver = BrowserDriver(storage_state=state, user_agent="TestUA/1.0")
        with (
            patch("playwright.async_api.async_playwright", factory),
            patch(
                "src.integrations.browser.driver.install_cookie_consent_observer", new=AsyncMock()
            ),
        ):
            await driver._ensure_browser()
        kwargs = browser.new_context.call_args.kwargs
        assert kwargs["storage_state"] == state
        assert kwargs["user_agent"] == "TestUA/1.0"

    @pytest.mark.asyncio
    async def test_no_storage_state_keeps_default_behaviour(self):
        factory, browser, _ = _fake_playwright()
        driver = BrowserDriver()
        with (
            patch("playwright.async_api.async_playwright", factory),
            patch(
                "src.integrations.browser.driver.install_cookie_consent_observer", new=AsyncMock()
            ),
        ):
            await driver._ensure_browser()
        kwargs = browser.new_context.call_args.kwargs
        assert "storage_state" not in kwargs
        assert "Chrome/120" in kwargs["user_agent"]

    @pytest.mark.asyncio
    async def test_on_close_gets_state_before_context_closes(self):
        calls = []
        _, _, context = _fake_playwright()
        context.storage_state = AsyncMock(
            side_effect=lambda: calls.append("export") or {"cookies": ["x"], "origins": []}
        )
        context.close = AsyncMock(side_effect=lambda: calls.append("close"))
        driver = BrowserDriver(on_close=lambda state: calls.append(("on_close", state)))
        driver._context = context
        await driver.close()
        assert calls == ["export", ("on_close", {"cookies": ["x"], "origins": []}), "close"]

    @pytest.mark.asyncio
    async def test_failing_on_close_does_not_prevent_shutdown(self):
        _, _, context = _fake_playwright()
        driver = BrowserDriver(on_close=MagicMock(side_effect=RuntimeError("db locked")))
        driver._context = context
        await driver.close()
        context.close.assert_awaited_once()


# ----------------------------------------------------------------------------
# Service: hints, write-back, test endpoint, validation
# ----------------------------------------------------------------------------


class FakeDriver:
    """Stand-in for BrowserDriver recording how the service builds it."""

    instances = []
    landing_url = "https://www.example.com/inbox"
    is_idle_expired = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self._page = SimpleNamespace(
            url=self.landing_url,
            title=AsyncMock(return_value="Inbox"),
            wait_for_timeout=AsyncMock(),
        )
        FakeDriver.instances.append(self)

    async def navigate(self, url, wait_until="domcontentloaded"):
        validate_navigation_url(url)

    async def get_accessibility_tree(self, mode="interactive", include_invisible=False):
        return {
            "tree": "[ref=1] link 'Mail'",
            "node_count": 10,
            "token_estimate": 5,
            "url": self._page.url,
            "title": "Inbox",
        }

    async def extract_text(self):
        return {"title": "Inbox", "url": self._page.url, "text": "hello"}

    exported_state = None

    async def export_storage_state(self):
        return type(self).exported_state

    async def execute_action(self, ref_id, action, value=None, timeout=5000):
        return {"success": True, "url": self._page.url, "title": "Inbox"}

    async def close(self):
        self.closed = True
        on_close = self.kwargs.get("on_close")
        if on_close:
            on_close(None)


@pytest.fixture
def service(credentials_repo):
    from src.services.browser import BrowserService

    settings = MagicMock()
    values = {
        "browser.enabled": True,
        "browser.headless": True,
        "browser.viewport_width": 1280,
        "browser.viewport_height": 720,
        "browser.screenshot_quality": 85,
        "browser.user_agent": "Custom/9.9",
    }
    settings.get.side_effect = values.get
    FakeDriver.instances = []
    FakeDriver.landing_url = "https://www.example.com/inbox"
    FakeDriver.exported_state = None
    with patch("src.services.browser.BrowserDriver", FakeDriver):
        yield BrowserService(settings, credentials_repo, MagicMock())


def _add_profile(credentials_repo, name="Personal Gmail", **kw):
    store = BrowserSessionStore(credentials_repo)
    return store.create(name, parse_session_export(_export(**kw)))


class TestServiceBrowseUrl:
    @pytest.mark.asyncio
    async def test_driver_receives_saved_session_and_user_agent(self, service, credentials_repo):
        _add_profile(credentials_repo)
        await service.browse_url("https://www.example.com/")
        driver = FakeDriver.instances[-1]
        cookies = driver.kwargs["storage_state"]["cookies"]
        assert [c["value"] for c in cookies] == [SECRET]
        assert driver.kwargs["user_agent"] == "Custom/9.9"
        assert callable(driver.kwargs["on_close"])

    @pytest.mark.asyncio
    async def test_result_names_the_session_but_never_leaks_values(self, service, credentials_repo):
        _add_profile(credentials_repo)
        result = await service.browse_url("https://www.example.com/")
        assert result["authenticated_session"] == "Personal Gmail"
        assert "Personal Gmail" in result["message"]
        assert "do not try to log in" in result["message"]
        assert "session_expired_suspected" not in result
        assert SECRET not in json.dumps(result)

    @pytest.mark.asyncio
    async def test_login_page_flags_expired_session(self, service, credentials_repo):
        _add_profile(credentials_repo)
        FakeDriver.landing_url = "https://www.example.com/login?next=/"
        result = await service.browse_url("https://www.example.com/")
        assert result["session_expired_suspected"] is True
        assert "probably expired" in result["message"]
        assert "refresh" in result["message"]

    @pytest.mark.asyncio
    async def test_no_hint_without_matching_session(self, service, credentials_repo):
        _add_profile(credentials_repo, domain=".other.org")
        result = await service.browse_url("https://www.example.com/")
        assert "authenticated_session" not in result

    @pytest.mark.asyncio
    async def test_no_sessions_means_anonymous_browser(self, service):
        result = await service.browse_url("https://www.example.com/")
        assert FakeDriver.instances[-1].kwargs["storage_state"] is None
        assert "authenticated_session" not in result

    @pytest.mark.asyncio
    async def test_disabled_profile_is_not_loaded(self, service, credentials_repo):
        meta = _add_profile(credentials_repo)
        BrowserSessionStore(credentials_repo).update(meta["id"], enabled=False)
        result = await service.browse_url("https://www.example.com/")
        assert FakeDriver.instances[-1].kwargs["storage_state"] is None
        assert "authenticated_session" not in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "chrome://x"])
    async def test_non_http_urls_rejected_before_any_driver(self, service, url):
        with pytest.raises(ValueError):
            await service.browse_url(url)
        assert FakeDriver.instances == []

    @pytest.mark.asyncio
    async def test_extract_carries_hint(self, service, credentials_repo):
        _add_profile(credentials_repo)
        await service.browse_url("https://www.example.com/")
        result = await service.browse_extract()
        assert result["authenticated_session"] == "Personal Gmail"
        assert SECRET not in json.dumps(result)


class TestServiceWriteBack:
    @pytest.mark.asyncio
    async def test_rotated_cookie_is_saved_when_session_closes(self, service, credentials_repo):
        _add_profile(credentials_repo)
        await service.browse_url("https://www.example.com/")
        on_close = FakeDriver.instances[-1].kwargs["on_close"]

        on_close({"cookies": [json.loads(_export(value=ROTATED))["cookies"][0]], "origins": []})

        stored = BrowserSessionStore(credentials_repo).load_storage_state()
        assert stored["cookies"][0]["value"] == ROTATED

    @pytest.mark.asyncio
    async def test_fresh_import_is_not_clobbered_by_older_session(self, service, credentials_repo):
        meta = _add_profile(credentials_repo)
        await service.browse_url("https://www.example.com/")
        on_close = FakeDriver.instances[-1].kwargs["on_close"]

        # User re-imports while the browser is still open...
        BrowserSessionStore(credentials_repo).update(
            meta["id"], parsed=parse_session_export(_export(value="fresh-import"))
        )
        # ...then the old browser session closes with its older rotated cookie.
        on_close({"cookies": [json.loads(_export(value=ROTATED))["cookies"][0]], "origins": []})

        stored = BrowserSessionStore(credentials_repo).load_storage_state()
        assert stored["cookies"][0]["value"] == "fresh-import"

    @pytest.mark.asyncio
    async def test_rotation_is_saved_after_browse_url_without_closing(
        self, service, credentials_repo
    ):
        _add_profile(credentials_repo)
        FakeDriver.exported_state = {
            "cookies": [json.loads(_export(value=ROTATED))["cookies"][0]],
            "origins": [],
        }
        await service.browse_url("https://www.example.com/")  # note: no close()
        stored = BrowserSessionStore(credentials_repo).load_storage_state()
        assert stored["cookies"][0]["value"] == ROTATED

    @pytest.mark.asyncio
    async def test_rotation_is_saved_after_browse_action(self, service, credentials_repo):
        _add_profile(credentials_repo)
        await service.browse_url("https://www.example.com/")
        FakeDriver.exported_state = {
            "cookies": [json.loads(_export(value=ROTATED))["cookies"][0]],
            "origins": [],
        }
        await service.browse_action(1, "click")
        stored = BrowserSessionStore(credentials_repo).load_storage_state()
        assert stored["cookies"][0]["value"] == ROTATED

    @pytest.mark.asyncio
    async def test_flush_respects_revision_guard_and_swallows_errors(
        self, service, credentials_repo
    ):
        meta = _add_profile(credentials_repo)
        await service.browse_url("https://www.example.com/")
        BrowserSessionStore(credentials_repo).update(
            meta["id"], parsed=parse_session_export(_export(value="fresh-import"))
        )
        FakeDriver.exported_state = {
            "cookies": [json.loads(_export(value=ROTATED))["cookies"][0]],
            "origins": [],
        }
        await service.browse_action(1, "click")  # stale snapshot: must not overwrite
        stored = BrowserSessionStore(credentials_repo).load_storage_state()
        assert stored["cookies"][0]["value"] == "fresh-import"

        with patch.object(FakeDriver, "export_storage_state", side_effect=RuntimeError("boom")):
            result = await service.browse_action(1, "click")  # failure must not break the tool
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_persist_failure_never_breaks_browsing(self, service, credentials_repo):
        _add_profile(credentials_repo)
        await service.browse_url("https://www.example.com/")
        with patch.object(service._sessions, "apply_updates", side_effect=RuntimeError("boom")):
            # The driver swallows on_close errors (see TestDriverSessionInjection);
            # the callback itself is allowed to raise.
            with pytest.raises(RuntimeError):
                FakeDriver.instances[-1].kwargs["on_close"]({"cookies": [], "origins": []})


class TestServiceTestSession:
    @pytest.mark.asyncio
    async def test_reports_where_the_site_landed_without_content(self, service, credentials_repo):
        meta = _add_profile(credentials_repo)
        result = await service.test_session(meta["id"], "https://www.example.com/inbox")
        assert result == {
            "final_url": "https://www.example.com/inbox",
            "title": "Inbox",
            "redirected_to_login": False,
        }
        driver = FakeDriver.instances[-1]
        assert driver.closed
        assert "on_close" not in driver.kwargs  # a test never writes cookies back
        assert [c["value"] for c in driver.kwargs["storage_state"]["cookies"]] == [SECRET]

    @pytest.mark.asyncio
    async def test_detects_bounce_to_login(self, service, credentials_repo):
        meta = _add_profile(credentials_repo)
        FakeDriver.landing_url = "https://www.example.com/login"
        result = await service.test_session(meta["id"], "https://www.example.com/inbox")
        assert result["redirected_to_login"] is True

    @pytest.mark.asyncio
    async def test_disabled_profile_can_still_be_tested(self, service, credentials_repo):
        meta = _add_profile(credentials_repo)
        BrowserSessionStore(credentials_repo).update(meta["id"], enabled=False)
        await service.test_session(meta["id"], "https://www.example.com/")
        assert FakeDriver.instances[-1].kwargs["storage_state"] is not None

    @pytest.mark.asyncio
    async def test_unknown_profile_and_bad_url(self, service, credentials_repo):
        meta = _add_profile(credentials_repo)
        with pytest.raises(LookupError):
            await service.test_session("nope", "https://www.example.com/")
        with pytest.raises(ValueError):
            await service.test_session(meta["id"], "file:///etc/passwd")

    @pytest.mark.asyncio
    async def test_navigation_errors_are_scrubbed_of_cookie_values(self, service, credentials_repo):
        from src.services.browser import BrowserSessionTestError

        meta = _add_profile(credentials_repo)

        async def boom(self, url, wait_until="domcontentloaded"):
            raise RuntimeError(f"net::ERR_FAILED at https://x/?t={SECRET}\n  stack line 2")

        with patch.object(FakeDriver, "navigate", boom):
            with pytest.raises(BrowserSessionTestError) as exc:
                await service.test_session(meta["id"], "https://www.example.com/")
        assert SECRET not in str(exc.value)
        assert "net::ERR_FAILED" in str(exc.value)
        assert "stack line 2" not in str(exc.value)
        assert FakeDriver.instances[-1].closed

    @pytest.mark.asyncio
    async def test_does_not_touch_the_shared_driver(self, service, credentials_repo):
        meta = _add_profile(credentials_repo)
        await service.test_session(meta["id"], "https://www.example.com/")
        assert service._driver is None


# ----------------------------------------------------------------------------
# Fetcher (browse_fetch): cookies reach Scrapling, scoped per URL
# ----------------------------------------------------------------------------


class TestFetcherCookies:
    def _provider(self, store):
        return store.cookies_for_url

    @pytest.mark.asyncio
    async def test_http_mode_sends_matching_cookies_only(self, store):
        store.create("A", parse_session_export(_export()))
        seen = {}

        class FakeFetcher:
            def get(self, url, **kwargs):
                seen[url] = kwargs
                return MagicMock()

        fetcher = ContentFetcher(cookie_provider=self._provider(store))
        with patch("scrapling.fetchers.Fetcher", FakeFetcher):
            await fetcher._fetch_http("https://www.example.com/")
            await fetcher._fetch_http("https://elsewhere.org/")
            await fetcher._fetch_http("http://www.example.com/")  # Secure cookie: not over http

        assert seen["https://www.example.com/"]["cookies"] == {"sid": SECRET}
        assert "cookies" not in seen["https://elsewhere.org/"]
        assert "cookies" not in seen["http://www.example.com/"]

    @pytest.mark.asyncio
    async def test_browser_modes_get_playwright_shaped_cookies(self, store):
        store.create("A", parse_session_export(_export()))
        captured = {}

        class FakeBrowserFetcher:
            async def async_fetch(self, url, **kwargs):
                captured.update(kwargs)
                return MagicMock()

        fetcher = ContentFetcher(cookie_provider=self._provider(store))
        with patch("scrapling.fetchers.DynamicFetcher", FakeBrowserFetcher):
            await fetcher._fetch_dynamic("https://www.example.com/", wait_for=".x")
        assert captured["cookies"][0]["name"] == "sid"
        assert captured["cookies"][0]["domain"] == ".example.com"

        captured.clear()
        with patch("scrapling.fetchers.StealthyFetcher", FakeBrowserFetcher):
            await fetcher._fetch_stealth("https://www.example.com/")
        assert captured["cookies"][0]["value"] == SECRET

    @pytest.mark.asyncio
    async def test_no_provider_or_no_match_adds_no_cookie_argument(self, store):
        captured = {}

        class FakeBrowserFetcher:
            async def async_fetch(self, url, **kwargs):
                captured.update(kwargs)
                return MagicMock()

        with patch("scrapling.fetchers.DynamicFetcher", FakeBrowserFetcher):
            await ContentFetcher()._fetch_dynamic("https://www.example.com/")
            assert "cookies" not in captured
            await ContentFetcher(cookie_provider=self._provider(store))._fetch_dynamic(
                "https://www.example.com/"
            )
            assert "cookies" not in captured

    def test_provider_errors_fall_back_to_anonymous(self):
        def boom(url):
            raise RuntimeError(SECRET)

        assert ContentFetcher(cookie_provider=boom)._cookies_for("https://example.com") == []

    @pytest.mark.asyncio
    async def test_service_browse_fetch_validates_url_and_hints(self, service, credentials_repo):
        _add_profile(credentials_repo)
        fetched = {}

        async def fake_fetch(self, url, **kwargs):
            fetched["url"] = url
            return {"url": url, "title": "t", "text": "hi", "status": 200, "message": "Fetched"}

        with patch("src.integrations.browser.fetcher.ContentFetcher.fetch", fake_fetch):
            result = await service.browse_fetch("https://www.example.com/x")
            assert result["authenticated_session"] == "Personal Gmail"
            assert SECRET not in json.dumps(result)
            with pytest.raises(ValueError):
                await service.browse_fetch("file:///etc/passwd")


# ----------------------------------------------------------------------------
# API: write-only
# ----------------------------------------------------------------------------


@pytest.fixture
def api(store):
    from src.api import browser as browser_api

    audit = MagicMock()
    fake_service = MagicMock()
    fake_service.test_session = AsyncMock(
        return_value={
            "final_url": "https://x.example.com/",
            "title": "T",
            "redirected_to_login": False,
        }
    )
    app = FastAPI()
    app.include_router(browser_api.router)
    app.dependency_overrides[browser_api.get_session_store] = lambda: store
    app.dependency_overrides[browser_api.get_audit_repo] = lambda: audit
    app.dependency_overrides[browser_api.get_browser_service] = lambda: fake_service
    return SimpleNamespace(client=TestClient(app), audit=audit, service=fake_service, store=store)


def _create(api, name="Personal Gmail", payload=None, **extra):
    body = {"name": name, "payload": payload or _export()}
    body.update(extra)
    return api.client.post("/api/browser/sessions", json=body)


class TestSessionsApi:
    def test_create_returns_metadata_only(self, api):
        r = _create(api)
        assert r.status_code == 201
        body = r.json()
        assert body["session"]["name"] == "Personal Gmail"
        assert body["session"]["domains"] == ["example.com"]
        assert body["session"]["cookie_count"] == 1
        assert SECRET not in r.text and '"sid"' not in r.text

    def test_list_never_contains_cookie_data(self, api):
        _create(api)
        r = api.client.get("/api/browser/sessions")
        assert r.status_code == 200 and len(r.json()) == 1
        assert (
            SECRET not in r.text
            and '"sid"' not in r.text
            and "cookies" not in r.text.replace("cookie_count", "")
        )

    def test_duplicate_name_conflicts(self, api):
        _create(api)
        assert _create(api, payload=_export(name="b")).status_code == 409

    def test_blank_or_overlong_name_is_422_not_409(self, api):
        assert _create(api, name="   ").status_code == 422
        assert _create(api, name="x" * 65).status_code == 422
        sid = _create(api).json()["session"]["id"]
        assert (
            api.client.patch(f"/api/browser/sessions/{sid}", json={"name": " "}).status_code == 422
        )

    def test_unparseable_export_is_422_without_echoing_values(self, api):
        r = _create(api, payload='[{"name": "x", "value": "' + SECRET + '"')  # truncated JSON
        assert r.status_code == 422
        assert "Could not parse cookie export" in r.json()["detail"]
        assert SECRET not in r.text

    def test_header_format_needs_domain(self, api):
        r = _create(api, payload="a=1; b=2", format="header")
        assert r.status_code == 422 and "domain is required" in r.json()["detail"]
        r = _create(api, name="Hdr", payload="a=1; b=2", format="header", domain="example.com")
        assert r.status_code == 201

    def test_patch_toggles_and_renames(self, api):
        sid = _create(api).json()["session"]["id"]
        r = api.client.patch(
            f"/api/browser/sessions/{sid}",
            json={"enabled": False, "persist_updates": False, "name": "Work"},
        )
        assert r.status_code == 200
        s = r.json()["session"]
        assert (s["enabled"], s["persist_updates"], s["name"]) == (False, False, "Work")

    def test_patch_replaces_cookies_and_bumps_revision(self, api):
        sid = _create(api).json()["session"]["id"]
        before = api.store._load()[0].revision
        r = api.client.patch(
            f"/api/browser/sessions/{sid}",
            json={"payload": _export(name="other", value="new-secret")},
        )
        assert r.status_code == 200 and "new-secret" not in r.text
        assert api.store._load()[0].revision == before + 1
        assert api.store.load_storage_state()["cookies"][0]["name"] == "other"

    def test_patch_bad_payload_leaves_session_untouched(self, api):
        sid = _create(api).json()["session"]["id"]
        r = api.client.patch(f"/api/browser/sessions/{sid}", json={"payload": "garbage ###"})
        assert r.status_code == 422
        assert api.store.load_storage_state()["cookies"][0]["value"] == SECRET

    def test_unknown_ids_404(self, api):
        assert (
            api.client.patch("/api/browser/sessions/nope", json={"enabled": True}).status_code
            == 404
        )
        assert api.client.delete("/api/browser/sessions/nope").status_code == 404

    def test_delete(self, api):
        sid = _create(api).json()["session"]["id"]
        r = api.client.delete(f"/api/browser/sessions/{sid}")
        assert r.status_code == 200 and r.json() == {"status": "deleted"}
        assert api.client.get("/api/browser/sessions").json() == []

    def test_audit_entries_are_masked(self, api):
        sid = _create(api).json()["session"]["id"]
        api.client.patch(
            f"/api/browser/sessions/{sid}", json={"payload": _export(value="v2-secret")}
        )
        api.client.delete(f"/api/browser/sessions/{sid}")
        assert api.audit.log_event.call_count == 3
        dumped = json.dumps([c.kwargs for c in api.audit.log_event.call_args_list], default=str)
        assert SECRET not in dumped and "v2-secret" not in dumped
        assert "***MASKED***" in dumped
        assert {c.kwargs["action"] for c in api.audit.log_event.call_args_list} == {
            "create_browser_session",
            "update_browser_session",
            "delete_browser_session",
        }

    def test_stored_row_is_ciphertext(self, api):
        _create(api)
        row = api.store.credentials_repo.fetch_one(
            "SELECT credential_data FROM service_credentials WHERE service_name = 'browser_sessions'"
        )
        assert SECRET not in row["credential_data"]

    def test_test_endpoint_maps_errors_without_leaking(self, api):
        sid = _create(api).json()["session"]["id"]
        url = f"/api/browser/sessions/{sid}/test"

        ok = api.client.post(url, json={"url": "https://x.example.com/"})
        assert ok.status_code == 200 and ok.json()["redirected_to_login"] is False

        api.service.test_session.side_effect = LookupError("Session not found")
        assert api.client.post(url, json={"url": "https://x.example.com/"}).status_code == 404

        api.service.test_session.side_effect = ValueError("Only absolute http:// and https:// URLs")
        assert api.client.post(url, json={"url": "file:///x"}).status_code == 400

        from src.services.browser import BrowserSessionTestError

        api.service.test_session.side_effect = BrowserSessionTestError("net::ERR_NAME_NOT_RESOLVED")
        r = api.client.post(url, json={"url": "https://x.example.com/"})
        assert r.status_code == 502 and "net::ERR_NAME_NOT_RESOLVED" in r.json()["detail"]

        api.service.test_session.side_effect = RuntimeError(f"net::ERR {SECRET}")
        r = api.client.post(url, json={"url": "https://x.example.com/"})
        assert r.status_code == 502 and SECRET not in r.text and "RuntimeError" in r.text


# ----------------------------------------------------------------------------
# Real Chromium end-to-end: a site that only answers logged-in requests
# ----------------------------------------------------------------------------

CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or "/opt/pw-browsers/chromium"


class _SiteHandler(BaseHTTPRequestHandler):
    """/inbox needs cookie sid=SECRET (and rotates it); /login is the bounce target."""

    seen_cookies = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        cookie = self.headers.get("Cookie", "")
        type(self).seen_cookies.append(cookie)
        if self.path.startswith("/inbox"):
            if f"sid={SECRET}" in cookie or f"sid={ROTATED}" in cookie:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                # Rotate the session cookie like a real site would.
                self.send_header("Set-Cookie", f"sid={ROTATED}; Path=/; Max-Age=86400; HttpOnly")
                self.end_headers()
                self.wfile.write(
                    b"<html><title>Inbox</title><body>Welcome back, owner</body></html>"
                )
                return
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><title>Login</title><body>Please sign in</body></html>")


@pytest.fixture
def site():
    _SiteHandler.seen_cookies = []
    server = HTTPServer(("127.0.0.1", 0), _SiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.mark.integration
@pytest.mark.skipif(not os.path.exists(CHROMIUM), reason="Chromium not available")
class TestRealBrowserEndToEnd:
    @pytest.fixture
    def real_service(self, credentials_repo, monkeypatch):
        from src.services.browser import BrowserService

        monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", CHROMIUM)
        settings = MagicMock()
        values = {"browser.enabled": True, "browser.headless": True}
        settings.get.side_effect = values.get
        return BrowserService(settings, credentials_repo, MagicMock())

    def _profile(self, credentials_repo, site, **kw):
        host = site.split("//")[1].split(":")[0]  # 127.0.0.1 (cookies ignore the port)
        raw = _export(domain=host, secure=False, **kw)
        return BrowserSessionStore(credentials_repo).create("Local site", parse_session_export(raw))

    @pytest.mark.asyncio
    async def test_logged_in_browse_then_rotated_cookie_is_persisted(
        self, real_service, credentials_repo, site
    ):
        self._profile(credentials_repo, site)

        result = await real_service.browse_url(f"{site}/inbox")
        assert result["title"] == "Inbox"
        assert result["authenticated_session"] == "Local site"
        assert "session_expired_suspected" not in result
        text = await real_service.browse_extract()
        assert "Welcome back, owner" in text["text"]
        assert any(f"sid={SECRET}" in c for c in _SiteHandler.seen_cookies)
        assert SECRET not in json.dumps(result) + json.dumps(text)

        # The rotated cookie is already saved after browse_url, without any close():
        # the web chat creates a service per request and never closes it.
        stored = BrowserSessionStore(credentials_repo).load_storage_state()
        assert [c["value"] for c in stored["cookies"]] == [ROTATED]

        await real_service.close()  # final flush must be harmless

        stored = BrowserSessionStore(credentials_repo).load_storage_state()
        assert [c["value"] for c in stored["cookies"]] == [ROTATED]

    @pytest.mark.asyncio
    async def test_without_session_the_site_bounces_to_login(self, real_service, site):
        result = await real_service.browse_url(f"{site}/inbox")
        assert result["title"] == "Login"
        assert "authenticated_session" not in result
        await real_service.close()

    @pytest.mark.asyncio
    async def test_bad_cookie_bounces_and_test_button_reports_login(
        self, real_service, credentials_repo, site
    ):
        meta = self._profile(credentials_repo, site, value="expired-or-wrong")
        result = await real_service.test_session(meta["id"], f"{site}/inbox")
        assert result["final_url"].endswith("/login")
        assert result["redirected_to_login"] is True

    @pytest.mark.asyncio
    async def test_browse_fetch_http_mode_is_authenticated(
        self, real_service, credentials_repo, site
    ):
        self._profile(credentials_repo, site)
        result = await real_service.browse_fetch(f"{site}/inbox", mode="http")
        assert "Welcome back, owner" in result["text"]
        assert result["authenticated_session"] == "Local site"
        assert SECRET not in json.dumps(result)

    @pytest.mark.asyncio
    async def test_javascript_url_never_reaches_the_browser(
        self, real_service, credentials_repo, site
    ):
        self._profile(credentials_repo, site)
        with pytest.raises(ValueError):
            await real_service.browse_url("javascript:document.title=document.cookie")
        assert real_service._driver is None
        await asyncio.sleep(0)
