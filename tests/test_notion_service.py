"""Tests for NotionService.create_note property handling."""

from unittest.mock import MagicMock

from src.services.notion import NotionService


def _make_service() -> tuple[NotionService, MagicMock]:
    """Build a NotionService with a mocked Notion client."""
    service = NotionService(
        settings_repo=MagicMock(),
        credentials_repo=MagicMock(),
        audit_repo=MagicMock(),
    )
    client = MagicMock()
    client.create_page.return_value = {"id": "page1"}
    service._get_client = MagicMock(return_value=client)
    return service, client


def test_create_note_merges_extra_properties() -> None:
    """Extra database columns (e.g. Type/State) are merged with the title."""
    service, client = _make_service()

    service.create_note(
        title="Walk-through of Descript API plugin",
        database_id="db1",
        properties={
            "Type": {"select": {"name": "Article"}},
            "State": {"status": {"name": "In progress"}},
        },
    )

    sent = client.create_page.call_args.kwargs["properties"]
    # Title is still set...
    assert sent["Name"]["title"][0]["text"]["content"] == "Walk-through of Descript API plugin"
    # ...and the extra columns now come through to the Notion API.
    assert sent["Type"] == {"select": {"name": "Article"}}
    assert sent["State"] == {"status": {"name": "In progress"}}


def test_create_note_without_properties_sets_only_title() -> None:
    """Backward compatibility: omitting properties yields just the title column."""
    service, client = _make_service()

    service.create_note(title="Quick note", database_id="db1")

    sent = client.create_page.call_args.kwargs["properties"]
    assert list(sent.keys()) == ["Name"]
    assert sent["Name"]["title"][0]["text"]["content"] == "Quick note"
