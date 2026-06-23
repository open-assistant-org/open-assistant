"""Google News client wrapping the gnews RSS scraper."""

from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

VALID_TOPICS = {
    "WORLD",
    "NATION",
    "BUSINESS",
    "TECHNOLOGY",
    "ENTERTAINMENT",
    "SCIENCE",
    "SPORTS",
    "HEALTH",
}


class GoogleNewsClient:
    """
    Client for Google News via the gnews RSS scraper.

    No API key is required. Articles are fetched from Google's public
    news RSS feeds and returned as structured dictionaries.
    """

    def __init__(
        self,
        language: str = "en",
        country: str = "US",
        max_results: int = 10,
    ) -> None:
        """
        Initialize the Google News client.

        Args:
            language: ISO 639-1 language code (e.g. 'en', 'de', 'fr').
            country:  ISO 3166-1 alpha-2 country code (e.g. 'US', 'GB', 'DE').
            max_results: Maximum number of articles to return per request (1-100).
        """
        from gnews import GNews

        self._gnews = GNews(
            language=language,
            country=country,
            max_results=max_results,
        )
        logger.info(
            f"GoogleNewsClient initialized (language={language}, country={country}, max_results={max_results})"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_top_news(self) -> List[Dict[str, Any]]:
        """
        Fetch the current top headlines from Google News.

        Returns:
            List of article dicts (see _normalize_article for schema).
        """
        logger.info("Fetching Google News top headlines")
        raw = self._gnews.get_top_news()
        return [self._normalize_article(a) for a in raw]

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search Google News for articles matching *query*.

        Args:
            query: Free-text search query (e.g. 'climate change').

        Returns:
            List of article dicts sorted by relevance / recency.
        """
        logger.info(f"Google News search: query='{query}'")
        raw = self._gnews.get_news(query)
        return [self._normalize_article(a) for a in raw]

    def get_by_topic(self, topic: str) -> List[Dict[str, Any]]:
        """
        Fetch news articles for a predefined Google News topic.

        Args:
            topic: One of WORLD, NATION, BUSINESS, TECHNOLOGY,
                   ENTERTAINMENT, SCIENCE, SPORTS, HEALTH.

        Returns:
            List of article dicts.

        Raises:
            ValueError: If *topic* is not a recognised Google News topic.
        """
        topic_upper = topic.upper()
        if topic_upper not in VALID_TOPICS:
            raise ValueError(
                f"Unknown topic '{topic}'. Valid topics: {', '.join(sorted(VALID_TOPICS))}"
            )
        logger.info(f"Google News topic: {topic_upper}")
        raw = self._gnews.get_news_by_topic(topic_upper)
        return [self._normalize_article(a) for a in raw]

    def get_by_location(self, location: str) -> List[Dict[str, Any]]:
        """
        Fetch news articles related to a geographic location.

        Args:
            location: City, country, or region name (e.g. 'New York', 'Germany').

        Returns:
            List of article dicts.
        """
        logger.info(f"Google News location: '{location}'")
        raw = self._gnews.get_news_by_location(location)
        return [self._normalize_article(a) for a in raw]

    def get_by_site(self, site: str) -> List[Dict[str, Any]]:
        """
        Fetch the latest news articles published by a specific website.

        Args:
            site: Domain of the publisher (e.g. 'bbc.com', 'techcrunch.com').

        Returns:
            List of article dicts.
        """
        logger.info(f"Google News site: '{site}'")
        raw = self._gnews.get_news_by_site(site)
        return [self._normalize_article(a) for a in raw]

    def test_connection(self) -> bool:
        """
        Verify that Google News is reachable by fetching a single article.

        Returns:
            True on success.

        Raises:
            Exception: Propagates any network / parsing error.
        """
        results = self._gnews.get_top_news()
        if results is None:
            raise RuntimeError("Google News returned no results")
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_article(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise a raw gnews article dict into a consistent schema.

        Output keys:
            title           – headline text
            description     – article summary / snippet
            published_date  – publication timestamp string (RFC 2822)
            url             – article URL
            publisher       – publisher name
            publisher_url   – publisher homepage URL
        """
        publisher = raw.get("publisher") or {}
        return {
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "published_date": raw.get("published date", ""),
            "url": raw.get("url", ""),
            "publisher": publisher.get("title", ""),
            "publisher_url": publisher.get("href", ""),
        }
