"""DuckDuckGo search fallback (no API key required)."""

from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class DuckDuckGoClient:
    """Fallback search client using DuckDuckGo Instant Answer API."""

    def search(
        self,
        query: str,
        count: int = 10,
        freshness: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search using DuckDuckGo.

        This uses the duckduckgo-search library for web results.
        The freshness parameter maps to timelimit: 'd', 'w', 'm', 'y'.

        Args:
            query: Search query string
            count: Number of results to return
            freshness: Filter by date - 'day', 'week', 'month', 'year'

        Returns:
            List of search result dicts with title, url, description
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.error(
                "duckduckgo-search package not installed. "
                "Install it with: pip install duckduckgo-search"
            )
            return [
                {
                    "title": "DuckDuckGo unavailable",
                    "url": "",
                    "description": "The duckduckgo-search package is not installed. "
                    "Install it with: pip install duckduckgo-search",
                }
            ]

        timelimit = None
        if freshness:
            freshness_map = {
                "day": "d",
                "pd": "d",
                "week": "w",
                "pw": "w",
                "month": "m",
                "pm": "m",
                "year": "y",
                "py": "y",
            }
            timelimit = freshness_map.get(freshness)

        logger.info(f"DuckDuckGo Search: query='{query}', count={count}, timelimit={timelimit}")

        try:
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=count, timelimit=timelimit))

            results = []
            for item in raw_results:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "description": item.get("body", ""),
                    }
                )

            logger.info(f"DuckDuckGo returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return [
                {
                    "title": "Search failed",
                    "url": "",
                    "description": f"DuckDuckGo search failed: {str(e)}",
                }
            ]
