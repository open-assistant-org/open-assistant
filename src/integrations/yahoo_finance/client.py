"""Yahoo Finance client using the yfinance library (no API key required)."""

from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class YahooFinanceClient:
    """
    Client for fetching financial data via Yahoo Finance (yfinance).

    No API key is required. Data is fetched directly from Yahoo Finance's
    unofficial API endpoints.
    """

    def __init__(self, request_timeout: int = 10):
        """
        Initialize Yahoo Finance client.

        Args:
            request_timeout: HTTP request timeout in seconds (default 10)
        """
        self.request_timeout = request_timeout
        logger.info("Yahoo Finance client initialized")

    def _get_ticker(self, symbol: str):
        """Return a yfinance Ticker object for the given symbol."""
        import yfinance as yf

        return yf.Ticker(symbol.upper().strip(), session=None)

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get current quote and key market metrics for a ticker.

        Args:
            symbol: Ticker symbol (e.g. "AAPL", "BTC-USD", "^GSPC")

        Returns:
            Dict with price, change, volume, market cap, P/E, 52-week range, etc.

        Raises:
            ValueError: If the symbol is not found or data is unavailable
        """
        ticker = self._get_ticker(symbol)

        # fast_info is lighter and more reliable for real-time price data
        try:
            fi = ticker.fast_info
            last_price = fi.last_price
        except Exception:
            last_price = None

        # info provides fundamentals but may be slower
        try:
            info = ticker.info
        except Exception:
            info = {}

        if not info and last_price is None:
            raise ValueError(f"No data found for symbol '{symbol}'. Check the ticker symbol.")

        current_price = last_price or info.get("currentPrice") or info.get("regularMarketPrice")
        if current_price is None:
            raise ValueError(f"Could not retrieve price for '{symbol}'.")

        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        change = None
        change_pct = None
        if current_price is not None and prev_close:
            change = round(current_price - prev_close, 4)
            change_pct = round((change / prev_close) * 100, 2)

        result: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "name": info.get("longName") or info.get("shortName") or symbol.upper(),
            "currency": info.get("currency", "USD"),
            "current_price": current_price,
            "previous_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "open": info.get("open") or info.get("regularMarketOpen"),
            "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
            "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
            "volume": info.get("volume") or info.get("regularMarketVolume"),
            "avg_volume": info.get("averageVolume"),
            "market_cap": info.get("marketCap"),
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "exchange": info.get("exchange"),
            "quote_type": info.get("quoteType"),
        }

        # Remove None values to keep response clean
        return {k: v for k, v in result.items() if v is not None}

    def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV price data for a ticker.

        Args:
            symbol: Ticker symbol (e.g. "AAPL", "^GSPC", "BTC-USD")
            period: Time period — "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y",
                    "5y", "10y", "ytd", "max"
            interval: Data interval — "1m", "5m", "15m", "30m", "1h",
                      "1d", "1wk", "1mo"

        Returns:
            List of OHLCV dicts with date, open, high, low, close, volume
        """
        ticker = self._get_ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            raise ValueError(
                f"No historical data found for '{symbol}' with period='{period}', "
                f"interval='{interval}'."
            )

        records = []
        for dt, row in hist.iterrows():
            records.append(
                {
                    "date": str(dt.date()) if hasattr(dt, "date") else str(dt),
                    "open": round(float(row["Open"]), 4) if "Open" in row else None,
                    "high": round(float(row["High"]), 4) if "High" in row else None,
                    "low": round(float(row["Low"]), 4) if "Low" in row else None,
                    "close": round(float(row["Close"]), 4) if "Close" in row else None,
                    "volume": int(row["Volume"]) if "Volume" in row else None,
                }
            )

        return records

    def get_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get detailed company or fund profile information.

        Args:
            symbol: Ticker symbol

        Returns:
            Dict with company description, sector, industry, employees, website,
            country, exchange, financial ratios, and key statistics
        """
        ticker = self._get_ticker(symbol)
        info = ticker.info

        if not info or info.get("trailingPegRatio") is None and not info.get("longName"):
            raise ValueError(f"No company info found for symbol '{symbol}'.")

        fields = [
            "longName",
            "shortName",
            "symbol",
            "exchange",
            "quoteType",
            "currency",
            "country",
            "sector",
            "industry",
            "fullTimeEmployees",
            "website",
            "longBusinessSummary",
            "marketCap",
            "enterpriseValue",
            "trailingPE",
            "forwardPE",
            "priceToBook",
            "priceToSalesTrailing12Months",
            "trailingEps",
            "forwardEps",
            "bookValue",
            "dividendRate",
            "dividendYield",
            "payoutRatio",
            "beta",
            "returnOnEquity",
            "returnOnAssets",
            "revenueGrowth",
            "earningsGrowth",
            "totalRevenue",
            "grossProfits",
            "ebitda",
            "totalDebt",
            "totalCash",
            "debtToEquity",
            "currentRatio",
            "quickRatio",
            "fiftyTwoWeekHigh",
            "fiftyTwoWeekLow",
            "fiftyDayAverage",
            "twoHundredDayAverage",
            "sharesOutstanding",
            "floatShares",
            "heldPercentInsiders",
            "heldPercentInstitutions",
            "shortRatio",
            "shortPercentOfFloat",
        ]

        result = {"symbol": symbol.upper()}
        for field in fields:
            val = info.get(field)
            if val is not None:
                result[field] = val

        return result

    def get_financials(
        self,
        symbol: str,
        statement_type: str = "income",
        quarterly: bool = False,
    ) -> Dict[str, Any]:
        """
        Get financial statements for a company.

        Args:
            symbol: Ticker symbol
            statement_type: One of "income", "balance_sheet", "cash_flow"
            quarterly: If True, return quarterly data; otherwise annual (default)

        Returns:
            Dict with statement data keyed by line item, with columns as fiscal periods
        """
        ticker = self._get_ticker(symbol)

        if statement_type == "income":
            df = ticker.quarterly_income_stmt if quarterly else ticker.income_stmt
            label = "income_statement"
        elif statement_type == "balance_sheet":
            df = ticker.quarterly_balance_sheet if quarterly else ticker.balance_sheet
            label = "balance_sheet"
        elif statement_type == "cash_flow":
            df = ticker.quarterly_cashflow if quarterly else ticker.cashflow
            label = "cash_flow_statement"
        else:
            raise ValueError(
                f"Invalid statement_type '{statement_type}'. "
                "Must be 'income', 'balance_sheet', or 'cash_flow'."
            )

        if df is None or df.empty:
            raise ValueError(f"No {statement_type} statement data available for '{symbol}'.")

        # Convert DataFrame to nested dict: {line_item: {period: value}}
        data: Dict[str, Any] = {}
        for idx in df.index:
            row_data = {}
            for col in df.columns:
                val = df.loc[idx, col]
                # Convert numpy/pandas types to Python native
                try:
                    import math

                    if val is not None and not (isinstance(val, float) and math.isnan(val)):
                        row_data[str(col.date() if hasattr(col, "date") else col)] = float(val)
                except (TypeError, ValueError):
                    pass
            if row_data:
                data[str(idx)] = row_data

        return {
            "symbol": symbol.upper(),
            "statement_type": label,
            "frequency": "quarterly" if quarterly else "annual",
            "data": data,
        }

    def get_news(self, symbol: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent news articles for a ticker.

        Args:
            symbol: Ticker symbol
            count: Maximum number of articles to return (default 10)

        Returns:
            List of news dicts with title, publisher, link, and publish date
        """
        import time

        ticker = self._get_ticker(symbol)
        news = ticker.news or []

        results = []
        for article in news[:count]:
            # yfinance returns providerPublishTime as a Unix timestamp
            publish_time = article.get("providerPublishTime")
            pub_date = None
            if publish_time:
                try:
                    pub_date = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(publish_time))
                except Exception:
                    pub_date = str(publish_time)

            results.append(
                {
                    "title": article.get("title", ""),
                    "publisher": article.get("publisher", ""),
                    "link": article.get("link", ""),
                    "published_at": pub_date,
                    "type": article.get("type", ""),
                }
            )

        return results

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for ticker symbols matching a company name or keyword.

        Args:
            query: Search query (company name, keyword, or partial ticker)
            limit: Maximum number of results to return (default 10)

        Returns:
            List of matching tickers with symbol, name, exchange, and type
        """
        import yfinance as yf

        try:
            search = yf.Search(query, max_results=limit)
            quotes = search.quotes or []
        except Exception as exc:
            raise ValueError(f"Search failed for query '{query}': {exc}") from exc

        results = []
        for q in quotes[:limit]:
            results.append(
                {
                    "symbol": q.get("symbol", ""),
                    "name": q.get("longname") or q.get("shortname") or "",
                    "exchange": q.get("exchDisp") or q.get("exchange") or "",
                    "type": q.get("typeDisp") or q.get("quoteType") or "",
                    "score": q.get("score"),
                }
            )

        return results

    def test_connection(self) -> bool:
        """
        Verify connectivity by fetching a minimal quote for a well-known ticker.

        Returns:
            True if connection is working

        Raises:
            Exception: If the request fails
        """
        ticker = self._get_ticker("AAPL")
        fi = ticker.fast_info
        price = fi.last_price
        if not price:
            raise RuntimeError("Received empty response from Yahoo Finance")
        return True
