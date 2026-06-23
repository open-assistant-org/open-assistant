"""Unified search request and response models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class UnifiedSearchRequest(BaseModel):
    """Request model for unified search across all sources."""

    query: str = Field(..., description="Search query")
    sources: Optional[List[str]] = Field(
        None,
        description="Sources to search. Options: 'notion', 'gmail', 'outlook_email', 'outlook_files', 'onenote', 'nextcloud'. Searches all enabled sources if not specified.",
    )
    search_type: str = Field(
        "hybrid",
        description="Search type: 'hybrid' (keyword + semantic), 'keyword' (keyword only), 'semantic' (semantic only, requires index)",
    )
    limit: int = Field(
        10,
        description="Maximum number of results to return",
        ge=1,
        le=50,
    )


class ReindexSearchRequest(BaseModel):
    """Request model for triggering search index rebuild."""

    sources: Optional[List[str]] = Field(
        None,
        description="Sources to reindex. Options: 'notion', 'gmail', 'outlook_email', 'outlook_files', 'onenote', 'nextcloud'. Reindexes all enabled sources if not specified.",
    )
