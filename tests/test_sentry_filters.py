"""Tests for Sentry instance tagging and Slack reconnect-noise filtering."""

import pytest

from src.utils.sentry import drop_transient_slack_errors, instance_domain


@pytest.mark.parametrize(
    "app_url,expected",
    [
        ("https://abc123.open-assistant.org", "abc123.open-assistant.org"),
        ("https://abc123.open-assistant.org/i/abc123", "abc123.open-assistant.org"),
        ("http://localhost:8080", None),
        ("http://127.0.0.1:8080", None),
        ("", None),
        (None, None),
    ],
)
def test_instance_domain(app_url, expected):
    assert instance_domain(app_url) == expected


def _slack_event(logger_name, message):
    return {"logger": logger_name, "logentry": {"formatted": message}, "message": message}


@pytest.mark.parametrize(
    "logger_name",
    ["slack_sdk.socket_mode.builtin.client", "slack_sdk.socket_mode.websocket_client"],
)
@pytest.mark.parametrize(
    "message",
    [
        "on_error invoked (session id: 7e2de467, error: BrokenPipeError, message: [Errno 32] Broken pipe)",
        "on_error invoked (error: ConnectionResetError, message: [Errno 104] Connection reset by peer)",
        "on_error invoked (error: WebSocketConnectionClosedException, message: Connection to remote host was lost.)",
    ],
)
def test_transient_slack_socket_errors_are_dropped(logger_name, message):
    assert drop_transient_slack_errors(_slack_event(logger_name, message), {}) is None


def test_unexpected_slack_socket_error_is_kept():
    event = _slack_event(
        "slack_sdk.socket_mode.builtin.client",
        "on_error invoked (session id: x, error: ValueError, message: boom)",
    )
    assert drop_transient_slack_errors(event, {}) is event


def test_same_error_from_other_logger_is_kept():
    event = _slack_event("src.services.slack", "on_error invoked (error: BrokenPipeError)")
    assert drop_transient_slack_errors(event, {}) is event


def test_event_without_logger_is_kept():
    event = {"message": "something broke"}
    assert drop_transient_slack_errors(event, {}) is event
