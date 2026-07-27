"""Tests for AsyncTaskDispatcher fan-out safety and result collection.

These cover the behaviour added to fix sub-tasks appearing to "time out and
die": concurrency capping, fan-out depth limiting, non-cancelling waits, and
re-attachment of finished-but-uncollected results.

The dispatcher only depends on stdlib + src.core.concurrency, so these tests
run without the full app stack.
"""

import asyncio

import pytest

from src.core import concurrency
from src.services.async_task_dispatcher import AsyncTaskDispatcher


@pytest.mark.asyncio
async def test_waited_tasks_complete_and_report_results():
    async def handler(message, channel="subtask", pinned_skill=None):
        await asyncio.sleep(0.01)
        return {"response": f"done:{message}", "tools_executed": ["t"]}

    d = AsyncTaskDispatcher(handler)
    ids = [d.dispatch(f"task-{i}", conversation_id="conv1") for i in range(3)]

    results = await d.wait_for(ids, timeout=5)

    assert len(results) == 3
    assert all(r["status"] == "completed" for r in results.values())
    assert all("done:" in r["result"] for r in results.values())


@pytest.mark.asyncio
async def test_slow_task_reported_running_not_cancelled():
    """A task that outruns the wait window stays 'running' and keeps going."""
    started = asyncio.Event()

    async def slow_handler(message, channel="subtask", pinned_skill=None):
        started.set()
        await asyncio.sleep(0.3)
        return {"response": "late", "tools_executed": []}

    d = AsyncTaskDispatcher(slow_handler)
    tid = d.dispatch("slow", conversation_id="conv1")
    await started.wait()

    # Wait far less than the task takes.
    results = await d.wait_for([tid], timeout=0.05, poll_interval=0.02)
    assert results[tid]["status"] == "running"

    # It was NOT cancelled — it finishes on its own and is then collectable.
    assert d._tasks[tid]._asyncio_task is not None
    await d._tasks[tid]._asyncio_task
    assert d.get_status(tid)["status"] == "completed"


@pytest.mark.asyncio
async def test_concurrency_cap_limits_simultaneous_tasks(monkeypatch):
    """No more than MAX_CONCURRENT_SUBTASKS run at once."""
    # Force a small cap and a fresh semaphore bound to this loop.
    monkeypatch.setattr(concurrency, "MAX_CONCURRENT_SUBTASKS", 2)
    monkeypatch.setattr(concurrency, "_subtask_semaphore", None)

    active = 0
    peak = 0

    async def handler(message, channel="subtask", pinned_skill=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {"response": "ok", "tools_executed": []}

    d = AsyncTaskDispatcher(handler)
    ids = [d.dispatch(f"t{i}", conversation_id="c") for i in range(6)]
    await d.wait_for(ids, timeout=5)

    assert peak <= 2, f"peak concurrency {peak} exceeded cap"


@pytest.mark.asyncio
async def test_fanout_depth_limit(monkeypatch):
    """A sub-task cannot dispatch beyond MAX_SUBTASK_DEPTH."""
    monkeypatch.setattr(concurrency, "MAX_SUBTASK_DEPTH", 1)
    monkeypatch.setattr(concurrency, "_subtask_semaphore", None)

    d = AsyncTaskDispatcher(None)  # handler unused; we call dispatch directly

    # Simulate running inside a depth-1 sub-task: dispatching would create a
    # depth-2 child, which exceeds the max.
    token = concurrency.subtask_depth.set(1)
    try:
        tid = d.dispatch("too deep", conversation_id="c")
    finally:
        concurrency.subtask_depth.reset(token)

    status = d.get_status(tid)
    assert status["status"] == "failed"
    assert "depth" in status["error"].lower()


@pytest.mark.asyncio
async def test_collect_unreported_surfaces_finished_tasks():
    async def handler(message, channel="subtask", pinned_skill=None):
        await asyncio.sleep(0.01)
        return {"response": "res", "tools_executed": []}

    d = AsyncTaskDispatcher(handler)
    tid = d.dispatch("bg", conversation_id="conv-x")
    await d._tasks[tid]._asyncio_task  # let it finish without a wait_for call

    unreported = d.collect_unreported("conv-x")
    assert len(unreported) == 1
    assert unreported[0]["task_id"] == tid

    # Only surfaced once.
    assert d.collect_unreported("conv-x") == []
    # Different conversation sees nothing.
    assert d.collect_unreported("other") == []
