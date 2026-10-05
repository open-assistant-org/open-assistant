"""Tests for the ElevenLabs voice agent channel."""

import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import elevenlabs as api
from src.core.dependencies import (
    get_elevenlabs_service,
    get_message_handler,
    get_slack_service,
    get_whatsapp_service,
)
from src.services.elevenlabs import (
    ElevenLabsService,
    VoiceJobRegistry,
    to_speech_text,
)

TOOL_SECRET = "tool-secret"
WEBHOOK_SECRET = "wsec"
AUTH = {"Authorization": f"Bearer {TOOL_SECRET}"}


class FakeSettings:
    def __init__(self, **values):
        self.values = {
            "elevenlabs.enabled": True,
            "elevenlabs.tool_secret": TOOL_SECRET,
            "elevenlabs.webhook_secret": WEBHOOK_SECRET,
            "elevenlabs.tool_wait_seconds": 3,
            "elevenlabs.fallback_channel": "none",
            "elevenlabs.new_chat_idle_seconds": 1800,
        }
        self.values.update(values)

    def get(self, key):
        return self.values.get(key)


def make_service(**values) -> ElevenLabsService:
    creds = MagicMock()
    creds.get.return_value = None
    return ElevenLabsService(FakeSettings(**values), creds)


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    registry = VoiceJobRegistry(orphan_grace=0.05)
    monkeypatch.setattr(api, "voice_jobs", registry)
    return registry


@pytest.fixture
def handler():
    h = MagicMock()
    h.handle_message = AsyncMock(
        return_value={"response": "It is **sunny** today.", "conversation_id": "c1"}
    )
    h.ingest_passive_message = AsyncMock(return_value={"conversation_id": "c1"})
    return h


@pytest.fixture
def slack():
    return MagicMock()


@pytest.fixture
def make_client(handler, slack):
    def _make(service=None):
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[get_elevenlabs_service] = lambda: service or make_service()
        app.dependency_overrides[get_message_handler] = lambda: handler
        app.dependency_overrides[get_slack_service] = lambda: slack
        app.dependency_overrides[get_whatsapp_service] = lambda: MagicMock()
        return TestClient(app)

    return _make


def sign(body: bytes, secret=WEBHOOK_SECRET, ts=None) -> str:
    ts = str(ts if ts is not None else int(time.time()))
    digest = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={ts},v0={digest}"


# -- auth ------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": TOOL_SECRET}]
)
def test_tool_rejects_bad_auth(make_client, headers):
    r = make_client().post(
        "/api/elevenlabs/tools/ask_assistant",
        json={"request": "hi", "conversation_id": "x"},
        headers=headers,
    )
    assert r.status_code == 401


def test_tool_rejected_when_secret_not_configured(make_client):
    client = make_client(make_service(**{"elevenlabs.tool_secret": ""}))
    r = client.post(
        "/api/elevenlabs/tools/ask_assistant",
        json={"request": "hi", "conversation_id": "x"},
        headers={"Authorization": "Bearer "},
    )
    assert r.status_code == 401


def test_disabled_channel_returns_503(make_client):
    client = make_client(make_service(**{"elevenlabs.enabled": False}))
    r = client.post(
        "/api/elevenlabs/tools/ask_assistant",
        json={"request": "hi", "conversation_id": "x"},
        headers=AUTH,
    )
    assert r.status_code == 503


# -- ask_assistant ---------------------------------------------------------


