"""Tests for the ElevenLabs voice channel (outbound-only Talk page)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
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
from src.services import elevenlabs as el
from src.services.elevenlabs import (
    ElevenLabsService,
    VoiceJobRegistry,
    to_speech_text,
    transcript_lines,
)

API_KEY = "sk_test_key"
AGENT_ID = "agent_123"
REAL_ASYNC_CLIENT = httpx.AsyncClient


class FakeSettings:
    def __init__(self, **values):
        self.values = {
            "elevenlabs.enabled": True,
            "elevenlabs.api_key": API_KEY,
            "elevenlabs.agent_id": AGENT_ID,
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


def mock_elevenlabs(monkeypatch, handler):
    """Route the service's outbound httpx calls to ``handler`` (a MockTransport callback)."""
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    monkeypatch.setattr(
        el.httpx,
        "AsyncClient",
        lambda **kw: REAL_ASYNC_CLIENT(**{**kw, "transport": httpx.MockTransport(respond)}),
    )
    return requests


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    registry = VoiceJobRegistry(orphan_grace=0.05)
    monkeypatch.setattr(api, "voice_jobs", registry)
    api._ended_calls.clear()
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
def make_app(handler, slack):
    def _make(service=None) -> FastAPI:
        whatsapp = MagicMock()
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[get_elevenlabs_service] = lambda: service or make_service()
        app.dependency_overrides[get_message_handler] = lambda: handler
        app.dependency_overrides[get_slack_service] = lambda: slack
        app.dependency_overrides[get_whatsapp_service] = lambda: whatsapp
        return app

    return _make


@pytest.fixture
def make_client(make_app):
    return lambda service=None: TestClient(make_app(service))


def async_client(app: FastAPI) -> httpx.AsyncClient:
    return REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=app), base_url="http://t")


# -- status / enablement ---------------------------------------------------


def test_status_reports_enabled_and_configured(make_client):
    r = make_client().get("/api/elevenlabs/status")
    assert r.json() == {"enabled": True, "configured": True}


def test_status_when_disabled_or_unconfigured(make_client):
    off = make_client(make_service(**{"elevenlabs.enabled": False})).get("/api/elevenlabs/status")
    assert off.json() == {"enabled": False, "configured": True}
    no_agent = make_client(make_service(**{"elevenlabs.agent_id": ""})).get(
        "/api/elevenlabs/status"
    )
    assert no_agent.json() == {"enabled": True, "configured": False}


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/elevenlabs/session", {}),
        ("post", "/api/elevenlabs/voice/ask", {"request": "hi", "conversation_id": "x"}),
        ("post", "/api/elevenlabs/voice/result", {"job_id": "j"}),
        ("post", "/api/elevenlabs/voice/end", {"conversation_id": "x"}),
    ],
)
def test_endpoints_return_503_when_disabled(make_client, method, path, body):
    client = make_client(make_service(**{"elevenlabs.enabled": False}))
    assert getattr(client, method)(path, json=body).status_code == 503


# -- session (outbound signed URL) -----------------------------------------


def test_session_returns_signed_url_and_never_the_key(make_client, monkeypatch):
    requests = mock_elevenlabs(
        monkeypatch, lambda req: httpx.Response(200, json={"signed_url": "wss://x/convai?token=t"})
    )
    r = make_client().post("/api/elevenlabs/session", json={})
    assert r.status_code == 200
    assert r.json() == {"signed_url": "wss://x/convai?token=t"}
    assert API_KEY not in r.text
    req = requests[0]
    assert req.headers["xi-api-key"] == API_KEY
    assert req.url.path == "/v1/convai/conversation/get-signed-url"
    assert req.url.params["agent_id"] == AGENT_ID


def test_session_maps_elevenlabs_rejection_without_leaking_key(make_client, monkeypatch):
    mock_elevenlabs(monkeypatch, lambda req: httpx.Response(401, json={"detail": "bad key"}))
    r = make_client().post("/api/elevenlabs/session", json={})
    assert r.status_code == 502
    assert "rejected the API key" in r.json()["detail"]
    assert API_KEY not in r.text


