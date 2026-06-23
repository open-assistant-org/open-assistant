"""Whisper transcription API endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.core.dependencies import get_whisper_service
from src.services.whisper import WhisperService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/whisper", tags=["whisper"])


@router.post("/test-connection")
async def test_connection(
    whisper_service: WhisperService = Depends(get_whisper_service),
) -> Dict[str, Any]:
    """
    Test Whisper transcription API connection.

    Args:
        whisper_service: Whisper service (injected)

    Returns:
        Connection test result
    """
    return whisper_service.test_connection()
