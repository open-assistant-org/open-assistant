"""Tests for the /cancel slash command.

Covers:
- AsyncTaskDispatcher.cancel_all_for_conversation — cancels asyncio tasks and
  marks records as "cancelled".
- MessageHandler /cancel branch — returns a clean response, records the command
  in the conversation, and cancels running sub-tasks.
- MessageHandler._clear_suspended_state — removes an ask_user suspension so the
  next message is treated as a fresh request.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from src.services.async_task_dispatcher import AsyncTaskDispatcher

# ---------------------------------------------------------------------------
# AsyncTaskDispatcher.cancel_all_for_conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_all_stops_running_tasks():
    """Running sub-tasks for the given conversation are cancelled."""

    started = asyncio.Event()

    async def slow_handler(message, channel="subtask", pinned_skill=None, **kw):
        started.set()
        await asyncio.sleep(10)  # long-running — must be cancelled
        return {"response": "should not reach here", "tools_executed": []}

    d = AsyncTaskDispatcher(slow_handler)
    tid = d.dispatch("long job", conversation_id="conv-1")
    await started.wait()  # ensure the task is actually running

    cancelled = d.cancel_all_for_conversation("conv-1")

    assert cancelled == [tid]
    assert d._tasks[tid].status == "cancelled"
    assert "cancelled" in d._tasks[tid].error.lower()


@pytest.mark.asyncio
async def test_cancel_all_ignores_other_conversations():
    """Sub-tasks from a different conversation must not be affected."""

    started = asyncio.Event()

    async def slow_handler(message, channel="subtask", pinned_skill=None, **kw):
        started.set()
        await asyncio.sleep(10)
        return {"response": "ok", "tools_executed": []}

    d = AsyncTaskDispatcher(slow_handler)
    tid = d.dispatch("other conv task", conversation_id="conv-OTHER")
    await started.wait()

    cancelled = d.cancel_all_for_conversation("conv-MINE")
    assert cancelled == []
    # The unrelated task is still running (or finished on its own)
    assert d._tasks[tid].status in ("running", "completed")


@pytest.mark.asyncio
async def test_cancel_all_skips_already_finished_tasks():
    """Completed or failed tasks are not included in the cancellation list."""

    async def instant_handler(message, channel="subtask", pinned_skill=None, **kw):
        return {"response": "done", "tools_executed": []}

    d = AsyncTaskDispatcher(instant_handler)
    tid = d.dispatch("fast task", conversation_id="conv-1")

    # Wait for the task to finish before calling cancel.
    await asyncio.wait_for(d.wait_for([tid], timeout=2), timeout=5)

    cancelled = d.cancel_all_for_conversation("conv-1")
    assert tid not in cancelled
    assert d._tasks[tid].status == "completed"


@pytest.mark.asyncio
async def test_cancel_all_returns_empty_when_no_tasks():
    """cancel_all_for_conversation returns an empty list when nothing is running."""

    async def handler(message, **kw):
        return {"response": "ok", "tools_executed": []}

    d = AsyncTaskDispatcher(handler)
    result = d.cancel_all_for_conversation("conv-empty")
    assert result == []


# ---------------------------------------------------------------------------
# MessageHandler /cancel command
# ---------------------------------------------------------------------------


def _make_handler():
    """Return a minimal MessageHandler-like object with mocked dependencies."""
    from src.services.message_handler import MessageHandler

    skill_repo = MagicMock()
    skill_repo.get_skills_by_keywords.return_value = []
    skill_repo.get_enabled_skills.return_value = []

    conversation_service = MagicMock()
    conversation_service.create_or_get_conversation.return_value = {"conversation_id": "conv-test"}
    conversation_service.add_message.return_value = {"message_id": "msg-1"}
    conversation_service.message_repo = MagicMock()
    conversation_service.message_repo.get_recent_messages.return_value = []
    conversation_service.conversation_repo = MagicMock()
    conversation_service.conversation_repo.get_by_id.return_value = None

    memory_service = MagicMock()
    memory_service.prompts_repo = MagicMock()
    memory_service.prompts_repo.get_value.return_value = ""

    settings_service = MagicMock()
    settings_service.get_config_with_fallback.return_value = False
    settings_service.settings_repo = MagicMock()

    tool_executor = MagicMock()

    handler = MessageHandler(
        skill_repo=skill_repo,
        conversation_service=conversation_service,
        memory_service=memory_service,
        settings_service=settings_service,
        tool_executor=tool_executor,
    )
    return handler


@pytest.mark.asyncio
async def test_cancel_command_returns_cancelled_flag():
    """/cancel returns a result dict with cancelled=True."""
    handler = _make_handler()

    result = await handler.handle_message(
        message="/cancel",
        conversation_id="conv-test",
        channel="webui",
    )

    assert result["cancelled"] is True
    assert result["conversation_id"] == "conv-test"
    assert result["iterations"] == 0
    assert result["stuck_detected"] is False
    assert "stopped" in result["response"].lower() or "cancelled" in result["response"].lower()


@pytest.mark.asyncio
async def test_cancel_command_stores_messages_in_conversation():
    """/cancel writes both user and assistant messages to the conversation."""
    handler = _make_handler()

    await handler.handle_message(
        message="/cancel",
        conversation_id="conv-test",
        channel="webui",
    )

    calls = handler.conversation_service.add_message.call_args_list
    roles = [c.kwargs.get("role") or c.args[1] for c in calls]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_cancel_command_cancels_running_subtasks():
    """/cancel invokes cancel_all_for_conversation on the dispatcher."""
    handler = _make_handler()
    handler.async_task_dispatcher.cancel_all_for_conversation = MagicMock(return_value=["abc123"])

    result = await handler.handle_message(
        message="/cancel",
        conversation_id="conv-test",
        channel="webui",
    )

    handler.async_task_dispatcher.cancel_all_for_conversation.assert_called_once_with("conv-test")
    assert "abc123" in result["cancelled_tasks"]
    assert "1 background task" in result["response"]


@pytest.mark.asyncio
async def test_cancel_command_no_subtasks_still_works():
    """/cancel works cleanly when no sub-tasks are running."""
    handler = _make_handler()
    handler.async_task_dispatcher.cancel_all_for_conversation = MagicMock(return_value=[])

    result = await handler.handle_message(
        message="/cancel",
        conversation_id="conv-test",
        channel="webui",
    )

    assert result["cancelled"] is True
    assert result["cancelled_tasks"] == []
    # Response should not mention a task count when there were none
    assert "background task" not in result["response"]


@pytest.mark.asyncio
async def test_cancel_command_clears_suspended_state():
    """/cancel calls _clear_suspended_state on the conversation."""
    handler = _make_handler()
    handler._clear_suspended_state = MagicMock(return_value=True)

    await handler.handle_message(
        message="/cancel",
        conversation_id="conv-test",
        channel="webui",
    )

    handler._clear_suspended_state.assert_called_once_with("conv-test")


# ---------------------------------------------------------------------------
# MessageHandler._clear_suspended_state
# ---------------------------------------------------------------------------


def test_clear_suspended_state_marks_message_cancelled():
    """_clear_suspended_state updates the suspended message's metadata."""
    handler = _make_handler()

    suspended_msg = {
        "message_id": "msg-suspended",
        "role": "assistant",
        "content": "What would you like?",
        "metadata": json.dumps({"suspended_state": {"messages": [], "iteration": 1}}),
    }
    handler.conversation_service.message_repo.get_recent_messages.return_value = [suspended_msg]

    cleared = handler._clear_suspended_state("conv-test")

    assert cleared is True
    handler.conversation_service.message_repo.update_metadata.assert_called_once_with(
        "msg-suspended", {"cancelled": True}
    )


def test_clear_suspended_state_returns_false_when_nothing_suspended():
    """_clear_suspended_state returns False when no suspended state is found."""
    handler = _make_handler()
    handler.conversation_service.message_repo.get_recent_messages.return_value = [
        {"message_id": "m1", "role": "assistant", "content": "Hello", "metadata": None}
    ]

    cleared = handler._clear_suspended_state("conv-test")

    assert cleared is False
    handler.conversation_service.message_repo.update_metadata.assert_not_called()


def test_clear_suspended_state_returns_false_on_empty_history():
    """_clear_suspended_state returns False gracefully when history is empty."""
    handler = _make_handler()
    handler.conversation_service.message_repo.get_recent_messages.return_value = []

    cleared = handler._clear_suspended_state("conv-test")

    assert cleared is False
