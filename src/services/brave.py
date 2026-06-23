"""Brave Search service for web search operations."""

from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.brave.client import BraveSearchClient
from src.integrations.brave.duckduckgo import DuckDuckGoClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Map user-friendly freshness values to Brave API parameters
FRESHNESS_MAP = {
    "day": "pd",
    "week": "pw",
    "month": "pm",
    "year": "py",
    # Also accept Brave's native values
    "pd": "pd",
    "pw": "pw",
    "pm": "pm",
    "py": "py",
}


class BraveService(BaseService):
    """Service for web search operations via Brave Search API."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        """
        Initialize Brave Search service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository (optional)
        """
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_client(self) -> BraveSearchClient:
        """
        Get configured Brave Search client.

        Returns:
            BraveSearchClient instance

        Raises:
            ValueError: If Brave Search is not configured or API key is missing
        """
        enabled = self.settings_repo.get("brave.enabled")
        if not enabled:
            raise ValueError("Brave Search integration is not enabled")

        creds = self.credentials_repo.get("brave")
        if not creds:
            raise ValueError("Brave Search API key not found. Please configure it in Settings.")

        api_key = creds.get("credential_data", {}).get("value")
        if not api_key:
            raise ValueError("Brave Search API key is empty")

        safe_search = self.settings_repo.get("brave.safe_search") or "moderate"

        return BraveSearchClient(api_key=api_key, safe_search=safe_search)

    def _get_fallback_client(self) -> DuckDuckGoClient:
        """Get DuckDuckGo fallback client."""
        return DuckDuckGoClient()

    def web_search(
        self,
        query: str,
        count: int = 10,
        freshness: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search the web for information.

        Uses Brave Search API as primary, falls back to DuckDuckGo if
        Brave is not configured or fails.

        Args:
            query: Search query
            count: Number of results (max 20)
            freshness: Filter by date - 'day', 'week', 'month', 'year'

        Returns:
            Dict with search results including title, snippet, and URL
        """
        # Normalize freshness parameter
        brave_freshness = None
        if freshness:
            brave_freshness = FRESHNESS_MAP.get(freshness, freshness)

        # Get configured results limit
        results_limit = self.settings_repo.get("brave.results_limit")
        if results_limit:
            count = min(count, int(results_limit))

        # Try Brave Search first
        try:
            client = self._get_client()
            results = client.search(
                query=query,
                count=count,
                freshness=brave_freshness,
            )
            source = "brave"
        except (ValueError, Exception) as e:
            logger.warning(f"Brave Search failed, trying DuckDuckGo fallback: {e}")
            # Fall back to DuckDuckGo
            try:
                fallback = self._get_fallback_client()
                results = fallback.search(
                    query=query,
                    count=count,
                    freshness=freshness,
                )
                source = "duckduckgo"
            except Exception as fallback_error:
                logger.error(f"DuckDuckGo fallback also failed: {fallback_error}")
                return {
                    "query": query,
                    "results": [],
                    "total": 0,
                    "source": "none",
                    "error": f"All search providers failed. Brave: {e}. DuckDuckGo: {fallback_error}",
                }

        # Format results for LLM consumption
        formatted = self._format_results(results, query, source)
        return formatted

    def _format_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        source: str,
    ) -> Dict[str, Any]:
        """
        Format search results for LLM consumption.

        Args:
            results: Raw search results
            query: Original query
            source: Search provider used

        Returns:
            Formatted results dict
        """
        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.append(
                {
                    "position": i,
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("description", ""),
                }
            )

        return {
            "query": query,
            "results": formatted_results,
            "total": len(formatted_results),
            "source": source,
        }

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Brave Search connection.

        Returns:
            Dictionary with test results
        """
        try:
            client = self._get_client()
            client.test_connection()

            return {
                "service_name": "brave",
                "status": "success",
                "message": "Connection successful",
            }

        except ValueError as e:
            return {"service_name": "brave", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Brave Search connection test failed: {e}")
            return {
                "service_name": "brave",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }
