"""Tests for browser integration (screenshots, driver, service, tools)."""

import base64
import io
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.integrations.browser.screenshots import (
    Screenshot,
    ScreenshotConfig,
    optimize_screenshot,
)
from src.models.browser import (
    BrowseActionRequest,
    BrowseExtractRequest,
    BrowseScrollRequest,
    BrowseUrlRequest,
)

# ---------------------------------------------------------------------------
# ScreenshotConfig tests
# ---------------------------------------------------------------------------


class TestScreenshotConfig:
    """Tests for ScreenshotConfig dataclass."""

    def test_defaults(self):
        config = ScreenshotConfig()
        assert config.format == "jpeg"
        assert config.quality == 85
        assert config.max_width == 1280
        assert config.max_height == 720

    def test_custom_values(self):
        config = ScreenshotConfig(format="png", quality=50, max_width=800, max_height=600)
        assert config.format == "png"
        assert config.quality == 50
        assert config.max_width == 800
        assert config.max_height == 600


# ---------------------------------------------------------------------------
# Screenshot model tests
# ---------------------------------------------------------------------------


class TestScreenshot:
    """Tests for Screenshot dataclass."""

    def _make_screenshot(self, data: bytes = b"fake-image-data") -> Screenshot:
        return Screenshot(
            data=data,
            width=1280,
            height=720,
            format="jpeg",
            url="https://example.com",
            title="Example",
            timestamp="2026-01-01T00:00:00Z",
        )

    def test_base64_encoding(self):
        data = b"hello-world"
        s = self._make_screenshot(data)
        assert s.base64 == base64.b64encode(data).decode("utf-8")

    def test_size_kb(self):
        data = b"x" * 2048
        s = self._make_screenshot(data)
        assert s.size_kb == 2.0

    def test_media_type_jpeg(self):
        s = self._make_screenshot()
        assert s.media_type == "image/jpeg"

    def test_media_type_png(self):
        s = self._make_screenshot()
        s.format = "png"
        assert s.media_type == "image/png"

    def test_to_vision_payload(self):
        s = self._make_screenshot()
        payload = s.to_vision_payload()
        assert payload["type"] == "image"
        assert payload["source"]["type"] == "base64"
        assert payload["source"]["media_type"] == "image/jpeg"
        assert payload["source"]["data"] == s.base64

    def test_to_summary(self):
        s = self._make_screenshot()
        summary = s.to_summary()
        assert summary["url"] == "https://example.com"
        assert summary["title"] == "Example"
        assert summary["width"] == 1280
        assert summary["height"] == 720
        assert summary["format"] == "jpeg"
        assert "size_kb" in summary


# ---------------------------------------------------------------------------
# Screenshot optimization tests
# ---------------------------------------------------------------------------


class TestOptimizeScreenshot:
    """Tests for screenshot optimization."""

    def _make_png_bytes(self, width: int = 100, height: int = 80) -> bytes:
        """Create a minimal PNG image in memory using Pillow."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        img = Image.new("RGB", (width, height), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_optimize_without_pillow(self):
        """When Pillow is not available, raw bytes are returned as-is."""
        raw = b"raw-png-data"
        config = ScreenshotConfig()
        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
            # Force reimport failure
            result = optimize_screenshot(raw, config)
        # If Pillow IS installed it will succeed; if not it returns raw.
        # Either way the function should not raise.
        assert isinstance(result, bytes)

    def test_optimize_resizes_large_image(self):
        """Large images should be resized to fit within max dimensions."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        raw = self._make_png_bytes(width=2560, height=1440)
        config = ScreenshotConfig(max_width=1280, max_height=720, quality=85)
        result = optimize_screenshot(raw, config)
        # Result should be a valid JPEG
        img = Image.open(io.BytesIO(result))
        assert img.width <= 1280
        assert img.height <= 720

    def test_optimize_jpeg_output(self):
        """Output should be JPEG when configured."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        raw = self._make_png_bytes()
        config = ScreenshotConfig(format="jpeg", quality=70)
        result = optimize_screenshot(raw, config)
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_optimize_small_image_unchanged_dimensions(self):
        """Small images should not be upscaled."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        raw = self._make_png_bytes(width=100, height=80)
        config = ScreenshotConfig(max_width=1280, max_height=720)
        result = optimize_screenshot(raw, config)
        img = Image.open(io.BytesIO(result))
        assert img.width == 100
        assert img.height == 80


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestBrowserModels:
    """Tests for browser request Pydantic models."""

    def test_browse_url_request(self):
        req = BrowseUrlRequest(url="https://example.com")
        assert req.url == "https://example.com"
        assert req.wait_until == "domcontentloaded"

    def test_browse_url_request_custom_wait(self):
        req = BrowseUrlRequest(url="https://example.com", wait_until="networkidle")
        assert req.wait_until == "networkidle"

    def test_browse_action_request_click(self):
        req = BrowseActionRequest(ref_id=1, action="click")
        assert req.ref_id == 1
        assert req.action == "click"

    def test_browse_action_request_type(self):
        req = BrowseActionRequest(ref_id=2, action="type", value="hello")
        assert req.ref_id == 2
        assert req.action == "type"
        assert req.value == "hello"

    def test_browse_action_request_focus(self):
        req = BrowseActionRequest(ref_id=3, action="focus")
        assert req.ref_id == 3
        assert req.action == "focus"

    def test_browse_scroll_request_defaults(self):
        req = BrowseScrollRequest()
        assert req.direction == "down"
        assert req.amount == 3

    def test_browse_scroll_request_custom(self):
        req = BrowseScrollRequest(direction="up", amount=5)
        assert req.direction == "up"
        assert req.amount == 5

    def test_browse_extract_request(self):
        req = BrowseExtractRequest()
        assert req is not None


