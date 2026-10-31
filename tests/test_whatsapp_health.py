"""Tests for the WhatsApp bridge health monitor."""

from unittest.mock import MagicMock

import pytest
import requests

from src.services import whatsapp_health
from src.services.whatsapp_health import (
    BridgeStatus,
    WhatsAppHealthMonitor,
    classify_health,
)

HEALTHY = {"ready": True, "state": "ready"}
DISCONNECTED = {"ready": False, "state": "disconnected", "state_reason": "NAVIGATION"}
QR = {"ready": False, "state": "qr", "state_reason": "scan"}


def _repo(values):
    repo = MagicMock()
    repo.get.side_effect = lambda k: values.get(k)
    return repo


def _slack(enabled=True):
    slack = MagicMock()
    slack.settings_repo = _repo({"slack.enabled": enabled, "slack.default_channel": "C1"})
    return slack


class _Bridge:
    """Fake WhatsAppClient: returns queued /health payloads (last one repeats)."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.restarts = 0

    def get_health(self):
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        if isinstance(payload, Exception):
            raise payload
        return payload

    def restart(self):
        self.restarts += 1
        return {"success": True}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(whatsapp_health, "CONFIRM_DELAY_SECONDS", 0)
    monkeypatch.setattr(whatsapp_health, "RECOVERY_POLL_SECONDS", 0)
    monkeypatch.setattr(whatsapp_health, "RECOVERY_TIMEOUT_SECONDS", 0.05)
    # Pretend supervisord manages the bridge, and use the HTTP restart path.
    monkeypatch.setattr(WhatsAppHealthMonitor, "_can_restart", lambda self: True)
    monkeypatch.setattr(whatsapp_health.shutil, "which", lambda _: None)


def _monitor(bridge, slack=None):
    return WhatsAppHealthMonitor(
        _repo({"whatsapp.enabled": True}), slack, client_factory=lambda: bridge
    )


# --------------------------------------------------------------- classify


@pytest.mark.parametrize(
    "payload,expected",
    [
        (HEALTHY, BridgeStatus.HEALTHY),
        (QR, BridgeStatus.NEEDS_LINK),
        (DISCONNECTED, BridgeStatus.BROKEN),
        ({"ready": False, "state": "initializing", "state_age_seconds": 10}, BridgeStatus.STARTING),
        ({"ready": False, "state": "initializing", "state_age_seconds": 999}, BridgeStatus.BROKEN),
        # Events say ready, but the live WhatsApp Web probe failed.
        ({"ready": False, "state": "ready", "probe_error": "Session closed"}, BridgeStatus.BROKEN),
        # Older bridge without lifecycle state.
        ({"ready": False}, BridgeStatus.BROKEN),
    ],
)
def test_classify_health(payload, expected):
    assert classify_health(payload).status == expected


# ------------------------------------------------------------- check_once


def test_healthy_bridge_does_nothing():
    bridge, slack = _Bridge(HEALTHY), _slack()
    monitor = _monitor(bridge, slack)

    assert monitor.check_once().status == BridgeStatus.HEALTHY
    assert bridge.restarts == 0
    slack.send_message_to_default_channel.assert_not_called()
    assert not monitor.outage_active


def test_single_blip_is_ignored():
    bridge, slack = _Bridge(DISCONNECTED, HEALTHY), _slack()
    monitor = _monitor(bridge, slack)

    assert monitor.check_once().status == BridgeStatus.HEALTHY
    assert bridge.restarts == 0
    slack.send_message_to_default_channel.assert_not_called()


def test_restart_fixes_it_without_bothering_the_owner():
    # Unhealthy twice (probe + confirm), healthy after the restart.
    bridge, slack = _Bridge(DISCONNECTED, DISCONNECTED, HEALTHY), _slack()
    monitor = _monitor(bridge, slack)

    assert monitor.check_once().status == BridgeStatus.HEALTHY
    assert bridge.restarts == 1
    slack.send_message_to_default_channel.assert_not_called()
    assert not monitor.outage_active


def test_still_broken_after_restarts_notifies_slack_once():
    bridge, slack = _Bridge(DISCONNECTED), _slack()
    monitor = _monitor(bridge, slack)

    monitor.check_once()
    assert bridge.restarts == whatsapp_health.MAX_RESTARTS_PER_OUTAGE
    assert monitor.outage_active
    slack.send_message_to_default_channel.assert_called_once()
    text = slack.send_message_to_default_channel.call_args.kwargs["message"]
    assert "WhatsApp bridge is broken" in text
    assert "disconnected: NAVIGATION" in text

    # Next check during the same outage: no new restarts, no new alert.
    monitor.check_once()
    assert bridge.restarts == whatsapp_health.MAX_RESTARTS_PER_OUTAGE
    slack.send_message_to_default_channel.assert_called_once()


def test_recovery_after_alert_sends_all_clear():
    bridge, slack = _Bridge(DISCONNECTED), _slack()
    monitor = _monitor(bridge, slack)
    monitor.check_once()

    bridge.payloads = [HEALTHY]
    monitor.check_once()

    assert slack.send_message_to_default_channel.call_count == 2
    text = slack.send_message_to_default_channel.call_args.kwargs["message"]
    assert "working again" in text
    assert not monitor.outage_active


def test_revoked_device_gets_one_restart_then_relink_instructions():
    bridge, slack = _Bridge(QR), _slack()
    monitor = _monitor(bridge, slack)

    monitor.check_once()

    assert bridge.restarts == 1
    text = slack.send_message_to_default_channel.call_args.kwargs["message"]
    assert "scan the QR code" in text


def test_retries_a_restart_after_the_retry_interval(monkeypatch):
    now = [1000.0]
    bridge, slack = _Bridge(DISCONNECTED), _slack()
    monitor = WhatsAppHealthMonitor(
        _repo({"whatsapp.enabled": True}),
        slack,
        client_factory=lambda: bridge,
        clock=lambda: now[0],
    )
    monkeypatch.setattr(monitor, "_wait_for_recovery", monitor._probe)
    monitor.check_once()
    restarts = bridge.restarts

    now[0] += whatsapp_health.RESTART_RETRY_INTERVAL_SECONDS + 1
    monitor.check_once()

    assert bridge.restarts == restarts + 1
    slack.send_message_to_default_channel.assert_called_once()  # still one alert


def test_no_restart_without_supervisord_but_still_alerts(monkeypatch):
    monkeypatch.setattr(WhatsAppHealthMonitor, "_can_restart", lambda self: False)
    bridge, slack = _Bridge(requests.ConnectionError("refused")), _slack()
    monitor = _monitor(bridge, slack)

    probe = monitor.check_once()

    assert probe.status == BridgeStatus.DOWN
    assert bridge.restarts == 0
    text = slack.send_message_to_default_channel.call_args.kwargs["message"]
    assert "couldn't restart" in text


def test_slack_disabled_logs_error_without_crashing(caplog):
    bridge, slack = _Bridge(DISCONNECTED), _slack(enabled=False)
    monitor = _monitor(bridge, slack)

    monitor.check_once()

    slack.send_message_to_default_channel.assert_not_called()
    assert "WhatsApp bridge broken" in caplog.text
    assert monitor.outage_active


def test_starting_bridge_is_left_alone():
    bridge = _Bridge({"ready": False, "state": "initializing", "state_age_seconds": 5})
    monitor = _monitor(bridge, _slack())

    assert monitor.check_once().status == BridgeStatus.STARTING
    assert bridge.restarts == 0


def test_disabled_in_managed_mode(monkeypatch):
    monkeypatch.setenv("MANAGED_API_KEY", "x")
    assert not _monitor(_Bridge(HEALTHY))._is_enabled()


# --------------------------------------------------- send-failure reporting


def test_whatsapp_send_failure_kicks_monitor(monkeypatch):
    from src.services.whatsapp import WhatsAppService

    monitor = MagicMock()
    monkeypatch.setattr(whatsapp_health, "_monitor", monitor)
    service = WhatsAppService(
        _repo({"whatsapp.enabled": True, "whatsapp.phone_number": "+1"}), MagicMock()
    )
    client = MagicMock()
    client.send_message.side_effect = requests.HTTPError("503")
    monkeypatch.setattr(service, "_get_client", lambda: client)

    with pytest.raises(requests.HTTPError):
        service.send_message_to_owner("hi")
    monitor.report_send_failure.assert_called_once()
