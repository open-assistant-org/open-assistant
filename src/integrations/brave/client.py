"""Brave Search API client with rate-limit throttling."""

import threading
import time
from typing import Any, Dict, List, Optional

import httpx

from src.utils.logger import get_logger

logger = get_logger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# Free tier: 1 request per second
DEFAULT_MIN_REQUEST_INTERVAL = 1.0
MAX_RETRIES = 2


class BraveSearchClient:
    """Client for the Brave Search API with built-in rate-limit throttling."""

    # Class-level lock and timestamp shared across all instances so that
    # multiple BraveSearchClient objects (e.g. from different requests)
    # still respect a single global rate limit.
    _lock = threading.Lock()
    _last_request_time: float = 0.0

    def __init__(self, api_key: str, safe_search: str = "moderate"):
        """
        Initialize Brave Search client.

        Args:
            api_key: Brave Search API key
            safe_search: Safe search level - 'off', 'moderate', 'strict'
        """
        self.api_key = api_key
        self.safe_search = safe_search
        self.headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        logger.info("Brave Search client initialized")

    @classmethod
    def _throttle(cls) -> None:
        """Enforce minimum interval between requests (free tier: 1 req/s)."""
        with cls._lock:
            now = time.monotonic()
            elapsed = now - cls._last_request_time
            if elapsed < DEFAULT_MIN_REQUEST_INTERVAL:
                sleep_time = DEFAULT_MIN_REQUEST_INTERVAL - elapsed
                logger.debug(f"Brave rate-limit throttle: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
            cls._last_request_time = time.monotonic()

    def search(
        self,
        query: str,
        count: int = 10,
        freshness: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the web using Brave Search API.

        Includes proactive throttling to stay within the free-tier rate limit
        (1 req/s) and retry logic for 429 responses.

        Args:
            query: Search query string
            count: Number of results to return (max 20)
            freshness: Filter by date - 'pd' (past day), 'pw' (past week),
                       'pm' (past month), 'py' (past year), or None

        Returns:
            List of search result dicts with title, url, description

        Raises:
            httpx.HTTPStatusError: If the API returns a non-retryable error
        """
        params: Dict[str, Any] = {
            "q": query,
            "count": min(count, 20),
            "safesearch": self.safe_search,
        }

        if freshness:
            params["freshness"] = freshness

        logger.info(f"Brave Search: query='{query}', count={count}, freshness={freshness}")

        last_error: Optional[Exception] = None

        for attempt in range(1 + MAX_RETRIES):
            # Proactive throttle before every request
            self._throttle()

            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    BRAVE_SEARCH_URL,
                    headers=self.headers,
                    params=params,
                )

            if response.status_code == 429:
                # Rate limited — back off and retry.
                # Respect Retry-After when present; otherwise use exponential backoff.
                header_val = response.headers.get("Retry-After")
                if header_val is not None:
                    retry_after = min(float(header_val), 10.0)
                else:
                    retry_after = min(2**attempt, 10.0)  # 1s, 2s, 4s for attempts 0, 1, 2
                logger.warning(
                    f"Brave Search 429 rate-limited (attempt {attempt + 1}/{1 + MAX_RETRIES}), "
                    f"retrying after {retry_after}s"
                )
                time.sleep(retry_after)
                last_error = httpx.HTTPStatusError(
                    message=f"429 Too Many Requests",
                    request=response.request,
                    response=response,
                )
                continue

            response.raise_for_status()
            data = response.json()

            web_results = data.get("web", {}).get("results", [])
            results = []
            for item in web_results:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("description", ""),
                    }
                )

            logger.info(f"Brave Search returned {len(results)} results")
            return results

        # All retries exhausted
        logger.error("Brave Search: rate limit retries exhausted")
        raise last_error  # type: ignore[misc]

    def test_connection(self) -> bool:
        """
        Test the API connection with a minimal query.

        Returns:
            True if the connection is successful
        """
        try:
            self.search("test", count=1)
            return True
        except Exception as e:
            logger.error(f"Brave Search connection test failed: {e}")
            raise
