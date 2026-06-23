"""Tests for NotionClient schema discovery."""

from unittest.mock import MagicMock

from src.integrations.notion.client import NotionClient


def test_list_data_sources_exposes_choice_options() -> None:
    """select/multi_select/status columns report their valid option names."""
    client = NotionClient(api_token="test-token")
    client.client = MagicMock()
    client.client.search.return_value = {
        "results": [
            {
                "id": "ds1",
                "title": [{"plain_text": "Diary"}],
                "url": "https://notion.so/ds1",
                "properties": {
                    "Name": {"type": "title", "title": {}},
                    "type": {
                        "type": "select",
                        "select": {"options": [{"name": "Article"}, {"name": "Diary"}]},
                    },
                    "State": {
                        "type": "status",
                        "status": {"options": [{"name": "Draft"}, {"name": "Done"}]},
                    },
                    "Tags": {
                        "type": "multi_select",
                        "multi_select": {"options": [{"name": "Work"}]},
                    },
                },
            }
        ]
    }

    props = client.list_data_sources()[0]["properties"]

    # Plain columns carry just their type...
    assert props["Name"] == {"type": "title"}
    # ...while choice columns also expose the valid option names.
    assert props["type"] == {"type": "select", "options": ["Article", "Diary"]}
    assert props["State"] == {"type": "status", "options": ["Draft", "Done"]}
    assert props["Tags"] == {"type": "multi_select", "options": ["Work"]}
