"""Tests for streaming assistant text to the chat UI (text_delta / text_reset)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm_client import LLMClient, LLMConfig
from src.services.message_handler import MessageHandler


def _chunk(content=None, tool_calls=None, finish_reason=None, usage=None, choices=True):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)] if choices else [],
        usage=usage,
    )


def _tc_delta(index, id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments)
    )


def _client(chunks, provider="openrouter"):
    config = LLMConfig(provider=provider, model="m", api_key="k")
    with patch("src.core.llm_client.OpenAI") as mock_openai:
        create = MagicMock(return_value=iter(chunks))
        mock_openai.return_value.chat.completions.create = create
        client = LLMClient(config)
    return client, create


class TestStreamCompletion:
    def test_text_is_forwarded_and_reassembled(self):
        client, create = _client(
            [_chunk("Hel"), _chunk("lo"), _chunk(finish_reason="stop"), _chunk(choices=False)]
        )
        deltas = []
        response = client.stream_completion(
            messages=[{"role": "user", "content": "hi"}], on_text=deltas.append
        )
        assert deltas == ["Hel", "lo"]
        message = response.choices[0].message
        assert message.content == "Hello"
        assert message.tool_calls is None
        assert response.choices[0].finish_reason == "stop"
        kwargs = create.call_args.kwargs
        assert kwargs["stream"] is True
        assert "tools" not in kwargs

    def test_tool_call_fragments_are_merged(self):
        client, create = _client(
            [
                _chunk(tool_calls=[_tc_delta(0, id="c1", name="search", arguments='{"q"')]),
                _chunk(tool_calls=[_tc_delta(0, arguments=': "x"}')]),
                _chunk(tool_calls=[_tc_delta(1, id="c2", name="other", arguments="{}")]),
                _chunk(finish_reason="tool_calls"),
            ]
        )
        tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
        response = client.stream_completion(messages=[], on_text=lambda d: None, tools=tools)
        calls = response.choices[0].message.tool_calls
        assert [(c.id, c.function.name, c.function.arguments) for c in calls] == [
            ("c1", "search", '{"q": "x"}'),
            ("c2", "other", "{}"),
        ]
        assert response.choices[0].message.model_dump()["tool_calls"][0]["type"] == "function"
        assert create.call_args.kwargs["tools"] == tools

    def test_usage_from_final_chunk_is_recorded_once(self):
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12)
        client, _ = _client([_chunk("hi"), _chunk(choices=False, usage=usage)])
        with patch("src.core.usage_recorder.usage_recorder.record") as record:
            client.stream_completion(messages=[], on_text=lambda d: None)
        record.assert_called_once()
        assert record.call_args.args[0] is usage

    def test_groq_falls_back_to_a_single_text_callback(self):
        config = LLMConfig(provider="groq", model="m", api_key="k")
        with patch("groq.Groq"):
            client = LLMClient(config)
        full = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="All"))])
        client.complete = MagicMock(return_value=full)
        deltas = []
        assert client.stream_completion(messages=[], on_text=deltas.append) is full
        assert deltas == ["All"]


# ---------------------------------------------------------------------------
# Conversation loop events
# ---------------------------------------------------------------------------


def _handler():
    h = object.__new__(MessageHandler)
    h.settings_service = MagicMock()
    h.settings_service.get_config_with_fallback.side_effect = lambda key, default=None: default
    h.memory_service = MagicMock()
    h.memory_service._get_max_tokens.return_value = 100_000
    h.max_iterations = 5
    h.async_task_dispatcher = MagicMock()
    h.async_task_dispatcher.collect_unreported.return_value = []
    h.async_task_dispatcher.get_running_tasks.return_value = []
    h.tool_executor = MagicMock()
    h.tool_executor.execute_tool = AsyncMock(return_value={"ok": True})
    h._find_skill_for_tool = lambda name: None
    h._validate_response = AsyncMock(return_value={"complete": True, "reason": ""})
    return h


def _streaming_llm(*turns):
    """LLM whose stream_completion replays (text_chunks, tool_calls) per call."""
    client = MagicMock()
    client.config.model = "m"
    client.config.get_media_model.return_value = "m"
    queue = list(turns)

    def _stream(on_text, **kwargs):
        if not queue:
            raise AssertionError("unexpected extra LLM call")
        chunks, tool_calls = queue.pop(0)
        for c in chunks:
            on_text(c)

        class _Msg(SimpleNamespace):
            def model_dump(self):
                return {"role": "assistant", "content": self.content, "tool_calls": None}

        message = _Msg(content="".join(chunks) or None, tool_calls=tool_calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client.stream_completion.side_effect = _stream
    return client


TOOLS = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]


async def _run(handler, llm, events):
    async def _cb(event):
        events.append(event)

    return await handler._execute_conversation_loop(
        llm_client=llm,
        system_prompt="sys",
        user_message="q",
        conversation_id="conv",
        tools=TOOLS,
        recent_messages=[{"role": "user", "content": "q"}],
        event_callback=_cb,
    )


class TestLoopStreamsText:
    @pytest.mark.asyncio
    async def test_final_answer_streams_as_text_deltas(self):
        events = []
        result = await _run(_handler(), _streaming_llm((["The ", "answer"], None)), events)
        assert result["response"] == "The answer"
        text = "".join(e["delta"] for e in events if e["type"] == "text_delta")
        assert text == "The answer"
        assert not any(e["type"] == "text_reset" for e in events)

    @pytest.mark.asyncio
    async def test_preamble_before_tool_call_is_reset(self):
        tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="lookup", arguments="{}"))
        events = []
        result = await _run(
            _handler(),
            _streaming_llm((["Let me check."], [tc]), (["Found it."], None)),
            events,
        )
        assert result["response"] == "Found it."
        types = [e["type"] for e in events]
        # Draft is withdrawn right before the second LLM call starts.
        reset_at = types.index("text_reset")
        assert types[reset_at + 1] == "iteration_start"
        before = "".join(e["delta"] for e in events[:reset_at] if e["type"] == "text_delta")
        after = "".join(e["delta"] for e in events[reset_at:] if e["type"] == "text_delta")
        assert (before, after) == ("Let me check.", "Found it.")

    @pytest.mark.asyncio
    async def test_rejected_answer_is_reset(self):
        h = _handler()
        h._validate_response = AsyncMock(
            side_effect=[{"complete": False, "reason": "vague"}, {"complete": True, "reason": ""}]
        )
        events = []
        result = await _run(h, _streaming_llm((["Maybe."], None), (["42."], None)), events)
        assert result["response"] == "42."
        assert [e["type"] for e in events].count("text_reset") == 1

    @pytest.mark.asyncio
    async def test_no_callback_uses_non_streaming_calls(self):
        llm = _streaming_llm()
        llm.complete_with_tools.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hi", tool_calls=None))]
        )
        result = await _handler()._execute_conversation_loop(
            llm_client=llm,
            system_prompt="sys",
            user_message="q",
            conversation_id="conv",
            tools=TOOLS,
            recent_messages=[{"role": "user", "content": "q"}],
        )
        assert result["response"] == "Hi"
        llm.stream_completion.assert_not_called()
