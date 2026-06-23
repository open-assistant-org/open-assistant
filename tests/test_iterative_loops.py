"""Tests for iterative loop support: batch_tool, planner iteration detection, stuck detection."""

import json
from collections import Counter, deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.planner import PlanStep, PlanTracker, Planner

# ---------------------------------------------------------------------------
# PlanStep / PlanTracker – iterative step parsing
# ---------------------------------------------------------------------------


class TestPlanTrackerIterativeParsing:
    """Test that PlanTracker correctly identifies iterative steps."""

    def test_repeat_marker_detected(self):
        plan_text = (
            "1. Search for emails matching the query\n"
            "2. List available Gmail labels\n"
            "3. [repeat] Apply label to each email using google_modify_labels\n"
        )
        tracker = PlanTracker.from_llm_output(plan_text)
        assert tracker.total == 3
        assert tracker.steps[0].requires_iteration is False
        assert tracker.steps[1].requires_iteration is False
        assert tracker.steps[2].requires_iteration is True
        # The marker should be stripped from the description
        assert "[repeat]" not in tracker.steps[2].description

    def test_for_each_language_detected(self):
        plan_text = "1. List all emails\n" "2. For each email, apply the Work label\n"
        tracker = PlanTracker.from_llm_output(plan_text)
        assert tracker.steps[1].requires_iteration is True

    def test_for_every_language_detected(self):
        plan_text = "1. Trash messages for every matched email\n"
        tracker = PlanTracker.from_llm_output(plan_text)
        assert tracker.steps[0].requires_iteration is True

    def test_for_all_language_detected(self):
        plan_text = "1. Move files for all items in the list\n"
        tracker = PlanTracker.from_llm_output(plan_text)
        assert tracker.steps[0].requires_iteration is True

    def test_each_of_the_detected(self):
        plan_text = "1. Label each of the found emails\n"
        tracker = PlanTracker.from_llm_output(plan_text)
        assert tracker.steps[0].requires_iteration is True

    def test_plain_step_not_iterative(self):
        plan_text = "1. Search emails\n2. Get labels\n"
        tracker = PlanTracker.from_llm_output(plan_text)
        assert all(not s.requires_iteration for s in tracker.steps)

    def test_has_iterative_steps_property(self):
        tracker = PlanTracker(
            steps=[
                PlanStep(number=1, description="search"),
                PlanStep(number=2, description="label each", requires_iteration=True),
            ]
        )
        assert tracker.has_iterative_steps is True

    def test_has_iterative_steps_false(self):
        tracker = PlanTracker(steps=[PlanStep(number=1, description="search")])
        assert tracker.has_iterative_steps is False


# ---------------------------------------------------------------------------
# PlanTracker – advance / complete_current for iterative steps
# ---------------------------------------------------------------------------


class TestPlanTrackerIterativeAdvance:
    """Test that advance() does not skip iterative steps."""

    def _make_tracker(self):
        return PlanTracker(
            steps=[
                PlanStep(number=1, description="list emails"),
                PlanStep(number=2, description="label each email", requires_iteration=True),
                PlanStep(number=3, description="summarise results"),
            ]
        )

    def test_advance_skips_iterative_step(self):
        tracker = self._make_tracker()
        tracker.start()  # step 1 → in_progress
        assert tracker.current_step.number == 1

        # Advance past step 1 (non-iterative) → should move to step 2
        advanced = tracker.advance()
        assert advanced.number == 2
        assert tracker.steps[0].status == "completed"
        assert tracker.steps[1].status == "in_progress"

        # Advance again — step 2 is iterative, should NOT auto-complete
        still_current = tracker.advance()
        assert still_current.number == 2  # still on step 2
        assert tracker.steps[1].status == "in_progress"

    def test_complete_current_forces_advance(self):
        tracker = self._make_tracker()
        tracker.start()
        tracker.advance()  # step 1 done, step 2 in_progress

        # Force-complete the iterative step
        nxt = tracker.complete_current()
        assert tracker.steps[1].status == "completed"
        assert nxt.number == 3
        assert nxt.status == "in_progress"

    def test_complete_current_on_last_step(self):
        tracker = self._make_tracker()
        tracker.start()
        tracker.advance()  # step 1 done → step 2
        tracker.complete_current()  # step 2 done → step 3
        result = tracker.complete_current()  # step 3 done → None
        assert result is None
        assert all(s.status == "completed" for s in tracker.steps)


