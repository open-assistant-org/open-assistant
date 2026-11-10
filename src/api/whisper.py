"""Whisper transcription API endpoints."""

import base64
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from src.core.dependencies import get_settings_service, get_whisper_service
from src.services.settings import SettingsService
from src.services.transcription import is_audio_mimetype, transcribe_audio
from src.services.whisper import WhisperService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/whisper", tags=["whisper"])

# The Whisper API takes files up to 25 MB
MAX_AUDIO_SIZE = 25 * 1024 * 1024


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


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    settings_service: SettingsService = Depends(get_settings_service),
) -> Dict[str, str]:
    """
    Transcribe a recorded voice message, e.g. one dictated in a chat UI.

    The audio is transcribed once, as a whole, and is not stored. The caller
    sends the returned text as an ordinary chat message.

    Args:
        file: The recording (any audio format Whisper accepts)
        settings_service: Settings service (injected)

    Returns:
        The transcribed text
    """
    if not settings_service.get_config_with_fallback("whisper.enabled", False):
        raise HTTPException(
            status_code=503, detail="Voice messages are not set up for this assistant."
        )
    api_key = settings_service.get_config_with_fallback(
        "whisper.api_key", ""
    ) or settings_service.get_config_with_fallback("llm.api_key")
    if not api_key:
        raise HTTPException(
            status_code=503, detail="Voice messages are not set up for this assistant."
        )

    mimetype = file.content_type or ""
    if not is_audio_mimetype(mimetype):
        raise HTTPException(status_code=415, detail="Only audio recordings can be transcribed.")

    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="The recording is empty.")
    if len(audio) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"The recording is too long. The limit is {MAX_AUDIO_SIZE // (1024 * 1024)} MB.",
        )

    try:
        # The OpenAI client is synchronous; keep the event loop free meanwhile
        text = await run_in_threadpool(
            transcribe_audio,
            audio_base64=base64.b64encode(audio).decode("ascii"),
            mimetype=mimetype,
            api_key=api_key,
            base_url=settings_service.get_config_with_fallback("whisper.base_url", "") or None,
            model=settings_service.get_config_with_fallback("whisper.model", "whisper-1"),
            filename=file.filename,
        )
    except ValueError as e:
        # transcribe_audio already logged the cause
        raise HTTPException(
            status_code=502, detail="The recording could not be transcribed."
        ) from e

    if not text:
        raise HTTPException(status_code=422, detail="No speech was heard in the recording.")
    return {"text": text}
