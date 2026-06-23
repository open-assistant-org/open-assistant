"""Tests for adaptive planning: plan reflection, revise_plan, ask_user, and suspension/resumption."""

import json

from src.services.planner import PlanStep, PlanTracker, Planner

# ---------------------------------------------------------------------------
# PlanTracker – mutation methods
# ---------------------------------------------------------------------------


class TestPlanTrackerMutations:
    """Test PlanTracker mutation methods for adaptive planning."""

    def _make_tracker(self):
        return PlanTracker(
            steps=[
                PlanStep(number=1, description="Search emails", status="completed"),
                PlanStep(number=2, description="Get labels", status="in_progress"),
                PlanStep(number=3, description="Apply labels to emails"),
                PlanStep(number=4, description="Summarize results"),
            ],
            raw_plan="1. Search emails\n2. Get labels\n3. Apply labels\n4. Summarize",
        )

    def test_mark_failed(self):
        tracker = self._make_tracker()
        failed = tracker.mark_failed("API returned 403")
        assert failed.number == 2
        assert failed.status == "failed"
        assert "403" in failed.result_summary

    def test_mark_failed_no_current(self):
        tracker = PlanTracker(steps=[PlanStep(number=1, description="done", status="completed")])
        result = tracker.mark_failed("no step")
        assert result is None

    def test_insert_step_after(self):
        tracker = self._make_tracker()
        new_step = tracker.insert_step_after(2, "Re-authenticate with Google")
        # New step is inserted after step 2
        assert len(tracker.steps) == 5
        assert tracker.steps[2].description == "Re-authenticate with Google"
        # Renumbering happened
        assert tracker.steps[2].number == 3
        assert tracker.steps[3].number == 4  # was "Apply labels"
        assert tracker.steps[4].number == 5  # was "Summarize"

    def test_insert_step_after_nonexistent_appends(self):
        tracker = self._make_tracker()
        tracker.insert_step_after(99, "Fallback step")
        assert tracker.steps[-1].description == "Fallback step"
        assert len(tracker.steps) == 5

    def test_remove_step_pending(self):
        tracker = self._make_tracker()
        removed = tracker.remove_step(4)  # "Summarize results" is pending
        assert removed is True
        assert len(tracker.steps) == 3
        assert all(s.number == i + 1 for i, s in enumerate(tracker.steps))

    def test_remove_step_non_pending_fails(self):
        tracker = self._make_tracker()
        removed = tracker.remove_step(1)  # completed — can't remove
        assert removed is False
        assert len(tracker.steps) == 4

    def test_remove_step_in_progress_fails(self):
        tracker = self._make_tracker()
        removed = tracker.remove_step(2)  # in_progress — can't remove
        assert removed is False

    def test_replace_remaining(self):
        tracker = self._make_tracker()
        tracker.replace_remaining(
            [
                "Retry getting labels with different API",
                "Apply labels using batch_tool",
            ]
        )
        # completed + in_progress + 2 new = 4 steps
        assert len(tracker.steps) == 4
        assert tracker.steps[0].status == "completed"
        assert tracker.steps[1].status == "in_progress"
        assert tracker.steps[2].description == "Retry getting labels with different API"
        assert tracker.steps[2].status == "pending"
        assert tracker.steps[3].description == "Apply labels using batch_tool"
        # Numbers should be sequential
        assert [s.number for s in tracker.steps] == [1, 2, 3, 4]

    def test_replace_remaining_detects_iteration(self):
        tracker = self._make_tracker()
        tracker.replace_remaining(["For each email, apply the Work label"])
        new_step = tracker.steps[-1]
        assert new_step.requires_iteration is True

    def test_replace_remaining_updates_raw_plan(self):
        tracker = self._make_tracker()
        tracker.replace_remaining(["New step A", "New step B"])
        assert "New step A" in tracker.raw_plan
        assert "New step B" in tracker.raw_plan


# ---------------------------------------------------------------------------
# PlanTracker – serialization
# ---------------------------------------------------------------------------


