"""Tests for other bots/agents in Slack threads.

Covers: ingesting other bots' thread messages (they used to be dropped by a
blanket ``bot_id`` filter), speaker labels, the bot allow-list that gates
bot-triggered replies, and the consecutive bot-reply cap.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks

from src.api.slack import handle_slack_event
from src.integrations.slack import participants
from src.integrations.slack.participants import (
    Action,
    BotReplyGuard,
    SlackSender,
    format_with_speaker,
    route_message_event,
)
from src.integrations.slack.socket_mode import SlackSocketModeHandler

OWN_USER = "UOWN"
OWN_BOT = "BOWN"


@pytest.fixture(autouse=True)
def _clear_state():
    participants.clear_name_cache()
    participants.bot_reply_guard.reset("C1:1.1")
    yield
    participants.clear_name_cache()


def _event(text="hello", user="U1", bot_id=None, subtype=None, **extra):
    event = {"type": "message", "channel": "C1", "text": text, "ts": "1.1", "thread_ts": "1.1"}
    if user:
        event["user"] = user
    if bot_id:
        event["bot_id"] = bot_id
    if subtype:
        event["subtype"] = subtype
    event.update(extra)
    return event


def _route(event, allowed_bots=(), guard=None, **overrides):
    kwargs = dict(
        has_files=False,
        own_user_id=OWN_USER,
        own_bot_id=OWN_BOT,
        mention_only=True,
        ingest_all=True,
        reply_to_bots=False,
        thread_scoped=True,
        conversation_key="C1:1.1",
        is_user_allowed=lambda uid: True,
        is_bot_allowed=lambda sender: participants.bot_in_allowlist(sender, set(allowed_bots)),
        guard=guard or BotReplyGuard(),
    )
    kwargs.update(overrides)
    return route_message_event(event, **kwargs)


MENTION = f"<@{OWN_USER}> hi"


# ---------------------------------------------------------------------------
# Ingesting other bots (the original bug)
# ---------------------------------------------------------------------------


def test_bot_message_without_mention_is_ingested():
    route = _route(_event("steven says 4", user="USTEVEN", bot_id="BSTEVEN"))
    assert route.action == Action.INGEST
    assert route.sender.is_bot


def test_legacy_bot_message_without_user_uses_bot_id_as_sender():
    route = _route(_event("webhook says hi", user=None, bot_id="BHOOK", subtype="bot_message"))
    assert route.action == Action.INGEST
    assert route.sender.id == "BHOOK"


def test_own_messages_are_never_ingested_or_answered():
    by_user = _route(_event(MENTION, user=OWN_USER, bot_id=OWN_BOT))
    by_bot_id = _route(_event(MENTION, user=None, bot_id=OWN_BOT, subtype="bot_message"))
    assert by_user.action == Action.IGNORE
    assert by_bot_id.action == Action.IGNORE


def test_bot_messages_ignored_when_not_mention_only():
    route = _route(_event("hi", bot_id="BX"), mention_only=False, ingest_all=False)
    assert route.action == Action.IGNORE


def test_bot_not_ingested_without_ingest_all():
    route = _route(_event("hi", bot_id="BX"), ingest_all=False)
    assert route.action == Action.IGNORE


def test_bot_ingest_not_blocked_by_human_allowlist():
    route = _route(_event("hi", user="UBOT", bot_id="BX"), is_user_allowed=lambda uid: False)
    assert route.action == Action.INGEST


def test_human_blocked_by_human_allowlist():
    route = _route(_event(MENTION), is_user_allowed=lambda uid: False)
    assert route.action == Action.IGNORE


def test_unknown_own_identity_does_not_ingest_bots():
    route = _route(_event("hi", bot_id="BX"), own_user_id=None, own_bot_id=None)
    assert route.action == Action.IGNORE


# ---------------------------------------------------------------------------
# Bot mentions: toggle + allow-list + loop cap
# ---------------------------------------------------------------------------


def test_bot_mention_with_toggle_off_is_ingested_not_answered():
    route = _route(_event(MENTION, user="USTEVEN", bot_id="BSTEVEN"), allowed_bots={"USTEVEN"})
    assert route.action == Action.INGEST


@pytest.mark.parametrize("allowed", [{"USTEVEN"}, {"BSTEVEN"}])
def test_allowed_bot_mention_gets_reply_by_user_or_bot_id(allowed):
    route = _route(
        _event(MENTION, user="USTEVEN", bot_id="BSTEVEN"),
        allowed_bots=allowed,
        reply_to_bots=True,
    )
    assert route.action == Action.REPLY
    assert route.text == "hi"


@pytest.mark.parametrize("allowed", [set(), {"UOTHER"}])
def test_unlisted_bot_mention_not_answered_but_ingested(allowed):
    route = _route(
        _event(MENTION, user="USTEVEN", bot_id="BSTEVEN"),
        allowed_bots=allowed,
        reply_to_bots=True,
    )
    assert route.action == Action.INGEST


def test_unlisted_bot_mention_ignored_without_ingest_all():
    route = _route(
        _event(MENTION, user="USTEVEN", bot_id="BSTEVEN"),
        reply_to_bots=True,
        ingest_all=False,
    )
    assert route.action == Action.IGNORE


def test_consecutive_bot_replies_are_capped_until_a_human_posts():
    guard = BotReplyGuard(max_consecutive=3)
    bot = _event(MENTION, user="USTEVEN", bot_id="BSTEVEN")

    actions = [
        _route(bot, allowed_bots={"USTEVEN"}, reply_to_bots=True, guard=guard).action
        for _ in range(4)
    ]
    assert actions == [Action.REPLY] * 3 + [Action.INGEST]

    _route(_event("a human speaks"), guard=guard)  # resets the counter
    again = _route(bot, allowed_bots={"USTEVEN"}, reply_to_bots=True, guard=guard)
    assert again.action == Action.REPLY


def test_human_mention_still_replies():
    route = _route(_event(MENTION))
    assert route.action == Action.REPLY
    assert route.text == "hi"


# ---------------------------------------------------------------------------
# Speaker labels
# ---------------------------------------------------------------------------


def _lookup(users):
    return lambda uid: users[uid]


def test_bot_label_uses_bot_profile_name():
    sender = SlackSender(id="USTEVEN", is_bot=True, bot_id="BS", name_hint="Steven")
    assert format_with_speaker("2+2=4", sender, _lookup({}), False) == "[Steven]: 2+2=4"
    assert format_with_speaker("2+2=4", sender, _lookup({}), True) == "[Steven <@USTEVEN>]: 2+2=4"


def test_human_label_uses_display_name_and_annotates_mentions():
    users = {
        "U1": {"display_name": "Oli", "real_name": "Oliver"},
        "USTEVEN": {"display_name": "", "real_name": "Steven", "name": "steven"},
    }
    sender = SlackSender(id="U1", is_bot=False)
    text = "ask <@USTEVEN> please"
    assert format_with_speaker(text, sender, _lookup(users), False) == "[Oli]: ask @Steven please"
    assert (
        format_with_speaker(text, sender, _lookup(users), True)
        == "[Oli <@U1>]: ask @Steven (<@USTEVEN>) please"
    )


def test_label_falls_back_to_raw_id_when_lookup_fails():
    def boom(uid):
        raise RuntimeError("users.info failed")

    sender = SlackSender(id="U9", is_bot=False)
    assert format_with_speaker("hi <@U8>", sender, boom, False) == "[U9]: hi <@U8>"


# ---------------------------------------------------------------------------
# Socket Mode dispatch
# ---------------------------------------------------------------------------


def _settings(**overrides):
    values = {
        "slack.mention_only": True,
        "slack.thread_replies": True,
        "slack.thread_ingest_all_messages": True,
        "slack.reply_to_bots": False,
    }
    values.update(overrides)
    svc = MagicMock()
    svc.get_setting.side_effect = lambda key: values.get(key)
    svc.get_config_with_fallback.return_value = "key"
    return svc


def _socket_handler(settings, allowed_bots=()):
    handler = SlackSocketModeHandler.__new__(SlackSocketModeHandler)
    handler.message_handler = MagicMock()
    handler.message_handler.ingest_passive_message = AsyncMock(
        return_value={"conversation_id": "c"}
    )
    handler.slack_service = MagicMock()
    handler.slack_service.is_user_allowed.return_value = True
    handler.slack_service.is_bot_allowed.side_effect = lambda s: participants.bot_in_allowlist(
        s, set(allowed_bots)
    )
    handler.slack_service.get_user_display_info.side_effect = lambda uid: {"display_name": uid}
    handler.settings_service = settings
    handler.media_handler = None
    handler.event_loop = MagicMock()
    handler.event_loop.is_closed.return_value = False
    handler._bot_user_id = OWN_USER
    handler._bot_id = OWN_BOT
    return handler


def _dispatch(handler, event, monkeypatch):
    sent = []

    def fake(coro, loop):
        sent.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr("src.integrations.slack.socket_mode.asyncio.run_coroutine_threadsafe", fake)
    req = MagicMock()
    req.type = "events_api"
    req.payload = {"event": event}
    handler._handle_request(MagicMock(), req)
    return sent


def test_socket_mode_ingests_bot_message(monkeypatch):
    handler = _socket_handler(_settings())
    event = _event("steven says 4", user="USTEVEN", bot_id="BS")
    assert _dispatch(handler, event, monkeypatch) == ["_ingest_thread_message"]


def test_socket_mode_replies_to_allowed_bot_mention(monkeypatch):
    handler = _socket_handler(_settings(**{"slack.reply_to_bots": True}), {"BS"})
    event = _event(MENTION, user="USTEVEN", bot_id="BS")
    assert _dispatch(handler, event, monkeypatch) == ["_process_and_reply"]


def test_socket_mode_does_not_reply_to_unlisted_bot_mention(monkeypatch):
    handler = _socket_handler(_settings(**{"slack.reply_to_bots": True}))
    event = _event(MENTION, user="USTEVEN", bot_id="BS")
    assert _dispatch(handler, event, monkeypatch) == ["_ingest_thread_message"]


def test_socket_mode_ignores_own_message(monkeypatch):
    handler = _socket_handler(_settings())
    event = _event("my own reply", user=OWN_USER, bot_id=OWN_BOT)
    assert _dispatch(handler, event, monkeypatch) == []


@pytest.mark.asyncio
async def test_ingested_bot_message_is_labelled_in_history():
    handler = _socket_handler(_settings())
    sender = SlackSender(id="USTEVEN", is_bot=True, bot_id="BS", name_hint="Steven")
    labelled = format_with_speaker("2+2=4", sender, handler._lookup_user, False)

    await handler._ingest_thread_message("C1", "USTEVEN", labelled, "1.1", sender)

    kwargs = handler.message_handler.ingest_passive_message.call_args.kwargs
    assert kwargs["message"] == "[Steven]: 2+2=4"
    assert kwargs["contact_identifier"] == "C1:1.1"
    assert kwargs["metadata"]["is_bot"] is True


# ---------------------------------------------------------------------------
# Events API webhook
# ---------------------------------------------------------------------------


async def _webhook_call(event, settings, allowed_bots=()):
    request = MagicMock()
    request.json = AsyncMock(return_value={"event": event})
    tasks = BackgroundTasks()
    slack_service = MagicMock()
    slack_service.get_own_ids.return_value = {"user_id": OWN_USER, "bot_id": OWN_BOT}
    slack_service.is_user_allowed.return_value = True
    slack_service.is_bot_allowed.side_effect = lambda s: participants.bot_in_allowlist(
        s, set(allowed_bots)
    )
    slack_service.get_user_display_info.side_effect = lambda uid: {"display_name": uid}
    message_handler = MagicMock()
    await handle_slack_event(request, tasks, message_handler, settings, slack_service, MagicMock())
    return tasks, message_handler


@pytest.mark.asyncio
async def test_webhook_ingests_bot_message_with_speaker_label():
    event = _event("steven says 4", user="USTEVEN", bot_id="BS", bot_profile={"name": "Steven"})
    tasks, message_handler = await _webhook_call(event, _settings())

    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].func is message_handler.ingest_passive_message
    assert tasks.tasks[0].kwargs["message"] == "[Steven]: steven says 4"
    assert tasks.tasks[0].kwargs["contact_identifier"] == "C1:1.1"


@pytest.mark.asyncio
async def test_webhook_does_not_reply_to_unlisted_bot_mention():
    event = _event(MENTION, user="USTEVEN", bot_id="BS")
    tasks, message_handler = await _webhook_call(event, _settings(**{"slack.reply_to_bots": True}))

    assert [t.func for t in tasks.tasks] == [message_handler.ingest_passive_message]


@pytest.mark.asyncio
async def test_webhook_replies_to_allowed_bot_mention():
    event = _event(MENTION, user="USTEVEN", bot_id="BS")
    tasks, message_handler = await _webhook_call(
        event, _settings(**{"slack.reply_to_bots": True}), {"USTEVEN"}
    )

    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].func is not message_handler.ingest_passive_message
