"""Tests for persisting and replaying tool results across conversation turns."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.config import SETTING_DEFINITIONS, ConfigCategory
from src.services.message_handler import MessageHandler
from src.services.tool_trace import (
    DIGEST_WINDOW_TURNS,
    RECALL_TOOL_DEF,
    RECALL_TOOL_NAME,
    TRACE_KEY,
    build_tool_trace,
    expand_history,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assistant_call(*calls):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}
            for cid, name, args in calls
        ],
    }


def _tool(cid, content):
    return {"role": "tool", "tool_call_id": cid, "content": content}


def _entry(step=1, name="gmail_get_message", args='{"id": "abc"}', result="BODY", chars=None):
    return {
        "step": step,
        "name": name,
        "arguments": args,
        "result": result,
        "chars": len(result) if chars is None else chars,
    }


def _history(traces_by_turn):
    """Build alternating user/assistant history; traces_by_turn[i] is turn i's trace or None."""
    history = []
    for i, trace in enumerate(traces_by_turn):
        history.append({"role": "user", "content": f"question {i}"})
        history.append(
            {
                "role": "assistant",
                "content": f"answer {i}",
                "message_id": f"msgid{i:04d}-rest",
                "metadata": {TRACE_KEY: trace} if trace else {},
            }
        )
    history.append({"role": "user", "content": "follow-up"})
    return history


def _assert_valid_tool_sequence(messages):
    """Every tool_call has a matching tool message right after it, and vice versa."""
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("tool_calls"):
            ids = [tc["id"] for tc in msg["tool_calls"]]
            following = messages[i + 1 : i + 1 + len(ids)]
            assert [m["role"] for m in following] == ["tool"] * len(ids)
            assert [m["tool_call_id"] for m in following] == ids
            i += 1 + len(ids)
        else:
            assert msg["role"] != "tool"
            i += 1


# ---------------------------------------------------------------------------
# build_tool_trace
# ---------------------------------------------------------------------------


class TestBuildToolTrace:
    def test_pairs_calls_with_results_and_skips_prefix(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            _assistant_call(("c1", "gmail_get_message", '{"id": "1"}')),
            _tool("c1", '{"body": "hello"}'),
            {"role": "user", "content": "[Internal: nudge]"},
            _assistant_call(("c2", "gmail_search", '{"q": "x"}'), ("c3", "gmail_labels", "{}")),
            _tool("c2", "r2"),
            _tool("c3", "r3"),
        ]
        trace = build_tool_trace(messages, start_idx=2, max_result_chars=100)
        assert [(e["step"], e["name"]) for e in trace] == [
            (1, "gmail_get_message"),
            (2, "gmail_search"),
            (2, "gmail_labels"),
        ]
        assert trace[0]["result"] == '{"body": "hello"}'
        # Nothing from before start_idx and no nudge text leaks into the trace.
        assert "nudge" not in json.dumps(trace)

    def test_orchestration_tools_are_excluded(self):
        messages = [
            _assistant_call(("a", "ask_user", "{}"), ("b", "gmail_get_message", "{}")),
            _tool("a", "{}"),
            _tool("b", "data"),
        ]
        trace = build_tool_trace(messages, 0, 100)
        assert [e["name"] for e in trace] == ["gmail_get_message"]

    def test_orphan_call_without_result_is_dropped(self):
        messages = [_assistant_call(("a", "t1", "{}"), ("b", "t2", "{}")), _tool("a", "ok")]
        trace = build_tool_trace(messages, 0, 100)
        assert [e["name"] for e in trace] == ["t1"]

    def test_oversized_result_is_truncated_but_chars_kept(self):
        messages = [_assistant_call(("a", "t1", "{}")), _tool("a", "x" * 500)]
        (entry,) = build_tool_trace(messages, 0, 100)
        assert entry["chars"] == 500
        assert entry["result"].startswith("x" * 100)
        assert "truncated, 500 chars" in entry["result"]
        assert len(entry["result"]) < 200

    def test_oversized_arguments_stay_valid_json(self):
        messages = [_assistant_call(("a", "python_agent", "z" * 5000)), _tool("a", "ok")]
        (entry,) = build_tool_trace(messages, 0, 100)
        assert len(entry["arguments"]) < 1000
        json.loads(entry["arguments"])

    def test_non_string_tool_content_is_serialised(self):
        messages = [_assistant_call(("a", "t1", "{}")), _tool("a", {"k": "v"})]
        (entry,) = build_tool_trace(messages, 0, 100)
        assert json.loads(entry["result"]) == {"k": "v"}

    def test_entry_count_is_bounded_keeping_latest(self):
        messages = []
        for i in range(60):
            messages += [_assistant_call((f"c{i}", "t", f'{{"i": {i}}}')), _tool(f"c{i}", "r")]
        trace = build_tool_trace(messages, 0, 100)
        assert len(trace) == 40
        assert json.loads(trace[-1]["arguments"]) == {"i": 59}


