"""Tests for the create_html tool: non-blocking generation, context_path, progress, timeout."""

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.tool_events import bind_emitter
from src.services.document import create_html


class _FakeSettings:
    def __init__(self, **overrides):
        self._overrides = overrides

    def get_config_with_fallback(self, key, default=None):
        return self._overrides.get(key, default)


class _FakeConfig:
    def get_worker_model(self):
        return "worker-model"


def _response(text, finish_reason="stop"):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)])


class _FakeLLM:
    def __init__(self, replies, delay=0.0):
        self.replies = list(replies)
        self.delay = delay
        self.calls = []

    def stream_completion(self, messages, on_text, max_tokens=None, model_override=None, **kw):
        self.calls.append({"messages": [dict(m) for m in messages], "model": model_override})
        if self.delay:
            time.sleep(self.delay)  # blocking on purpose: must not freeze the event loop
        text, reason = self.replies.pop(0)
        on_text(text)
        return _response(text, reason)


def _install(monkeypatch, tmp_path, llm):
    monkeypatch.setenv("TMP_DIR", str(tmp_path))
    monkeypatch.setattr("src.core.llm_client.LLMClient", lambda cfg: llm)
    monkeypatch.setattr(
        "src.core.llm_client.LLMConfig.from_settings", lambda ss, **kw: _FakeConfig()
    )


@pytest.mark.asyncio
async def test_strips_fences_joins_continuations_uses_worker_model(tmp_path, monkeypatch):
    llm = _FakeLLM([("```html\n<!DOCTYPE html><html>", "length"), ("</html>\n```", "stop")])
    _install(monkeypatch, tmp_path, llm)

    result = await create_html("a page", "page", settings_service=_FakeSettings())

    html = Path(result["filepath"]).read_text(encoding="utf-8")
    assert html == "<!DOCTYPE html><html></html>"
    assert result["filename"] == "page.html"
    assert [c["model"] for c in llm.calls] == ["worker-model", "worker-model"]
    assert llm.calls[1]["messages"][-1]["content"].startswith("Continue")


@pytest.mark.asyncio
async def test_context_path_embedded_and_outside_tmp_rejected(tmp_path, monkeypatch):
    llm = _FakeLLM([("<!DOCTYPE html>", "stop")])
    _install(monkeypatch, tmp_path, llm)
    data = tmp_path / "rows.json"
    data.write_text('[{"a": 1}]')

    await create_html("chart", "c", context_path=str(data), settings_service=_FakeSettings())
    assert '[{"a": 1}]' in llm.calls[0]["messages"][1]["content"]

    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret")
    result = await create_html(
        "chart", "c2", context_path=str(outside), settings_service=_FakeSettings()
    )
    assert result["success"] is False
    assert len(llm.calls) == 1  # no LLM call for the rejected path


@pytest.mark.asyncio
async def test_does_not_block_event_loop_and_emits_progress(tmp_path, monkeypatch):
    llm = _FakeLLM([("<!DOCTYPE html>", "stop")], delay=0.4)
    _install(monkeypatch, tmp_path, llm)

    events = []

    async def emit(event):
        events.append(event)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    task = asyncio.create_task(ticker())
    with bind_emitter(emit):
        await create_html("page", "p", settings_service=_FakeSettings())
    task.cancel()

    assert ticks >= 10  # loop kept running during the 0.4s blocking LLM call
    assert any(e["type"] == "tool_progress" and e["tool"] == "create_html" for e in events)


@pytest.mark.asyncio
async def test_timeout_returns_error(tmp_path, monkeypatch):
    llm = _FakeLLM([("<!DOCTYPE html>", "stop")], delay=1.5)
    _install(monkeypatch, tmp_path, llm)

    # Settings minimum is enforced by config; the function itself takes any int.
    result = await create_html(
        "page", "p", settings_service=_FakeSettings(**{"llm.create_html_timeout_seconds": 0.2})
    )
    assert result["success"] is False
    assert "timed out" in result["error"]
