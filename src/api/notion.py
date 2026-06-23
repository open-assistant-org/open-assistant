"""Notion API endpoints for page and note management."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import get_credentials_repo, get_settings_repo
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.notion import (
    AppendContentRequest,
    CreateNoteRequest,
    CreatePageRequest,
    ListDataSourcesRequest,
    ListDatabasesRequest,
    NotionConnectionTestResponse,
    QueryDatabaseRequest,
    SearchRequest,
    UpdatePageRequest,
)
from src.services.notion import NotionService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/notion", tags=["notion"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


def get_notion_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> NotionService:
    """Get Notion service with dependencies."""
    return NotionService(settings_repo, credentials_repo)


# ============================================================================
# NOTE OPERATIONS
# ============================================================================


@router.post("/notes")
async def create_note(
    request: CreateNoteRequest, notion_service: NotionService = Depends(get_notion_service)
) -> Dict[str, Any]:
    """
    Create a new note in Notion.

    Args:
        request: Note creation request
        notion_service: Notion service (injected)

    Returns:
        Created page object

    Raises:
        HTTPException: If creation fails
    """
    try:
        page = notion_service.create_note(
            title=request.title,
            content=request.content,
            database_id=request.database_id,
            parent_page_id=request.parent_page_id,
            data_source_id=request.data_source_id,
            properties=request.properties,
        )
        return page

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create Notion note: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create note: {str(e)}")


# ============================================================================
# PAGE OPERATIONS
# ============================================================================


@router.post("/pages")
async def create_page(
    request: CreatePageRequest, notion_service: NotionService = Depends(get_notion_service)
) -> Dict[str, Any]:
    """
    Create a new page with custom properties.

    Args:
        request: Page creation request
        notion_service: Notion service (injected)

    Returns:
        Created page object

    Raises:
        HTTPException: If creation fails
    """
    try:
        client = notion_service._get_client()
        page = client.create_page(
            database_id=request.database_id,
            parent_page_id=request.parent_page_id,
            properties=request.properties,
            children=request.children,
            data_source_id=request.data_source_id,
        )
        return page

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create Notion page: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create page: {str(e)}")


@router.get("/pages/{page_id}")
async def get_page(
    page_id: str, notion_service: NotionService = Depends(get_notion_service)
) -> Dict[str, Any]:
    """
    Get page details.

    Args:
        page_id: Page ID
        notion_service: Notion service (injected)

    Returns:
        Page object

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        page = notion_service.get_page(page_id=page_id)
        return page

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get Notion page: {e}")
        raise HTTPException(status_code=404, detail=f"Page not found: {str(e)}")


@router.get("/pages/{page_id}/content")
async def get_page_content(
    page_id: str, notion_service: NotionService = Depends(get_notion_service)
) -> List[Dict[str, Any]]:
    """
    Get page content blocks.

    Args:
        page_id: Page ID
        notion_service: Notion service (injected)

    Returns:
        List of content blocks

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        blocks = notion_service.get_page_content(page_id=page_id)
        return blocks

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get page content: {e}")
        raise HTTPException(status_code=404, detail=f"Page not found: {str(e)}")


@router.patch("/pages/{page_id}")
async def update_page(
    page_id: str,
    request: UpdatePageRequest,
    notion_service: NotionService = Depends(get_notion_service),
) -> Dict[str, Any]:
    """
    Update page properties.

    Args:
        page_id: Page ID
        request: Update request
        notion_service: Notion service (injected)

    Returns:
        Updated page object

    Raises:
        HTTPException: If update fails
    """
    try:
        page = notion_service.update_page(page_id=page_id, properties=request.properties)
        return page

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update page: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update page: {str(e)}")


@router.post("/pages/{page_id}/append")
async def append_content(
    page_id: str,
    request: AppendContentRequest,
    notion_service: NotionService = Depends(get_notion_service),
) -> Dict[str, Any]:
    """
    Append content to a page.

    Args:
        page_id: Page ID
        request: Content to append
        notion_service: Notion service (injected)

    Returns:
        Response with appended blocks

    Raises:
        HTTPException: If append fails
    """
    try:
        result = notion_service.append_content(page_id=page_id, content=request.content)
        return result

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to append content: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to append content: {str(e)}")


# ============================================================================
# SEARCH OPERATIONS
# ============================================================================


@router.post("/search")
async def search_pages(
    request: SearchRequest, notion_service: NotionService = Depends(get_notion_service)
) -> List[Dict[str, Any]]:
    """
    Search for pages.

    Args:
        request: Search request
        notion_service: Notion service (injected)

    Returns:
        List of matching pages

    Raises:
        HTTPException: If search fails
    """
    try:
        results = notion_service.search_pages(query=request.query, filter_type=request.filter_type)
        return results

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to search pages: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================


@router.post("/databases/query")
async def query_database(
    request: QueryDatabaseRequest, notion_service: NotionService = Depends(get_notion_service)
) -> List[Dict[str, Any]]:
    """
    Query database entries.

    Args:
        request: Query request
        notion_service: Notion service (injected)

    Returns:
        List of database entries

    Raises:
        HTTPException: If query fails
    """
    try:
        entries = notion_service.query_database(
            database_id=request.database_id,
            filter_dict=request.filter,
            sorts=request.sorts,
            data_source_id=request.data_source_id,
        )
        return entries

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to query database: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/databases")
async def list_databases(
    notion_service: NotionService = Depends(get_notion_service),
) -> List[Dict[str, Any]]:
    """
    List all databases accessible to the integration.

    This is an alias for list_data_sources for backward compatibility.
    In Notion API version 2025-09-03, databases are exposed as data sources.

    Args:
        notion_service: Notion service (injected)

    Returns:
        List of database objects with id, title, and property schemas

    Raises:
        HTTPException: If listing fails
    """
    try:
        databases = notion_service.list_databases()
        return databases

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list databases: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list databases: {str(e)}")


@router.get("/data-sources")
async def list_data_sources(
    notion_service: NotionService = Depends(get_notion_service),
) -> List[Dict[str, Any]]:
    """
    List all data sources (databases) accessible to the integration.

    In Notion API version 2025-09-03, databases are exposed as data sources.

    Args:
        notion_service: Notion service (injected)

    Returns:
        List of data source objects with id, title, and property schemas

    Raises:
        HTTPException: If listing fails
    """
    try:
        data_sources = notion_service.list_data_sources()
        return data_sources

    except ValueError as e:
        logger.error(f"Invalid Notion configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list data sources: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list data sources: {str(e)}")


# ============================================================================
# CONNECTION TESTING
# ============================================================================


@router.post("/test-connection", response_model=NotionConnectionTestResponse)
async def test_connection(
    notion_service: NotionService = Depends(get_notion_service),
) -> NotionConnectionTestResponse:
    """
    Test Notion connection.

    Args:
        notion_service: Notion service (injected)

    Returns:
        Connection test result
    """
    result = notion_service.test_connection()
    return NotionConnectionTestResponse(**result)
