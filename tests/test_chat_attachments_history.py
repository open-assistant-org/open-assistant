"""Chat requests keep attached files and the typed text in the user message's metadata.

``message`` carries the file context the LLM needs, so the history needs these
display fields to show the message the way the user sent it.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.chat import router
from src.core.dependencies import get_message_handler, get_settings_service
from src.models.conversation import ChatRequest

FILE_CONTEXT = '[The user attached the following file(s). ...:]\n- "notes.txt" → /tmp/uploads/abc-notes.txt\n\n'


class _Settings:
    def get_config_with_fallback(self, key, default=None):
        return {"llm.api_key": "test-key", "llm.paused": False}.get(key, default)


class _Handler:
    def __init__(self):
        self.calls = []

    async def handle_message(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "response": "Read it",
            "conversation_id": kwargs.get("conversation_id") or "conv-1",
            "skills_used": [],
            "tools_executed": [],
            "iterations": 1,
            "stuck_detected": False,
        }


@pytest.fixture
def client_and_handler():
    handler = _Handler()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_message_handler] = lambda: handler
    app.dependency_overrides[get_settings_service] = lambda: _Settings()
    return TestClient(app), handler


BODY = {
    "message": FILE_CONTEXT + "Summarise this",
    "conversation_id": "conv-1",
    "attachments": [{"filename": "notes.txt", "size": 2048, "content_type": "text/plain"}],
    "display_text": "Summarise this",
}


def test_chat_stores_attachments_and_display_text(client_and_handler):
    client, handler = client_and_handler
    assert client.post("/api/chat", json=BODY).status_code == 200
    call = handler.calls[0]
    assert call["message"] == BODY["message"]
    assert call["metadata"] == {
        "source": "chat_api",
        "attachments": [{"filename": "notes.txt", "size": 2048, "content_type": "text/plain"}],
        "display_text": "Summarise this",
    }


def test_chat_stream_stores_attachments_and_display_text(client_and_handler):
    client, handler = client_and_handler
    with client.stream("POST", "/api/chat/stream", json=BODY) as response:
        frames = [
            json.loads(line[len("data: ") :])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    assert frames[-1]["type"] == "complete"
    assert handler.calls[0]["metadata"]["source"] == "chat_api_stream"
    assert handler.calls[0]["metadata"]["display_text"] == "Summarise this"
    assert handler.calls[0]["metadata"]["attachments"][0]["filename"] == "notes.txt"


def test_plain_message_metadata_is_unchanged(client_and_handler):
    client, handler = client_and_handler
    client.post("/api/chat", json={"message": "Hello"})
    assert handler.calls[0]["metadata"] == {"source": "chat_api"}


def test_files_alone_keep_an_empty_display_text():
    request = ChatRequest(
        message=FILE_CONTEXT + "(No additional message)",
        attachments=[{"filename": "a.png", "size": 1}],
        display_text="",
    )
    assert request.history_metadata("chat_api") == {
        "source": "chat_api",
        "attachments": [{"filename": "a.png", "size": 1}],
        "display_text": "",
    }


def test_attachment_fields_are_validated(client_and_handler):
    client, _ = client_and_handler
    bad = {**BODY, "attachments": [{"filename": "x", "size": -1}]}
    assert client.post("/api/chat", json=bad).status_code == 422
