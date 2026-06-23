"""Brave Search API request and response models."""

from typing import Optional

from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    """Request model for web search."""

    query: str = Field(..., description="Search query")
    count: int = Field(
        10,
        description="Number of results to return (max 20)",
        ge=1,
        le=20,
    )
    freshness: Optional[str] = Field(
        None,
        description="Filter results by freshness: 'day' (past 24h), 'week' (past 7 days), 'month' (past 30 days), 'year' (past year)",
    )
