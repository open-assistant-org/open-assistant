"""A chat turn started from /api/chat/stream outlives the connection that started it.

When a client drops mid-run (a phone that locks or loses signal) the turn must still
finish and save its reply; ``/cancel`` is how a person stops it on purpose.
"""

import asyncio
from contextlib import suppress

import pytest

from src.api.chat import chat_stream
from src.models.conversation import ChatRequest
from src.services import running_turns


class _Settings:
    def get_config_with_fallback(self, key, default=None):
        return {"llm.api_key": "test-key", "llm.paused": False}.get(key, default)


class _SlowHandler:
    """Saves its reply only once released, like the real handler does at the end of a turn."""

    def __init__(self):
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.saved: list[str] = []

    async def handle_message(self, **kwargs):
        self.started.set()
        await self.release.wait()
        self.saved.append("reply")
        return {
            "response": "reply",
            "conversation_id": kwargs["conversation_id"],
            "skills_used": [],
            "tools_executed": [],
            "iterations": 1,
            "stuck_detected": False,
        }


async def _open_stream(handler, conversation_id="conv-1"):
    request = ChatRequest(message="hi", conversation_id=conversation_id)
    response = await chat_stream(request, handler, _Settings())
    return response.body_iterator


async def _drop(frames, first):
    """The client goes away mid-run: the connection closes the stream."""
    first.cancel()
    with suppress(asyncio.CancelledError):
        await first
    await frames.aclose()


@pytest.mark.asyncio
async def test_turn_finishes_and_saves_after_client_disconnects():
    handler = _SlowHandler()
    frames = await _open_stream(handler)
    first = asyncio.create_task(frames.__anext__())
    await handler.started.wait()

    await _drop(frames, first)

    handler.release.set()
    for _ in range(50):
        if handler.saved:
            break
        await asyncio.sleep(0.01)
    assert handler.saved == ["reply"]


@pytest.mark.asyncio
async def test_cancel_stops_a_turn_that_lost_its_client():
    handler = _SlowHandler()
    frames = await _open_stream(handler, "conv-2")
    first = asyncio.create_task(frames.__anext__())
    await handler.started.wait()
    await _drop(frames, first)

    assert running_turns.cancel("conv-2") is True
    handler.release.set()
    await asyncio.sleep(0.05)
    assert handler.saved == []


@pytest.mark.asyncio
async def test_cancel_ends_a_stream_that_is_still_attached():
    handler = _SlowHandler()
    frames = await _open_stream(handler, "conv-3")
    pending = asyncio.create_task(frames.__anext__())
    await handler.started.wait()

    assert running_turns.cancel("conv-3") is True
    frame = await asyncio.wait_for(pending, timeout=2)
    assert '"type": "error"' in frame
    assert handler.saved == []


def test_cancel_with_nothing_running():
    assert running_turns.cancel("nobody") is False


@pytest.mark.asyncio
async def test_progress_reports_a_turn_that_lost_its_client():
    from src.api.chat import chat_progress

    class _Audit:
        def get_tool_actions(self, conversation_id, after_id=0, turn_id=None):
            return [{"id": 7, "tool": "web_search"}]

    handler = _SlowHandler()
    frames = await _open_stream(handler, "conv-4")
    first = asyncio.create_task(frames.__anext__())
    await handler.started.wait()
    await _drop(frames, first)

    during = await chat_progress("conv-4", after_id=3, audit_repo=_Audit())
    assert during == {"running": True, "actions": [{"id": 7, "tool": "web_search"}], "next_id": 7}

    handler.release.set()
    for _ in range(50):
        if not running_turns.is_running("conv-4"):
            break
        await asyncio.sleep(0.01)
    assert (await chat_progress("conv-4", audit_repo=_Audit()))["running"] is False


@pytest.mark.asyncio
async def test_progress_for_a_conversation_with_nothing_running():
    from src.api.chat import chat_progress

    class _Audit:
        def get_tool_actions(self, conversation_id, after_id=0, turn_id=None):
            return []

    assert await chat_progress("never-ran", after_id=5, audit_repo=_Audit()) == {
        "running": False,
        "actions": [],
        "next_id": 5,
    }
