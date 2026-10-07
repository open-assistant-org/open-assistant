"""ElevenLabs voice channel (outbound only).

The Talk page in the web UI opens a voice session from the browser *out* to
ElevenLabs. The agent's client tools run in that page and call the endpoints
below on the same origin, so no connection from ElevenLabs into this instance
is needed. This app only makes outbound requests to ElevenLabs: a signed
session URL before the call and the transcript after it.

Like the rest of the web UI API (``/api/chat``), these endpoints rely on the
instance being reachable only by its owner.
"""

import asyncio
from typing import Set

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import (
    get_elevenlabs_service,
    get_message_handler,
    get_slack_service,
    get_whatsapp_service,
)
from src.models.elevenlabs import (
    AskAssistantRequest,
    CheckResultRequest,
    EndCallRequest,
    SessionResponse,
    StatusResponse,
    ToolResponse,
)
from src.services.elevenlabs import (
    CHANNEL,
    ElevenLabsError,
    ElevenLabsService,
    VoiceJob,
    voice_jobs,
)
from src.services.message_handler import MessageHandler
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/elevenlabs", tags=["elevenlabs"])

STILL_WORKING_NOTE = (
    "Tell the caller you are still working on it, then call check_assistant_result "
    "with this job_id."
)

# Calls whose end has already been handled (the page may report it twice: the
# disconnect callback and the page-close beacon).
_ended_calls: Set[str] = set()
_background_tasks: Set["asyncio.Task[None]"] = set()


def require_enabled(
    service: ElevenLabsService = Depends(get_elevenlabs_service),
) -> ElevenLabsService:
    if not service.is_enabled():
        raise HTTPException(status_code=503, detail="ElevenLabs voice is not enabled")
    return service


def _response_for(job: VoiceJob) -> ToolResponse:
    if job.error:
        return ToolResponse(status="error", answer=job.spoken_answer())
    pending = (job.result or {}).get("pending_input")
    if pending:
        return ToolResponse(
            status="done", question=pending.get("question"), answer=job.spoken_answer()
        )
    return ToolResponse(status="done", answer=job.spoken_answer())


def _working(job: VoiceJob) -> ToolResponse:
    return ToolResponse(status="working", job_id=job.job_id, note=STILL_WORKING_NOTE)


def _build_fallback(service: ElevenLabsService, slack_service, whatsapp_service):
    channel = service.fallback_channel()
    if channel == "slack":

        async def send(text: str) -> None:
            slack_service.send_message_to_default_channel(f"🎙️ Voice request finished: {text}")

        return send
    if channel == "whatsapp":

        async def send(text: str) -> None:
            whatsapp_service.send_message_to_owner(f"🎙️ Voice request finished: {text}")

        return send
    return None


@router.get("/status", response_model=StatusResponse)
async def status(
    service: ElevenLabsService = Depends(get_elevenlabs_service),
) -> StatusResponse:
    """Whether the Talk page should be offered (the navbar polls this)."""
    return StatusResponse(enabled=service.is_enabled(), configured=service.is_configured())


@router.post("/session", response_model=SessionResponse)
async def start_session(
    service: ElevenLabsService = Depends(require_enabled),
) -> SessionResponse:
    """Signed URL for the browser to open a voice session (the API key stays here)."""
    try:
        return SessionResponse(signed_url=await service.get_signed_url())
    except ElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/voice/ask", response_model=ToolResponse)
async def ask_assistant(
    body: AskAssistantRequest,
    service: ElevenLabsService = Depends(require_enabled),
    message_handler: MessageHandler = Depends(get_message_handler),
    slack_service=Depends(get_slack_service),
    whatsapp_service=Depends(get_whatsapp_service),
) -> ToolResponse:
    """Client tool ``ask_assistant``: hand a request over and wait briefly for the answer."""

    async def run():
        return await message_handler.handle_message(
            message=body.request,
            conversation_id=None,
            channel=CHANNEL,
            contact_identifier=body.conversation_id,
            max_idle_seconds=service.new_chat_idle_seconds(),
            metadata={"source": "elevenlabs_talk", "voice_conversation_id": body.conversation_id},
        )

    job = voice_jobs.start(
        body.conversation_id,
        run,
        fallback=_build_fallback(service, slack_service, whatsapp_service),
    )
    if await voice_jobs.wait(job, service.tool_wait_seconds()):
        return _response_for(job)
    return _working(job)


@router.post("/voice/result", response_model=ToolResponse)
async def check_assistant_result(
    body: CheckResultRequest,
    service: ElevenLabsService = Depends(require_enabled),
) -> ToolResponse:
    """Client tool ``check_assistant_result``: collect a request that was still running."""
    job = voice_jobs.get(body.job_id)
    if job is None:
        return ToolResponse(
            status="error",
            answer="Sorry, I lost track of that request. Could you ask again?",
        )
    if await voice_jobs.wait(job, service.tool_wait_seconds()):
        return _response_for(job)
    return _working(job)


@router.post("/voice/end")
async def end_call(
    body: EndCallRequest,
    service: ElevenLabsService = Depends(require_enabled),
    message_handler: MessageHandler = Depends(get_message_handler),
) -> dict:
    """The Talk page reports a finished call: flush pending results, store the transcript."""
    voice_jobs.mark_call_ended(body.conversation_id)
    if body.conversation_id in _ended_calls:
        return {"ok": True, "duplicate": True}
    if len(_ended_calls) > 1000:
        _ended_calls.clear()
    _ended_calls.add(body.conversation_id)

    task = asyncio.create_task(service.ingest_transcript(message_handler, body.conversation_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"ok": True}


@router.post("/test-connection")
async def test_connection(service: ElevenLabsService = Depends(get_elevenlabs_service)):
    """Check the API key and agent ID (used by the settings page)."""
    return await service.test_connection()