def test_ask_assistant_done(make_client, handler):
    r = make_client().post(
        "/api/elevenlabs/tools/ask_assistant",
        json={"request": "weather?", "conversation_id": "conv_1"},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["answer"] == "It is sunny today."
    kwargs = handler.handle_message.await_args.kwargs
    assert kwargs["message"] == "weather?"
    assert kwargs["channel"] == "elevenlabs"
    assert kwargs["contact_identifier"] == "conv_1"
    assert kwargs["max_idle_seconds"] == 1800


def test_ask_assistant_surfaces_pending_question(make_client, handler):
    handler.handle_message.return_value = {
        "response": "Which calendar?",
        "pending_input": {"question": "Which calendar?"},
    }
    r = make_client().post(
        "/api/elevenlabs/tools/ask_assistant",
        json={"request": "book it", "conversation_id": "c"},
        headers=AUTH,
    )
    assert r.json()["question"] == "Which calendar?"


def test_ask_assistant_error_is_spoken_not_500(make_client, handler):
    handler.handle_message.side_effect = RuntimeError("boom")
    r = make_client().post(
        "/api/elevenlabs/tools/ask_assistant",
        json={"request": "x", "conversation_id": "c"},
        headers=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    assert "boom" not in r.json()["answer"]


@pytest.mark.asyncio
async def test_slow_job_returns_working_then_done(handler, slack):
    import httpx

    gate = asyncio.Event()

    async def slow(**_):
        await gate.wait()
        return {"response": "finally"}

    handler.handle_message.side_effect = slow
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_elevenlabs_service] = lambda: make_service(
        **{"elevenlabs.tool_wait_seconds": 0}
    )
    app.dependency_overrides[get_message_handler] = lambda: handler
    app.dependency_overrides[get_slack_service] = lambda: slack
    app.dependency_overrides[get_whatsapp_service] = lambda: MagicMock()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        ask = {"request": "long", "conversation_id": "c"}
        first = (
            await client.post("/api/elevenlabs/tools/ask_assistant", json=ask, headers=AUTH)
        ).json()
        assert first["status"] == "working"
        assert first["job_id"] and "check_assistant_result" in first["note"]

        # a second ask during the run reuses the same job
        again = (
            await client.post("/api/elevenlabs/tools/ask_assistant", json=ask, headers=AUTH)
        ).json()
        assert again["job_id"] == first["job_id"]
        assert handler.handle_message.await_count == 1

        gate.set()
        await asyncio.sleep(0.05)
        done = (
            await client.post(
                "/api/elevenlabs/tools/check_assistant_result",
                json={"job_id": first["job_id"]},
                headers=AUTH,
            )
        ).json()
        assert done == {
            "status": "done",
            "answer": "finally",
            "question": None,
            "job_id": None,
            "note": None,
        }


def test_check_unknown_job(make_client):
    r = make_client().post(
        "/api/elevenlabs/tools/check_assistant_result", json={"job_id": "nope"}, headers=AUTH
    )
    assert r.json()["status"] == "error"


# -- registry (async) ------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_wait_and_collect():
    reg = VoiceJobRegistry(orphan_grace=0.05)

    async def run():
        await asyncio.sleep(0.05)
        return {"response": "ok"}

    job = reg.start("c", run)
    assert not await reg.wait(job, 0.001)
    assert await reg.wait(job, 1)
    assert job.spoken_answer() == "ok"
    assert job.picked_up


@pytest.mark.asyncio
async def test_orphaned_result_is_delivered_to_fallback():
    reg = VoiceJobRegistry(orphan_grace=0.05)
    fallback = AsyncMock()

    async def run():
        return {"response": "Result **ready**"}

    job = reg.start("c", run, fallback=fallback)
    await asyncio.sleep(0.2)
    fallback.assert_awaited_once_with("Result ready")
    assert job.delivered


@pytest.mark.asyncio
async def test_collected_result_is_not_delivered():
    reg = VoiceJobRegistry(orphan_grace=0.05)
    fallback = AsyncMock()

    async def run():
        return {"response": "x"}

    job = reg.start("c", run, fallback=fallback)
    assert await reg.wait(job, 1)
    await asyncio.sleep(0.2)
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_ended_delivers_immediately():
    reg = VoiceJobRegistry(orphan_grace=30)
    fallback = AsyncMock()
    gate = asyncio.Event()

    async def run():
        await gate.wait()
        return {"response": "late"}

    job = reg.start("c", run, fallback=fallback)
    reg.mark_call_ended("c")
    gate.set()
    await asyncio.wait_for(job.done_event.wait(), 1)
    await asyncio.sleep(0.05)
    fallback.assert_awaited_once_with("late")


@pytest.mark.asyncio
async def test_no_fallback_configured_does_not_deliver():
    reg = VoiceJobRegistry(orphan_grace=0.01)

    async def run():
        return {"response": "x"}

    job = reg.start("c", run, fallback=None)
    await asyncio.sleep(0.1)
    assert not job.delivered


def test_fallback_channel_slack_builds_sender(make_client, handler, slack):
    sender = api._build_fallback(
        make_service(**{"elevenlabs.fallback_channel": "slack"}), slack, MagicMock()
    )
    asyncio.run(sender("done"))
    slack.send_message_to_default_channel.assert_called_once()
    assert api._build_fallback(make_service(), slack, MagicMock()) is None


# -- post-call webhook -----------------------------------------------------


def _payload(**data):
    return json.dumps(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": "conv_9",
                "transcript": [
                    {"role": "user", "message": "Remind me to call Sam"},
                    {"role": "agent", "message": "Done."},
                    {"role": "agent", "message": None},
                ],
                **data,
            },
        }
    ).encode()


