"""Yahoo Finance API endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.core.dependencies import get_yahoo_finance_service

router = APIRouter(prefix="/api/yahoo-finance", tags=["yahoo_finance"])


@router.post("/test-connection")
async def test_connection(
    yahoo_finance_service=Depends(get_yahoo_finance_service),
) -> Dict[str, Any]:
    """Test Yahoo Finance connectivity by fetching a live price quote."""
    return yahoo_finance_service.test_connection()