# ---------------------------------------------------------------------------
# Stuck detection (MessageHandler._is_stuck)
# ---------------------------------------------------------------------------


class TestStuckDetection:
    """Test the improved stuck detection that distinguishes iteration from loops.

    We replicate the _is_stuck logic inline to avoid importing MessageHandler
    (which pulls the full dependency tree).  The logic is identical to
    MessageHandler._is_stuck — if you change that method, update here too.
    """

    @staticmethod
    def _is_stuck(tool_call_history: deque) -> bool:
        """Mirror of MessageHandler._is_stuck for isolated testing."""
        if len(tool_call_history) < 3:
            return False
        history = list(tool_call_history)
        if len(history) >= 3:
            last_three = history[-3:]
            if len(set(last_three)) == 1:
                return True
        if len(history) >= 7:
            call_counts = Counter(history[-10:])
            most_common_call, count = call_counts.most_common(1)[0]
            if count >= 5:
                return True
        return False

    def test_not_stuck_with_few_calls(self):
        history = deque(maxlen=10)
        history.append(("google_modify_labels", '{"message_id":"1"}'))
        history.append(("google_modify_labels", '{"message_id":"2"}'))
        assert self._is_stuck(history) is False

    def test_stuck_on_consecutive_identical_calls(self):
        history = deque(maxlen=10)
        call = ("google_modify_labels", '{"message_id":"1","add_labels":["X"]}')
        history.append(call)
        history.append(call)
        history.append(call)
        assert self._is_stuck(history) is True

    def test_not_stuck_same_tool_different_args(self):
        """Calling the same tool with different args is iteration, not stuck."""
        history = deque(maxlen=10)
        for i in range(7):
            history.append(("google_modify_labels", json.dumps({"message_id": str(i)})))
        assert self._is_stuck(history) is False

    def test_stuck_same_tool_same_args_many_times(self):
        """Same exact call 5+ times in the window is stuck."""
        history = deque(maxlen=10)
        call = ("google_search_emails", '{"query":"test"}')
        for _ in range(7):
            history.append(call)
        assert self._is_stuck(history) is True

    def test_not_stuck_mixed_tools(self):
        history = deque(maxlen=10)
        history.append(("google_search_emails", '{"query":"test"}'))
        history.append(("google_get_labels", "{}"))
        history.append(("google_modify_labels", '{"message_id":"1"}'))
        history.append(("google_modify_labels", '{"message_id":"2"}'))
        history.append(("google_modify_labels", '{"message_id":"3"}'))
        history.append(("google_modify_labels", '{"message_id":"4"}'))
        history.append(("google_modify_labels", '{"message_id":"5"}'))
        assert self._is_stuck(history) is False


# ---------------------------------------------------------------------------
# Batch tool execution
# ---------------------------------------------------------------------------