def test_webhook_ingests_transcript(make_client, handler):
    body = _payload()
    r = make_client().post(
        "/api/elevenlabs/webhooks/post-call",
        content=body,
        headers={"ElevenLabs-Signature": sign(body)},
    )
    assert r.status_code == 200 and r.json()["turns"] == 2
    kwargs = handler.ingest_passive_message.await_args.kwargs
    assert kwargs["channel"] == "elevenlabs"
    assert kwargs["contact_identifier"] == "conv_9"
    assert "[Voice caller]: Remind me to call Sam" in kwargs["message"]
    assert "[Voice agent]: Done." in kwargs["message"]


@pytest.mark.parametrize(
    "header_factory",
    [
        lambda b: None,
        lambda b: "garbage",
        lambda b: sign(b, secret="wrong"),
        lambda b: sign(b, ts=int(time.time()) - 3 * 3600),
    ],
)
def test_webhook_rejects_bad_signature(make_client, handler, header_factory):
    body = _payload()
    headers = {}
    header = header_factory(body)
    if header:
        headers["ElevenLabs-Signature"] = header
    r = make_client().post("/api/elevenlabs/webhooks/post-call", content=body, headers=headers)
    assert r.status_code == 401
    handler.ingest_passive_message.assert_not_awaited()


def test_webhook_ignores_other_event_types(make_client, handler):
    body = json.dumps({"type": "post_call_audio", "data": None}).encode()
    r = make_client().post(
        "/api/elevenlabs/webhooks/post-call",
        content=body,
        headers={"ElevenLabs-Signature": sign(body)},
    )
    assert r.json() == {"ok": True, "ignored": "post_call_audio"}
    handler.ingest_passive_message.assert_not_awaited()


# -- speech text -----------------------------------------------------------


def test_speech_text_strips_markdown_and_urls():
    text = "# Title\n- **one** see [docs](https://x.io/a)\n- two https://example.com/very/long\n```py\nx=1\n```"
    out = to_speech_text(text)
    assert "**" not in out and "#" not in out and "http" not in out and "```" not in out
    assert "one see docs" in out and "a link" in out and "code omitted" in out


def test_speech_text_truncates_long_answers():
    out = to_speech_text("Sentence number one. " * 200, max_chars=100)
    assert len(out) < 200 and out.endswith("like.")


def test_test_connection_states():
    assert make_service(**{"elevenlabs.enabled": False}).test_connection()["status"] == "error"
    assert make_service(**{"elevenlabs.tool_secret": ""}).test_connection()["status"] == "error"
    assert make_service().test_connection()["status"] == "success"
