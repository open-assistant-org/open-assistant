"""Sentry initialisation: instance identification and noise filtering."""

import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# Loggers whose "on_error invoked" records are emitted by slack_sdk's Socket Mode
# clients on every dropped websocket. The client reconnects on its own, so these
# are expected churn; SlackSocketModeHandler reports a sustained outage itself.
_SLACK_SOCKET_LOGGER_PREFIX = "slack_sdk.socket_mode"
_TRANSIENT_ERRORS = {
    "BrokenPipeError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "ConnectionRefusedError",
    "TimeoutError",
    "WebSocketConnectionClosedException",
    "WebSocketTimeoutException",
    "WebSocketBadStatusException",
    "SSLEOFError",
    "SSLError",
    "gaierror",
}
_ON_ERROR_RE = re.compile(r"on_error invoked .*?error: (\w+)")


def instance_domain(app_url: Optional[str]) -> Optional[str]:
    """Return the host of ``app_url`` (e.g. ``abc123.open-assistant.org``).

    Returns None for unset or local URLs, which identify nothing useful.
    """
    host = urlparse(app_url or "").hostname
    if not host or host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return None
    return host


def drop_transient_slack_errors(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """``before_send`` hook: drop reconnect noise from slack_sdk's socket clients.

    The records still reach Sentry as breadcrumbs on any later event.
    """
    if str(event.get("logger") or "").startswith(_SLACK_SOCKET_LOGGER_PREFIX):
        message = (event.get("logentry") or {}).get("formatted") or event.get("message") or ""
        match = _ON_ERROR_RE.search(message)
        if match and match.group(1) in _TRANSIENT_ERRORS:
            return None
    return event


def init_sentry(dsn: str, release: str, environment: str, app_url: Optional[str]) -> None:
    """Initialise Sentry, tagging every event with the instance it came from."""
    import sentry_sdk

    domain = instance_domain(app_url)
    sentry_sdk.init(
        dsn=dsn,
        release=release,
        environment=environment,
        # Defaults to the container id, which says nothing about whose instance it is.
        server_name=domain,
        before_send=drop_transient_slack_errors,
    )
    if domain:
        sentry_sdk.set_tag("instance_domain", domain)
    instance_id = os.getenv("INSTANCE_ID")
    if instance_id:
        sentry_sdk.set_tag("instance_id", instance_id)
