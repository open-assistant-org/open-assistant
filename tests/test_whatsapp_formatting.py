"""Tests for converting LLM Markdown into WhatsApp formatting before sending."""

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.whatsapp.client import WhatsAppClient
from src.integrations.whatsapp.formatting import markdown_to_whatsapp


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
        ("[docs](https://example.com)", "docs (https://example.com)"),
        ("[https://example.com](https://example.com)", "https://example.com"),
        ("![chart](https://example.com/c.png)", "chart (https://example.com/c.png)"),
        ("- one\n* two\n  + nested", "- one\n- two\n  - nested"),
        ("1. first\n2. second", "1. first\n2. second"),
        ("> quoted", "> quoted"),
        ("above\n\n---\n\nbelow", "above\n\n──────────\n\nbelow"),
        ("2 * 3 * 4", "2 * 3 * 4"),
        ("snake_case_name", "snake_case_name"),
        ("", ""),
    ],
)
def test_markdown_to_whatsapp(markdown, expected):
    assert markdown_to_whatsapp(markdown) == expected


def test_code_is_left_alone():
    text = "Run `**not bold**` then:\n```python\n# not a heading\nx = a*b*c\n```"
    assert markdown_to_whatsapp(text) == (
        "Run `**not bold**` then:\n```\n# not a heading\nx = a*b*c\n```"
    )


def test_table_is_wrapped_in_code_block():
    text = "Results:\n| Name | **Score** |\n|---|---|\n| Ann | 9 |\nDone."
    assert markdown_to_whatsapp(text) == (
        "Results:\n```\n| Name | **Score** |\n|---|---|\n| Ann | 9 |\n```\nDone."
    )


def test_blank_lines_around_headings_are_kept():
    assert markdown_to_whatsapp("## Plan\n\n- **step**") == "*Plan*\n\n- *step*"


def test_send_message_converts_markdown():
    client = WhatsAppClient("http://bridge:3001")
    response = MagicMock()
    response.json.return_value = {"success": True}

    with patch("src.integrations.whatsapp.client.requests.post", return_value=response) as post:
        client.send_message("+123", "**Hello** from [here](https://x.io)")

    assert post.call_args.kwargs["json"] == {
        "phone_number": "+123",
        "message": "*Hello* from here (https://x.io)",
    }