class TestBatchToolExecution:
    """Test the batch_tool handler in ToolExecutor."""

    @pytest.mark.asyncio
    async def test_batch_tool_calls_target_tool_per_item(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        # Register a fake tool
        fake_tool = MagicMock()
        fake_tool.service_name = "google"
        executor.registry._tools["google_modify_labels"] = fake_tool
        executor.services["google"] = MagicMock()

        # Mock execute_tool to track calls
        call_log = []

        async def mock_execute(tool_name, arguments, tool_call_id=None, iteration=None):
            call_log.append((tool_name, arguments))
            return {"success": True, "result": "ok"}

        executor.execute_tool = mock_execute

        result = await executor._handle_batch_tool(
            {
                "tool_name": "google_modify_labels",
                "items": [
                    {"message_id": "msg1", "add_labels": ["Label_1"]},
                    {"message_id": "msg2", "add_labels": ["Label_1"]},
                    {"message_id": "msg3", "add_labels": ["Label_1"]},
                ],
            }
        )

        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0
        assert len(call_log) == 3
        assert call_log[0][1]["message_id"] == "msg1"
        assert call_log[2][1]["message_id"] == "msg3"

    @pytest.mark.asyncio
    async def test_batch_tool_handles_partial_failures(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        fake_tool = MagicMock()
        fake_tool.service_name = "google"
        executor.registry._tools["google_trash_email"] = fake_tool
        executor.services["google"] = MagicMock()

        call_count = 0

        async def mock_execute(tool_name, arguments, tool_call_id=None, iteration=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return {"success": False, "error": "not found"}
            return {"success": True, "result": "ok"}

        executor.execute_tool = mock_execute

        result = await executor._handle_batch_tool(
            {
                "tool_name": "google_trash_email",
                "items": [
                    {"message_id": "msg1"},
                    {"message_id": "msg2"},
                    {"message_id": "msg3"},
                ],
            }
        )

        assert result["total"] == 3
        assert result["succeeded"] == 2
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_batch_tool_rejects_unknown_tool(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        result = await executor._handle_batch_tool(
            {
                "tool_name": "nonexistent_tool",
                "items": [{"x": 1}],
            }
        )
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_batch_tool_rejects_empty_items(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        result = await executor._handle_batch_tool(
            {
                "tool_name": "google_modify_labels",
                "items": [],
            }
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_batch_tool_rejects_self_reference(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        result = await executor._handle_batch_tool(
            {
                "tool_name": "batch_tool",
                "items": [{"tool_name": "x", "items": []}],
            }
        )
        assert "error" in result
        assert "cannot call itself" in result["error"]


# ---------------------------------------------------------------------------
# Loop tool execution
# ---------------------------------------------------------------------------


class TestLoopToolExecution:
    """Test the loop_tool handler in ToolExecutor."""

    def _make_executor(self, *tool_names: str):
        """Return a ToolExecutor with fake registrations for the given tool names."""
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        for name in tool_names:
            fake_tool = MagicMock()
            fake_tool.service_name = "google"
            executor.registry._tools[name] = fake_tool
        executor.services["google"] = MagicMock()
        return executor

    @pytest.mark.asyncio
    async def test_loop_runs_all_steps_per_item(self):
        executor = self._make_executor("google_get_email", "notion_create_page")
        call_log = []

        async def mock_execute(tool_name, arguments, tool_call_id=None, iteration=None):
            call_log.append((tool_name, dict(arguments)))
            return {"success": True, "result": "ok"}

        executor.execute_tool = mock_execute

        result = await executor._handle_loop_tool(
            {
                "steps": [
                    {"tool_name": "google_get_email", "arguments": {}},
                    {"tool_name": "notion_create_page", "arguments": {"database_id": "db1"}},
                ],
                "items": [{"message_id": "msg1"}, {"message_id": "msg2"}],
            }
        )

        assert result["total_items"] == 2
        assert result["succeeded"] == 2
        assert result["failed"] == 0
        # 2 items × 2 steps = 4 total calls
        assert len(call_log) == 4
        # Item fields merged into step arguments
        assert call_log[0] == ("google_get_email", {"message_id": "msg1"})
        assert call_log[1] == ("notion_create_page", {"database_id": "db1", "message_id": "msg1"})
        assert call_log[2] == ("google_get_email", {"message_id": "msg2"})
        assert call_log[3] == ("notion_create_page", {"database_id": "db1", "message_id": "msg2"})

    @pytest.mark.asyncio
    async def test_loop_stops_steps_on_step_failure_continues_next_item(self):
        """If a step fails for item N, skip remaining steps for that item but continue to N+1."""
        executor = self._make_executor("step_a", "step_b")
        call_log = []

        async def mock_execute(tool_name, arguments, tool_call_id=None, iteration=None):
            call_log.append(tool_name)
            # step_b always fails
            if tool_name == "step_b":
                return {"success": False, "error": "step_b failed"}
            return {"success": True, "result": "ok"}

        executor.execute_tool = mock_execute

        result = await executor._handle_loop_tool(
            {
                "steps": [
                    {"tool_name": "step_a", "arguments": {}},
                    {"tool_name": "step_b", "arguments": {}},
                ],
                "items": [{"id": "1"}, {"id": "2"}],
            }
        )

        assert result["total_items"] == 2
        assert result["succeeded"] == 0
        assert result["failed"] == 2
        # step_a runs for both items, step_b runs (and fails) for both, no further steps
        assert call_log == ["step_a", "step_b", "step_a", "step_b"]
        assert result["results"][0]["success"] is False
        assert result["results"][1]["success"] is False

    @pytest.mark.asyncio
    async def test_loop_without_items_runs_pipeline_once(self):
        """Omitting items (or passing [{}]) runs the pipeline exactly once."""
        executor = self._make_executor("tool_x", "tool_y")
        call_log = []

        async def mock_execute(tool_name, arguments, tool_call_id=None, iteration=None):
            call_log.append(tool_name)
            return {"success": True, "result": "ok"}

        executor.execute_tool = mock_execute

        result = await executor._handle_loop_tool(
            {
                "steps": [
                    {"tool_name": "tool_x", "arguments": {"key": "val"}},
                    {"tool_name": "tool_y", "arguments": {}},
                ],
                # no items → defaults to [{}]
            }
        )

        assert result["total_items"] == 1
        assert result["succeeded"] == 1
        assert call_log == ["tool_x", "tool_y"]

    @pytest.mark.asyncio
    async def test_loop_item_fields_override_step_defaults(self):
        """Item fields take precedence over the step's shared arguments."""
        executor = self._make_executor("some_tool")
        received_args = {}

        async def mock_execute(tool_name, arguments, tool_call_id=None, iteration=None):
            received_args.update(arguments)
            return {"success": True, "result": "ok"}

        executor.execute_tool = mock_execute

        await executor._handle_loop_tool(
            {
                "steps": [
                    {
                        "tool_name": "some_tool",
                        "arguments": {"shared": "default", "override_me": "old"},
                    }
                ],
                "items": [{"override_me": "new", "extra": "extra_val"}],
            }
        )

        assert received_args["shared"] == "default"
        assert received_args["override_me"] == "new"  # item wins
        assert received_args["extra"] == "extra_val"

    @pytest.mark.asyncio
    async def test_loop_rejects_empty_steps(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        result = await executor._handle_loop_tool({"steps": [], "items": [{"x": 1}]})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_loop_rejects_unknown_tool_in_steps(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        result = await executor._handle_loop_tool(
            {
                "steps": [{"tool_name": "nonexistent_tool", "arguments": {}}],
                "items": [{"x": 1}],
            }
        )
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_loop_rejects_self_reference_batch(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        result = await executor._handle_loop_tool(
            {
                "steps": [{"tool_name": "batch_tool", "arguments": {}}],
                "items": [{}],
            }
        )
        assert "error" in result
        assert "batch_tool" in result["error"]

    @pytest.mark.asyncio
    async def test_loop_rejects_self_reference_loop(self):
        from src.core.tools.executor import ToolExecutor

        executor = ToolExecutor()
        result = await executor._handle_loop_tool(
            {
                "steps": [{"tool_name": "loop_tool", "arguments": {}}],
                "items": [{}],
            }
        )
        assert "error" in result
        assert "loop_tool" in result["error"]
