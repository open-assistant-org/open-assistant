"""Tests for Slack "Ingest All Thread Messages".

This option only takes effect when "Reply Only on Mention" is on. With
both enabled, a non-mention message inside a thread must be recorded into
that thread's conversation history (so a later @mention has full context,
including messages from other participants/agents) without triggering a
reply. Without it, non-mention messages keep being dropped entirely.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.slack.socket_mode import SlackSocketModeHandler
from src.services.message_handler import MessageHandler


def _settings(**overrides):
    values = {
        "slack.mention_only": False,
        "slack.thread_replies": False,
        "slack.thread_ingest_all_messages": False,
        "slack.allowed_user_ids": "",
    }
    values.update(overrides)

    settings_service = MagicMock()
    settings_service.get_setting.side_effect = lambda key: values.get(key)
    settings_service.get_config_with_fallback.return_value = "test-api-key"
    return settings_service


def _socket_handler(settings_service):
    message_handler = MagicMock()
    message_handler.handle_message = AsyncMock(
        return_value={"response": "done", "skills_used": [], "tools_executed": [], "iterations": 1}
    )
    message_handler.ingest_passive_message = AsyncMock(return_value={"conversation_id": "conv-1"})

    handler = SlackSocketModeHandler.__new__(SlackSocketModeHandler)
    handler.message_handler = message_handler
    handler.slack_service = MagicMock()
    handler.slack_service.is_user_allowed.return_value = True
    handler.settings_service = settings_service
    handler.media_handler = None
    handler.event_loop = None
    handler._bot_user_id = "BOT1"
    return handler


def _message_event(text="hello", thread_ts="111.1", channel="C123", user="U1"):
    return {
        "type": "message",
        "user": user,
        "channel": channel,
        "text": text,
        "ts": thread_ts,
        "thread_ts": thread_ts,
    }


# ---------------------------------------------------------------------------
# _resolve_thread_scope_ts
# ---------------------------------------------------------------------------


def test_thread_scope_follows_thread_replies():
    handler = _socket_handler(_settings(**{"slack.thread_replies": True}))
    assert handler._resolve_thread_scope_ts("111.1") == "111.1"


def test_thread_scope_follows_mention_only_plus_ingest_all():
    handler = _socket_handler(
        _settings(**{"slack.mention_only": True, "slack.thread_ingest_all_messages": True})
    )
    assert handler._resolve_thread_scope_ts("111.1") == "111.1"


def test_thread_scope_ignores_ingest_all_without_mention_only():
    handler = _socket_handler(_settings(**{"slack.thread_ingest_all_messages": True}))
    assert handler._resolve_thread_scope_ts("111.1") is None


def test_thread_scope_off_by_default():
    handler = _socket_handler(_settings())
    assert handler._resolve_thread_scope_ts("111.1") is None


# ---------------------------------------------------------------------------
# _ingest_thread_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_thread_message_records_without_replying():
    handler = _socket_handler(
        _settings(**{"slack.mention_only": True, "slack.thread_ingest_all_messages": True})
    )

    await handler._ingest_thread_message("C123", "U1", "context for later", "111.1")

    handler.message_handler.ingest_passive_message.assert_awaited_once()
    kwargs = handler.message_handler.ingest_passive_message.call_args.kwargs
    assert kwargs["contact_identifier"] == "C123:111.1"
    assert kwargs["channel"] == "slack"
    assert kwargs["message"] == "context for later"
    handler.message_handler.handle_message.assert_not_called()
    handler.slack_service.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_thread_message_noop_when_not_thread_scoped():
    # thread_ingest_all_messages is off, so there is no thread scope to
    # ingest into even if this were called directly.
    handler = _socket_handler(_settings(**{"slack.mention_only": True}))

    await handler._ingest_thread_message("C123", "U1", "hi", "111.1")

    handler.message_handler.ingest_passive_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_request end-to-end dispatch
# ---------------------------------------------------------------------------


def test_non_mention_ignored_completely_without_ingest_all(monkeypatch):
    handler = _socket_handler(_settings(**{"slack.mention_only": True}))

    called = {}

    def fake_run_coroutine_threadsafe(coro, loop):
        called["dispatched"] = True
        coro.close()

    monkeypatch.setattr(
        "src.integrations.slack.socket_mode.asyncio.run_coroutine_threadsafe",
        fake_run_coroutine_threadsafe,
    )

    client = MagicMock()
    req = MagicMock()
    req.type = "events_api"
    req.envelope_id = "env-1"
    req.payload = {"event": _message_event(text="just chatting, no mention")}

    handler._handle_request(client, req)

    assert "dispatched" not in called


def test_non_mention_ingested_when_ingest_all_enabled(monkeypatch):
    handler = _socket_handler(
        _settings(**{"slack.mention_only": True, "slack.thread_ingest_all_messages": True})
    )
    handler.event_loop = MagicMock()
    handler.event_loop.is_closed.return_value = False

    dispatched = {}

    def fake_run_coroutine_threadsafe(coro, loop):
        dispatched["coro"] = coro
        coro.close()

    monkeypatch.setattr(
        "src.integrations.slack.socket_mode.asyncio.run_coroutine_threadsafe",
        fake_run_coroutine_threadsafe,
    )

    client = MagicMock()
    req = MagicMock()
    req.type = "events_api"
    req.envelope_id = "env-2"
    req.payload = {"event": _message_event(text="other agent posting here")}

    handler._handle_request(client, req)

    assert "coro" in dispatched


def test_mention_still_triggers_normal_reply_flow(monkeypatch):
    handler = _socket_handler(
        _settings(**{"slack.mention_only": True, "slack.thread_ingest_all_messages": True})
    )
    handler.event_loop = MagicMock()
    handler.event_loop.is_closed.return_value = False

    dispatched = {}

    def fake_run_coroutine_threadsafe(coro, loop):
        dispatched["coro"] = coro
        coro.close()

    monkeypatch.setattr(
        "src.integrations.slack.socket_mode.asyncio.run_coroutine_threadsafe",
        fake_run_coroutine_threadsafe,
    )

    client = MagicMock()
    req = MagicMock()
    req.type = "events_api"
    req.envelope_id = "env-3"
    req.payload = {"event": _message_event(text="<@BOT1> please help")}

    handler._handle_request(client, req)

    assert "coro" in dispatched


# ---------------------------------------------------------------------------
# MessageHandler.ingest_passive_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_passive_message_stores_without_llm_call():
    handler = MessageHandler.__new__(MessageHandler)
    handler.conversation_service = MagicMock()
    handler.conversation_service.create_or_get_conversation.return_value = {
        "conversation_id": "conv-42"
    }

    result = await handler.ingest_passive_message(
        message="hi from another agent",
        channel="slack",
        contact_identifier="C123:111.1",
        metadata={"passive": True},
        max_idle_seconds=18000,
    )

    assert result == {"conversation_id": "conv-42"}
    handler.conversation_service.create_or_get_conversation.assert_called_once_with(
        channel="slack",
        contact_identifier="C123:111.1",
        max_idle_seconds=18000,
    )
    handler.conversation_service.add_message.assert_called_once_with(
        conversation_id="conv-42",
        role="user",
        content="hi from another agent",
        metadata={"passive": True},
    )
