"""Google News service — no API key required."""

from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.google_news.client import GoogleNewsClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Sensible cap so the LLM isn't flooded with articles
MAX_RESULTS_CAP = 50
DEFAULT_MAX_RESULTS = 10


class GoogleNewsService(BaseService):
    """Service for fetching news from Google News (no API key required)."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ) -> None:
        super().__init__(settings_repo, credentials_repo, audit_repo)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_client(self) -> GoogleNewsClient:
        """
        Build a GoogleNewsClient from stored settings.

        Raises:
            ValueError: When the integration is disabled.
        """
        enabled = self.settings_repo.get("google_news.enabled")
        if not enabled:
            raise ValueError("Google News integration is not enabled")

        language = self.settings_repo.get("google_news.language") or "en"
        country = self.settings_repo.get("google_news.country") or "US"
        max_results = int(self.settings_repo.get("google_news.max_results") or DEFAULT_MAX_RESULTS)
        max_results = min(max_results, MAX_RESULTS_CAP)

        return GoogleNewsClient(
            language=language,
            country=country,
            max_results=max_results,
        )

    def _format_results(self, articles: List[Dict[str, Any]], source_label: str) -> Dict[str, Any]:
        """Return a structured dict suitable for LLM consumption."""
        return {
            "source": source_label,
            "count": len(articles),
            "articles": articles,
        }

    # ------------------------------------------------------------------
    # Tool methods — called by ToolExecutor
    # ------------------------------------------------------------------

    def google_news_top_headlines(self) -> Dict[str, Any]:
        """
        Fetch the current top headlines from Google News.

        Returns:
            Dict with count and list of article dicts.
        """
        client = self._get_client()
        articles = client.get_top_news()
        logger.info(f"Google News top headlines: {len(articles)} articles")
        return self._format_results(articles, "google_news_top")

    def google_news_search(self, query: str) -> Dict[str, Any]:
        """
        Search Google News by keyword(s).

        Args:
            query: Search keywords (e.g. 'electric vehicles 2025').

        Returns:
            Dict with count and list of matching article dicts.
        """
        client = self._get_client()
        articles = client.search(query)
        logger.info(f"Google News search '{query}': {len(articles)} articles")
        return self._format_results(articles, f"google_news_search:{query}")

    def google_news_by_topic(self, topic: str) -> Dict[str, Any]:
        """
        Fetch news for a predefined Google News topic category.

        Args:
            topic: WORLD | NATION | BUSINESS | TECHNOLOGY | ENTERTAINMENT
                   | SCIENCE | SPORTS | HEALTH

        Returns:
            Dict with count and list of article dicts.
        """
        client = self._get_client()
        articles = client.get_by_topic(topic)
        logger.info(f"Google News topic '{topic}': {len(articles)} articles")
        return self._format_results(articles, f"google_news_topic:{topic}")

    def google_news_by_location(self, location: str) -> Dict[str, Any]:
        """
        Fetch news related to a geographic location.

        Args:
            location: City, country, or region (e.g. 'Berlin', 'Japan').

        Returns:
            Dict with count and list of article dicts.
        """
        client = self._get_client()
        articles = client.get_by_location(location)
        logger.info(f"Google News location '{location}': {len(articles)} articles")
        return self._format_results(articles, f"google_news_location:{location}")

    def google_news_by_site(self, site: str) -> Dict[str, Any]:
        """
        Fetch the latest articles from a specific news publisher.

        Args:
            site: Publisher domain (e.g. 'reuters.com', 'bbc.com').

        Returns:
            Dict with count and list of article dicts.
        """
        client = self._get_client()
        articles = client.get_by_site(site)
        logger.info(f"Google News site '{site}': {len(articles)} articles")
        return self._format_results(articles, f"google_news_site:{site}")

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def test_connection(self) -> Dict[str, Any]:
        """
        Test that Google News is reachable and the integration is configured.

        Returns:
            Dict with service_name, status ('success' | 'error'), and message.
        """
        try:
            client = self._get_client()
            client.test_connection()
            return {
                "service_name": "google_news",
                "status": "success",
                "message": "Google News is reachable — no API key required",
            }
        except ValueError as e:
            return {"service_name": "google_news", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Google News connection test failed: {e}")
            return {
                "service_name": "google_news",
                "status": "error",
                "message": f"Connection failed: {e}",
            }
