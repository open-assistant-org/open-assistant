"""Tests for converting LLM Markdown into Slack mrkdwn before sending."""

from unittest.mock import MagicMock

import pytest

from src.integrations.slack.client import SlackClient
from src.integrations.slack.formatting import markdown_to_mrkdwn


@pytest.mark.parametrize(
    "markdown, expected",
    [
        ("**bold**", "*bold*"),
        ("*italic*", "_italic_"),
        ("_italic_", "_italic_"),
        ("**bold with *italic* inside**", "*bold with _italic_ inside*"),
        ("~~gone~~", "~gone~"),
        ("# Title", "*Title*"),
        ("### **Already bold** ###", "*Already bold*"),
        ("[docs](https://example.com)", "<https://example.com|docs>"),
        ("![chart](https://example.com/c.png)", "<https://example.com/c.png|chart>"),
        ("- one\n* two\n  - nested", "• one\n• two\n  • nested"),
        ("1. first\n2. second", "1. first\n2. second"),
        ("above\n\n---\n\nbelow", "above\n\n──────────\n\nbelow"),
        ("2 * 3 * 4", "2 * 3 * 4"),
        ("snake_case_name", "snake_case_name"),
        ("hi <@U123>, see <https://x.io|this>", "hi <@U123>, see <https://x.io|this>"),
        ("", ""),
    ],
)
def test_markdown_to_mrkdwn(markdown, expected):
    assert markdown_to_mrkdwn(markdown) == expected


def test_code_is_left_alone():
    text = "Run `**not bold**` then:\n```python\n# not a heading\nx = a*b*c\n```"
    assert markdown_to_mrkdwn(text) == (
        "Run `**not bold**` then:\n```\n# not a heading\nx = a*b*c\n```"
    )


def test_table_is_wrapped_in_code_block():
    text = "Results:\n| Name | **Score** |\n|---|---|\n| Ann | 9 |\nDone."
    assert markdown_to_mrkdwn(text) == (
        "Results:\n```\n| Name | **Score** |\n|---|---|\n| Ann | 9 |\n```\nDone."
    )


def test_blank_lines_around_headings_are_kept():
    assert markdown_to_mrkdwn("## Plan\n\n- **step**") == "*Plan*\n\n• *step*"


def test_send_message_converts_markdown():
    client = SlackClient.__new__(SlackClient)
    client.client = MagicMock()
    client.client.chat_postMessage.return_value = {"ok": True, "channel": "C1", "ts": "1.1"}

    client.send_message("C1", "**Hello** from [here](https://x.io)", thread_ts="1.0")

    client.client.chat_postMessage.assert_called_once_with(
        channel="C1", text="*Hello* from <https://x.io|here>", thread_ts="1.0"
    )