# ---------------------------------------------------------------------------
# expand_history
# ---------------------------------------------------------------------------


class TestExpandHistory:
    def test_no_traces_gives_plain_history(self):
        out, recall, stats = expand_history(
            _history([None, None]), full_turns=1, trace_budget_chars=10_000
        )
        assert [m["role"] for m in out] == ["user", "assistant", "user", "assistant", "user"]
        assert recall == {}
        assert stats["chars"] == 0

    def test_latest_traced_turn_is_replayed_before_assistant_text(self):
        history = _history([None, [_entry(result="EMAIL BODY")]])
        out, recall, stats = expand_history(history, full_turns=1, trace_budget_chars=10_000)

        roles = [m["role"] for m in out]
        assert roles == ["user", "assistant", "user", "assistant", "tool", "assistant", "user"]
        call_msg, tool_msg, text_msg = out[3], out[4], out[5]
        assert call_msg["tool_calls"][0]["function"]["name"] == "gmail_get_message"
        assert tool_msg["content"] == "EMAIL BODY"
        assert tool_msg["tool_call_id"] == call_msg["tool_calls"][0]["id"]
        assert text_msg["content"] == "answer 1"
        assert recall == {}
        assert stats["full_turns"] == 1
        _assert_valid_tool_sequence(out)

    def test_same_step_calls_are_grouped_into_one_assistant_message(self):
        trace = [_entry(step=1, name="a"), _entry(step=1, name="b"), _entry(step=2, name="c")]
        out, _, _ = expand_history(_history([trace]), full_turns=1, trace_budget_chars=10_000)
        call_msgs = [m for m in out if m.get("tool_calls")]
        assert [len(m["tool_calls"]) for m in call_msgs] == [2, 1]
        _assert_valid_tool_sequence(out)

    def test_replayed_tool_call_ids_are_unique_across_turns(self):
        history = _history([[_entry()], [_entry()]])
        out, _, _ = expand_history(history, full_turns=2, trace_budget_chars=10_000)
        ids = [tc["id"] for m in out for tc in m.get("tool_calls", [])]
        assert len(ids) == 2 and len(set(ids)) == 2

    def test_older_traced_turn_becomes_digest_with_recall_ref(self):
        history = _history([[_entry(result="OLD BODY", chars=4210)], [_entry(result="NEW")]])
        out, recall, stats = expand_history(history, full_turns=1, trace_budget_chars=10_000)

        old_text = next(m for m in out if m["content"].startswith("answer 0"))
        assert "gmail_get_message(id=abc)" in old_text["content"]
        assert "4210 chars" in old_text["content"]
        assert "OLD BODY" not in old_text["content"]
        (ref,) = recall
        assert recall[ref] == "OLD BODY" and f"ref={ref}" in old_text["content"]
        assert stats["full_turns"] == 1 and stats["digest_turns"] == 1
        _assert_valid_tool_sequence(out)

    def test_trace_over_budget_falls_back_to_digest(self):
        history = _history([[_entry(result="x" * 5000)]])
        out, recall, stats = expand_history(history, full_turns=1, trace_budget_chars=1000)
        assert not any(m.get("tool_calls") for m in out)
        assert len(recall) == 1
        assert stats["full_turns"] == 0 and stats["digest_turns"] == 1

    def test_zero_budget_drops_traces_entirely(self):
        history = _history([[_entry(result="x" * 5000)]])
        out, recall, _ = expand_history(history, full_turns=1, trace_budget_chars=0)
        assert recall == {}
        assert out[1]["content"] == "answer 0"

    def test_traces_older_than_window_are_plain_text(self):
        traces = [[_entry()]] + [None] * DIGEST_WINDOW_TURNS
        out, recall, _ = expand_history(_history(traces), full_turns=1, trace_budget_chars=10_000)
        assert recall == {}
        assert out[1]["content"] == "answer 0"

    def test_malformed_trace_is_ignored(self):
        bad = [{"step": 1, "name": "t", "arguments": "{}"}]  # no result
        out, recall, _ = expand_history(_history([bad]), full_turns=1, trace_budget_chars=10_000)
        assert recall == {} and not any(m.get("tool_calls") for m in out)
        assert out[1]["content"] == "answer 0"

    def test_messages_without_content_are_skipped_like_before(self):
        history = [{"role": "user", "content": ""}, {"role": "user", "content": "hi"}]
        out, _, _ = expand_history(history, full_turns=1, trace_budget_chars=100)
        assert out == [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------------------
# MessageHandler integration
# ---------------------------------------------------------------------------


def _handler(config=None):
    """A MessageHandler without __init__, with just what the paths under test use."""
    h = object.__new__(MessageHandler)
    values = dict(config or {})
    h.settings_service = MagicMock()
    h.settings_service.get_config_with_fallback.side_effect = lambda key, default=None: values.get(
        key, default
    )
    h.memory_service = MagicMock()
    h.memory_service._get_max_tokens.return_value = 100_000
    h.max_iterations = 5
    h.async_task_dispatcher = MagicMock()
    h.async_task_dispatcher.collect_unreported.return_value = []
    h.async_task_dispatcher.get_running_tasks.return_value = []
    h.tool_executor = MagicMock()
    h.tool_executor.execute_tool = AsyncMock(return_value={"body": "hello from X"})
    h._find_skill_for_tool = lambda name: None
    return h


def _llm(*responses):
    """LLM client whose complete_with_tools yields the given messages in order."""
    client = MagicMock()
    client.config.model = "m"
    client.config.get_media_model.return_value = "m"
    client.config.get_worker_model.return_value = "m"
    queue = [SimpleNamespace(choices=[SimpleNamespace(message=r)]) for r in responses]

    def _next(**kwargs):
        # StopIteration inside the executor thread would hang the event loop.
        if not queue:
            raise AssertionError("unexpected extra LLM call")
        return queue.pop(0)

    client.complete_with_tools.side_effect = _next
    return client


def _msg(content="", tool_calls=None):
    class _Msg(SimpleNamespace):
        def model_dump(self):
            return {
                "role": "assistant",
                "content": self.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in (self.tool_calls or [])
                ]
                or None,
            }

    return _Msg(content=content, tool_calls=tool_calls)


