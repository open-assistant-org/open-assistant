"""Browser service for web browsing with accessibility-tree-based page understanding."""

from typing import Any, Dict, Optional

from src.core.concurrency import get_browser_semaphore
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.browser.cookie_consent import dismiss_cookie_consent
from src.integrations.browser.driver import BrowserDriver, validate_navigation_url
from src.integrations.browser.fetcher import ContentFetcher
from src.integrations.browser.screenshots import ScreenshotConfig
from src.integrations.browser.sessions import BrowserSessionStore, looks_like_login_url
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BrowserSessionTestError(Exception):
    """A saved-session test failed; the message is safe to show to the user."""


def _scrub_error(message: str, secrets: set) -> str:
    """First line of an error with any known secret values masked and length capped."""
    lines = [ln.strip() for ln in str(message).splitlines() if ln.strip()]
    text = lines[0] if lines else "unknown error"
    for secret in sorted(secrets, key=len, reverse=True):
        if len(secret) >= 6:
            text = text.replace(secret, "***")
    return text[:300]


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
        # Saved logins (cookies/localStorage), encrypted in service_credentials.
        # Injected below the tool layer: the model only ever sees a profile name.
        self._sessions = BrowserSessionStore(credentials_repo)
        # Profile revisions when the current driver started (see apply_updates).
        self._session_revisions: Dict[str, int] = {}

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

    def _driver_kwargs(self) -> Dict[str, Any]:
        """BrowserDriver constructor arguments derived from current settings."""
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

        user_agent = self.settings_repo.get("browser.user_agent")
        return {
            "headless": headless,
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            "screenshot_config": screenshot_config,
            "user_agent": (
                user_agent if isinstance(user_agent, str) and user_agent.strip() else None
            ),
        }

    async def _create_driver(self) -> BrowserDriver:
        """Create a new BrowserDriver from current settings and saved sessions."""
        self._session_revisions = revisions = self._sessions.snapshot_revisions()
        self._driver = BrowserDriver(
            **self._driver_kwargs(),
            storage_state=self._sessions.load_storage_state(),
            on_close=lambda state: self._persist_session_state(state, revisions),
        )

        return self._driver

    def _persist_session_state(
        self, state: Optional[Dict[str, Any]], revisions: Optional[Dict[str, int]] = None
    ) -> None:
        """Write cookies rotated during a browser session back to the encrypted store.

        ``revisions`` is the snapshot taken when the browser started; profiles the
        user replaced since then are skipped so a fresh import is never clobbered.
        """
        self._sessions.apply_updates(state, expected_revisions=revisions)

    async def _flush_session(self, driver: BrowserDriver) -> None:
        """Save cookies the site has rotated so far (a no-op when nothing changed).

        Called after calls that can renew a login so "Keep refreshed" does not depend
        on the browser session being closed cleanly (the web chat builds a new
        service per request and never closes it). Close still flushes as a final pass.
        """
        try:
            state = await driver.export_storage_state()
            self._persist_session_state(state, self._session_revisions)
        except Exception as e:
            logger.warning(f"Could not save refreshed session cookies ({type(e).__name__})")

    def _session_hint(self, url: Optional[str]) -> Optional[str]:
        """Name of the saved session active for ``url`` (never any cookie data)."""
        if not url:
            return None
        try:
            return self._sessions.profile_for_url(url)
        except Exception as e:
            logger.warning(f"Could not resolve saved session for page: {type(e).__name__}")
            return None

    def _annotate_session(self, result: Dict[str, Any], url: Optional[str]) -> Dict[str, Any]:
        """Tell the model, in words only, whether a saved login is active on this page."""
        name = self._session_hint(url)
        if not name:
            return result
        result["authenticated_session"] = name
        if url and looks_like_login_url(url):
            result["session_expired_suspected"] = True
            note = (
                f"Saved session '{name}' was loaded but the site is showing a login page, so it has "
                "probably expired. Do not try to log in or ask for a password; tell the user to "
                "refresh that session in Settings > Integrations > Browser."
            )
        else:
            note = f"Using saved session '{name}' (already logged in; do not try to log in)."
        if "message" in result:
            result["message"] = f"{result['message']}\n\n{note}"
        return result

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
        return ContentFetcher(
            default_mode=str(default_mode),
            timeout=timeout,
            cookie_provider=self._sessions.cookies_for_url,
        )

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
        url = validate_navigation_url(url)

        fetcher = self._get_fetcher()
        result = await fetcher.fetch(url, mode=mode, selector=selector, wait_for=wait_for)
        return self._annotate_session(result, result.get("url") or url)

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
        url = validate_navigation_url(url)
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

        self._annotate_session(result, tree_result["url"])
        await self._flush_session(driver)

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
            await self._flush_session(driver)

            return self._annotate_session(
                {
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
                },
                result["url"],
            )
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
        return self._annotate_session(
            {
                "url": result["url"],
                "title": result["title"],
                "text": result["text"],
                "message": f"Extracted text from {result['url']}",
            },
            result["url"],
        )

    async def test_session(self, profile_id: str, url: str) -> Dict[str, Any]:
        """Open ``url`` in a throwaway browser carrying only one saved session.

        Used by the Settings "Test" button. Never touches the shared browser
        driver, never writes cookies back, and returns no page content or
        cookie data -- just where the site landed.

        Raises:
            ValueError: Browser disabled or URL not http(s).
            LookupError: No such session (or it holds no usable cookies).
        """
        if not self.settings_repo.get("browser.enabled"):
            raise ValueError("Browser integration is not enabled. Enable it in Settings.")
        url = validate_navigation_url(url)
        state = self._sessions.load_storage_state(only_id=profile_id)
        if state is None:
            raise LookupError("Session not found or it has no unexpired cookies")

        secrets = {c["value"] for c in state.get("cookies", []) if c.get("value")}
        for origin in state.get("origins", []):
            secrets.update(i["value"] for i in origin.get("localStorage", []) if i.get("value"))

        driver = BrowserDriver(**self._driver_kwargs(), storage_state=state)
        try:
            async with get_browser_semaphore():
                await driver.navigate(url)
                final_url = driver._page.url
                title = await driver._page.title()
        except Exception as e:
            logger.error(f"Saved session test failed: {_scrub_error(e, secrets)}")
            raise BrowserSessionTestError(_scrub_error(e, secrets)) from None
        finally:
            await driver.close()

        return {
            "final_url": final_url,
            "title": (title or "")[:120],
            "redirected_to_login": looks_like_login_url(final_url)
            and not looks_like_login_url(url),
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
