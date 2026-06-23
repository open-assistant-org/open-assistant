"""Pydantic request models for Yahoo Finance tools."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class YahooFinanceGetQuoteRequest(BaseModel):
    """Request model for yahoo_finance_get_quote."""

    symbol: str = Field(
        ...,
        description=(
            "Ticker symbol to look up. Examples: 'AAPL' (Apple), 'MSFT' (Microsoft), "
            "'BTC-USD' (Bitcoin), '^GSPC' (S&P 500), 'EURUSD=X' (EUR/USD forex). "
            "Always use the exact Yahoo Finance ticker symbol."
        ),
    )


class YahooFinanceGetHistoryRequest(BaseModel):
    """Request model for yahoo_finance_get_history."""

    symbol: str = Field(
        ...,
        description=("Ticker symbol. Examples: 'AAPL', 'TSLA', '^DJI' (Dow Jones), 'ETH-USD'."),
    )
    period: Literal["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"] = Field(
        default="1mo",
        description=(
            "Time period for historical data. Options: "
            "'1d' (1 day), '5d' (5 days), '1mo' (1 month), '3mo' (3 months), "
            "'6mo' (6 months), '1y' (1 year), '2y' (2 years), '5y' (5 years), "
            "'10y' (10 years), 'ytd' (year-to-date), 'max' (all available). "
            "Default: '1mo'."
        ),
    )
    interval: Literal["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"] = Field(
        default="1d",
        description=(
            "Data interval between price points. Options: "
            "'1m' (1 minute), '5m', '15m', '30m', '1h' (hourly), "
            "'1d' (daily, default), '1wk' (weekly), '1mo' (monthly). "
            "Note: intraday intervals (< 1d) are only available for the last 60 days."
        ),
    )


class YahooFinanceGetInfoRequest(BaseModel):
    """Request model for yahoo_finance_get_info."""

    symbol: str = Field(
        ...,
        description=(
            "Ticker symbol for the company or fund to look up. "
            "Examples: 'AAPL', 'GOOGL', 'SPY', 'AMZN'."
        ),
    )


class YahooFinanceGetFinancialsRequest(BaseModel):
    """Request model for yahoo_finance_get_financials."""

    symbol: str = Field(
        ...,
        description="Ticker symbol of the company (e.g. 'AAPL', 'MSFT', 'TSLA').",
    )
    statement_type: Literal["income", "balance_sheet", "cash_flow"] = Field(
        default="income",
        description=(
            "Which financial statement to retrieve: "
            "'income' (income statement — revenue, profit, EPS), "
            "'balance_sheet' (assets, liabilities, equity), "
            "'cash_flow' (operating, investing, financing cash flows). "
            "Default: 'income'."
        ),
    )
    quarterly: bool = Field(
        default=False,
        description=(
            "If True, return the most recent quarterly statements. "
            "If False (default), return annual statements."
        ),
    )


class YahooFinanceGetNewsRequest(BaseModel):
    """Request model for yahoo_finance_get_news."""

    symbol: str = Field(
        ...,
        description=("Ticker symbol to fetch news for (e.g. 'AAPL', 'TSLA', 'NVDA')."),
    )
    count: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of news articles to return (1–50, default 10).",
    )


class YahooFinanceSearchRequest(BaseModel):
    """Request model for yahoo_finance_search."""

    query: str = Field(
        ...,
        description=(
            "Search query to find ticker symbols. Can be a company name (e.g. 'Apple'), "
            "a partial ticker (e.g. 'APP'), or a keyword (e.g. 'semiconductor ETF'). "
            "Use this when you don't know the exact ticker symbol."
        ),
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum number of search results to return (1–25, default 10).",
    )