class TestPlanTrackerSerialization:
    """Test PlanTracker to_dict / from_dict round-trip."""

    def test_round_trip(self):
        original = PlanTracker(
            steps=[
                PlanStep(
                    number=1, description="Search", status="completed", result_summary="Found 5"
                ),
                PlanStep(
                    number=2, description="Label", status="in_progress", requires_iteration=True
                ),
                PlanStep(number=3, description="Summarize"),
            ],
            raw_plan="1. Search\n2. Label\n3. Summarize",
        )
        data = original.to_dict()
        restored = PlanTracker.from_dict(data)

        assert restored.total == original.total
        assert restored.raw_plan == original.raw_plan
        assert restored.steps[0].status == "completed"
        assert restored.steps[0].result_summary == "Found 5"
        assert restored.steps[1].requires_iteration is True
        assert restored.steps[1].status == "in_progress"
        assert restored.steps[2].status == "pending"

    def test_serialization_is_json_compatible(self):
        tracker = PlanTracker(
            steps=[PlanStep(number=1, description="Test")],
            raw_plan="1. Test",
        )
        data = tracker.to_dict()
        # Should be fully JSON-serializable
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = PlanTracker.from_dict(restored_data)
        assert restored.steps[0].description == "Test"

    def test_from_dict_empty(self):
        tracker = PlanTracker.from_dict({})
        assert tracker.total == 0
        assert tracker.raw_plan == ""


# ---------------------------------------------------------------------------
# PlanStep serialization
# ---------------------------------------------------------------------------


class TestPlanStepSerialization:
    """Test PlanStep to_dict / from_dict."""

    def test_round_trip(self):
        step = PlanStep(
            number=3,
            description="Do something",
            status="failed",
            requires_iteration=True,
            result_summary="Timed out",
        )
        data = step.to_dict()
        restored = PlanStep.from_dict(data)
        assert restored.number == 3
        assert restored.description == "Do something"
        assert restored.status == "failed"
        assert restored.requires_iteration is True
        assert restored.result_summary == "Timed out"


# ---------------------------------------------------------------------------
# Planner – reflection heuristic
# ---------------------------------------------------------------------------


class TestPlannerReflection:
    """Test Planner.should_reflect() heuristic."""

    def _make_plan(self, total=4, completed=0):
        steps = []
        for i in range(total):
            status = (
                "completed" if i < completed else ("in_progress" if i == completed else "pending")
            )
            steps.append(PlanStep(number=i + 1, description=f"Step {i + 1}", status=status))
        return PlanTracker(steps=steps, raw_plan="test plan")

    def test_no_reflection_without_plan(self):
        assert Planner.should_reflect([], None) is False

    def test_no_reflection_single_step_plan(self):
        plan = self._make_plan(total=1)
        assert Planner.should_reflect([], plan) is False

    def test_reflection_on_error_keyword(self):
        plan = self._make_plan(total=4, completed=1)
        results = [{"content": '{"success": false, "error": "not found"}'}]
        assert Planner.should_reflect(results, plan) is True

    def test_reflection_on_failed_step(self):
        plan = self._make_plan(total=4, completed=1)
        # Mark the current step as failed — keep it findable by current_step
        # (current_step looks for pending/in_progress, so we mark_failed directly)
        plan.mark_failed("test failure")
        assert Planner.should_reflect([], plan) is True

    def test_reflection_at_halfway(self):
        plan = self._make_plan(total=4, completed=2)
        assert Planner.should_reflect([], plan) is True

    def test_no_reflection_on_clean_results(self):
        plan = self._make_plan(total=4, completed=1)
        results = [{"content": '{"success": true, "result": "all good"}'}]
        assert Planner.should_reflect(results, plan) is False

    def test_reflection_triggers_multiple_keywords(self):
        """Should trigger on any of the defined keywords."""
        plan = self._make_plan(total=4, completed=1)
        for keyword in ["failed", "unauthorized", "ambiguous", "timeout", "0 results"]:
            results = [{"content": f'{{"detail": "{keyword}"}}'}]
            assert Planner.should_reflect(results, plan) is True, f"Should trigger on '{keyword}'"

    def test_no_reflection_on_successful_json_with_trigger_words(self):
        """JSON results with success=true should skip keyword scanning."""
        plan = self._make_plan(total=4, completed=1)
        # Contains "error" and "empty" as data fields, but success is True
        results = [{"content": '{"success": true, "error_count": 0, "empty_trash": "completed"}'}]
        assert Planner.should_reflect(results, plan) is False

    def test_reflection_on_failed_json(self):
        """JSON results without success=true should still trigger on keywords."""
        plan = self._make_plan(total=4, completed=1)
        results = [{"content": '{"success": false, "error": "access denied"}'}]
        assert Planner.should_reflect(results, plan) is True

    def test_no_reflection_on_status_success(self):
        """JSON results with status=success should skip keyword scanning."""
        plan = self._make_plan(total=4, completed=1)
        results = [{"content": '{"status": "success", "message": "empty inbox, 0 results found"}'}]
        assert Planner.should_reflect(results, plan) is False


