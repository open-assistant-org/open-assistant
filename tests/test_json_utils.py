"""Tests for LLM tool-call argument JSON repair helpers."""

import json

import pytest

from src.utils.json_utils import try_repair_json


def _repair(raw: str):
    """Mimic the caller: only invoke repair after a real parse failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        return try_repair_json(raw, hint=exc)


class TestMissingClosers:
    """The exact failure mode from the 2026-06-21 Notion update incident:
    the model drops the final closing brace on a deeply nested object."""

    def test_missing_single_closing_brace(self):
        # 3 opening braces, only 2 closing — the reported payload.
        raw = '{"properties": {"State": {"select": {"name": "DONE"}}}'
        assert _repair(raw) == {"properties": {"State": {"select": {"name": "DONE"}}}}

    def test_missing_multiple_closers(self):
        raw = '{"a": {"b": {"c": 1'
        assert _repair(raw) == {"a": {"b": {"c": 1}}}

    def test_missing_array_and_object_closers(self):
        raw = '{"items": [1, 2, 3'
        assert _repair(raw) == {"items": [1, 2, 3]}

    def test_braces_inside_string_values_are_ignored(self):
        raw = '{"text": "a { nested } brace", "n": 1'
        assert _repair(raw) == {"text": "a { nested } brace", "n": 1}

    def test_escaped_quote_inside_string(self):
        raw = '{"q": "she said \\"hi\\"", "n": 1'
        assert _repair(raw) == {"q": 'she said "hi"', "n": 1}


class TestTrailingComma:
    def test_trailing_comma_object(self):
        assert _repair('{"a": 1,}') == {"a": 1}

    def test_trailing_comma_array(self):
        assert _repair('{"a": [1, 2,]}') == {"a": [1, 2]}

    def test_trailing_comma_combined_with_missing_brace(self):
        # Both mistakes at once.
        assert _repair('{"a": [1, 2,]') == {"a": [1, 2]}


class TestCodeFences:
    def test_strips_json_fence(self):
        raw = '```json\n{"a": 1}\n```'
        assert _repair(raw) == {"a": 1}


class TestNonRepairable:
    """Cases that must NOT be silently "repaired" into a valid-but-wrong dict."""

    def test_stray_closing_brace_returns_none(self):
        assert _repair('{"a": 1}}') is None

    def test_unterminated_string_returns_none(self):
        assert _repair('{"a": "hello') is None

    def test_garbage_returns_none(self):
        assert _repair("not json at all") is None

    def test_empty_string_returns_none(self):
        assert try_repair_json("") is None


@pytest.mark.parametrize(
    "valid",
    ['{"a": 1}', '{"properties": {"State": {"status": {"name": "Done"}}}}'],
)
def test_already_valid_passes_through(valid):
    assert _repair(valid) == json.loads(valid)