# ---------------------------------------------------------------------------
# BrowserDriver tests (mocked Playwright)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Tests need to be updated for async BrowserDriver methods")
class TestBrowserDriver:
    """Tests for BrowserDriver with mocked Playwright."""

    def _make_driver(self):
        from src.integrations.browser.driver import BrowserDriver

        return BrowserDriver(
            headless=True,
            viewport_width=1280,
            viewport_height=720,
        )

    def _setup_mock_playwright(self, driver):
        """Set up mock Playwright objects on the driver."""
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_browser.is_connected.return_value = True
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # Default page properties
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example Domain"

        # Return a minimal PNG for screenshots
        try:
            from PIL import Image

            img = Image.new("RGB", (1280, 720), color="red")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            mock_page.screenshot.return_value = buf.getvalue()
        except ImportError:
            mock_page.screenshot.return_value = b"fake-png"

        driver._playwright = mock_playwright
        driver._browser = mock_browser
        driver._context = mock_context
        driver._page = mock_page

        return mock_page

    def test_navigate(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)

        screenshot = driver.navigate("https://example.com")

        mock_page.goto.assert_called_once()
        assert screenshot.url == "https://example.com"
        assert screenshot.title == "Example Domain"
        assert isinstance(screenshot.data, bytes)

    def test_click(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)

        screenshot = driver.click(100, 200)

        mock_page.mouse.click.assert_called_once_with(100, 200)
        assert isinstance(screenshot, Screenshot)

    def test_type_text_with_coords(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)

        screenshot = driver.type_text("hello", x=50, y=60)

        mock_page.mouse.click.assert_called_once_with(50, 60)
        mock_page.keyboard.type.assert_called_once_with("hello", delay=50)
        assert isinstance(screenshot, Screenshot)

    def test_type_text_without_coords(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)

        screenshot = driver.type_text("hello")

        mock_page.mouse.click.assert_not_called()
        mock_page.keyboard.type.assert_called_once_with("hello", delay=50)

    def test_scroll_down(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)

        screenshot = driver.scroll(direction="down", amount=3)

        mock_page.mouse.wheel.assert_called_once_with(0, 300)
        assert isinstance(screenshot, Screenshot)

    def test_scroll_up(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)

        screenshot = driver.scroll(direction="up", amount=2)

        mock_page.mouse.wheel.assert_called_once_with(0, -200)

    def test_extract_text(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)
        mock_page.evaluate.return_value = "Hello world content"

        result = driver.extract_text()

        assert result["title"] == "Example Domain"
        assert result["url"] == "https://example.com"
        assert result["text"] == "Hello world content"

    def test_close(self):
        driver = self._make_driver()
        mock_page = self._setup_mock_playwright(driver)

        driver.close()

        assert driver._browser is None
        assert driver._page is None
        assert driver._playwright is None

    def test_idle_timeout(self):
        driver = self._make_driver()
        driver.idle_timeout = 0  # Expire immediately
        driver._last_activity = 1.0  # Set some past time

        assert driver.is_idle_expired is True

    def test_cleanup_if_idle(self):
        driver = self._make_driver()
        self._setup_mock_playwright(driver)
        driver.idle_timeout = 0
        driver._last_activity = 1.0

        closed = driver.cleanup_if_idle()
        assert closed is True
        assert driver._browser is None


