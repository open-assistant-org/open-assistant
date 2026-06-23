"""Browser service for web browsing with accessibility-tree-based page understanding."""

from typing import Any, Dict, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.browser.cookie_consent import dismiss_cookie_consent
from src.integrations.browser.driver import BrowserDriver
from src.integrations.browser.fetcher import ContentFetcher
from src.integrations.browser.screenshots import ScreenshotConfig
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BrowserService(BaseService):
    """Service for web browsing operations via Playwright with accessibility tree."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)
        self._driver: Optional[BrowserDriver] = None

    async def _get_or_create_driver(self) -> BrowserDriver:
        """
        Return the existing browser driver if alive, or create a new one.

        This preserves the browser session across tool calls so that
        browse_action, browse_get_tree, browse_scroll, and browse_extract
        can operate on the page loaded by a previous browse_url call.

        Returns:
            BrowserDriver instance.

        Raises:
            ValueError: If browser integration is not enabled.
        """
        enabled = self.settings_repo.get("browser.enabled")
        if not enabled:
            raise ValueError("Browser integration is not enabled. Enable it in Settings.")

        # Reuse existing driver if it's still alive and not idle-expired
        if self._driver is not None:
            if self._driver.is_idle_expired:
                logger.info("Browser session idle-expired, creating fresh driver")
                await self._close_driver()
            else:
                return self._driver

        return await self._create_driver()

    async def _create_fresh_driver(self) -> BrowserDriver:
        """
        Close any existing driver and create a brand-new one.

        Used by browse_url when navigating to a new URL (intentional reset).

        Returns:
            BrowserDriver instance.

        Raises:
            ValueError: If browser integration is not enabled.
        """
        enabled = self.settings_repo.get("browser.enabled")
        if not enabled:
            raise ValueError("Browser integration is not enabled. Enable it in Settings.")

        await self._close_driver()
        return await self._create_driver()

    async def _create_driver(self) -> BrowserDriver:
        """Create a new BrowserDriver from current settings."""
        headless = self.settings_repo.get("browser.headless")
        if headless is None:
            headless = True
        else:
            headless = bool(headless)

        viewport_width = int(self.settings_repo.get("browser.viewport_width") or 1280)
        viewport_height = int(self.settings_repo.get("browser.viewport_height") or 720)
        screenshot_quality = int(self.settings_repo.get("browser.screenshot_quality") or 85)

        screenshot_config = ScreenshotConfig(
            format="jpeg",
            quality=screenshot_quality,
            max_width=viewport_width,
            max_height=viewport_height,
        )

        self._driver = BrowserDriver(
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            screenshot_config=screenshot_config,
        )

        return self._driver

    async def _close_driver(self) -> None:
        """Close the current driver if one exists."""
        if self._driver is not None:
            try:
                await self._driver.close()
            except Exception as e:
                logger.warning(f"Error closing previous driver: {e}")
            self._driver = None

    def _get_fetcher(self) -> ContentFetcher:
        """Create a ContentFetcher from current settings."""
        default_mode = self.settings_repo.get("browser.scrapling_default_mode") or "http"
        timeout = int(self.settings_repo.get("browser.scrapling_timeout") or 30)
        return ContentFetcher(default_mode=str(default_mode), timeout=timeout)

    async def browse_fetch(
        self,
        url: str,
        mode: Optional[str] = None,
        selector: Optional[str] = None,
        wait_for: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch and extract content from a URL using Scrapling.

        Uses Scrapling's fetcher backends for efficient content extraction
        with anti-bot bypass capabilities. Does not require a full browser
        session for simple HTTP fetches.

        Args:
            url: URL to fetch content from.
            mode: Fetcher mode - 'http' (fast TLS-impersonated HTTP),
                  'stealth' (Camoufox with Cloudflare bypass),
                  'dynamic' (Playwright with anti-detection).
            selector: CSS selector to extract specific content.
            wait_for: CSS selector to wait for before extraction
                      (only used with 'dynamic' mode).

        Returns:
            Dict with url, title, text, status, selected_content, and message.
        """
        enabled = self.settings_repo.get("browser.enabled")
        if not enabled:
            raise ValueError("Browser integration is not enabled. Enable it in Settings.")

        fetcher = self._get_fetcher()
        return await fetcher.fetch(url, mode=mode, selector=selector, wait_for=wait_for)

    async def browse_url(self, url: str, wait_until: Optional[str] = None) -> Dict[str, Any]:
        """
        Navigate to URL and return accessibility tree + metadata.

        Creates a fresh browser session for the new navigation.

        Args:
            url: URL to navigate to
            wait_until: Playwright wait condition

        Returns:
            Dict with tree, metadata, and message
        """
        driver = await self._create_fresh_driver()
        wait = wait_until or "domcontentloaded"

        # Navigate with timeout handling
        try:
            await driver.navigate(url, wait_until=wait)
        except Exception as e:
            logger.warning(f"Navigation error: {e}")
            # Continue to try extracting tree

        # Get accessibility tree
        tree_result = await driver.get_accessibility_tree(mode="interactive")

        # If the page returned no elements, it likely hasn't fully rendered yet or a
        # cookie/paywall overlay is blocking everything. Try harder before giving up:
        #   1. Wait 3 s for late-loading JS (SPAs, async consent managers).
        #   2. Re-run cookie-consent dismissal (in case the banner loaded after navigate).
        #   3. Re-extract the tree.
        #   4. If still empty, reload with networkidle and repeat once more.
        if tree_result.get("node_count", 0) == 0:
            logger.info("No elements found on first pass - waiting and retrying dismissal")
            await driver._page.wait_for_timeout(3000)
            await dismiss_cookie_consent(driver._page)
            await driver._page.wait_for_timeout(1000)
            tree_result = await driver.get_accessibility_tree(mode="interactive")

            if tree_result.get("node_count", 0) == 0:
                logger.info("Still no elements - retrying navigation with networkidle")
                try:
                    await driver._page.goto(url, wait_until="networkidle", timeout=30_000)
                    await driver._page.wait_for_timeout(1500)
                    await dismiss_cookie_consent(driver._page)
                    await driver._page.wait_for_timeout(800)
                    tree_result = await driver.get_accessibility_tree(mode="interactive")
                except Exception as e:
                    logger.warning(f"networkidle retry failed: {e}")

            # Log final outcome after all retries
            if tree_result.get("node_count", 0) == 0:
                logger.warning(
                    "Accessibility tree extraction returned no elements after all retries. "
                    "Page may have blocking overlays, be a SPA still loading, or be inaccessible."
                )

        result = {
            "url": tree_result["url"],
            "title": tree_result["title"],
            "tree": tree_result["tree"],
            "node_count": tree_result.get("node_count", 0),
            "token_estimate": tree_result.get("token_estimate", 0),
            "message": (
                f"Navigated to {tree_result['url']} - '{tree_result['title']}'\n\n"
                f"Accessibility tree extracted with {tree_result.get('node_count', 0)} elements. "
                f"Use browse_action(ref=N, action='click') to interact with elements."
            ),
        }

        # Check for sparse content
        if tree_result.get("node_count", 0) < 5:
            result["content_sparse"] = True
            result["message"] += (
                "\n\n⚠️ WARNING: Page appears to have very few interactive elements. "
                "This may be a JavaScript-heavy SPA that hasn't fully loaded, or a page with "
                "minimal content. Consider trying an alternative URL, searching for cached "
                "content, or using a different data source."
            )

        return result

    async def browse_get_tree(self, mode: str = "interactive") -> Dict[str, Any]:
        """
        Get accessibility tree of current page (reuses existing session).

        Args:
            mode: Filter mode - "full", "interactive", "forms"

        Returns:
            Dict with tree and metadata
        """
        driver = await self._get_or_create_driver()
        tree_result = await driver.get_accessibility_tree(mode=mode)

        return {
            "url": tree_result["url"],
            "title": tree_result["title"],
            "tree": tree_result["tree"],
            "node_count": tree_result.get("node_count", 0),
            "token_estimate": tree_result.get("token_estimate", 0),
            "message": f"Extracted accessibility tree with {tree_result.get('node_count', 0)} elements",
        }

    async def browse_action(
        self, ref_id: int, action: str, value: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute action on element by reference ID (reuses existing session).

        After a successful action, automatically refreshes the accessibility
        tree so the LLM can see the updated page state without a separate
        browse_get_tree call.

        Args:
            ref_id: Element reference from tree
            action: Action to perform
            value: Optional value for type action

        Returns:
            Dict with result, message, and updated accessibility tree
        """
        driver = await self._get_or_create_driver()

        result = await driver.execute_action(ref_id, action, value)

        if result.get("success"):
            action_desc = f"{action} on ref={ref_id}"
            if value:
                action_desc += f" with value '{value[:50]}...'"

            # Auto-refresh the accessibility tree after action
            tree_result = await driver.get_accessibility_tree(mode="interactive")

            return {
                "url": result["url"],
                "title": result["title"],
                "message": (
                    f"Successfully executed: {action_desc}\n"
                    f"Page is now: {result['url']} - '{result['title']}'\n\n"
                    f"Updated accessibility tree ({tree_result.get('node_count', 0)} elements):"
                ),
                "tree": tree_result.get("tree", ""),
                "node_count": tree_result.get("node_count", 0),
                "ref_id": ref_id,
                "action": action,
            }
        else:
            return {
                "error": result.get("error", "Unknown error"),
                "message": f"Failed to execute {action} on ref={ref_id}: {result.get('error', 'Unknown error')}",
            }

    async def browse_scroll(self, direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        """
        Scroll the current page (reuses existing session).

        After scrolling, automatically refreshes the accessibility tree
        so the LLM can see newly visible elements.

        Args:
            direction: 'up' or 'down'.
            amount: Number of scroll ticks.

        Returns:
            Dict with updated accessibility tree and metadata.
        """
        driver = await self._get_or_create_driver()
        await driver.scroll(direction=direction, amount=amount)

        # Auto-refresh tree after scroll so LLM sees new elements
        tree_result = await driver.get_accessibility_tree(mode="interactive")

        return {
            "url": tree_result["url"],
            "title": tree_result["title"],
            "tree": tree_result.get("tree", ""),
            "node_count": tree_result.get("node_count", 0),
            "message": (
                f"Scrolled {direction} on {tree_result['url']}\n\n"
                f"Updated accessibility tree ({tree_result.get('node_count', 0)} elements):"
            ),
        }

    async def browse_extract(self) -> Dict[str, Any]:
        """
        Extract visible text from the current page (reuses existing session).

        Returns:
            Dict with extracted text, title, and URL.
        """
        driver = await self._get_or_create_driver()
        result = await driver.extract_text()
        return {
            "url": result["url"],
            "title": result["title"],
            "text": result["text"],
            "message": f"Extracted text from {result['url']}",
        }

    async def close(self) -> None:
        """Close the browser session."""
        await self._close_driver()
        logger.info("Browser service closed")

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the browser integration.

        Returns:
            Dict with test results.
        """
        # Simple sync test - just check if settings are configured
        enabled = self.settings_repo.get("browser.enabled")
        if not enabled:
            return {
                "service_name": "browser",
                "status": "error",
                "message": "Browser integration is not enabled",
            }

        return {
            "service_name": "browser",
            "status": "success",
            "message": "Browser integration is enabled and configured",
        }