def _tc(cid, name, args):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=args))


TOOLS = [{"type": "function", "function": {"name": "gmail_get_message", "parameters": {}}}]


class TestLoopCapturesTrace:
    @pytest.mark.asyncio
    async def test_turn_returns_trace_of_executed_tools(self):
        h = _handler()
        llm = _llm(
            _msg(tool_calls=[_tc("c1", "gmail_get_message", '{"id": "42"}')]),
            _msg(content="The mail from X says hello."),
        )
        result = await h._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="what does the mail from X say?",
            conversation_id="conv",
            tools=TOOLS,
            recent_messages=[{"role": "user", "content": "what does the mail from X say?"}],
        )
        assert result["response"] == "The mail from X says hello."
        (entry,) = result[TRACE_KEY]
        assert entry["name"] == "gmail_get_message"
        assert json.loads(entry["arguments"]) == {"id": "42"}
        assert json.loads(entry["result"]) == {"body": "hello from X"}

    @pytest.mark.asyncio
    async def test_no_tools_means_no_trace_key(self):
        h = _handler()
        llm = _llm(_msg(content="hi"))
        result = await h._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="hello",
            conversation_id="conv",
            tools=TOOLS,
            recent_messages=[{"role": "user", "content": "hello"}],
        )
        assert TRACE_KEY not in result

    @pytest.mark.asyncio
    async def test_subtask_channel_stores_no_trace(self):
        h = _handler()
        llm = _llm(
            _msg(tool_calls=[_tc("c1", "gmail_get_message", "{}")]),
            _msg(content="done"),
        )
        result = await h._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="go",
            conversation_id="conv",
            tools=TOOLS,
            recent_messages=[{"role": "user", "content": "go"}],
            channel="subtask",
        )
        assert TRACE_KEY not in result

    @pytest.mark.asyncio
    async def test_trace_result_is_capped_by_setting(self):
        h = _handler({"llm.history_tool_result_max_chars": 1000})
        h.tool_executor.execute_tool = AsyncMock(return_value={"body": "y" * 5000})
        llm = _llm(
            _msg(tool_calls=[_tc("c1", "gmail_get_message", "{}")]),
            _msg(content="ok"),
        )
        result = await h._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="go",
            conversation_id="conv",
            tools=TOOLS,
            recent_messages=[{"role": "user", "content": "go"}],
        )
        (entry,) = result[TRACE_KEY]
        assert "truncated" in entry["result"] and len(entry["result"]) < 1200

    @pytest.mark.asyncio
    async def test_history_messages_replace_plain_history_and_skip_second_fetch(self):
        h = _handler()
        history = _history([[_entry(result='{"body": "hello from X"}')]])
        replay, recall_index = h._prepare_tool_replay(history, "sys", "webui")
        assert recall_index == {}

        llm = _llm(_msg(content="It was sent Tuesday."))
        result = await h._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="follow-up",
            conversation_id="conv",
            tools=TOOLS,
            recent_messages=history,
            history_messages=replay,
        )
        sent = llm.complete_with_tools.call_args.kwargs["messages"]
        assert any(m.get("tool_calls") for m in sent)
        assert sent[-1] == {"role": "user", "content": "follow-up"}
        _assert_valid_tool_sequence(sent[1:])
        h.tool_executor.execute_tool.assert_not_called()
        assert result["response"] == "It was sent Tuesday."

    @pytest.mark.asyncio
    async def test_recall_tool_serves_stored_result_without_executing_a_tool(self):
        h = _handler()
        llm = _llm(
            _msg(tool_calls=[_tc("r1", RECALL_TOOL_NAME, '{"ref": "msgid000.1"}')]),
            _msg(content="From the stored mail."),
        )
        result = await h._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="again",
            conversation_id="conv",
            tools=[*TOOLS, RECALL_TOOL_DEF],
            recent_messages=[{"role": "user", "content": "again"}],
            recall_index={"msgid000.1": "STORED BODY"},
        )
        second_call_messages = llm.complete_with_tools.call_args.kwargs["messages"]
        tool_msg = next(m for m in second_call_messages if m["role"] == "tool")
        assert json.loads(tool_msg["content"]) == {"ref": "msgid000.1", "result": "STORED BODY"}
        h.tool_executor.execute_tool.assert_not_called()
        assert result["response"] == "From the stored mail."
        # Recalling is not new data: it must not be stored as a trace entry.
        assert TRACE_KEY not in result or all(
            e["name"] != RECALL_TOOL_NAME for e in result[TRACE_KEY]
        )

    @pytest.mark.asyncio
    async def test_unknown_recall_ref_returns_error(self):
        h = _handler()
        llm = _llm(
            _msg(tool_calls=[_tc("r1", RECALL_TOOL_NAME, '{"ref": "nope"}')]),
            _msg(content="ok"),
        )
        await h._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="again",
            conversation_id="conv",
            tools=[*TOOLS, RECALL_TOOL_DEF],
            recent_messages=[{"role": "user", "content": "again"}],
            recall_index={},
        )
        msgs = llm.complete_with_tools.call_args.kwargs["messages"]
        tool_msg = next(m for m in msgs if m["role"] == "tool")
        assert "error" in json.loads(tool_msg["content"])