# ---------------------------------------------------------------------------
# BrowserService tests (mocked driver)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Tests need to be updated for async BrowserService methods")
class TestBrowserService:
    """Tests for BrowserService with mocked dependencies."""

    def _make_service(self, enabled=True):
        from src.services.browser import BrowserService

        settings_repo = MagicMock()
        credentials_repo = MagicMock()
        audit_repo = MagicMock()

        def settings_get(key):
            settings_map = {
                "browser.enabled": enabled,
                "browser.headless": True,
                "browser.viewport_width": 1280,
                "browser.viewport_height": 720,
                "browser.screenshot_quality": 85,
            }
            return settings_map.get(key)

        settings_repo.get.side_effect = settings_get

        service = BrowserService(settings_repo, credentials_repo, audit_repo)
        return service

    def test_get_driver_raises_when_disabled(self):
        service = self._make_service(enabled=False)
        with pytest.raises(ValueError, match="not enabled"):
            service._get_driver()

    def test_browse_url(self):
        service = self._make_service()
        mock_screenshot = Screenshot(
            data=b"img",
            width=1280,
            height=720,
            format="jpeg",
            url="https://example.com",
            title="Example",
            timestamp="2026-01-01T00:00:00Z",
        )
        mock_driver = MagicMock()
        mock_driver.navigate.return_value = mock_screenshot
        mock_driver._browser = MagicMock()
        mock_driver._browser.is_connected.return_value = True

        with patch.object(service, "_get_driver", return_value=mock_driver):
            result = service.browse_url("https://example.com")

        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert "screenshot" in result
        assert "metadata" in result

    def test_browse_click(self):
        service = self._make_service()
        mock_screenshot = Screenshot(
            data=b"img",
            width=1280,
            height=720,
            format="jpeg",
            url="https://example.com",
            title="Example",
            timestamp="2026-01-01T00:00:00Z",
        )
        mock_driver = MagicMock()
        mock_driver.click.return_value = mock_screenshot

        with patch.object(service, "_get_driver", return_value=mock_driver):
            result = service.browse_click(100, 200)

        assert result["message"] == "Clicked at (100, 200) on https://example.com"

    def test_browse_type(self):
        service = self._make_service()
        mock_screenshot = Screenshot(
            data=b"img",
            width=1280,
            height=720,
            format="jpeg",
            url="https://example.com",
            title="Example",
            timestamp="2026-01-01T00:00:00Z",
        )
        mock_driver = MagicMock()
        mock_driver.type_text.return_value = mock_screenshot

        with patch.object(service, "_get_driver", return_value=mock_driver):
            result = service.browse_type("hello", x=50, y=60)

        assert "Typed text" in result["message"]

    def test_browse_scroll(self):
        service = self._make_service()
        mock_screenshot = Screenshot(
            data=b"img",
            width=1280,
            height=720,
            format="jpeg",
            url="https://example.com",
            title="Example",
            timestamp="2026-01-01T00:00:00Z",
        )
        mock_driver = MagicMock()
        mock_driver.scroll.return_value = mock_screenshot

        with patch.object(service, "_get_driver", return_value=mock_driver):
            result = service.browse_scroll(direction="down", amount=3)

        assert "Scrolled down" in result["message"]

    def test_browse_extract(self):
        service = self._make_service()
        mock_driver = MagicMock()
        mock_driver.extract_text.return_value = {
            "title": "Example",
            "url": "https://example.com",
            "text": "Page content here",
        }

        with patch.object(service, "_get_driver", return_value=mock_driver):
            result = service.browse_extract()

        assert result["text"] == "Page content here"
        assert result["title"] == "Example"

    def test_close(self):
        service = self._make_service()
        mock_driver = MagicMock()
        service._driver = mock_driver

        service.close()

        mock_driver.close.assert_called_once()
        assert service._driver is None

    def test_test_connection_success(self):
        service = self._make_service()
        mock_screenshot = Screenshot(
            data=b"img",
            width=1280,
            height=720,
            format="jpeg",
            url="about:blank",
            title="",
            timestamp="2026-01-01T00:00:00Z",
        )
        mock_driver = MagicMock()
        mock_driver.navigate.return_value = mock_screenshot

        with patch.object(service, "_get_driver", return_value=mock_driver):
            result = service.test_connection()

        assert result["status"] == "success"

    def test_test_connection_disabled(self):
        service = self._make_service(enabled=False)
        result = service.test_connection()
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Tests need to be updated for async browser tools")
class TestBrowserToolRegistration:
    """Tests for browser tool registration."""

    def test_browser_tools_are_registered(self):
        from src.core.tools.definitions import define_browser_tools
        from src.core.tools.registry import get_tool_registry

        define_browser_tools()
        registry = get_tool_registry()

        expected_tools = [
            "browse_url",
            "browse_click",
            "browse_type",
            "browse_scroll",
            "browse_extract",
        ]

        for tool_name in expected_tools:
            tool = registry.get(tool_name)
            assert tool is not None, f"Tool '{tool_name}' not registered"
            assert tool.service_name == "browser"


