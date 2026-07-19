"""Tests for the notify_owner tool.

Covers:
- Channel auto-detection (WhatsApp preferred, Slack fallback, neither-enabled error)
- Explicit channel selection and its error paths
- The execute_tool dispatch path (regression: must route to the handler, not
  short-circuit with "Service not available: messaging")
- Registry gating: notify_owner is enabled when either WhatsApp or Slack is on
"""

from unittest.mock import MagicMock

import pytest

from src.core.tools.executor import ToolExecutor

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _settings_repo(values):
    """Fake settings repo whose ``.get(key)`` returns ``values.get(key)``."""

    repo = MagicMock()
    repo.get.side_effect = lambda k: values.get(k)
    return repo


def _service(values, send_return=None):
    """A fake whatsapp/slack service carrying a settings repo."""

    svc = MagicMock()
    svc.settings_repo = _settings_repo(values)
    if send_return is not None:
        svc.send_message_to_owner.return_value = send_return
        svc.send_message_to_default_channel.return_value = send_return
    return svc


@pytest.fixture
def executor():
    """A ToolExecutor backed by a freshly-initialized tool registry.

    Swaps the module-global registry so the test is isolated from other tests
    and from global init state, and restores it afterwards.
    """
    import src.core.tools.definitions as definitions
    import src.core.tools.registry as reg_module

    registry = reg_module.ToolRegistry()
    original = reg_module._registry
    reg_module._registry = registry
    try:
        definitions.initialize_all_tools()
        yield ToolExecutor()
    finally:
        reg_module._registry = original


# ---------------------------------------------------------------------------
# Auto-detection (channel omitted)
# ---------------------------------------------------------------------------


class TestNotifyOwnerAutoDetect:
    def test_prefers_whatsapp_when_both_enabled(self, executor):
        wa = _service(
            {"whatsapp.enabled": True, "whatsapp.phone_number": "+1"},
            send_return={"success": True, "via": "whatsapp"},
        )
        sl = _service({"slack.enabled": True, "slack.default_channel": "C"})
        executor.services["whatsapp"] = wa
        executor.services["slack"] = sl

        result = executor._handle_notify_owner({"message": "hi"})

        assert result == {"success": True, "via": "whatsapp"}
        wa.send_message_to_owner.assert_called_once_with(message="hi")
        sl.send_message_to_default_channel.assert_not_called()

    def test_falls_back_to_slack_when_only_slack_enabled(self, executor):
        wa = _service({"whatsapp.enabled": False, "whatsapp.phone_number": "+1"})
        sl = _service(
            {"slack.enabled": True, "slack.default_channel": "C"},
            send_return={"success": True, "via": "slack"},
        )
        executor.services["whatsapp"] = wa
        executor.services["slack"] = sl

        result = executor._handle_notify_owner({"message": "hi"})

        assert result == {"success": True, "via": "slack"}
        sl.send_message_to_default_channel.assert_called_once_with(message="hi")
        wa.send_message_to_owner.assert_not_called()

    def test_falls_back_to_slack_when_whatsapp_service_absent(self, executor):
        sl = _service(
            {"slack.enabled": True, "slack.default_channel": "C"},
            send_return={"success": True},
        )
        executor.services["slack"] = sl
        # No whatsapp service registered at all.

        result = executor._handle_notify_owner({"message": "hi"})

        assert result["success"] is True
        sl.send_message_to_default_channel.assert_called_once_with(message="hi")

    def test_neither_enabled_returns_error(self, executor):
        executor.services["whatsapp"] = _service({"whatsapp.enabled": False})
        executor.services["slack"] = _service({"slack.enabled": False})

        result = executor._handle_notify_owner({"message": "hi"})

        assert result["success"] is False
        assert "Neither WhatsApp nor Slack is enabled" in result["error"]

    def test_neither_service_present_returns_error(self, executor):
        # No services registered at all.
        result = executor._handle_notify_owner({"message": "hi"})

        assert result["success"] is False
        assert "Neither WhatsApp nor Slack is enabled" in result["error"]


# ---------------------------------------------------------------------------
# Explicit channel selection
# ---------------------------------------------------------------------------


