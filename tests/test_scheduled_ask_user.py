"""Scheduled runs and ask_user.

- A scheduled prompt is never taken as the answer to an open question: the run
  moves to a new conversation and the question stays answerable.
- With ``automations.ask_user`` on, scheduled runs get the ask_user tool, also
  after the user has answered from another channel.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

ASK_USER = {"type": "function", "function": {"name": "ask_user", "parameters": {}}}
OTHER = {"type": "function", "function": {"name": "web_search", "parameters": {}}}


class _Stop(Exception):
    pass


def _make_handler(ask_user_setting=False):
    from src.services.message_handler import MessageHandler

    skill_repo = MagicMock()
    skill_repo.get_skills_by_keywords.return_value = []
    skill_repo.get_enabled_skills.return_value = []

    conversation_service = MagicMock()
    conversation_service.create_or_get_conversation.return_value = {
        "conversation_id": "conv-waiting"
    }
    conversation_service.add_message.return_value = {"message_id": "msg-1"}
    conversation_service.message_repo = MagicMock()
    conversation_service.conversation_repo = MagicMock()

    memory_service = MagicMock()

    settings = {"automations.ask_user": ask_user_setting}
    settings_service = MagicMock()
    settings_service.get_config_with_fallback.side_effect = lambda key, default=None: settings.get(
        key, default
    )
    settings_service.settings_repo = MagicMock()

    handler = MessageHandler(
        skill_repo=skill_repo,
        conversation_service=conversation_service,
        memory_service=memory_service,
        settings_service=settings_service,
        tool_executor=MagicMock(),
    )
    handler.tool_registry = MagicMock()
    handler.tool_registry.get_openai_tools.return_value = [OTHER, ASK_USER]
    return handler


def _suspended(handler, state=None):
    handler._get_suspended_state = MagicMock(
        return_value=(state or {"messages": [], "ask_user_tool_call_id": "tc-1"}, "msg-q")
    )
    handler._resume_suspended_execution = AsyncMock(return_value={"response": "resumed"})
    # Stop right after the conversation is settled
    handler._load_context = MagicMock(side_effect=_Stop)


@pytest.mark.asyncio
async def test_scheduled_prompt_does_not_answer_an_open_question():
    handler = _make_handler()
    _suspended(handler)

    with pytest.raises(_Stop):
        await handler.handle_message(
            message="Weekly research", channel="system", contact_identifier="cron_job-1"
        )

    handler._resume_suspended_execution.assert_not_called()
    created = handler.conversation_service.conversation_repo.create.call_args.kwargs
    assert created["conversation_id"] != "conv-waiting"
    assert created["channel"] == "system"
    assert created["contact_identifier"] == "cron_job-1"
    stored = handler.conversation_service.add_message.call_args.kwargs
    assert stored["conversation_id"] == created["conversation_id"]
    assert stored["content"] == "Weekly research"


@pytest.mark.asyncio
async def test_a_reply_from_the_user_still_resumes():
    handler = _make_handler()
    _suspended(handler)

    result = await handler.handle_message(
        message="Focus on Europe", conversation_id="conv-waiting", channel="webui"
    )

    assert result == {"response": "resumed"}
    handler.conversation_service.conversation_repo.create.assert_not_called()
    assert handler._resume_suspended_execution.call_args.kwargs["conv_id"] == "conv-waiting"


def test_with_ask_user_adds_it_once():
    handler = _make_handler()
    tools = handler._with_ask_user([OTHER])
    assert [t["function"]["name"] for t in tools] == ["web_search", "ask_user"]
    assert handler._with_ask_user(tools) == tools


async def _resume_tools(handler, state):
    handler._get_llm_client = MagicMock()
    handler._execute_conversation_loop = AsyncMock(
        return_value={
            "response": "done",
            "tools_executed": [],
            "iterations": 1,
            "stuck_detected": False,
        }
    )
    await handler._resume_suspended_execution(
        conv_id="conv-waiting",
        user_answer="Focus on Europe",
        suspended_state=state,
        channel="webui",
    )
    kwargs = handler._execute_conversation_loop.call_args.kwargs
    return [t["function"]["name"] for t in kwargs["tools"]], kwargs["origin_channel"]


@pytest.mark.asyncio
async def test_resumed_scheduled_run_can_ask_again_when_enabled():
    handler = _make_handler(ask_user_setting=True)
    names, origin = await _resume_tools(handler, {"messages": [], "origin_channel": "system"})
    assert "ask_user" in names
    assert origin == "system"


@pytest.mark.asyncio
async def test_resumed_scheduled_run_without_the_setting():
    handler = _make_handler(ask_user_setting=False)
    names, origin = await _resume_tools(handler, {"messages": [], "origin_channel": "system"})
    assert "ask_user" not in names
    assert origin == "system"


@pytest.mark.asyncio
async def test_resumed_chat_keeps_its_own_channel():
    handler = _make_handler(ask_user_setting=True)
    names, origin = await _resume_tools(handler, {"messages": []})
    assert "ask_user" not in names
    assert origin == "webui"
