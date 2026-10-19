"""Tests for unwrapping the nested {"tool_name", "arguments"} envelope in ToolExecutor."""

from unittest.mock import MagicMock

import pytest

from src.core.tools.executor import ToolExecutor


def _make_tool(properties=None) -> MagicMock:
    tool = MagicMock()
    tool.service_name = "system"
    tool.schema.parameters = {"type": "object", "properties": properties or {}}
    return tool


def _make_executor(tool: MagicMock) -> ToolExecutor:
    executor = ToolExecutor()
    executor.registry = MagicMock()
    executor.registry.get.return_value = tool
    executor.services["system"] = MagicMock()
    return executor


class TestUnwrapNestedArguments:
    def test_unwraps_envelope_with_matching_tool_name(self):
        tool = _make_tool({"date": {}, "facts": {}})
        args = {
            "tool_name": "system_index_memory_facts",
            "arguments": {"date": "2026-01-01", "facts": "Some fact."},
        }
        result = ToolExecutor._unwrap_nested_arguments(tool, "system_index_memory_facts", args)
        assert result == {"date": "2026-01-01", "facts": "Some fact."}

    def test_unwraps_envelope_without_tool_name(self):
        tool = _make_tool({"query": {}})
        result = ToolExecutor._unwrap_nested_arguments(
            tool, "search", {"arguments": {"query": "hi"}}
        )
        assert result == {"query": "hi"}

    def test_keeps_envelope_for_different_tool_name(self):
        tool = _make_tool({"query": {}})
        args = {"tool_name": "other_tool", "arguments": {"query": "hi"}}
        assert ToolExecutor._unwrap_nested_arguments(tool, "search", args) is args

    def test_keeps_args_when_tool_declares_arguments_param(self):
        tool = _make_tool({"tool_name": {}, "arguments": {}})
        args = {"tool_name": "schedule_me", "arguments": {"x": 1}}
        assert ToolExecutor._unwrap_nested_arguments(tool, "schedule_me", args) is args

    def test_keeps_args_with_extra_keys(self):
        tool = _make_tool({"query": {}})
        args = {"arguments": {"query": "hi"}, "limit": 5}
        assert ToolExecutor._unwrap_nested_arguments(tool, "search", args) is args

    def test_keeps_flat_args(self):
        tool = _make_tool({"query": {}})
        args = {"query": "hi"}
        assert ToolExecutor._unwrap_nested_arguments(tool, "search", args) is args


class TestExecuteToolUnwrapsEnvelope:
    @pytest.mark.asyncio
    async def test_service_receives_inner_arguments(self):
        executor = _make_executor(_make_tool({"date": {}, "facts": {}}))
        received = {}

        async def fake_route(tool_name, service, arguments):
            received.update(arguments)
            return {"ok": True}

        executor._route_tool_call = fake_route

        result = await executor.execute_tool(
            "system_index_memory_facts",
            {
                "tool_name": "system_index_memory_facts",
                "arguments": {"date": "2026-01-01", "facts": "Some fact."},
            },
        )

        assert result["success"] is True
        assert received == {"date": "2026-01-01", "facts": "Some fact."}