class TestNotifyOwnerExplicitChannel:
    def test_explicit_whatsapp_sends(self, executor):
        wa = _service(
            {"whatsapp.enabled": True, "whatsapp.phone_number": "+1"},
            send_return={"success": True},
        )
        executor.services["whatsapp"] = wa

        result = executor._handle_notify_owner({"message": "hi", "channel": "whatsapp"})

        assert result["success"] is True
        wa.send_message_to_owner.assert_called_once_with(message="hi")

    def test_explicit_whatsapp_disabled_returns_error(self, executor):
        wa = _service({"whatsapp.enabled": False, "whatsapp.phone_number": "+1"})
        executor.services["whatsapp"] = wa

        result = executor._handle_notify_owner({"message": "hi", "channel": "whatsapp"})

        assert result["success"] is False
        assert "not enabled" in result["error"]

    def test_explicit_whatsapp_missing_phone_returns_error(self, executor):
        wa = _service({"whatsapp.enabled": True})  # no phone_number configured
        executor.services["whatsapp"] = wa

        result = executor._handle_notify_owner({"message": "hi", "channel": "whatsapp"})

        assert result["success"] is False
        assert "phone number" in result["error"].lower()

    def test_explicit_whatsapp_service_absent_returns_error(self, executor):
        result = executor._handle_notify_owner({"message": "hi", "channel": "whatsapp"})

        assert result["success"] is False
        assert "not available" in result["error"].lower()

    def test_explicit_slack_sends(self, executor):
        sl = _service(
            {"slack.enabled": True, "slack.default_channel": "C"},
            send_return={"success": True},
        )
        executor.services["slack"] = sl

        result = executor._handle_notify_owner({"message": "hi", "channel": "slack"})

        assert result["success"] is True
        sl.send_message_to_default_channel.assert_called_once_with(message="hi")

    def test_explicit_slack_disabled_returns_error(self, executor):
        sl = _service({"slack.enabled": False, "slack.default_channel": "C"})
        executor.services["slack"] = sl

        result = executor._handle_notify_owner({"message": "hi", "channel": "slack"})

        assert result["success"] is False
        assert "not enabled" in result["error"]

    def test_explicit_slack_missing_channel_returns_error(self, executor):
        sl = _service({"slack.enabled": True})  # no default_channel configured
        executor.services["slack"] = sl

        result = executor._handle_notify_owner({"message": "hi", "channel": "slack"})

        assert result["success"] is False
        assert "Default Slack channel" in result["error"]

    def test_explicit_slack_service_absent_returns_error(self, executor):
        result = executor._handle_notify_owner({"message": "hi", "channel": "slack"})

        assert result["success"] is False
        assert "not available" in result["error"].lower()

    def test_unknown_channel_returns_error(self, executor):
        result = executor._handle_notify_owner({"message": "hi", "channel": "carrier_pigeon"})

        assert result["success"] is False
        assert "Unknown channel" in result["error"]
        assert "carrier_pigeon" in result["error"]


# ---------------------------------------------------------------------------
# execute_tool dispatch path (regression)
# ---------------------------------------------------------------------------


class TestNotifyOwnerExecuteToolDispatch:
    """Regression: execute_tool must route notify_owner to _handle_notify_owner.

    Previously, notify_owner's service_name="messaging" had no entry in
    ToolExecutor.services, so execute_tool short-circuited with
    "Service not available: messaging" before the handler was ever reached.
    """

    @pytest.mark.asyncio
    async def test_execute_tool_routes_to_handler_slack_only(self, executor):
        sl = _service(
            {"slack.enabled": True, "slack.default_channel": "C"},
            send_return={"success": True, "message_id": "m1"},
        )
        executor.services["slack"] = sl

        result = await executor.execute_tool("notify_owner", {"message": "hi"})

        # The regression returned a top-level "Service not available" error.
        assert result.get("error") != "Service not available: messaging"
        assert "error" not in result
        assert result["success"] is True
        sl.send_message_to_default_channel.assert_called_once_with(message="hi")

    @pytest.mark.asyncio
    async def test_execute_tool_neither_enabled_returns_handler_error(self, executor):
        executor.services["whatsapp"] = _service({"whatsapp.enabled": False})
        executor.services["slack"] = _service({"slack.enabled": False})

        result = await executor.execute_tool("notify_owner", {"message": "hi"})

        # Handler returns its own failure dict; execute_tool wraps it as a result.
        assert result["success"] is True
        assert result["result"]["success"] is False
        assert "Neither WhatsApp nor Slack is enabled" in result["result"]["error"]


# ---------------------------------------------------------------------------
# Registry gating
# ---------------------------------------------------------------------------


class TestNotifyOwnerRegistryGating:
    """notify_owner uses the "messaging" pseudo-service and must be included in
    enabled tools when either WhatsApp or Slack is enabled."""

    @staticmethod
    def _enabled_names(executor, settings_values):
        names = {
            t.name
            for t in executor.registry.list_tools(
                _settings_repo(settings_values), enabled_only=True
            )
        }
        return names

    def test_present_when_only_slack_enabled(self, executor):
        names = self._enabled_names(executor, {"slack.enabled": True, "whatsapp.enabled": False})
        assert "notify_owner" in names

    def test_present_when_only_whatsapp_enabled(self, executor):
        names = self._enabled_names(executor, {"slack.enabled": False, "whatsapp.enabled": True})
        assert "notify_owner" in names

    def test_present_when_both_enabled(self, executor):
        names = self._enabled_names(executor, {"slack.enabled": True, "whatsapp.enabled": True})
        assert "notify_owner" in names

    def test_absent_when_neither_enabled(self, executor):
        names = self._enabled_names(executor, {"slack.enabled": False, "whatsapp.enabled": False})
        assert "notify_owner" not in names