class TestPrepareToolReplay:
    def test_disabled_toggle_returns_none(self):
        h = _handler({"llm.tool_context_replay": False})
        assert h._prepare_tool_replay(_history([[_entry()]]), "sys", "webui") == (None, {})

    def test_subtask_channel_returns_none(self):
        h = _handler()
        assert h._prepare_tool_replay(_history([[_entry()]]), "sys", "subtask") == (None, {})

    def test_no_traces_returns_none(self):
        h = _handler()
        assert h._prepare_tool_replay(_history([None, None]), "sys", "webui") == (None, {})

    def test_enabled_returns_expanded_history(self):
        h = _handler()
        history, recall = h._prepare_tool_replay(_history([[_entry()]]), "sys", "webui")
        assert any(m.get("tool_calls") for m in history)
        assert recall == {}

    def test_settings_limit_replay(self):
        h = _handler({"llm.history_tool_trace_max_chars": 0})
        history, recall = h._prepare_tool_replay(_history([[_entry()]]), "sys", "webui")
        assert not any(m.get("tool_calls") for m in history) and recall == {}

    def test_replay_never_exceeds_remaining_context_budget(self):
        h = _handler()
        h.memory_service._get_max_tokens.return_value = 10  # nothing left for tool output
        history, recall = h._prepare_tool_replay(_history([[_entry()]]), "sys" * 100, "webui")
        assert not any(m.get("tool_calls") for m in history) and recall == {}

    def test_unusable_mock_settings_fall_back_to_defaults(self):
        h = _handler()
        h.settings_service.get_config_with_fallback.side_effect = None
        h.settings_service.get_config_with_fallback.return_value = MagicMock()
        history, _ = h._prepare_tool_replay(_history([[_entry()]]), "sys", "webui")
        assert any(m.get("tool_calls") for m in history)


