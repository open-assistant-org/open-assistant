"""Synchronous tools run off the event loop, and their audit rows say which turn they belong to."""

import asyncio
import time

import pytest

from src.core.repositories.audit import AuditLogRepository
from src.core.tools.executor import ToolExecutor
from src.core.turn_context import bind_turn


class _SlowService:
    def slow(self, seconds):
        time.sleep(seconds)
        return {"done": True}


class _Cron:
    pass


_Cron.__name__ = "CronJobService"


def _executor():
    return ToolExecutor.__new__(ToolExecutor)


@pytest.mark.asyncio
async def test_a_blocking_tool_does_not_freeze_the_event_loop():
    executor = _executor()
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    result = await executor._offload(_SlowService().slow, 0.3)
    task.cancel()
    assert result == {"done": True}
    # Run on the loop, the 0.3 s sleep would have allowed no ticks at all
    assert ticks >= 10


@pytest.mark.asyncio
async def test_calls_into_one_service_do_not_overlap():
    executor = _executor()
    running = 0
    peak = 0

    class Svc:
        def work(self):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            time.sleep(0.05)
            running -= 1

    svc = Svc()
    await asyncio.gather(*(executor._offload(svc.work) for _ in range(4)))
    assert peak == 1


@pytest.mark.asyncio
async def test_async_tools_are_awaited_where_they_are():
    executor = _executor()

    class Svc:
        async def browse(self):
            return "page"

    assert await executor._offload(Svc().browse) == "page"


@pytest.mark.asyncio
async def test_scheduler_services_stay_on_the_event_loop():
    import threading

    executor = _executor()

    class CronJobService:
        def create(self):
            return threading.current_thread() is threading.main_thread()

    assert await executor._offload(CronJobService().create) is True


class _Audit:
    def __init__(self):
        self.rows = []

    def log_event(self, **row):
        self.rows.append(row)


def test_audit_rows_carry_the_conversation_and_turn():
    executor = _executor()
    executor.audit_repo = _Audit()
    executor.conversation_id = None
    executor._sanitize_arguments = lambda a: a
    executor._create_result_summary = lambda r: "ok"

    bind_turn("conv-9", "msg-42")
    executor._log_tool_execution("web_search", "brave", {"q": "x"}, {}, True)

    row = executor.audit_repo.rows[0]
    assert row["conversation_id"] == "conv-9"
    assert row["details"]["turn_id"] == "msg-42"


def test_get_tool_actions_returns_new_rows_of_one_turn_oldest_first(clean_temp_db):
    repo = AuditLogRepository(clean_temp_db)
    for turn, tool in [("a", "t1"), ("a", "t2"), ("b", "t3")]:
        repo.log_event(
            event_type="tool_execution",
            conversation_id="c",
            action=tool,
            success=True,
            details={"turn_id": turn, "arguments": {}, "result_summary": tool},
        )
    repo.log_event(event_type="api_call", conversation_id="c", action="noise", success=True)

    everything = repo.get_tool_actions("c")
    assert [a["tool"] for a in everything] == ["t1", "t2", "t3"]
    assert [a["tool"] for a in repo.get_tool_actions("c", turn_id="a")] == ["t1", "t2"]
    assert [a["tool"] for a in repo.get_tool_actions("c", after_id=everything[1]["id"])] == ["t3"]
    # The newest rows, still oldest first, for showing the end of a long history
    assert [a["tool"] for a in repo.get_tool_actions("c", limit=2, tail=True)] == ["t2", "t3"]
