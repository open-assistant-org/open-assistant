"""Google News API endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.core.dependencies import get_google_news_service

router = APIRouter(prefix="/api/google-news", tags=["google_news"])


@router.post("/test-connection")
async def test_connection(
    google_news_service=Depends(get_google_news_service),
) -> Dict[str, Any]:
    """Test Google News connectivity by fetching a top headline."""
    return google_news_service.test_connection()
