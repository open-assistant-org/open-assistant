"""The final reply must be self-contained: withdrawn drafts are never "above" for the user."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.message_handler import UNSEEN_NOTICE, MessageHandler
from src.services.planner import PlanStep, PlanTracker
from tests.test_tool_trace_history import TOOLS, _handler, _llm, _msg

ANSWER = (
    "Here are three ideas: 1) EU AI Act myth-bust. 2) Sovereignty vs speed. 3) Invisible ships. "
    * 3
)


def _plan():
    return PlanTracker(
        steps=[
            PlanStep(number=1, description="Draft a post", status="in_progress"),
            PlanStep(number=2, description="Edit the post"),
            PlanStep(number=3, description="Pick headlines"),
        ]
    )


async def _run(h, llm, plan=None):
    return await h._execute_conversation_loop(
        llm_client=llm,
        system_prompt="sys",
        user_message="give me tweet ideas",
        conversation_id="conv",
        tools=TOOLS,
        recent_messages=[{"role": "user", "content": "give me tweet ideas"}],
        plan=plan,
    )


def _prompts(llm):
    return [
        m["content"]
        for call in llm.complete_with_tools.call_args_list
        for m in call.kwargs["messages"]
    ]


class TestUnrelatedPlan:
    @pytest.mark.asyncio
    async def test_substantive_answer_is_kept_instead_of_summarised(self):
        h = _handler()
        # Three text-only answers: the first is nudged, the second is accepted.
        llm = _llm(_msg(content=ANSWER), _msg(content=ANSWER), _msg(content="unused"))
        llm.complete = MagicMock()  # a summary call would go through complete()
        result = await _run(h, llm, _plan())
        assert result["response"] == ANSWER
        llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_plan_nudge_marks_reply_unseen_and_offers_revise_plan(self):
        h = _handler()
        llm = _llm(_msg(content=ANSWER), _msg(content=ANSWER))
        await _run(h, llm, _plan())
        nudges = [c for c in _prompts(llm) if "unfinished steps" in c]
        assert nudges
        assert UNSEEN_NOTICE in nudges[0]
        assert "revise_plan" in nudges[0]


class TestForcedSummary:
    @pytest.mark.asyncio
    async def test_nudge_limit_summary_asks_for_full_results(self):
        h = _handler()
        # Short replies never count as substantive, so the nudge limit is reached.
        llm = _llm(*[_msg(content="ok") for _ in range(4)])
        summary = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="FULL ANSWER"))]
        )
        llm.complete = MagicMock(return_value=summary)
        result = await _run(h, llm, _plan())
        assert result["response"] == "FULL ANSWER"
        prompt = llm.complete.call_args.kwargs["messages"][-1]["content"]
        assert UNSEEN_NOTICE in prompt
        assert "in full" in prompt
        assert "Draft a post" in prompt


class TestSystemPrompt:
    def test_tells_model_only_final_reply_is_shown(self):
        h = object.__new__(MessageHandler)
        h.settings_service = MagicMock()
        h.settings_service.get_config_with_fallback.side_effect = lambda k, d=None: d
        prompt = h._build_system_prompt([], {})
        assert "only sees your final reply" in prompt
