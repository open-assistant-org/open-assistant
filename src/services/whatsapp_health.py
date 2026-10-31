"""Watchdog for the WhatsApp bridge: detect breakage, restart, alert via Slack.

The Node.js bridge can break without its process exiting, so supervisord
never restarts it. Two common ways:

* the WhatsApp Web session drops (``disconnected``) or Chromium dies, and the
  bridge keeps answering HTTP with ``503 not ready``;
* the linked device gets revoked, so the bridge waits on a QR code nobody
  will scan.

This monitor probes the bridge periodically, and right away when a send
fails. When the bridge stays unhealthy it restarts it through supervisord
(often enough on its own) and checks again. If it is still broken after that,
it tells the owner once per outage on Slack, and once more when WhatsApp
comes back.

Messages that fail on WhatsApp still go out on Slack through the normal
delivery paths (``notify_owner`` falls back automatically). The alert sent
here is an extra message on top of those that explains why.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

import requests

from src.integrations.whatsapp.client import WhatsAppClient
from src.utils.logger import get_logger
from src.utils.settings import settings_truthy

logger = get_logger(__name__)

# How often the bridge is probed while everything is fine.
CHECK_INTERVAL_SECONDS = int(os.getenv("WHATSAPP_HEALTH_CHECK_INTERVAL_SECONDS", "60"))
# An unhealthy probe is re-checked after this delay before acting, so a single
# blip (or a probe racing a reconnect) doesn't trigger a restart.
CONFIRM_DELAY_SECONDS = 15
# Booting Chromium and loading WhatsApp Web can take a while; within this
# window "initializing"/"authenticated" counts as starting, not broken.
STARTUP_GRACE_SECONDS = 180
# After a restart, how long to wait for the bridge to become ready again.
RECOVERY_TIMEOUT_SECONDS = 150
RECOVERY_POLL_SECONDS = 5
# Restarts tried right away when an outage starts...
MAX_RESTARTS_PER_OUTAGE = 2
# ...and, if it is still down, one more attempt this often.
RESTART_RETRY_INTERVAL_SECONDS = 30 * 60

SUPERVISOR_SOCKET = os.getenv("SUPERVISOR_SOCKET", "/tmp/supervisor.sock")
SUPERVISOR_PROGRAM = "whatsapp-bridge"


class BridgeStatus(str, Enum):
    HEALTHY = "healthy"
    STARTING = "starting"  # booting, within the grace period
    NEEDS_LINK = "needs_link"  # waiting for a QR scan (linked device revoked)
    BROKEN = "broken"  # process up but WhatsApp not usable
    DOWN = "down"  # bridge process not reachable at all


@dataclass
class Probe:
    status: BridgeStatus
    detail: str = ""


def classify_health(health: Dict[str, Any]) -> Probe:
    """Turn the bridge's ``/health`` payload into a :class:`Probe`."""
    if health.get("ready"):
        return Probe(BridgeStatus.HEALTHY)

    state = health.get("state")
    reason = health.get("state_reason")
    age = health.get("state_age_seconds") or 0

    if state == "qr":
        return Probe(
            BridgeStatus.NEEDS_LINK,
            "the linked device was logged out or revoked; a new QR code has to be scanned",
        )
    if state in ("initializing", "authenticated"):
        if age < STARTUP_GRACE_SECONDS:
            return Probe(BridgeStatus.STARTING, f"{state} for {age}s")
        return Probe(BridgeStatus.BROKEN, f"stuck in '{state}' for {age}s")
    if state == "ready":
        # Client events say ready, but the live probe of WhatsApp Web failed
        # (dead Chromium page, dropped socket, ...).
        detail = health.get("probe_error") or f"WhatsApp Web state is {health.get('wa_state')}"
        return Probe(BridgeStatus.BROKEN, f"connection lost ({detail})")
    if state:
        return Probe(BridgeStatus.BROKEN, f"{state}: {reason}" if reason else state)
    # Older bridge without lifecycle state reporting.
    return Probe(BridgeStatus.BROKEN, "WhatsApp client not ready")


