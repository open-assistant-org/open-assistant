"""Pydantic request models for Google News tools."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

GoogleNewsTopic = Literal[
    "WORLD",
    "NATION",
    "BUSINESS",
    "TECHNOLOGY",
    "ENTERTAINMENT",
    "SCIENCE",
    "SPORTS",
    "HEALTH",
]


class GoogleNewsTopHeadlinesRequest(BaseModel):
    """Request model for google_news_top_headlines — no parameters required."""


class GoogleNewsSearchRequest(BaseModel):
    """Request model for google_news_search."""

    query: str = Field(
        ...,
        description=(
            "Keywords to search for in Google News. "
            "Examples: 'artificial intelligence', 'euro 2025 football', 'Apple earnings'. "
            "Supports multi-word queries and operators like quotes for exact phrases."
        ),
    )


class GoogleNewsByTopicRequest(BaseModel):
    """Request model for google_news_by_topic."""

    topic: GoogleNewsTopic = Field(
        ...,
        description=(
            "Predefined Google News topic category. "
            "Choose one of: WORLD, NATION, BUSINESS, TECHNOLOGY, "
            "ENTERTAINMENT, SCIENCE, SPORTS, HEALTH."
        ),
    )


class GoogleNewsByLocationRequest(BaseModel):
    """Request model for google_news_by_location."""

    location: str = Field(
        ...,
        description=(
            "Geographic location to filter news by. "
            "Can be a city, country, or region. "
            "Examples: 'New York', 'Germany', 'Southeast Asia'."
        ),
    )


class GoogleNewsBySiteRequest(BaseModel):
    """Request model for google_news_by_site."""

    site: str = Field(
        ...,
        description=(
            "Domain of the news publisher to fetch articles from. "
            "Provide the bare domain without 'https://'. "
            "Examples: 'bbc.com', 'reuters.com', 'techcrunch.com'."
        ),
    )
