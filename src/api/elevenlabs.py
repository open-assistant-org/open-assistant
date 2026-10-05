"""ElevenLabs voice agent channel.

An ElevenLabs agent keeps the live conversation on its own fast LLM and calls
these endpoints as *server tools* when the caller wants real work done. The
request runs through the same ``MessageHandler`` as Slack/WhatsApp, with
``channel="elevenlabs"`` and the ElevenLabs conversation id as the contact.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from src.core.dependencies import (
    get_elevenlabs_service,
    get_message_handler,
    get_slack_service,
    get_whatsapp_service,
)
from src.models.elevenlabs import (
    AskAssistantRequest,
    CheckResultRequest,
    PostCallPayload,
    ToolResponse,
    WebhookAck,
)
from src.services.elevenlabs import CHANNEL, ElevenLabsService, VoiceJob, voice_jobs
from src.services.message_handler import MessageHandler
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/elevenlabs", tags=["elevenlabs"])

STILL_WORKING_NOTE = (
    "Tell the caller you are still working on it, then call check_assistant_result "
    "with this job_id."
)


def require_enabled(
    service: ElevenLabsService = Depends(get_elevenlabs_service),
) -> ElevenLabsService:
    if not service.is_enabled():
        raise HTTPException(status_code=503, detail="ElevenLabs voice agent is not enabled")
    return service


def require_tool_auth(
    authorization: Optional[str] = Header(default=None),
    service: ElevenLabsService = Depends(require_enabled),
) -> ElevenLabsService:
    if not service.verify_bearer(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")
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


@router.post("/tools/ask_assistant", response_model=ToolResponse)
async def ask_assistant(
    body: AskAssistantRequest,
    service: ElevenLabsService = Depends(require_tool_auth),
    message_handler: MessageHandler = Depends(get_message_handler),
    slack_service=Depends(get_slack_service),
    whatsapp_service=Depends(get_whatsapp_service),
) -> ToolResponse:
    """Hand a request to the assistant and wait briefly for the answer."""

    async def run():
        return await message_handler.handle_message(
            message=body.request,
            conversation_id=None,
            channel=CHANNEL,
            contact_identifier=body.conversation_id,
            max_idle_seconds=service.new_chat_idle_seconds(),
            metadata={"source": "elevenlabs_tool", "voice_conversation_id": body.conversation_id},
        )

    job = voice_jobs.start(
        body.conversation_id,
        run,
        fallback=_build_fallback(service, slack_service, whatsapp_service),
    )
    if await voice_jobs.wait(job, service.tool_wait_seconds()):
        return _response_for(job)
    return _working(job)


@router.post("/tools/check_assistant_result", response_model=ToolResponse)
async def check_assistant_result(
    body: CheckResultRequest,
    service: ElevenLabsService = Depends(require_tool_auth),
) -> ToolResponse:
    """Collect the result of a request that was still running."""
    job = voice_jobs.get(body.job_id)
    if job is None:
        return ToolResponse(
            status="error",
            answer="Sorry, I lost track of that request. Could you ask again?",
        )
    if await voice_jobs.wait(job, service.tool_wait_seconds()):
        return _response_for(job)
    return _working(job)


@router.post("/webhooks/post-call", response_model=None)
async def post_call_webhook(
    request: Request,
    elevenlabs_signature: Optional[str] = Header(default=None, alias="ElevenLabs-Signature"),
    service: ElevenLabsService = Depends(require_enabled),
    message_handler: MessageHandler = Depends(get_message_handler),
) -> WebhookAck:
    """Store the call transcript so the assistant remembers the voice conversation."""
    raw = await request.body()
    if not service.verify_webhook_signature(elevenlabs_signature, raw):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = PostCallPayload.model_validate(json.loads(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}")

    if payload.type != "post_call_transcription" or payload.data is None:
        return {"ok": True, "ignored": payload.type}

    conversation_id = payload.data.conversation_id
    voice_jobs.mark_call_ended(conversation_id)

    lines = []
    for turn in payload.data.transcript:
        text = (turn.message or "").strip()
        if text:
            speaker = "Voice agent" if turn.role == "agent" else "Voice caller"
            lines.append(f"[{speaker}]: {text}")
    if lines:
        await message_handler.ingest_passive_message(
            message="[Voice call transcript]\n" + "\n".join(lines),
            channel=CHANNEL,
            contact_identifier=conversation_id,
            metadata={"source": "elevenlabs_post_call", "voice_conversation_id": conversation_id},
            max_idle_seconds=service.new_chat_idle_seconds(),
        )
    return {"ok": True, "turns": len(lines)}


@router.post("/test-connection")
async def test_connection(service: ElevenLabsService = Depends(get_elevenlabs_service)):
    """Report whether the channel is configured (used by the settings page)."""
    return service.test_connection()