class WhatsAppHealthMonitor:
    """Background thread that keeps the WhatsApp bridge healthy (see module docstring)."""

    def __init__(
        self,
        settings_repo: Any,
        slack_service: Optional[Any] = None,
        client_factory: Optional[Callable[[], WhatsAppClient]] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.settings_repo = settings_repo
        self.slack_service = slack_service
        self._client_factory = client_factory or self._default_client
        self._clock = clock

        self._stop_event = threading.Event()
        self._kick_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()  # one check at a time

        # Outage bookkeeping (reset once the bridge is healthy again).
        self._outage_since: Optional[float] = None
        self._notified = False  # outage reported (log + Slack attempt)
        self._slack_alerted = False  # owner actually got the Slack alert
        self._restarts = 0
        self._last_restart_at: Optional[float] = None
        self._last_probe: Optional[Probe] = None

    # ------------------------------------------------------------------ API

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="whatsapp-health-monitor", daemon=True
        )
        self._thread.start()
        logger.info(f"[WhatsApp Health] Monitor started (every {CHECK_INTERVAL_SECONDS}s)")

    def stop(self) -> None:
        self._stop_event.set()
        self._kick_event.set()

    def report_send_failure(self, error: Exception) -> None:
        """Run a check now instead of waiting for the next interval."""
        logger.info(f"[WhatsApp Health] Send failed ({error}); checking the bridge now")
        self._kick_event.set()

    @property
    def outage_active(self) -> bool:
        """True while WhatsApp is known to be broken (confirmed by a re-check)."""
        return self._outage_since is not None

    # ------------------------------------------------------------- the loop

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._is_enabled():
                    self.check_once()
            except Exception as e:  # never let the watchdog die
                logger.warning(f"[WhatsApp Health] Check failed unexpectedly: {e}", exc_info=True)
            self._kick_event.wait(CHECK_INTERVAL_SECONDS)
            self._kick_event.clear()

    def _is_enabled(self) -> bool:
        if os.getenv("MANAGED_API_KEY"):
            return False  # bridge is not run in managed mode
        return settings_truthy(self.settings_repo.get("whatsapp.enabled"))

    def check_once(self) -> Probe:
        """Probe the bridge and restart / notify as needed. Returns the final probe."""
        with self._lock:
            probe = self._probe()
            if probe.status in (BridgeStatus.HEALTHY, BridgeStatus.STARTING):
                return self._settle(probe)

            # Confirm before acting.
            if self._stop_event.wait(CONFIRM_DELAY_SECONDS):
                return probe
            probe = self._probe()
            if probe.status in (BridgeStatus.HEALTHY, BridgeStatus.STARTING):
                return self._settle(probe)

            if self._outage_since is None:
                self._outage_since = self._clock()
                logger.warning(f"[WhatsApp Health] Bridge unhealthy: {probe.detail}")

            for _ in range(self._restart_budget(probe)):
                if not self._restart():
                    break
                probe = self._wait_for_recovery()
                if probe.status == BridgeStatus.HEALTHY:
                    logger.info("[WhatsApp Health] Bridge recovered after restart")
                    return self._settle(probe)
                if probe.status == BridgeStatus.NEEDS_LINK:
                    break  # a restart can't restore a revoked session

            if not self._notified:
                self._notify_outage(probe)
            self._last_probe = probe
            return probe

    # -------------------------------------------------------------- helpers

    def _default_client(self) -> WhatsAppClient:
        bridge_url = self.settings_repo.get("whatsapp.bridge_url") or "http://localhost:3001"
        return WhatsAppClient(bridge_url=bridge_url)

    def _probe(self) -> Probe:
        try:
            return classify_health(self._client_factory().get_health())
        except requests.RequestException as e:
            return Probe(BridgeStatus.DOWN, f"bridge not responding ({e.__class__.__name__})")

    def _settle(self, probe: Probe) -> Probe:
        """Record a healthy/starting probe; close the outage if healthy."""
        self._last_probe = probe
        if probe.status == BridgeStatus.HEALTHY and self._outage_since is not None:
            down_for = self._clock() - self._outage_since
            logger.info(f"[WhatsApp Health] WhatsApp healthy again after {down_for:.0f}s")
            if self._slack_alerted:
                self._notify_slack(
                    "✅ **WhatsApp is working again.** The bridge recovered, so I'm back "
                    "to messaging you on WhatsApp."
                )
            self._outage_since = None
            self._notified = False
            self._slack_alerted = False
            self._restarts = 0
            self._last_restart_at = None
        return probe

    def _restart_budget(self, probe: Probe) -> int:
        """How many restarts to try now for this outage."""
        if not self._can_restart():
            return 0
        if probe.status == BridgeStatus.NEEDS_LINK:
            # One restart sometimes clears a stale session; more won't help.
            return 1 if self._restarts == 0 else 0
        if self._restarts < MAX_RESTARTS_PER_OUTAGE:
            return MAX_RESTARTS_PER_OUTAGE - self._restarts
        if (
            self._last_restart_at is not None
            and self._clock() - self._last_restart_at >= RESTART_RETRY_INTERVAL_SECONDS
        ):
            return 1
        return 0

    def _can_restart(self) -> bool:
        # Only restart when supervisord manages the bridge; otherwise an exit
        # would leave it down for good.
        return os.path.exists(SUPERVISOR_SOCKET)

    def _restart(self) -> bool:
        """Restart the bridge process. Returns True when a restart was triggered."""
        self._restarts += 1
        self._last_restart_at = self._clock()
        logger.warning(
            f"[WhatsApp Health] Restarting the WhatsApp bridge (attempt {self._restarts})"
        )

        supervisorctl = shutil.which("supervisorctl")
        if supervisorctl:
            try:
                result = subprocess.run(
                    [
                        supervisorctl,
                        "-s",
                        f"unix://{SUPERVISOR_SOCKET}",
                        "restart",
                        SUPERVISOR_PROGRAM,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    return True
                logger.warning(
                    f"[WhatsApp Health] supervisorctl restart failed: "
                    f"{(result.stdout + result.stderr).strip()}"
                )
            except (OSError, subprocess.SubprocessError) as e:
                logger.warning(f"[WhatsApp Health] supervisorctl restart failed: {e}")

        # Fallback: ask the bridge to exit; supervisord brings it back up.
        try:
            self._client_factory().restart()
            return True
        except requests.RequestException as e:
            logger.warning(f"[WhatsApp Health] Bridge restart endpoint failed: {e}")
            return False

    def _wait_for_recovery(self) -> Probe:
        deadline = self._clock() + RECOVERY_TIMEOUT_SECONDS
        probe = Probe(BridgeStatus.DOWN, "restarting")
        while self._clock() < deadline:
            if self._stop_event.wait(RECOVERY_POLL_SECONDS):
                break
            probe = self._probe()
            if probe.status in (BridgeStatus.HEALTHY, BridgeStatus.NEEDS_LINK):
                return probe
        if probe.status == BridgeStatus.STARTING:
            probe = Probe(BridgeStatus.BROKEN, f"did not become ready ({probe.detail})")
        return probe

    def _notify_outage(self, probe: Probe) -> None:
        restarted = (
            f"I restarted the WhatsApp bridge {self._restarts}× but it's still not working."
            if self._restarts
            else "I couldn't restart the WhatsApp bridge automatically."
        )
        if probe.status == BridgeStatus.NEEDS_LINK:
            action = (
                "Please re-link the device: open **Settings → Integrations → WhatsApp** and "
                "scan the QR code with WhatsApp on your phone (Settings → Linked Devices → "
                "Link a Device)."
            )
        else:
            action = (
                "Please check the WhatsApp connection in **Settings → Integrations → WhatsApp** "
                "and the linked device on your phone (WhatsApp → Settings → Linked Devices)."
            )
        message = (
            f"⚠️ **Your WhatsApp bridge is broken** ({probe.detail}).\n"
            f"{restarted} Until it's fixed I can't reach you on WhatsApp, so I'll use Slack "
            f"instead.\n{action}"
        )
        # One error per outage, so it shows up in Sentry even without Slack.
        logger.error(f"[WhatsApp Health] WhatsApp bridge broken: {probe.detail}")
        # Report once per outage even if Slack fails: the error above is in
        # Sentry, and retrying every minute would only spam.
        self._notified = True
        self._slack_alerted = self._notify_slack(message)

    def _notify_slack(self, message: str) -> bool:
        slack = self.slack_service
        if not slack:
            return False
        repo = slack.settings_repo
        if not settings_truthy(repo.get("slack.enabled")) or not repo.get("slack.default_channel"):
            logger.info("[WhatsApp Health] Slack not configured; skipping owner notification")
            return False
        try:
            slack.send_message_to_default_channel(message=message)
            return True
        except Exception as e:
            logger.warning(f"[WhatsApp Health] Failed to notify owner on Slack: {e}")
            return False


# Process-wide instance, so WhatsAppService (created per request) can report
# send failures and notify_owner can check for an active outage.
_monitor: Optional[WhatsAppHealthMonitor] = None


def set_whatsapp_health_monitor(monitor: Optional[WhatsAppHealthMonitor]) -> None:
    global _monitor
    _monitor = monitor


def get_whatsapp_health_monitor() -> Optional[WhatsAppHealthMonitor]:
    return _monitor
