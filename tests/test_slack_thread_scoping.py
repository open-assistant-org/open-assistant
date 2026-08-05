"""Tests for Slack thread scoping ("Reply in Thread").

When the toggle is ON, a Slack thread must behave as its own conversation:

* every message the bot sends for that exchange goes into the thread —
  including out-of-band sub-task progress updates, not just the final reply;
* the conversation identity carries the ``thread_ts``, so context (and the
  background sub-tasks keyed off it) stay inside the thread.

When the toggle is OFF the previous channel-wide behaviour is preserved.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.slack.socket_mode import SlackSocketModeHandler
from src.services.message_handler import MessageHandler

# ---------------------------------------------------------------------------
# Progress notifications must honour the thread
# ---------------------------------------------------------------------------


def _handler_with_slack(slack_service):
    """Build a bare MessageHandler exposing only what the notifier touches."""
    handler = MessageHandler.__new__(MessageHandler)
    handler.tool_executor = SimpleNamespace(services={"slack": slack_service})
    return handler


@pytest.mark.asyncio
async def test_progress_notification_posts_into_thread():
    slack_service = MagicMock()
    handler = _handler_with_slack(slack_service)

    await handler._send_progress_notification(
        channel="slack",
        contact_identifier="C123:1699999999.000100",
        message="⏳ Sub-tasks: 1/5 finished, 4 still working…",
        reply_thread_ts="1699999999.000100",
    )

    slack_service.send_message.assert_called_once_with(
        channel="C123",
        message="⏳ Sub-tasks: 1/5 finished, 4 still working…",
        thread_ts="1699999999.000100",
    )


@pytest.mark.asyncio
async def test_progress_notification_posts_at_channel_root_when_not_threaded():
    slack_service = MagicMock()
    handler = _handler_with_slack(slack_service)

    await handler._send_progress_notification(
        channel="slack",
        contact_identifier="C123",
        message="⏳ Working…",
    )

    slack_service.send_message.assert_called_once_with(
        channel="C123",
        message="⏳ Working…",
        thread_ts=None,
    )


# ---------------------------------------------------------------------------
# Conversation identity must be thread-scoped only when the toggle is on
# ---------------------------------------------------------------------------


def _socket_handler(thread_replies: bool):
    """Build a socket-mode handler with stubbed collaborators."""
    settings_service = MagicMock()
    settings_service.get_setting.side_effect = lambda key: (
        thread_replies if key == "slack.thread_replies" else None
    )
    settings_service.get_config_with_fallback.return_value = "test-api-key"

    message_handler = MagicMock()
    message_handler.handle_message = AsyncMock(
        return_value={
            "response": "done",
            "skills_used": [],
            "tools_executed": [],
            "iterations": 1,
        }
    )

    handler = SlackSocketModeHandler.__new__(SlackSocketModeHandler)
    handler.message_handler = message_handler
    handler.slack_service = MagicMock()
    handler.settings_service = settings_service
    handler.media_handler = None
    return handler


@pytest.mark.asyncio
async def test_thread_replies_on_scopes_conversation_to_thread():
    handler = _socket_handler(thread_replies=True)

    await handler._process_and_reply(
        channel_id="C123",
        user_id="U1",
        text="hello",
        files=None,
        thread_ts="1699999999.000100",
    )

    kwargs = handler.message_handler.handle_message.call_args.kwargs
    assert kwargs["contact_identifier"] == "C123:1699999999.000100"
    assert kwargs["reply_thread_ts"] == "1699999999.000100"

    # The final reply lands in the thread too.
    assert handler.slack_service.send_message.call_args.kwargs["thread_ts"] == ("1699999999.000100")


@pytest.mark.asyncio
async def test_thread_replies_off_preserves_channel_wide_conversation():
    handler = _socket_handler(thread_replies=False)

    await handler._process_and_reply(
        channel_id="C123",
        user_id="U1",
        text="hello",
        files=None,
        thread_ts="1699999999.000100",
    )

    kwargs = handler.message_handler.handle_message.call_args.kwargs
    assert kwargs["contact_identifier"] == "C123"
    assert kwargs["reply_thread_ts"] is None
    assert handler.slack_service.send_message.call_args.kwargs["thread_ts"] is None


@pytest.mark.asyncio
async def test_separate_threads_get_separate_conversation_identities():
    """Two threads in one channel must not share a conversation."""
    handler = _socket_handler(thread_replies=True)

    await handler._process_and_reply(
        channel_id="C123", user_id="U1", text="a", files=None, thread_ts="111.1"
    )
    first = handler.message_handler.handle_message.call_args.kwargs["contact_identifier"]

    await handler._process_and_reply(
        channel_id="C123", user_id="U2", text="b", files=None, thread_ts="222.2"
    )
    second = handler.message_handler.handle_message.call_args.kwargs["contact_identifier"]

    assert first != second
    assert first == "C123:111.1"
    assert second == "C123:222.2"
