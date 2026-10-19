"""Tests for the ``onenote_create_page`` tool.

Regression coverage for ``TypeError: OutlookService.create_page() got an
unexpected keyword argument 'content_type'``: the tool schema advertises
``content_type`` but the service method did not accept it, so every LLM call
that filled it in failed.
"""

import inspect
from unittest.mock import MagicMock, patch

from src.models.outlook import OnenoteCreatePageRequest
from src.services.outlook import OutlookService


def _service_with_mock_client():
    service = OutlookService(
        settings_repo=MagicMock(),
        credentials_repo=MagicMock(),
    )
    mock_client = MagicMock()
    mock_client.create_page.return_value = {"id": "page-1"}
    return service, mock_client


def test_service_accepts_every_schema_field():
    """Every field the LLM can send must be accepted by the service method."""
    params = inspect.signature(OutlookService.create_page).parameters
    missing = set(OnenoteCreatePageRequest.model_fields) - set(params)
    assert not missing


def test_html_content_is_forwarded_unchanged():
    service, mock_client = _service_with_mock_client()
    content = "<b><u>Attendants</u></b><ul><li>Alice</li></ul>"
    with patch.object(service, "_get_client", return_value=mock_client):
        result = service.create_page(
            section_id="section-1", title="Meeting", content=content, content_type="html"
        )

    assert result == {"id": "page-1"}
    mock_client.create_page.assert_called_once_with(
        section_id="section-1", title="Meeting", content=content
    )


def test_content_type_defaults_to_html():
    service, mock_client = _service_with_mock_client()
    with patch.object(service, "_get_client", return_value=mock_client):
        service.create_page(section_id="section-1", title="Meeting", content="<p>x</p>")

    assert mock_client.create_page.call_args.kwargs["content"] == "<p>x</p>"


def test_text_content_is_escaped_and_line_breaks_preserved():
    service, mock_client = _service_with_mock_client()
    with patch.object(service, "_get_client", return_value=mock_client):
        service.create_page(
            section_id="section-1",
            title="Notes",
            content="a < b & c\r\nsecond line",
            content_type="text",
        )

    assert mock_client.create_page.call_args.kwargs["content"] == "a &lt; b &amp; c<br>second line"
