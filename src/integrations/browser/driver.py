"""Playwright browser management with session pooling."""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.integrations.browser.accessibility import (
    AccessibilityNode,
    AccessibilityTreeBuilder,
    AccessibilityTreeFormatter,
)
from src.integrations.browser.cookie_consent import (
    dismiss_cookie_consent,
    install_cookie_consent_observer,
)
from src.integrations.browser.screenshots import (
    Screenshot,
    ScreenshotConfig,
    optimize_screenshot,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default idle timeout before closing a browser session (seconds)
DEFAULT_IDLE_TIMEOUT = 300  # 5 minutes


class BrowserDriver:
    """
    Manages a Playwright browser instance with session reuse.

    Launches a Chromium browser on first use and reuses it for subsequent
    requests. The browser is closed after an idle timeout period.

    Uses async Playwright API to avoid event loop conflicts.
    """

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        screenshot_config: Optional[ScreenshotConfig] = None,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
    ):
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.screenshot_config = screenshot_config or ScreenshotConfig()
        self.idle_timeout = idle_timeout

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._last_activity: float = 0.0

        # Accessibility tree support
        self._tree_builder = AccessibilityTreeBuilder()
        self._tree_formatter = AccessibilityTreeFormatter()
        self._current_tree: List[AccessibilityNode] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_browser(self) -> None:
        """Start Playwright and launch a browser if not already running."""
        if self._browser and self._browser.is_connected():
            return

        from playwright.async_api import async_playwright

        logger.info("Launching Playwright browser (headless=%s)", self.headless)
        self._playwright = await async_playwright().start()

        # Allow overriding the Chromium binary via env var (e.g. to use
        # a system-installed Chromium instead of the Playwright-managed one).
        launch_kwargs: Dict[str, Any] = {"headless": self.headless}
        executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
            logger.info("Using custom Chromium executable: %s", executable_path)

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        # Auto-dismiss cookie consent banners on every navigation
        await install_cookie_consent_observer(self._context)
        self._page = await self._context.new_page()
        self._last_activity = time.monotonic()
        logger.info("Browser launched successfully")

    async def close(self) -> None:
        """Shut down the browser and Playwright."""
        await self._close_internal()

    async def _close_internal(self) -> None:
        """Internal close."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        logger.info("Browser closed")

    def _touch(self) -> None:
        """Update last-activity timestamp."""
        self._last_activity = time.monotonic()

    @property
    def is_idle_expired(self) -> bool:
        """Return True if the session has been idle longer than the timeout."""
        if self._last_activity == 0.0:
            return False
        return (time.monotonic() - self._last_activity) > self.idle_timeout

    async def cleanup_if_idle(self) -> bool:
        """Close the browser if it has been idle too long. Returns True if closed."""
        if self.is_idle_expired and self._browser:
            logger.info("Browser idle timeout reached; closing session")
            await self._close_internal()
            return True
        return False

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> Screenshot:
        """
        Navigate to a URL and return a screenshot.

        Args:
            url: The URL to navigate to.
            wait_until: Playwright wait condition ('load', 'domcontentloaded',
                        'networkidle').

        Returns:
            Screenshot of the page after navigation.
        """
        await self._ensure_browser()
        logger.info(f"Navigating to {url}")
        await self._page.goto(url, wait_until=wait_until, timeout=30_000)
        # Allow JS rendering to settle
        await self._page.wait_for_timeout(1000)
        # Dismiss cookie consent popups before the caller sees the page
        result = await dismiss_cookie_consent(self._page)
        # If a banner was dismissed, wait longer for the overlay animation/re-render
        # then attempt a second pass (some CMPs show a follow-up dialog after the first)
        if result.get("dismissed"):
            await self._page.wait_for_timeout(1000)
            result = await dismiss_cookie_consent(self._page)
            if result.get("dismissed"):
                logger.info(
                    "Cookie consent dismissed on second pass via %s", result.get("method", "?")
                )
            await self._page.wait_for_timeout(500)
        else:
            await self._page.wait_for_timeout(500)
        self._touch()
        return await self._take_screenshot()

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    async def click(self, x: int, y: int) -> Screenshot:
        """
        Click at the given coordinates and return a screenshot.

        Args:
            x: X coordinate (pixels from left).
            y: Y coordinate (pixels from top).

        Returns:
            Screenshot of the page after click.
        """
        await self._ensure_browser()
        logger.info(f"Clicking at ({x}, {y})")
        await self._page.mouse.click(x, y)
        await self._page.wait_for_timeout(1000)
        self._touch()
        return await self._take_screenshot()

    async def type_text(
        self, text: str, x: Optional[int] = None, y: Optional[int] = None
    ) -> Screenshot:
        """
        Type text, optionally clicking a position first.

        Args:
            text: Text to type.
            x: Optional X coordinate to click before typing.
            y: Optional Y coordinate to click before typing.

        Returns:
            Screenshot of the page after typing.
        """
        await self._ensure_browser()
        if x is not None and y is not None:
            logger.info(f"Clicking ({x}, {y}) then typing '{text[:50]}...'")
            await self._page.mouse.click(x, y)
            await self._page.wait_for_timeout(300)
        else:
            logger.info(f"Typing '{text[:50]}...'")
        await self._page.keyboard.type(text, delay=50)
        await self._page.wait_for_timeout(500)
        self._touch()
        return await self._take_screenshot()

    async def scroll(self, direction: str = "down", amount: int = 3) -> Screenshot:
        """
        Scroll the page and return a screenshot.

        Args:
            direction: 'up' or 'down'.
            amount: Number of "scroll ticks" (each ~100px).

        Returns:
            Screenshot of the page after scrolling.
        """
        await self._ensure_browser()
        delta = amount * 100
        if direction == "up":
            delta = -delta
        logger.info(f"Scrolling {direction} by {abs(delta)}px")
        await self._page.mouse.wheel(0, delta)
        await self._page.wait_for_timeout(800)
        self._touch()
        return await self._take_screenshot()

    async def extract_text(self) -> Dict[str, Any]:
        """
        Extract visible text content from the current page.

        Returns:
            Dict with page title, url, and extracted text content.
        """
        await self._ensure_browser()
        self._touch()

        title = await self._page.title()
        url = self._page.url

        # Extract main text content via JS
        text = await self._page.evaluate("""() => {
            // Remove script and style elements
            const clone = document.body.cloneNode(true);
            const scripts = clone.querySelectorAll('script, style, noscript');
            scripts.forEach(s => s.remove());

            // Get text content, collapse whitespace
            return clone.innerText
                .replace(/\\n{3,}/g, '\\n\\n')
                .trim()
                .substring(0, 10000);
        }""")

        logger.info(f"Extracted {len(text)} chars from {url}")
        return {
            "title": title,
            "url": url,
            "text": text,
        }

    # ------------------------------------------------------------------
    # Accessibility Tree
    # ------------------------------------------------------------------

    async def get_accessibility_tree(
        self, mode: str = "interactive", include_invisible: bool = False
    ) -> Dict[str, Any]:
        """
        Get accessibility tree snapshot of current page.

        Args:
            mode: Filter mode - "full", "interactive", "forms"
            include_invisible: Include hidden elements

        Returns:
            Dict with tree, formatted text, and element count
        """
        await self._ensure_browser()
        self._touch()

        try:
            # Extract interactive elements using JavaScript
            # Since Playwright Python doesn't have page.accessibility.snapshot(),
            # we'll query for interactive elements directly
            elements_data = await self._page.evaluate(
                """(includeInvisible) => {
                const elements = [];
                let refId = 0;

                // Query all interactive elements
                const selectors = [
                    'a[href]',
                    'button:not([disabled])',
                    'input:not([type="hidden"]):not([disabled])',
                    'textarea:not([disabled])',
                    'select:not([disabled])',
                    '[role="button"]:not([disabled])',
                    '[role="link"]',
                    '[role="tab"]',
                    '[role="checkbox"]',
                    '[role="radio"]',
                    '[role="menuitem"]',
                    '[onclick]'
                ];

                const allElements = new Set();
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => allElements.add(el));
                });

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const isVisible = rect.width > 0 && rect.height > 0 &&
                                    window.getComputedStyle(el).visibility !== 'hidden' &&
                                    window.getComputedStyle(el).display !== 'none';

                    if (!isVisible && !includeInvisible) return; // Skip invisible if not requested

                    // Get role
                    let role = el.getAttribute('role') || el.tagName.toLowerCase();
                    if (role === 'a') role = 'link';
                    if (role === 'input') {
                        const type = el.getAttribute('type') || 'text';
                        if (type === 'text' || type === 'email' || type === 'password' || type === 'search') {
                            role = 'textbox';
                        } else if (type === 'checkbox') {
                            role = 'checkbox';
                        } else if (type === 'radio') {
                            role = 'radio';
                        }
                    }

                    // Get accessible name
                    let name = el.getAttribute('aria-label') ||
                              el.getAttribute('title') ||
                              el.getAttribute('placeholder') ||
                              el.innerText?.trim().substring(0, 100) ||
                              el.value ||
                              '';

                    // Get value for inputs
                    let value = null;
                    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                        value = el.value;
                    }

                    elements.push({
                        role: role,
                        name: name,
                        value: value,
                        disabled: el.disabled || false,
                        ref_id: refId++,
                        tag: el.tagName.toLowerCase(),
                        id: el.id,
                        classes: el.className
                    });
                });

                return elements;
            }""",
                include_invisible,
            )

            # Build tree structure from extracted elements
            self._tree_builder = AccessibilityTreeBuilder()
            # Convert flat list to tree-like structure
            nodes = []
            for elem_data in elements_data:
                node = AccessibilityNode(
                    ref_id=elem_data["ref_id"],
                    role=elem_data["role"],
                    name=elem_data["name"],
                    value=elem_data.get("value"),
                    disabled=elem_data.get("disabled", False),
                    children=[],
                    selector=self._build_selector_from_element(elem_data),
                )
                nodes.append(node)
                # Store ref to selector mapping
                self._tree_builder.ref_to_selector[elem_data["ref_id"]] = node.selector

            self._tree_builder.node_counter = len(nodes)
            self._current_tree = nodes

            # Format for LLM
            formatted = self._tree_formatter.format_tree(
                nodes, mode=mode, max_depth=10, max_nodes=100
            )

            token_estimate = self._tree_formatter.estimate_token_count(formatted)

            logger.info(
                f"Extracted accessibility tree: {len(nodes)} elements, " f"~{token_estimate} tokens"
            )

            return {
                "tree": formatted,
                "node_count": len(nodes),
                "token_estimate": token_estimate,
                "url": self._page.url,
                "title": await self._page.title(),
            }

        except Exception as e:
            logger.error(f"Failed to extract accessibility tree: {e}", exc_info=True)
            return {
                "tree": "",
                "error": str(e),
                "node_count": 0,
                "token_estimate": 0,
                "url": self._page.url,
                "title": await self._page.title(),
            }

    def _build_selector_from_element(self, elem_data: Dict[str, Any]) -> str:
        """Build CSS selector from element data."""
        tag = elem_data.get("tag", "")
        elem_id = elem_data.get("id", "")
        name = elem_data.get("name", "")
        role = elem_data.get("role", "")

        # Try ID first
        if elem_id:
            return f"#{elem_id}"

        # Try text content for links/buttons
        if tag == "a" and name:
            safe_name = name.replace("'", "\\'")[:30]
            return f"a:has-text('{safe_name}')"

        if tag == "button" and name:
            safe_name = name.replace("'", "\\'")[:30]
            return f"button:has-text('{safe_name}')"

        # Try aria-label
        if name and role:
            safe_name = name.replace("'", "\\'")[:30]
            return f"[role='{role}'][aria-label*='{safe_name}']"

        # Generic fallback
        if role:
            return f"[role='{role}']"

        return tag or "*"

    async def execute_action(
        self,
        ref_id: int,
        action: str,
        value: Optional[str] = None,
        timeout: int = 5000,
    ) -> Dict[str, Any]:
        """
        Execute action on element by reference ID.

        Args:
            ref_id: Element reference from accessibility tree
            action: Action to perform - "click", "type", "focus", "check", "uncheck"
            value: Value for "type" action
            timeout: Action timeout in ms

        Returns:
            Dict with success status and message
        """
        await self._ensure_browser()
        self._touch()

        # Get selector for this ref
        selector = self._tree_builder.get_selector_for_ref(ref_id)
        if not selector:
            return {
                "success": False,
                "error": f"No selector found for ref={ref_id}",
                "url": self._page.url,
                "title": await self._page.title(),
            }

        logger.info(f"Executing {action} on ref={ref_id} (selector: {selector})")

        try:
            # Locate element
            element = self._page.locator(selector).first

            # Execute action
            if action == "click":
                await element.click(timeout=timeout)
            elif action == "type":
                if not value:
                    return {
                        "success": False,
                        "error": "'type' action requires a value",
                        "url": self._page.url,
                        "title": await self._page.title(),
                    }
                await element.fill(value, timeout=timeout)
            elif action == "focus":
                await element.focus(timeout=timeout)
            elif action == "check":
                await element.check(timeout=timeout)
            elif action == "uncheck":
                await element.uncheck(timeout=timeout)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "url": self._page.url,
                    "title": await self._page.title(),
                }

            # Wait for page to stabilize
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except Exception:
                # Timeout on wait is okay, page might not navigate
                pass

            await self._page.wait_for_timeout(500)

            # Dismiss any cookie consent banners that appeared (e.g. after navigation)
            if action == "click":
                await dismiss_cookie_consent(self._page)

            # Refresh tree after action (next call will rebuild)
            self._current_tree = []

            return {
                "success": True,
                "url": self._page.url,
                "title": await self._page.title(),
                "ref_id": ref_id,
                "action": action,
            }

        except Exception as e:
            logger.error(f"Action failed on ref={ref_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": self._page.url,
                "title": await self._page.title(),
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _take_screenshot(self) -> Screenshot:
        """Capture and optimize a screenshot of the current page."""
        raw_bytes = await self._page.screenshot(type="png", full_page=False)
        optimized = optimize_screenshot(raw_bytes, self.screenshot_config)

        title = await self._page.title()
        return Screenshot(
            data=optimized,
            width=self.viewport_width,
            height=self.viewport_height,
            format=self.screenshot_config.format,
            url=self._page.url,
            title=title,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