# ---------------------------------------------------------------------------
# Settings definitions
# ---------------------------------------------------------------------------


class TestSettingDefinitions:
    def test_toggle_and_limits_are_registered_under_llm(self):
        toggle = SETTING_DEFINITIONS["llm.tool_context_replay"]
        assert toggle.category == ConfigCategory.LLM
        assert toggle.ui_widget == "toggle" and toggle.default_value is True

        for key, default in [
            ("llm.history_tool_turns", 1),
            ("llm.history_tool_result_max_chars", 8000),
            ("llm.history_tool_trace_max_chars", 24000),
        ]:
            d = SETTING_DEFINITIONS[key]
            assert d.category == ConfigCategory.LLM
            assert d.ui_widget == "number" and d.default_value == default
            assert d.min_value <= default <= d.max_value


# ---------------------------------------------------------------------------
# MemoryService: metadata passthrough
# ---------------------------------------------------------------------------


class TestMemoryContextMetadata:
    def _service(self, strategy):
        from src.services.memory import MemoryService

        stored = [
            {"role": "user", "content": "q", "message_id": "u1", "metadata": None},
            {
                "role": "assistant",
                "content": "a",
                "message_id": "a1",
                "metadata": {TRACE_KEY: [_entry()]},
            },
        ]
        message_repo, memory_repo, settings_repo = MagicMock(), MagicMock(), MagicMock()
        message_repo.get_by_conversation.return_value = stored
        memory_repo.get_by_type.return_value = []
        settings_repo.get.side_effect = lambda key: {"llm.context_strategy": strategy}.get(key)
        return MemoryService(
            message_repo=message_repo,
            memory_repo=memory_repo,
            conversation_repo=MagicMock(),
            prompts_repo=MagicMock(),
            settings_repo=settings_repo,
            db_manager=MagicMock(),
        )

    @pytest.mark.parametrize("strategy", ["summarization", "last_messages"])
    def test_metadata_only_included_on_request(self, strategy):
        svc = self._service(strategy)
        plain = svc.get_conversation_context("c", "m", include_system_message=False)
        assert all(set(m) == {"role", "content"} for m in plain["messages"])

        rich = svc.get_conversation_context(
            "c", "m", include_system_message=False, include_message_meta=True
        )
        assistant = next(m for m in rich["messages"] if m["role"] == "assistant")
        assert assistant["message_id"] == "a1"
        assert assistant["metadata"][TRACE_KEY][0]["name"] == "gmail_get_message"

    def test_metadata_does_not_inflate_token_count(self):
        svc = self._service("last_messages")
        plain = svc.get_conversation_context("c", "m", include_system_message=False)
        rich = svc.get_conversation_context(
            "c", "m", include_system_message=False, include_message_meta=True
        )
        assert plain["total_tokens"] == rich["total_tokens"]