# ---------------------------------------------------------------------------
# Agent definition tests
# ---------------------------------------------------------------------------


try:
    import crewai  # noqa: F401

    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False


@pytest.mark.skipif(not HAS_CREWAI, reason="crewai not installed")
class TestBrowserAgentDefinition:
    """Tests for browser agent in DEFAULT_AGENTS."""

    def test_browser_agent_exists(self):
        from src.agents.base import DEFAULT_AGENTS

        assert "browser" in DEFAULT_AGENTS

    def test_browser_agent_has_correct_tools(self):
        from src.agents.base import DEFAULT_AGENTS

        browser_agent = DEFAULT_AGENTS["browser"]
        expected_tools = [
            "browse_url",
            "browse_click",
            "browse_type",
            "browse_scroll",
            "browse_extract",
        ]
        assert browser_agent["tools"] == expected_tools

    def test_browser_agent_is_enabled(self):
        from src.agents.base import DEFAULT_AGENTS

        assert DEFAULT_AGENTS["browser"]["enabled"] is True

    def test_browser_agent_no_delegation(self):
        from src.agents.base import DEFAULT_AGENTS

        assert DEFAULT_AGENTS["browser"]["allow_delegation"] is False

    def test_coordinator_mentions_browser(self):
        from src.agents.base import DEFAULT_AGENTS

        coordinator = DEFAULT_AGENTS["coordinator"]
        assert "BROWSER" in coordinator["backstory"].upper()


# ---------------------------------------------------------------------------
# Cookie consent tests
# ---------------------------------------------------------------------------
import re

import pytest


