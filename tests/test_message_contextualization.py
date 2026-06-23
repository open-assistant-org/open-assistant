"""Tests for _contextualize_message_for_skill_selection in MessageHandler."""

from unittest.mock import MagicMock

import pytest

from src.services.message_handler import MessageHandler


def _make_handler() -> MessageHandler:
    """Return a MessageHandler with all dependencies mocked."""
    handler = MessageHandler.__new__(MessageHandler)
    handler.skill_repo = MagicMock()
    handler.conversation_service = MagicMock()
    handler.memory_service = MagicMock()
    handler.settings_service = MagicMock()
    handler.max_skills_per_request = 5
    return handler


def _user_msg(content: str) -> dict:
    return {"role": "user", "content": content}


def _assistant_msg(content: str, skills_used: list = None) -> dict:
    return {
        "role": "assistant",
        "content": content,
        "metadata": {"skills_used": skills_used or []},
    }


class TestContextualizeMessage:
    def setup_method(self):
        self.handler = _make_handler()

    def test_long_message_returned_unchanged(self):
        msg = "Please search my inbox for emails from Alice about the Q3 budget report"
        result = self.handler._contextualize_message_for_skill_selection(msg, [])
        assert result == msg

    def test_short_non_continuation_returned_unchanged(self):
        # Short but not a continuation phrase
        msg = "Hello there"
        result = self.handler._contextualize_message_for_skill_selection(msg, [])
        assert result == msg

    def test_continuation_no_history_returned_unchanged(self):
        result = self.handler._contextualize_message_for_skill_selection("go on then", [])
        assert result == "go on then"

    def test_continuation_enriched_with_prior_user_messages(self):
        history = [
            _user_msg("search my emails for invoices from Acme"),
            _assistant_msg("Found 3 emails with invoices from Acme."),
        ]
        result = self.handler._contextualize_message_for_skill_selection("go on then", history)
        assert "go on then" in result
        assert "search my emails for invoices from Acme" in result

    def test_pulls_up_to_three_prior_user_messages(self):
        history = [
            _user_msg("write a report about sales"),
            _assistant_msg("Draft started."),
            _user_msg("add a summary section"),
            _assistant_msg("Summary added."),
            _user_msg("include Q3 numbers"),
            _assistant_msg("Numbers included."),
        ]
        result = self.handler._contextualize_message_for_skill_selection("continue", history)
        assert "write a report about sales" in result
        assert "add a summary section" in result
        assert "include Q3 numbers" in result

    def test_does_not_include_current_message_as_prior_context(self):
        # If the same text appears in history, it should not be duplicated
        history = [_user_msg("yes"), _user_msg("find emails from Bob")]
        result = self.handler._contextualize_message_for_skill_selection("yes", history)
        assert result.count("yes") == 1
        assert "find emails from Bob" in result

    def test_various_continuation_phrases_are_detected(self):
        history = [_user_msg("send a whatsapp message to John")]
        for phrase in ("ok", "sure", "proceed", "do it", "go ahead", "yep", "carry on"):
            result = self.handler._contextualize_message_for_skill_selection(phrase, history)
            assert "whatsapp" in result, f"Expected enrichment for phrase: {phrase!r}"

    def test_exact_50_char_message_not_enriched(self):
        # Boundary: >= 50 chars → unchanged
        msg = "a" * 50
        result = self.handler._contextualize_message_for_skill_selection(
            msg, [_user_msg("search emails")]
        )
        assert result == msg

    def test_49_char_continuation_is_enriched(self):
        # 49-char message that contains a continuation phrase
        msg = "ok" + " " * 47  # starts with continuation phrase, total 49 chars
        result = self.handler._contextualize_message_for_skill_selection(
            msg, [_user_msg("search emails for invoices")]
        )
        assert "search emails for invoices" in result
