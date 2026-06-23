"""Brave Search API endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.core.dependencies import get_brave_service
from src.services.brave import BraveService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/brave", tags=["brave"])


@router.post("/test-connection")
async def test_connection(
    brave_service: BraveService = Depends(get_brave_service),
) -> Dict[str, Any]:
    """
    Test Brave Search connection.

    Args:
        brave_service: Brave Search service (injected)

    Returns:
        Connection test result
    """
    return brave_service.test_connection()
