"""Scrapling-based content fetcher with anti-bot bypass capabilities.

Provides three fetching modes:
- http: Fast HTTP requests with TLS fingerprint impersonation
- stealth: Stealth browser via Camoufox with Cloudflare bypass
- dynamic: Full Playwright with anti-detection for JS-heavy pages
"""

from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContentFetcher:
    """Fetch and extract web content using Scrapling.

    Wraps Scrapling's Fetcher, StealthyFetcher, and PlayWrightFetcher
    behind a unified interface with configurable mode selection.
    """

    VALID_MODES = {"http", "stealth", "dynamic"}

    def __init__(self, default_mode: str = "http", timeout: int = 30):
        """Initialize the content fetcher.

        Args:
            default_mode: Default fetching mode ('http', 'stealth', 'dynamic').
            timeout: Request timeout in seconds.
        """
        if default_mode not in self.VALID_MODES:
            raise ValueError(f"Invalid mode '{default_mode}'. Must be one of: {self.VALID_MODES}")
        self.default_mode = default_mode
        self.timeout = timeout

    async def fetch(
        self,
        url: str,
        mode: Optional[str] = None,
        selector: Optional[str] = None,
        wait_for: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch content from a URL using the specified mode.

        Args:
            url: URL to fetch.
            mode: Fetcher mode - 'http', 'stealth', or 'dynamic'.
                  Falls back to default_mode if not specified.
            selector: Optional CSS selector to extract specific content.
            wait_for: Optional CSS selector to wait for before extraction
                      (only used with 'dynamic' mode).

        Returns:
            Dict with url, title, text, status, selected_content, and message.
        """
        fetch_mode = mode or self.default_mode
        if fetch_mode not in self.VALID_MODES:
            return {
                "url": url,
                "title": "",
                "text": "",
                "status": 0,
                "selected_content": [],
                "error": f"Invalid mode '{fetch_mode}'. Must be one of: {self.VALID_MODES}",
                "message": f"Invalid fetcher mode: {fetch_mode}",
            }

        logger.info("Fetching %s with mode=%s", url, fetch_mode)

        try:
            if fetch_mode == "http":
                page = await self._fetch_http(url)
            elif fetch_mode == "stealth":
                page = await self._fetch_stealth(url)
            else:
                page = await self._fetch_dynamic(url, wait_for)

            return self._extract_content(page, url, selector)

        except Exception as e:
            logger.error("Fetch failed for %s (mode=%s): %s", url, fetch_mode, e)
            return {
                "url": url,
                "title": "",
                "text": "",
                "status": 0,
                "selected_content": [],
                "error": str(e),
                "message": f"Failed to fetch {url}: {e}",
            }

    async def _fetch_http(self, url: str) -> Any:
        """Fetch using Scrapling's HTTP Fetcher with TLS impersonation."""
        from scrapling.fetchers import Fetcher

        fetcher = Fetcher()
        page = fetcher.get(url, stealthy_headers=True, timeout=self.timeout)
        return page

    async def _fetch_stealth(self, url: str) -> Any:
        """Fetch using Scrapling's StealthyFetcher with Camoufox."""
        try:
            from scrapling.fetchers import StealthyFetcher
        except ImportError as exc:
            raise RuntimeError(
                "scrapling StealthyFetcher is unavailable. "
                "Ensure 'msgspec' and 'patchright' are installed and 'patchright install chromium' has been run. "
                f"Original error: {exc}"
            ) from exc

        fetcher = StealthyFetcher()
        # StealthyFetcher expects timeout in milliseconds (default 30000ms = 30s)
        page = await fetcher.async_fetch(
            url,
            headless=True,
            timeout=self.timeout * 1000,
            disable_resources=True,
        )
        return page

    async def _fetch_dynamic(self, url: str, wait_for: Optional[str] = None) -> Any:
        """Fetch using Scrapling's DynamicFetcher for JS-heavy pages."""
        try:
            from scrapling.fetchers import DynamicFetcher
        except ImportError as exc:
            raise RuntimeError(
                "scrapling DynamicFetcher is unavailable. "
                "Ensure 'patchright' is installed and 'patchright install chromium' has been run. "
                f"Original error: {exc}"
            ) from exc

        fetcher = DynamicFetcher()
        kwargs: Dict[str, Any] = {
            "headless": True,
            # DynamicFetcher expects timeout in milliseconds (default 30000ms = 30s)
            "timeout": self.timeout * 1000,
            "disable_resources": True,
            "wait_selector": wait_for,
        }
        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        page = await fetcher.async_fetch(url, **kwargs)
        return page

    def _extract_content(
        self, page: Any, url: str, selector: Optional[str] = None
    ) -> Dict[str, Any]:
        """Extract text content from a Scrapling response.

        Args:
            page: Scrapling Adaptor response object.
            url: Original request URL.
            selector: Optional CSS selector for targeted extraction.

        Returns:
            Dict with extracted content and metadata.
        """
        # Get page metadata
        title = ""
        try:
            title_elements = page.css("title::text")
            if title_elements:
                title = title_elements.get("").strip()
        except Exception:
            pass

        # Get full page text
        text = ""
        try:
            body = page.css("body")
            if body:
                text = body[0].get_all_text(separator="\n", strip=True)
                # Truncate to avoid token limits
                if len(text) > 10000:
                    text = text[:10000] + "\n\n[Content truncated at 10000 characters]"
        except Exception as e:
            logger.warning("Text extraction failed: %s", e)
            try:
                text = page.get_all_text(separator="\n", strip=True)
                if len(text) > 10000:
                    text = text[:10000] + "\n\n[Content truncated at 10000 characters]"
            except Exception:
                text = ""

        # Extract selected content if selector provided
        selected_content: List[str] = []
        if selector:
            try:
                elements = page.css(selector)
                if elements:
                    for elem in elements:
                        elem_text = elem.get_all_text(separator=" ", strip=True)
                        if elem_text:
                            selected_content.append(elem_text)
            except Exception as e:
                logger.warning("Selector extraction failed for '%s': %s", selector, e)

        # Get status code
        status = getattr(page, "status", 200)

        final_url = getattr(page, "url", url) or url

        result = {
            "url": final_url,
            "title": title,
            "text": text,
            "status": status,
            "selected_content": selected_content,
            "message": f"Fetched {final_url} - '{title}' ({len(text)} chars extracted)",
        }

        if selector and selected_content:
            result["message"] += f", {len(selected_content)} elements matched '{selector}'"
        elif selector and not selected_content:
            result["message"] += f", no elements matched selector '{selector}'"

        return result
