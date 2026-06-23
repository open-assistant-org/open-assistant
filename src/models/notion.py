"""Notion API request and response models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateNoteRequest(BaseModel):
    """Request model for creating a note."""

    title: str = Field(..., description="The title of the note or page to create")
    content: Optional[str] = Field(
        None,
        description=(
            "The body content of the note. Supports markdown formatting: "
            "**bold**, *italic*, `code`, headings (#, ##, ###), "
            "bullet lists (- item), numbered lists (1. item), and code blocks (```). "
            "Leave empty to create a blank note."
        ),
    )
    database_id: Optional[str] = Field(
        None,
        description=(
            "Notion database ID to create the note in. "
            "Only provide this if the user explicitly specifies a database. "
            "Leave empty to use the default location."
        ),
    )
    parent_page_id: Optional[str] = Field(
        None,
        description=(
            "Notion page ID to create the note under as a child page. "
            "Only provide this if the user explicitly specifies a parent page. "
            "Leave empty to use the default location."
        ),
    )
    properties: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Extra database column values to set on the note, in addition to its title. "
            "Use this to fill columns such as select, status, multi-select, date, number, "
            "and checkbox. Each value must use Notion's property-value format, keyed by the "
            "exact column name. Examples: "
            'select -> {"Type": {"select": {"name": "Article"}}}; '
            'status -> {"State": {"status": {"name": "In progress"}}}; '
            'multi-select -> {"Tags": {"multi_select": [{"name": "a"}, {"name": "b"}]}}; '
            'date -> {"Due": {"date": {"start": "2026-06-05"}}}; '
            'number -> {"Score": {"number": 5}}; checkbox -> {"Done": {"checkbox": true}}. '
            "Call notion_list_databases first to discover the exact column names and types. "
            "Only applies when creating inside a database."
        ),
    )


class CreatePageRequest(BaseModel):
    """Request model for creating a page with custom properties."""

    database_id: Optional[str] = Field(None, description="Database ID")
    parent_page_id: Optional[str] = Field(None, description="Parent page ID")
    properties: Dict[str, Any] = Field(..., description="Page properties")
    children: Optional[List[Dict[str, Any]]] = Field(None, description="Page content blocks")
    data_source_id: Optional[str] = Field(
        None, description="Data source ID (auto-resolved from database_id if not provided)"
    )


class UpdatePageRequest(BaseModel):
    """Request model for updating a page."""

    page_id: str = Field(
        ...,
        description=(
            "Notion page ID of the page to update. This is a separate top-level "
            "parameter — do NOT nest it inside 'properties'."
        ),
    )
    properties: Dict[str, Any] = Field(
        ...,
        description=(
            "Properties to update, in Notion's property-value format, keyed by the "
            "exact column name. Examples: "
            'status -> {"State": {"status": {"name": "Done"}}}; '
            'select -> {"Type": {"select": {"name": "Article"}}}; '
            'multi-select -> {"Tags": {"multi_select": [{"name": "a"}, {"name": "b"}]}}; '
            'date -> {"Due": {"date": {"start": "2026-06-05"}}}; '
            'number -> {"Score": {"number": 5}}; checkbox -> {"Done": {"checkbox": true}}. '
            "A column displayed as a status field uses 'status', not 'select'. "
            "Call notion_list_databases first to discover the exact column names, "
            "types, and valid option values."
        ),
    )


class AppendContentRequest(BaseModel):
    """Request model for appending content to a page."""

    content: str = Field(..., description="Content to append")


class SearchRequest(BaseModel):
    """Request model for searching pages."""

    query: str = Field(..., description="Search query")
    filter_type: Optional[str] = Field("page", description="Filter by type (page or database)")


class QueryDatabaseRequest(BaseModel):
    """Request model for querying a database."""

    database_id: Optional[str] = Field(
        None, description="Database ID (uses default if not provided)"
    )
    filter: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Notion filter object to narrow results by property values. "
            "Single-property examples: "
            'select/status equals -> {"property": "State", "status": {"equals": "Done"}}; '
            'select not equals -> {"property": "Type", "select": {"does_not_equal": "Article"}}; '
            'checkbox -> {"property": "Done", "checkbox": {"equals": true}}; '
            'date on/after -> {"property": "Due", "date": {"on_or_after": "2026-06-01"}}; '
            'text contains -> {"property": "Name", "title": {"contains": "API"}}. '
            "Combine with AND: "
            '{"and": [{"property": "State", "status": {"equals": "In progress"}}, '
            '{"property": "Type", "select": {"equals": "Article"}}]}. '
            "Combine with OR: "
            '{"or": [...]}. '
            "Use the exact property name (case-sensitive) as returned by notion_list_databases."
        ),
    )
    sorts: Optional[List[Dict[str, Any]]] = Field(
        None,
        description=(
            "List of sort objects. Each object: "
            '{"property": "<column name>", "direction": "ascending" | "descending"}. '
            'Example: [{"property": "Last edited time", "direction": "descending"}].'
        ),
    )
    data_source_id: Optional[str] = Field(
        None, description="Data source ID (auto-resolved from database_id if not provided)"
    )


class GetPageRequest(BaseModel):
    """Request model for getting a page."""

    page_id: str = Field(..., description="Notion page ID")


class GetPageContentRequest(BaseModel):
    """Request model for getting page content blocks."""

    page_id: str = Field(..., description="Notion page ID")


class ListDatabasesRequest(BaseModel):
    """Request model for listing accessible databases."""

    pass  # No parameters needed


class ListDataSourcesRequest(BaseModel):
    """Request model for listing accessible data sources (databases)."""

    pass  # No parameters needed


class DeletePageRequest(BaseModel):
    """Request model for deleting (archiving) a page."""

    page_id: str = Field(..., description="Notion page ID to archive/delete")


class PageResponse(BaseModel):
    """Response model for page operations."""

    id: str = Field(..., description="Page ID")
    object: str = Field(..., description="Object type")
    created_time: str = Field(..., description="Creation timestamp")
    last_edited_time: str = Field(..., description="Last edit timestamp")
    url: str = Field(..., description="Page URL")
    properties: Optional[Dict[str, Any]] = Field(None, description="Page properties")


class SearchResultsResponse(BaseModel):
    """Response model for search results."""

    results: List[Dict[str, Any]] = Field(..., description="Search results")
    has_more: bool = Field(..., description="Whether there are more results")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")


class NotionConnectionTestResponse(BaseModel):
    """Response model for connection test."""

    service_name: str = Field(..., description="Service name")
    status: str = Field(..., description="Connection status (success, error, warning)")
    message: str = Field(..., description="Status message")