# ---------------------------------------------------------------------------
# Planner – reflection prompt builder
# ---------------------------------------------------------------------------


class TestPlannerReflectionPrompt:
    """Test Planner.build_reflection_prompt()."""

    def test_builds_prompt_with_progress(self):
        plan = PlanTracker(
            steps=[
                PlanStep(number=1, description="Search", status="completed"),
                PlanStep(number=2, description="Label", status="in_progress"),
                PlanStep(number=3, description="Summarize"),
            ],
            raw_plan="test",
        )
        results = [{"content": '{"error": "label not found"}'}]
        prompt = Planner.build_reflection_prompt(plan, results)

        assert "[Plan checkpoint]" in prompt
        assert "1/3 steps completed" in prompt
        assert "[done]" in prompt
        assert "[current]" in prompt
        assert "[pending]" in prompt
        assert "label not found" in prompt
        assert "revise_plan" in prompt
        assert "ask_user" in prompt

    def test_truncates_long_results(self):
        plan = PlanTracker(
            steps=[PlanStep(number=1, description="Test", status="in_progress")],
            raw_plan="test",
        )
        long_content = "x" * 1000
        results = [{"content": long_content}]
        prompt = Planner.build_reflection_prompt(plan, results)
        # Should be truncated with "..."
        assert "..." in prompt

    def test_handles_empty_results(self):
        plan = PlanTracker(
            steps=[PlanStep(number=1, description="Test", status="in_progress")],
            raw_plan="test",
        )
        prompt = Planner.build_reflection_prompt(plan, [])
        assert "(no results)" in prompt


# ---------------------------------------------------------------------------
# MessageHandler._handle_revise_plan (static-ish helper)
# ---------------------------------------------------------------------------


class TestHandleRevisePlan:
    """Test the revise_plan handler using the extracted plan_helpers function."""

    @staticmethod
    def _handle(plan, arguments):
        from src.services.plan_helpers import handle_revise_plan

        return handle_revise_plan(plan, arguments)

    def _make_plan(self):
        return PlanTracker(
            steps=[
                PlanStep(number=1, description="Search", status="completed"),
                PlanStep(number=2, description="Label", status="in_progress"),
                PlanStep(number=3, description="Notify user"),
                PlanStep(number=4, description="Summarize"),
            ],
            raw_plan="test",
        )

    def test_replace_remaining(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "replace_remaining",
                "new_steps": ["Re-authenticate", "Retry labelling", "Done"],
                "reason": "Auth expired",
            },
        )
        assert result["success"] is True
        assert result["action"] == "replace_remaining"
        # completed + in_progress + 3 new = 5
        assert len(plan.steps) == 5
        assert plan.steps[2].description == "Re-authenticate"

    def test_replace_remaining_missing_steps(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "replace_remaining",
                "reason": "oops",
            },
        )
        assert result["success"] is False

    def test_add_step(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "add_step",
                "step_number": 2,
                "new_steps": ["Verify labels exist"],
                "reason": "Need to check first",
            },
        )
        assert result["success"] is True
        assert len(plan.steps) == 5
        assert plan.steps[2].description == "Verify labels exist"

    def test_add_step_missing_params(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "add_step",
                "reason": "incomplete",
            },
        )
        assert result["success"] is False

    def test_remove_step(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "remove_step",
                "step_number": 4,
                "reason": "Not needed",
            },
        )
        assert result["success"] is True
        assert len(plan.steps) == 3

    def test_remove_step_non_pending(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "remove_step",
                "step_number": 1,  # completed
                "reason": "Trying to remove completed",
            },
        )
        assert result["success"] is False

    def test_skip_current(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "skip_current",
                "reason": "Not relevant anymore",
            },
        )
        assert result["success"] is True
        assert plan.steps[1].status == "completed"  # was in_progress
        assert "Skipped" in plan.steps[1].result_summary
        # Next step should now be in_progress
        assert plan.steps[2].status == "in_progress"

    def test_unknown_action(self):
        plan = self._make_plan()
        result = self._handle(
            plan,
            {
                "action": "teleport",
                "reason": "???",
            },
        )
        assert result["success"] is False
        assert "Unknown action" in result["error"]


