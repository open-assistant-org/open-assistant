"""Tests for SlackSocketModeHandler connection health tracking."""

import logging

from src.integrations.slack import socket_mode
from src.integrations.slack.socket_mode import SlackSocketModeHandler


def _handler():
    handler = SlackSocketModeHandler.__new__(SlackSocketModeHandler)
    handler._active_ws = None
    handler._connected_at = None
    handler._down_since = 0.0
    handler._outage_reported = False
    return handler


def test_close_of_replaced_socket_is_not_a_disconnect():
    handler = _handler()
    old, new = object(), object()
    handler._on_ws_open(old)
    handler._on_ws_open(new)  # client opens the replacement first...
    handler._on_ws_close(old)  # ...then closes the old socket
    assert handler._active_ws is new
    assert handler._down_since is None


def test_close_of_active_socket_marks_down_and_logs_lifetime(caplog):
    handler = _handler()
    ws = object()
    handler._on_ws_open(ws)
    with caplog.at_level(logging.INFO):
        handler._on_ws_close(ws)
    assert handler._active_ws is None
    assert handler._down_since is not None
    assert "Connection closed after" in caplog.text


def test_reconnect_after_reported_outage_warns_and_resets(caplog):
    handler = _handler()
    handler._outage_reported = True
    with caplog.at_level(logging.INFO):
        handler._on_ws_open(object())
    assert handler._outage_reported is False
    assert any(r.levelno == logging.WARNING and "restored" in r.message for r in caplog.records)


def test_watchdog_reports_a_sustained_outage_once(monkeypatch, caplog):
    handler = _handler()
    handler._down_since = 100.0
    monkeypatch.setattr(
        socket_mode.time, "monotonic", lambda: 100.0 + socket_mode.UNHEALTHY_AFTER_SECONDS + 1
    )

    class _Stop:
        """Event stub: run two watchdog iterations, then stop."""

        def __init__(self):
            self.calls = 0

        def wait(self, _timeout):
            self.calls += 1
            return self.calls > 2

    handler._stop_event = _Stop()
    with caplog.at_level(logging.INFO):
        handler._watch_health()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "No healthy connection" in errors[0].message


def test_watchdog_ignores_short_outage(monkeypatch, caplog):
    handler = _handler()
    handler._down_since = 100.0
    monkeypatch.setattr(socket_mode.time, "monotonic", lambda: 110.0)

    class _Stop:
        calls = 0

        def wait(self, _timeout):
            self.calls += 1
            return self.calls > 1

    handler._stop_event = _Stop()
    with caplog.at_level(logging.INFO):
        handler._watch_health()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
