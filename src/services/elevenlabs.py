"""ElevenLabs voice agent channel.

The voice agent (a fast LLM running inside ElevenLabs) hands real work to the
assistant through server tools. This module holds the pieces that make that
safe and usable for voice: secret handling, request signature verification,
speech-friendly text, and a small in-memory job registry so a request that
outlasts a tool timeout can be collected on a follow-up call (or delivered to
Slack/WhatsApp if the caller already hung up).

The job registry is process-local, which matches the single-process
deployment (one uvicorn worker under supervisord).
"""

import asyncio
import hashlib
import hmac
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)

CHANNEL = "elevenlabs"
WEBHOOK_TOLERANCE_SECONDS = 30 * 60
ORPHAN_GRACE_SECONDS = 60
JOB_RETENTION_SECONDS = 15 * 60
MAX_SPOKEN_CHARS = 1200


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

    # -- verification -------------------------------------------------------

    def verify_bearer(self, authorization: Optional[str]) -> bool:
        """Constant-time check of ``Authorization: Bearer <tool_secret>``."""
        secret = self._get_sensitive_setting("elevenlabs.tool_secret")
        if not secret or not authorization:
            return False
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return False
        return hmac.compare_digest(token.strip().encode(), secret.encode())

    def verify_webhook_signature(
        self, header: Optional[str], body: bytes, now: Optional[float] = None
    ) -> bool:
        """Verify ``ElevenLabs-Signature: t=<ts>,v0=<hmac_sha256(ts.body)>``."""
        secret = self._get_sensitive_setting("elevenlabs.webhook_secret")
        if not secret or not header:
            return False
        parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
        timestamp, signature = parts.get("t"), parts.get("v0")
        if not timestamp or not signature or not timestamp.isdigit():
            return False
        if (
            abs((now if now is not None else time.time()) - int(timestamp))
            > WEBHOOK_TOLERANCE_SECONDS
        ):
            return False
        expected = hmac.new(
            secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def test_connection(self) -> Dict[str, Any]:
        if not self.is_enabled():
            return {
                "service_name": CHANNEL,
                "status": "error",
                "message": "ElevenLabs voice agent is not enabled",
            }
        missing = [
            name
            for name in ("tool_secret", "webhook_secret")
            if not self._get_sensitive_setting(f"elevenlabs.{name}")
        ]
        if "tool_secret" in missing:
            return {
                "service_name": CHANNEL,
                "status": "error",
                "message": "Tool secret not configured. Set 'elevenlabs.tool_secret'.",
            }
        note = (
            " (post-call webhook secret not set; transcripts will be rejected)" if missing else ""
        )
        return {
            "service_name": CHANNEL,
            "status": "success",
            "message": "Voice tools are ready to be called by ElevenLabs" + note,
        }


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