# ---------------------------------------------------------------------------
# Progress message with failed status
# ---------------------------------------------------------------------------


class TestProgressMessageWithFailed:
    """Test that progress_message shows [FAILED] for failed steps."""

    def test_failed_step_shown(self):
        tracker = PlanTracker(
            steps=[
                PlanStep(number=1, description="Search", status="completed"),
                PlanStep(number=2, description="Label", status="failed"),
                PlanStep(number=3, description="Summarize"),
            ],
            raw_plan="test",
        )
        msg = tracker.progress_message()
        assert "[FAILED]" in msg
        assert "[done]" in msg
        assert "[pending]" in msg


# ---------------------------------------------------------------------------
# PendingInput model
# ---------------------------------------------------------------------------


class TestPendingInputModel:
    """Test the PendingInput model."""

    def test_basic_creation(self):
        from src.models.conversation import PendingInput

        pi = PendingInput(question="Which calendar?", options=["Work", "Personal"])
        assert pi.question == "Which calendar?"
        assert pi.options == ["Work", "Personal"]

    def test_without_options(self):
        from src.models.conversation import PendingInput

        pi = PendingInput(question="What email address?")
        assert pi.options is None
        assert pi.context is None


# ---------------------------------------------------------------------------
# AskUserRequest / RevisePlanRequest model validation
# ---------------------------------------------------------------------------


class TestPlanToolModels:
    """Test the Pydantic models for plan tools."""

    def test_ask_user_request(self):
        from src.models.plan_tools import AskUserRequest

        req = AskUserRequest(
            question="Which folder?",
            options=["Inbox", "Drafts"],
            context="Need to know where to move the emails",
        )
        assert req.question == "Which folder?"
        assert len(req.options) == 2

    def test_ask_user_minimal(self):
        from src.models.plan_tools import AskUserRequest

        req = AskUserRequest(question="Yes or no?")
        assert req.options is None
        assert req.context is None

    def test_revise_plan_request(self):
        from src.models.plan_tools import RevisePlanRequest

        req = RevisePlanRequest(
            action="replace_remaining",
            new_steps=["Step A", "Step B"],
            reason="Original steps no longer valid",
        )
        assert req.action == "replace_remaining"
        assert len(req.new_steps) == 2

    def test_revise_plan_skip(self):
        from src.models.plan_tools import RevisePlanRequest

        req = RevisePlanRequest(
            action="skip_current",
            reason="Step is irrelevant",
        )
        assert req.step_number is None
        assert req.new_steps is None


# ---------------------------------------------------------------------------
# MessageHandler._serialize_messages / _deserialize_messages
# ---------------------------------------------------------------------------


class TestMessageSerialization:
    """Test message serialization for suspension using the extracted plan_helpers functions."""

    @staticmethod
    def _serialize_messages(messages):
        from src.services.plan_helpers import serialize_messages

        return serialize_messages(messages)

    @staticmethod
    def _deserialize_messages(data):
        from src.services.plan_helpers import deserialize_messages

        return deserialize_messages(data)

    def test_round_trip(self):
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "tool", "tool_call_id": "tc_1", "content": '{"result": "ok"}'},
        ]
        serialized = self._serialize_messages(messages)
        restored = self._deserialize_messages(serialized)
        assert len(restored) == 4
        assert restored[0]["role"] == "system"
        assert restored[3]["tool_call_id"] == "tc_1"

    def test_non_serializable_values_converted(self):
        class NotSerializable:
            def __str__(self):
                return "stringified"

        messages = [{"role": "user", "content": "ok", "extra": NotSerializable()}]
        serialized = self._serialize_messages(messages)
        assert serialized[0]["extra"] == "stringified"
