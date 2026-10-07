"""ElevenLabs voice channel.

The browser "Talk" page opens a voice session *out* to ElevenLabs. The agent's
client tools run in that page and call back into this app on the same origin,
so nothing needs to reach this instance from the internet. This module holds
what the server side needs: outbound calls to ElevenLabs (signed session URL,
call transcript), speech-friendly text, and a small in-memory job registry so
a request that outlasts a tool call can be collected on a follow-up call (or
delivered to Slack/WhatsApp if the caller already hung up).

The job registry is process-local, which matches the single-process
deployment (one uvicorn worker under supervisord).
"""

import asyncio
import re
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)

CHANNEL = "elevenlabs"
API_BASE = "https://api.elevenlabs.io"
HTTP_TIMEOUT_SECONDS = 15
TRANSCRIPT_POLL_SECONDS = 5
TRANSCRIPT_MAX_WAIT_SECONDS = 90
ORPHAN_GRACE_SECONDS = 60
JOB_RETENTION_SECONDS = 15 * 60
MAX_SPOKEN_CHARS = 1200


class ElevenLabsError(Exception):
    """An outbound ElevenLabs request failed (message is safe to show the user)."""


class ElevenLabsService(BaseService):
    """Settings, secrets and verification for the ElevenLabs channel."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)

    # -- settings -----------------------------------------------------------

    def _get_sensitive_setting(self, key: str) -> Optional[str]:
        value = self.settings_repo.get(key)
        if value:
            return value
        service_name = key.split(".")[0]
        setting_key = key.split(".", 1)[1] if "." in key else "value"
        cred = self.credentials_repo.get(service_name)
        if cred:
            data = cred.get("credential_data", {})
            return data.get(setting_key) or data.get("value")
        return None

    def _get_int(self, key: str, default: int) -> int:
        try:
            return int(self.settings_repo.get(key) or default)
        except (TypeError, ValueError):
            return default

    def is_enabled(self) -> bool:
        return bool(self.settings_repo.get("elevenlabs.enabled"))

    def tool_wait_seconds(self) -> int:
        return self._get_int("elevenlabs.tool_wait_seconds", 20)

    def new_chat_idle_seconds(self) -> int:
        return self._get_int("elevenlabs.new_chat_idle_seconds", 1800)

    def fallback_channel(self) -> str:
        return (self.settings_repo.get("elevenlabs.fallback_channel") or "none").lower()

    def api_key(self) -> Optional[str]:
        return self._get_sensitive_setting("elevenlabs.api_key")

    def agent_id(self) -> str:
        return (self.settings_repo.get("elevenlabs.agent_id") or "").strip()

    def is_configured(self) -> bool:
        return bool(self.api_key() and self.agent_id())

    # -- outbound requests --------------------------------------------------

    async def _get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> Dict[str, Any]:
        key = self.api_key()
        if not key:
            raise ElevenLabsError("ElevenLabs API key is not configured")
        try:
            async with httpx.AsyncClient(
                base_url=API_BASE, timeout=HTTP_TIMEOUT_SECONDS, transport=transport
            ) as client:
                response = await client.get(path, params=params, headers={"xi-api-key": key})
        except httpx.HTTPError as exc:
            raise ElevenLabsError(f"Could not reach ElevenLabs: {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise ElevenLabsError("ElevenLabs rejected the API key")
        if response.status_code == 404:
            raise ElevenLabsError("ElevenLabs could not find that agent or conversation")
        if response.status_code >= 400:
            raise ElevenLabsError(f"ElevenLabs returned HTTP {response.status_code}")
        return response.json()

    async def get_signed_url(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> str:
        """Short-lived WebSocket URL the browser uses to start a voice session.

        Lets the agent stay private and keeps the API key off the client.
        """
        agent_id = self.agent_id()
        if not agent_id:
            raise ElevenLabsError("ElevenLabs agent ID is not configured")
        data = await self._get(
            "/v1/convai/conversation/get-signed-url", {"agent_id": agent_id}, transport
        )
        url = data.get("signed_url")
        if not url:
            raise ElevenLabsError("ElevenLabs did not return a session URL")
        return url

    async def fetch_conversation(
        self, conversation_id: str, transport: Optional[httpx.AsyncBaseTransport] = None
    ) -> Dict[str, Any]:
        quoted = urllib.parse.quote(conversation_id, safe="")
        return await self._get(f"/v1/convai/conversations/{quoted}", None, transport)

    async def ingest_transcript(
        self,
        message_handler: Any,
        conversation_id: str,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        poll_seconds: float = TRANSCRIPT_POLL_SECONDS,
        max_wait_seconds: float = TRANSCRIPT_MAX_WAIT_SECONDS,
    ) -> int:
        """Pull a finished call's transcript and store it in the voice conversation.

        ElevenLabs finalises the transcript a little after the call ends, so
        poll until its status is "done". Returns the number of turns stored.
        """
        deadline = time.monotonic() + max_wait_seconds
        while True:
            try:
                data = await self.fetch_conversation(conversation_id, transport)
            except ElevenLabsError as exc:
                logger.warning(f"Voice transcript fetch failed for {conversation_id}: {exc}")
                return 0
            if data.get("status") == "done" or time.monotonic() >= deadline:
                break
            await asyncio.sleep(poll_seconds)

        lines = transcript_lines(data.get("transcript") or [])
        if not lines:
            return 0
        await message_handler.ingest_passive_message(
            message="[Voice call transcript]\n" + "\n".join(lines),
            channel=CHANNEL,
            contact_identifier=conversation_id,
            metadata={"source": "elevenlabs_transcript", "voice_conversation_id": conversation_id},
            max_idle_seconds=self.new_chat_idle_seconds(),
        )
        return len(lines)

    async def test_connection(
        self, transport: Optional[httpx.AsyncBaseTransport] = None
    ) -> Dict[str, Any]:
        def result(status: str, message: str) -> Dict[str, Any]:
            return {"service_name": CHANNEL, "status": status, "message": message}

        if not self.is_enabled():
            return result("error", "ElevenLabs voice is not enabled")
        if not self.api_key():
            return result("error", "API key not configured. Set 'elevenlabs.api_key'.")
        if not self.agent_id():
            return result("error", "Agent ID not configured. Set 'elevenlabs.agent_id'.")
        try:
            agent = await self._get(
                f"/v1/convai/agents/{urllib.parse.quote(self.agent_id(), safe='')}", None, transport
            )
        except ElevenLabsError as exc:
            return result("error", str(exc))
        return result("success", f"Connected to agent '{agent.get('name') or self.agent_id()}'")


def transcript_lines(turns: List[Dict[str, Any]]) -> List[str]:
    """Label transcript turns by speaker, dropping empty ones."""
    lines = []
    for turn in turns:
        text = (turn.get("message") or "").strip()
        if text:
            speaker = "Voice agent" if turn.get("role") == "agent" else "Voice caller"
            lines.append(f"[{speaker}]: {text}")
    return lines


# -- speech text -----------------------------------------------------------

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_BARE_URL = re.compile(r"https?://\S+")
_MD_DECOR = re.compile(r"(\*\*|__|`|^#{1,6}\s*|^>\s*)", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)


def to_speech_text(text: str, max_chars: int = MAX_SPOKEN_CHARS) -> str:
    """Make assistant output suitable for text-to-speech."""
    text = _CODE_FENCE.sub(" (code omitted) ", text or "")
    text = _MD_LINK.sub(r"\1", text)
    text = _BARE_URL.sub("a link", text)
    text = _BULLET.sub("", text)
    text = _MD_DECOR.sub("", text)
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        text = (
            cut[: end + 1] if end > max_chars // 2 else cut
        ).rstrip() + " I can send the full details if you like."
    return text


# -- job registry ----------------------------------------------------------


@dataclass
class VoiceJob:
    job_id: str
    conversation_id: str
    task: Optional["asyncio.Task[None]"] = None
    created: float = field(default_factory=time.monotonic)
    finished: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    picked_up: bool = False
    call_ended: bool = False
    delivered: bool = False
    fallback: Optional[Callable[[str], Awaitable[None]]] = None
    done_event: asyncio.Event = field(default_factory=asyncio.Event)
    followup: Optional["asyncio.Task[None]"] = None

    @property
    def done(self) -> bool:
        return self.finished is not None

    def spoken_answer(self) -> str:
        if self.error:
            return "Sorry, something went wrong while I was working on that."
        return to_speech_text((self.result or {}).get("response") or "")


class VoiceJobRegistry:
    """Tracks assistant runs started by voice tool calls."""

    def __init__(self, orphan_grace: float = ORPHAN_GRACE_SECONDS):
        self._jobs: Dict[str, VoiceJob] = {}
        self._by_conversation: Dict[str, str] = {}
        self.orphan_grace = orphan_grace

    def get(self, job_id: str) -> Optional[VoiceJob]:
        return self._jobs.get(job_id)

    def active_for(self, conversation_id: str) -> Optional[VoiceJob]:
        job = self._jobs.get(self._by_conversation.get(conversation_id, ""))
        return job if job and not job.picked_up else None

    def start(
        self,
        conversation_id: str,
        run: Callable[[], Awaitable[Dict[str, Any]]],
        fallback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> VoiceJob:
        """Start a run, or return the one already in flight for this call."""
        self._prune()
        existing = self.active_for(conversation_id)
        if existing and not existing.done:
            return existing

        job = VoiceJob(
            job_id=uuid.uuid4().hex[:12], conversation_id=conversation_id, fallback=fallback
        )
        self._jobs[job.job_id] = job
        self._by_conversation[conversation_id] = job.job_id

        async def _runner() -> None:
            try:
                job.result = await run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a spoken apology
                logger.error(f"Voice job {job.job_id} failed: {exc}", exc_info=True)
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.finished = time.monotonic()
                job.done_event.set()
            # Separate task: the grace period must not delay wait() callers.
            job.followup = asyncio.create_task(self._after_finish(job))

        job.task = asyncio.create_task(_runner())
        return job

    async def wait(self, job: VoiceJob, timeout: float) -> bool:
        """Wait for a job; True when finished. Marks it collected on success."""
        if not job.done:
            try:
                await asyncio.wait_for(job.done_event.wait(), timeout)
            except asyncio.TimeoutError:
                return False
        if job.done:
            job.picked_up = True
        return job.done

    def mark_call_ended(self, conversation_id: str) -> None:
        job = self._jobs.get(self._by_conversation.get(conversation_id, ""))
        if job is None:
            return
        job.call_ended = True
        if job.done and not job.picked_up:
            job.followup = asyncio.create_task(self._deliver(job))

    async def _after_finish(self, job: VoiceJob) -> None:
        if job.call_ended:
            await self._deliver(job)
            return
        await asyncio.sleep(self.orphan_grace)
        if not job.picked_up:
            await self._deliver(job)

    async def _deliver(self, job: VoiceJob) -> None:
        if job.picked_up or job.delivered or job.fallback is None:
            return
        job.delivered = True
        try:
            await job.fallback(job.spoken_answer())
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Fallback delivery for voice job {job.job_id} failed: {exc}")

    def _prune(self) -> None:
        cutoff = time.monotonic() - JOB_RETENTION_SECONDS
        for job_id in [j.job_id for j in self._jobs.values() if j.finished and j.finished < cutoff]:
            job = self._jobs.pop(job_id)
            if self._by_conversation.get(job.conversation_id) == job_id:
                del self._by_conversation[job.conversation_id]


voice_jobs = VoiceJobRegistry()
