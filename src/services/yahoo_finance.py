"""Yahoo Finance service for stock, ETF, and market data (no API key required)."""

from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.yahoo_finance.client import YahooFinanceClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class YahooFinanceService(BaseService):
    """
    Service for financial market data via Yahoo Finance.

    No API key required — data is fetched using the yfinance library
    which accesses Yahoo Finance's public endpoints.
    """

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_client(self) -> YahooFinanceClient:
        """
        Build and return a YahooFinanceClient.

        Raises:
            ValueError: If the integration is disabled in settings.
        """
        enabled = self.settings_repo.get("yahoo_finance.enabled")
        if not enabled:
            raise ValueError("Yahoo Finance integration is not enabled")

        request_timeout = self.settings_repo.get("yahoo_finance.request_timeout") or 10
        return YahooFinanceClient(request_timeout=int(request_timeout))

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Yahoo Finance connectivity by fetching AAPL price.

        Returns:
            Dictionary with test results.
        """
        try:
            client = self._get_client()
            client.test_connection()
            return {
                "service_name": "yahoo_finance",
                "status": "success",
                "message": "Yahoo Finance is reachable. No API key required.",
            }
        except ValueError as exc:
            return {"service_name": "yahoo_finance", "status": "error", "message": str(exc)}
        except Exception as exc:
            logger.error(f"Yahoo Finance connection test failed: {exc}")
            return {
                "service_name": "yahoo_finance",
                "status": "error",
                "message": f"Connection failed: {exc}",
            }

    # ------------------------------------------------------------------
    # Tool methods
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get the current quote and key metrics for a ticker symbol.

        Args:
            symbol: Ticker symbol (e.g. "AAPL", "BTC-USD", "^GSPC")

        Returns:
            Current price, day change, volume, market cap, P/E, 52-week range, etc.
        """
        client = self._get_client()
        self._log_web_request(
            service_name="yahoo_finance",
            action="get_quote",
            endpoint=f"quote/{symbol}",
            method="GET",
            request_data={"symbol": symbol},
        )
        try:
            result = client.get_quote(symbol)
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_quote",
                endpoint=f"quote/{symbol}",
                method="GET",
                success=True,
                response_data={"symbol": symbol, "price": result.get("current_price")},
            )
            return result
        except Exception as exc:
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_quote",
                endpoint=f"quote/{symbol}",
                method="GET",
                success=False,
                error_message=str(exc),
            )
            raise

    def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> Dict[str, Any]:
        """
        Get historical OHLCV price data for a ticker.

        Args:
            symbol: Ticker symbol
            period: Time period (e.g. "1mo", "1y", "5y")
            interval: Data interval (e.g. "1d", "1wk", "1mo")

        Returns:
            Dict with symbol, period, interval, and list of OHLCV data points
        """
        client = self._get_client()
        self._log_web_request(
            service_name="yahoo_finance",
            action="get_history",
            endpoint=f"history/{symbol}",
            method="GET",
            request_data={"symbol": symbol, "period": period, "interval": interval},
        )
        try:
            records = client.get_history(symbol=symbol, period=period, interval=interval)
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_history",
                endpoint=f"history/{symbol}",
                method="GET",
                success=True,
                response_data={"symbol": symbol, "records": len(records)},
            )
            return {
                "symbol": symbol.upper(),
                "period": period,
                "interval": interval,
                "count": len(records),
                "data": records,
            }
        except Exception as exc:
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_history",
                endpoint=f"history/{symbol}",
                method="GET",
                success=False,
                error_message=str(exc),
            )
            raise

    def get_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get detailed company or fund profile information.

        Args:
            symbol: Ticker symbol

        Returns:
            Company description, sector, industry, financials, and key statistics
        """
        client = self._get_client()
        self._log_web_request(
            service_name="yahoo_finance",
            action="get_info",
            endpoint=f"info/{symbol}",
            method="GET",
            request_data={"symbol": symbol},
        )
        try:
            result = client.get_info(symbol)
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_info",
                endpoint=f"info/{symbol}",
                method="GET",
                success=True,
                response_data={"symbol": symbol},
            )
            return result
        except Exception as exc:
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_info",
                endpoint=f"info/{symbol}",
                method="GET",
                success=False,
                error_message=str(exc),
            )
            raise

    def get_financials(
        self,
        symbol: str,
        statement_type: str = "income",
        quarterly: bool = False,
    ) -> Dict[str, Any]:
        """
        Get financial statements (income statement, balance sheet, or cash flow).

        Args:
            symbol: Ticker symbol
            statement_type: "income", "balance_sheet", or "cash_flow"
            quarterly: True for quarterly data, False for annual (default)

        Returns:
            Financial statement data
        """
        client = self._get_client()
        self._log_web_request(
            service_name="yahoo_finance",
            action="get_financials",
            endpoint=f"financials/{symbol}",
            method="GET",
            request_data={
                "symbol": symbol,
                "statement_type": statement_type,
                "quarterly": quarterly,
            },
        )
        try:
            result = client.get_financials(
                symbol=symbol, statement_type=statement_type, quarterly=quarterly
            )
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_financials",
                endpoint=f"financials/{symbol}",
                method="GET",
                success=True,
                response_data={"symbol": symbol, "statement_type": statement_type},
            )
            return result
        except Exception as exc:
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_financials",
                endpoint=f"financials/{symbol}",
                method="GET",
                success=False,
                error_message=str(exc),
            )
            raise

    def get_news(self, symbol: str, count: int = 10) -> Dict[str, Any]:
        """
        Get recent news articles for a ticker.

        Args:
            symbol: Ticker symbol
            count: Maximum number of articles to return

        Returns:
            Dict with symbol and list of news articles
        """
        client = self._get_client()
        self._log_web_request(
            service_name="yahoo_finance",
            action="get_news",
            endpoint=f"news/{symbol}",
            method="GET",
            request_data={"symbol": symbol, "count": count},
        )
        try:
            articles = client.get_news(symbol=symbol, count=count)
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_news",
                endpoint=f"news/{symbol}",
                method="GET",
                success=True,
                response_data={"symbol": symbol, "articles": len(articles)},
            )
            return {"symbol": symbol.upper(), "count": len(articles), "articles": articles}
        except Exception as exc:
            self._log_web_request(
                service_name="yahoo_finance",
                action="get_news",
                endpoint=f"news/{symbol}",
                method="GET",
                success=False,
                error_message=str(exc),
            )
            raise

    def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Search for ticker symbols matching a company name or keyword.

        Args:
            query: Search term (company name, keyword, or partial ticker)
            limit: Maximum number of results

        Returns:
            Dict with query and list of matching tickers
        """
        client = self._get_client()
        self._log_web_request(
            service_name="yahoo_finance",
            action="search",
            endpoint="search",
            method="GET",
            request_data={"query": query, "limit": limit},
        )
        try:
            results = client.search(query=query, limit=limit)
            self._log_web_request(
                service_name="yahoo_finance",
                action="search",
                endpoint="search",
                method="GET",
                success=True,
                response_data={"query": query, "results": len(results)},
            )
            return {"query": query, "count": len(results), "results": results}
        except Exception as exc:
            self._log_web_request(
                service_name="yahoo_finance",
                action="search",
                endpoint="search",
                method="GET",
                success=False,
                error_message=str(exc),
            )
            raise
