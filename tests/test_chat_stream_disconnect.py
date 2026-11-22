"""A chat turn started from /api/chat/stream outlives the connection that started it.

When a client drops mid-run (a phone that locks or loses signal) the turn must still
finish and save its reply; ``/cancel`` is how a person stops it on purpose.
"""

import asyncio

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


@pytest.mark.asyncio
async def test_turn_finishes_and_saves_after_client_disconnects():
    handler = _SlowHandler()
    frames = await _open_stream(handler)
    first = asyncio.create_task(frames.__anext__())
    await handler.started.wait()

    # The client goes away mid-run: the connection closes the stream
    first.cancel()
    await frames.aclose()

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
    first.cancel()
    await frames.aclose()

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


class _ToolHandler(_SlowHandler):
    async def handle_message(self, **kwargs):
        await kwargs["event_callback"]({"type": "tool_call", "tool": "web_search"})
        return await super().handle_message(**kwargs)


@pytest.mark.asyncio
async def test_run_endpoint_lets_a_client_catch_up_after_losing_the_stream():
    from src.api.chat import chat_run

    handler = _ToolHandler()
    frames = await _open_stream(handler, "conv-4")
    first = asyncio.create_task(frames.__anext__())
    await handler.started.wait()
    first.cancel()
    await frames.aclose()

    mid = await chat_run("conv-4", after=0)
    assert mid["running"] is True
    assert [e["type"] for e in mid["events"]] == ["tool_call"]

    handler.release.set()
    for _ in range(50):
        done = await chat_run("conv-4", after=mid["next"])
        if not done["running"]:
            break
        await asyncio.sleep(0.01)
    assert done["running"] is False
    assert [e["type"] for e in done["events"]] == ["complete"]
    assert done["events"][0]["response"] == "reply"
    assert done["next"] == 2


@pytest.mark.asyncio
async def test_run_endpoint_for_an_unknown_conversation():
    from src.api.chat import chat_run

    assert await chat_run("never-ran") == {"running": False, "events": [], "next": 0}
