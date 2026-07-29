"""Tests for duplicate tool-call suppression in ToolExecutor."""

import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tools.executor import ToolExecutor


def _make_executor() -> ToolExecutor:
    """Return a minimal ToolExecutor with a fake registry and a non-None system service."""
    executor = ToolExecutor()
    fake_tool = MagicMock()
    fake_tool.service_name = "system"
    executor.registry = MagicMock()
    executor.registry.get.return_value = fake_tool
    executor.services["system"] = MagicMock()  # avoids "service not available" early-return
    return executor


@pytest.fixture
def executor():
    return _make_executor()


class TestMakeDedupKey:
    def test_same_tool_same_args_same_key(self):
        k1 = ToolExecutor._make_dedup_key("my_tool", {"a": 1, "b": 2})
        k2 = ToolExecutor._make_dedup_key("my_tool", {"b": 2, "a": 1})
        assert k1 == k2, "arg order must not affect the key"

    def test_different_tool_different_key(self):
        k1 = ToolExecutor._make_dedup_key("tool_a", {"x": 1})
        k2 = ToolExecutor._make_dedup_key("tool_b", {"x": 1})
        assert k1 != k2

    def test_different_args_different_key(self):
        k1 = ToolExecutor._make_dedup_key("tool", {"v": 1})
        k2 = ToolExecutor._make_dedup_key("tool", {"v": 2})
        assert k1 != k2

    def test_key_is_short_string(self):
        k = ToolExecutor._make_dedup_key("t", {})
        assert isinstance(k, str) and len(k) == 16


class TestDedupCacheHit:
    @pytest.mark.asyncio
    async def test_second_identical_call_is_blocked(self, executor):
        """Second call within the window returns cached result + note, skips execution."""
        call_count = 0

        async def fake_route(tool_name, service, arguments):
            nonlocal call_count
            call_count += 1
            return {"data": "ok"}

        executor._route_tool_call = fake_route

        args = {"query": "hello"}

        r1 = await executor.execute_tool("search_web", args)
        r2 = await executor.execute_tool("search_web", args)

        assert call_count == 1, "service should only be called once"
        assert r1["success"] is True
        assert r2["success"] is True
        assert "note" in r2, "blocked duplicate must carry a note"
        assert "already executed" in r2["note"]
        assert r2["result"] == r1["result"]

    @pytest.mark.asyncio
    async def test_note_is_absent_on_first_call(self, executor):
        async def fake_route(tool_name, service, arguments):
            return {"data": "ok"}

        executor._route_tool_call = fake_route

        r1 = await executor.execute_tool("search_web", {"q": "hi"})
        assert "note" not in r1

    @pytest.mark.asyncio
    async def test_different_args_not_blocked(self, executor):
        """Same tool with different args must execute both times."""
        call_count = 0

        async def fake_route(tool_name, service, arguments):
            nonlocal call_count
            call_count += 1
            return {"data": arguments.get("q")}

        executor._route_tool_call = fake_route

        await executor.execute_tool("search_web", {"q": "foo"})
        await executor.execute_tool("search_web", {"q": "bar"})

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_different_tools_not_blocked(self, executor):
        """Different tools with same args must both execute."""
        call_count = 0

        async def fake_route(tool_name, service, arguments):
            nonlocal call_count
            call_count += 1
            return {}

        executor._route_tool_call = fake_route

        await executor.execute_tool("tool_a", {"x": 1})
        await executor.execute_tool("tool_b", {"x": 1})

        assert call_count == 2


class TestDedupWindowExpiry:
    @pytest.mark.asyncio
    async def test_call_allowed_after_window_expires(self, executor):
        """After the TTL window, the same call must go through again."""
        call_count = 0

        async def fake_route(tool_name, service, arguments):
            nonlocal call_count
            call_count += 1
            return {}

        executor._route_tool_call = fake_route

        await executor.execute_tool("some_tool", {"k": "v"})
        assert call_count == 1

        # Backdate the cache entry to simulate expiry
        key = ToolExecutor._make_dedup_key("some_tool", {"k": "v"})
        cached_at, cached_result = executor._dedup_cache[key]
        executor._dedup_cache[key] = (cached_at - ToolExecutor._DEDUP_WINDOW - 1, cached_result)

        await executor.execute_tool("some_tool", {"k": "v"})
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_call_blocked_within_window(self, executor):
        """Call just inside the window boundary is still blocked."""
        call_count = 0

        async def fake_route(tool_name, service, arguments):
            nonlocal call_count
            call_count += 1
            return {}

        executor._route_tool_call = fake_route

        await executor.execute_tool("some_tool", {"k": "v"})

        # Backdate to 1s before expiry — should still be blocked
        key = ToolExecutor._make_dedup_key("some_tool", {"k": "v"})
        cached_at, cached_result = executor._dedup_cache[key]
        executor._dedup_cache[key] = (
            cached_at - ToolExecutor._DEDUP_WINDOW + 1,
            cached_result,
        )

        await executor.execute_tool("some_tool", {"k": "v"})
        assert call_count == 1


class TestDedupOnlyForSuccess:
    @pytest.mark.asyncio
    async def test_error_result_not_cached(self, executor):
        """Failed tool calls must not populate the dedup cache."""
        call_count = 0

        async def fake_route(tool_name, service, arguments):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("network error")

        executor._route_tool_call = fake_route
        executor.audit_repo = None

        r1 = await executor.execute_tool("flaky_tool", {"x": 1})
        r2 = await executor.execute_tool("flaky_tool", {"x": 1})

        assert call_count == 2, "errors must not be deduped"
        assert r1["success"] is False
        assert r2["success"] is False
