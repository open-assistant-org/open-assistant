"""Drift-guard: browser settings, session API and result keys stay documented.

Saved browser logins touch code, the browser agent's prompt (a DB migration) and several
docs pages. These tests fail if they silently go out of sync.

If one fails, update the code AND the docs/migration named in the message in the same PR.
"""

import re
from pathlib import Path

import pytest

from src.api.browser import router as browser_router
from src.models.config import SETTING_DEFINITIONS

REPO_ROOT = Path(__file__).parent.parent
DOCS = REPO_ROOT / "docs"
BROWSER_DOC = DOCS / "integrations" / "browser.md"
MANUAL = DOCS / "integrations" / "browser-sessions.md"
SECURITY_DOC = DOCS / "integrations" / "browser-sessions-security.md"
CONFIG_DOC = DOCS / "setup" / "configuration.md"
MIGRATION = REPO_ROOT / "src" / "core" / "migrations" / "061_browser_authenticated_sessions.sql"
MKDOCS = REPO_ROOT / "mkdocs.yml"

# Keys the service adds to tool results / that the browser agent prompt refers to.
RESULT_KEYS = ["authenticated_session", "session_expired_suspected"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


BROWSER_KEYS = sorted(k for k in SETTING_DEFINITIONS if k.startswith("browser."))


def test_browser_settings_exist():
    assert "browser.user_agent" in BROWSER_KEYS


@pytest.mark.parametrize("key", BROWSER_KEYS)
def test_every_browser_setting_is_documented_in_browser_reference(key):
    assert f"`{key}`" in _read(BROWSER_DOC), (
        f"{key} is defined in src/models/config.py but missing from the Configuration "
        "table in docs/integrations/browser.md"
    )


@pytest.mark.parametrize("key", BROWSER_KEYS)
def test_every_browser_setting_is_documented_in_configuration_guide(key):
    assert f"`{key}`" in _read(
        CONFIG_DOC
    ), f"{key} is missing from the Browser section of docs/setup/configuration.md"


def _session_routes():
    for route in browser_router.routes:
        if route.path.startswith("/api/browser/sessions"):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, route.path.replace("{session_id}", "{id}")


def test_session_routes_found():
    assert len(list(_session_routes())) >= 5


@pytest.mark.parametrize("method,path", sorted(_session_routes()))
def test_every_session_endpoint_is_documented(method, path):
    text = _read(BROWSER_DOC)
    row = re.compile(rf"\|\s*`{method}`\s*\|\s*`{re.escape(path)}`")
    assert row.search(text), (
        f"{method} {path} exists in src/api/browser.py but has no row in the "
        "'Saved login endpoints' table of docs/integrations/browser.md"
    )


@pytest.mark.parametrize("key", RESULT_KEYS)
def test_result_keys_are_documented(key):
    assert key in _read(BROWSER_DOC), f"`{key}` is not explained in docs/integrations/browser.md"


@pytest.mark.parametrize("key", RESULT_KEYS)
def test_agent_prompt_migration_mentions_result_keys(key):
    """The browser agent prompt (migration 061) must name the keys the service emits."""
    assert key in _read(MIGRATION), (
        f"Migration 061 (browser agent prompt) does not mention `{key}`; the agent would not "
        "know how to react to it"
    )


@pytest.mark.parametrize("key", RESULT_KEYS)
def test_service_actually_emits_result_keys(key):
    """Guards the other direction: docs/prompt mention keys the code no longer produces."""
    assert f'"{key}"' in _read(REPO_ROOT / "src" / "services" / "browser.py")


def test_manuals_exist_and_are_in_nav():
    nav = _read(MKDOCS)
    for doc in (MANUAL, SECURITY_DOC):
        assert doc.exists()
        assert f"integrations/{doc.name}" in nav, f"{doc.name} missing from mkdocs.yml nav"


def test_browser_reference_links_both_manuals():
    text = _read(BROWSER_DOC)
    assert "browser-sessions.md" in text and "browser-sessions-security.md" in text


def test_no_stale_cookie_persistence_claim():
    """The old 'No cookie persistence' limitation must not come back unqualified."""
    for path in DOCS.rglob("*.md"):
        assert "No cookie persistence" not in _read(path), f"stale claim in {path}"


def test_ui_doc_links_point_at_published_pages():
    """Links to docs.open-assistant.org in the settings UI must resolve to real docs pages."""
    site_url = re.search(r"^site_url:\s*(\S+)", _read(MKDOCS), re.M).group(1).rstrip("/")
    js = _read(REPO_ROOT / "src" / "ui" / "static" / "js" / "settings.js")
    links = re.findall(re.escape(site_url) + r"/([\w./-]+)", js)
    assert links, "expected the settings UI to link to the published browser manual"
    for path in links:
        page = DOCS / (path.strip("/") + ".md")
        assert page.exists(), f"settings.js links to {site_url}/{path} but {page} does not exist"
        assert path.endswith("/"), "mkdocs publishes directory URLs (trailing slash)"
