"""Browser API endpoints."""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.core.dependencies import get_browser_service
from src.services.browser import BrowserService

router = APIRouter(prefix="/api/browser", tags=["browser"])


@router.post("/test-connection")
async def test_connection(
    browser_service: BrowserService = Depends(get_browser_service),
) -> Dict[str, Any]:
    """
    Test browser connection by launching Playwright and navigating to a test page.

    Args:
        browser_service: Browser service (injected)

    Returns:
        Connection test result
    """
    # Run sync Playwright code in a thread to avoid async loop conflict
    return await asyncio.to_thread(browser_service.test_connection)