def test_session_requires_agent_id_and_key(make_client):
    r = make_client(make_service(**{"elevenlabs.agent_id": ""})).post(
        "/api/elevenlabs/session", json={}
    )
    assert r.status_code == 502 and "agent ID" in r.json()["detail"]
    r = make_client(make_service(**{"elevenlabs.api_key": ""})).post(
        "/api/elevenlabs/session", json={}
    )
    assert r.status_code == 502 and "API key" in r.json()["detail"]


def test_session_handles_network_failure(make_client, monkeypatch):
    def boom(req):
        raise httpx.ConnectError("no route")

    mock_elevenlabs(monkeypatch, boom)
    r = make_client().post("/api/elevenlabs/session", json={})
    assert r.status_code == 502 and "Could not reach ElevenLabs" in r.json()["detail"]


# -- ask_assistant ---------------------------------------------------------


def test_ask_assistant_done(make_client, handler):
    r = make_client().post(
        "/api/elevenlabs/voice/ask",
        json={"request": "weather?", "conversation_id": "conv_1"},
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
        "/api/elevenlabs/voice/ask",
        json={"request": "book it", "conversation_id": "c"},
    )
    assert r.json()["question"] == "Which calendar?"


def test_ask_assistant_error_is_spoken_not_500(make_client, handler):
    handler.handle_message.side_effect = RuntimeError("boom")
    r = make_client().post(
        "/api/elevenlabs/voice/ask",
        json={"request": "x", "conversation_id": "c"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    assert "boom" not in r.json()["answer"]


@pytest.mark.asyncio
async def test_slow_job_returns_working_then_done(handler, slack):
    gate = asyncio.Event()

    async def slow(**_):
        await gate.wait()
        return {"response": "finally"}

    handler.handle_message.side_effect = slow
    whatsapp = MagicMock()
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_elevenlabs_service] = lambda: make_service(
        **{"elevenlabs.tool_wait_seconds": 0}
    )
    app.dependency_overrides[get_message_handler] = lambda: handler
    app.dependency_overrides[get_slack_service] = lambda: slack
    app.dependency_overrides[get_whatsapp_service] = lambda: whatsapp

    async with async_client(app) as client:
        ask = {"request": "long", "conversation_id": "c"}
        first = (await client.post("/api/elevenlabs/voice/ask", json=ask)).json()
        assert first["status"] == "working"
        assert first["job_id"] and "check_assistant_result" in first["note"]

        # a second ask during the run reuses the same job
        again = (await client.post("/api/elevenlabs/voice/ask", json=ask)).json()
        assert again["job_id"] == first["job_id"]
        assert handler.handle_message.await_count == 1

        gate.set()
        await asyncio.sleep(0.05)
        done = (
            await client.post(
                "/api/elevenlabs/voice/result",
                json={"job_id": first["job_id"]},
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
    r = make_client().post("/api/elevenlabs/voice/result", json={"job_id": "nope"})
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


# -- end of call: transcript ingestion -------------------------------------

TURNS = [
    {"role": "user", "message": "Remind me to call Sam"},
    {"role": "agent", "message": "Done."},
    {"role": "agent", "message": None},
]


def test_transcript_lines_label_speakers_and_skip_empty():
    assert transcript_lines(TURNS) == [
        "[Voice caller]: Remind me to call Sam",
        "[Voice agent]: Done.",
    ]


@pytest.mark.asyncio
async def test_ingest_transcript_waits_until_done(handler, monkeypatch):
    states = iter(["processing", "processing", "done"])

    def respond(req):
        return httpx.Response(200, json={"status": next(states), "transcript": TURNS})

    requests = mock_elevenlabs(monkeypatch, respond)
    stored = await make_service().ingest_transcript(handler, "conv_9", poll_seconds=0.01)

    assert stored == 2 and len(requests) == 3
    assert requests[0].url.path == "/v1/convai/conversations/conv_9"
    assert requests[0].headers["xi-api-key"] == API_KEY
    kwargs = handler.ingest_passive_message.await_args.kwargs
    assert kwargs["channel"] == "elevenlabs"
    assert kwargs["contact_identifier"] == "conv_9"
    assert "[Voice caller]: Remind me to call Sam" in kwargs["message"]
    assert "[Voice agent]: Done." in kwargs["message"]


@pytest.mark.asyncio
async def test_ingest_transcript_gives_up_after_max_wait(handler, monkeypatch):
    mock_elevenlabs(
        monkeypatch,
        lambda req: httpx.Response(200, json={"status": "processing", "transcript": TURNS}),
    )
    stored = await make_service().ingest_transcript(
        handler, "conv_9", poll_seconds=0.01, max_wait_seconds=0.03
    )
    assert stored == 2  # stores what it has rather than losing the call


@pytest.mark.asyncio
async def test_ingest_transcript_survives_elevenlabs_errors(handler, monkeypatch):
    mock_elevenlabs(monkeypatch, lambda req: httpx.Response(500))
    assert await make_service().ingest_transcript(handler, "conv_9", poll_seconds=0.01) == 0
    handler.ingest_passive_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingest_transcript_skips_empty_call(handler, monkeypatch):
    mock_elevenlabs(
        monkeypatch, lambda req: httpx.Response(200, json={"status": "done", "transcript": []})
    )
    assert await make_service().ingest_transcript(handler, "c", poll_seconds=0.01) == 0
    handler.ingest_passive_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_conversation_quotes_the_id(monkeypatch):
    requests = mock_elevenlabs(monkeypatch, lambda req: httpx.Response(200, json={}))
    await make_service().fetch_conversation("a/b?c")
    assert "/" not in requests[0].url.raw_path.decode().split("conversations/")[1]


@pytest.mark.asyncio
async def test_end_call_flushes_jobs_and_ingests_once(make_app, handler, monkeypatch, _fresh_state):
    mock_elevenlabs(
        monkeypatch, lambda req: httpx.Response(200, json={"status": "done", "transcript": TURNS})
    )
    fallback = AsyncMock()
    gate = asyncio.Event()

    async def run():
        await gate.wait()
        return {"response": "late"}

    job = _fresh_state.start("conv_9", run, fallback=fallback)

    async with async_client(make_app()) as client:
        body = {"conversation_id": "conv_9"}
        first = await client.post("/api/elevenlabs/voice/end", json=body)
        second = await client.post("/api/elevenlabs/voice/end", json=body)
        assert first.json() == {"ok": True}
        assert second.json() == {"ok": True, "duplicate": True}

        gate.set()
        await asyncio.wait_for(job.done_event.wait(), 1)
        await asyncio.sleep(0.1)

    fallback.assert_awaited_once_with("late")
    assert handler.ingest_passive_message.await_count == 1


@pytest.mark.parametrize("bad_id", ["../etc", "a/b", "x" * 200, "", "has space"])
def test_end_call_rejects_malformed_conversation_ids(make_client, bad_id):
    r = make_client().post("/api/elevenlabs/voice/end", json={"conversation_id": bad_id})
    assert r.status_code == 422


# -- speech text -----------------------------------------------------------


def test_speech_text_strips_markdown_and_urls():
    text = "# Title\n- **one** see [docs](https://x.io/a)\n- two https://example.com/very/long\n```py\nx=1\n```"
    out = to_speech_text(text)
    assert "**" not in out and "#" not in out and "http" not in out and "```" not in out
    assert "one see docs" in out and "a link" in out and "code omitted" in out


def test_speech_text_truncates_long_answers():
    out = to_speech_text("Sentence number one. " * 200, max_chars=100)
    assert len(out) < 200 and out.endswith("like.")


@pytest.mark.asyncio
async def test_test_connection_states(monkeypatch):
    off = await make_service(**{"elevenlabs.enabled": False}).test_connection()
    assert off["status"] == "error" and "not enabled" in off["message"]
    no_key = await make_service(**{"elevenlabs.api_key": ""}).test_connection()
    assert no_key["status"] == "error" and "API key" in no_key["message"]
    no_agent = await make_service(**{"elevenlabs.agent_id": ""}).test_connection()
    assert no_agent["status"] == "error" and "Agent ID" in no_agent["message"]

    mock_elevenlabs(monkeypatch, lambda req: httpx.Response(200, json={"name": "Voice Helper"}))
    ok = await make_service().test_connection()
    assert ok == {
        "service_name": "elevenlabs",
        "status": "success",
        "message": "Connected to agent 'Voice Helper'",
    }

    mock_elevenlabs(monkeypatch, lambda req: httpx.Response(404))
    missing = await make_service().test_connection()
    assert missing["status"] == "error" and "could not find" in missing["message"]