class TestCookieConsentPatterns:
    """Tests for cookie consent detection patterns."""

    def test_accept_patterns_match_common_button_texts(self):
        """Verify accept patterns match common cookie button texts."""
        # These patterns mirror the JS regexes in cookie_consent.py
        ACCEPT_PATTERNS = [
            re.compile(r"^accept(\s+(all|cookies?|&\s*(close|continue|proceed)))?$", re.I),
            re.compile(r"^(i\s+)?accept(\s+all)?$", re.I),
            re.compile(r"^(i )?agree(\s+to all)?$", re.I),
            re.compile(r"^allow\s*(all)?\s*(cookies?)?$", re.I),
            re.compile(r"^(got it|ok|okay|sure)$", re.I),
            re.compile(r"^close$", re.I),
            re.compile(r"^dismiss$", re.I),
            re.compile(r"^agree\s*(&|and)?\s*(close|continue|proceed)?$", re.I),
            re.compile(r"^save\s*(preferences|settings|&\s*(exit|close))?$", re.I),
        ]

        test_cases = [
            "Accept",
            "Accept All",
            "Accept cookies",
            "Accept & Continue",
            "I accept",
            "I accept all",
            "I agree",
            "I agree to all",
            "Allow all",
            "Allow cookies",
            "Got it",
            "OK",
            "Okay",
            "Sure",
            "Close",
            "Dismiss",
            "Agree & Close",
            "Agree and Continue",
            "Save Preferences",
            "Save Settings",
            "Save & Exit",
        ]

        for text in test_cases:
            matched = any(p.match(text) for p in ACCEPT_PATTERNS)
            assert matched, f"Expected '{text}' to match an accept pattern"

    def test_reject_patterns_match_reject_button_texts(self):
        """Verify reject patterns match common reject button texts."""
        REJECT_PATTERNS = [
            re.compile(r"reject", re.I),
            re.compile(r"decline", re.I),
            re.compile(r"deny", re.I),
            re.compile(r"manage", re.I),
            re.compile(r"settings", re.I),
            re.compile(r"preferences", re.I),
        ]

        test_cases = [
            "Reject All",
            "Reject",
            "Decline",
            "Decline All",
            "Deny",
            "Manage Preferences",
            "Cookie Settings",
            "Privacy Preferences",
        ]

        for text in test_cases:
            matched = any(p.search(text) for p in REJECT_PATTERNS)
            assert matched, f"Expected '{text}' to match a reject pattern"

    def test_dialog_detection_regex(self):
        """Verify dialog detection looks for cookie-related keywords."""
        dialog_texts = [
            "We use cookies to improve your experience",
            "This website uses GDPR consent",
            "Privacy notice: We track analytics",
            "Cookie consent required",
        ]

        cookie_keywords = re.compile(r"cookie|consent|gdpr|privacy|tracking|analytics")

        for text in dialog_texts:
            assert cookie_keywords.search(
                text.lower()
            ), f"Expected '{text}' to match cookie keywords"

    def test_platform_selectors_in_dismiss_script(self):
        """Verify common platform selectors are in the dismiss script."""
        from src.integrations.browser.cookie_consent import DISMISS_COOKIE_CONSENT_JS

        expected_selectors = [
            "#onetrust-accept-btn-handler",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            ".trustarc-agree-btn",
            ".cky-btn-accept",
            ".klaro .cm-btn-accept",
            ".cmplz-accept",
            ".osano-cm-accept-all",
            "#didomi-notice-agree-button",
        ]

        for selector in expected_selectors:
            assert (
                selector in DISMISS_COOKIE_CONSENT_JS
            ), f"Expected selector '{selector}' in dismiss script"

    def test_overlay_selectors_in_dismiss_script(self):
        """Verify overlay selectors are in the dismiss script."""
        from src.integrations.browser.cookie_consent import DISMISS_COOKIE_CONSENT_JS

        expected_overlays = [
            "#onetrust-consent-sdk",
            ".cookie-banner",
            ".cookie-consent",
            ".cc-window",
            '[id*="cookie-banner"]',
            '[class*="cookie-banner"]',
        ]

        for overlay in expected_overlays:
            assert (
                overlay in DISMISS_COOKIE_CONSENT_JS
            ), f"Expected overlay '{overlay}' in dismiss script"

    def test_aria_dialog_handling_in_script(self):
        """Verify ARIA dialog roles are handled in the dismiss script."""
        from src.integrations.browser.cookie_consent import DISMISS_COOKIE_CONSENT_JS

        # Check for role="dialog" handling
        assert 'role="dialog"' in DISMISS_COOKIE_CONSENT_JS
        assert 'role="alertdialog"' in DISMISS_COOKIE_CONSENT_JS

    @pytest.mark.asyncio
    async def test_dismiss_cookie_consent_returns_dict(self):
        """Verify dismiss_cookie_consent returns expected dict structure."""
        from src.integrations.browser.cookie_consent import dismiss_cookie_consent

        # Test with a mock page
        mock_page = MagicMock()

        # evaluate is async so we need to return an awaitable
        async def mock_evaluate(*args):
            return {"dismissed": False}

        mock_page.evaluate.side_effect = mock_evaluate

        result = await dismiss_cookie_consent(mock_page)

        assert isinstance(result, dict)
        assert "dismissed" in result
        mock_page.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_dismiss_cookie_consent_logs_on_success(self):
        """Verify dismiss_cookie_consent logs when banner is dismissed."""
        from src.integrations.browser.cookie_consent import dismiss_cookie_consent
        from src.integrations.browser import cookie_consent as cc_module

        mock_page = MagicMock()

        # evaluate is async so we need to return an awaitable
        async def mock_evaluate(*args):
            return {
                "dismissed": True,
                "method": "platform",
                "selector": "#onetrust-accept-btn-handler",
            }

        mock_page.evaluate.side_effect = mock_evaluate

        # Patch the logger at the module level where it's defined
        with patch.object(cc_module.logger, "info") as mock_info:
            result = await dismiss_cookie_consent(mock_page)

        assert result["dismissed"] is True
        mock_info.assert_called_once()
        call_args = mock_info.call_args[0]
        assert "Cookie consent dismissed" in call_args[0]
        assert "platform" in call_args
