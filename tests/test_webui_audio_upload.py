"""Web UI audio upload: transcription + note via the shared MediaHandler."""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import uploads
from src.core.dependencies import get_webui_media_handler
from src.services.whatsapp_media import MediaProcessingResult


def _client(handler, tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path)
    app = FastAPI()
    app.include_router(uploads.router)
    app.dependency_overrides[get_webui_media_handler] = lambda: handler
    app.dependency_overrides[uploads.get_optional_ocr_service] = lambda: None
    return TestClient(app)


def test_audio_upload_returns_transcription_and_note(tmp_path, monkeypatch):
    handler = MagicMock()
    handler.process_media.return_value = MediaProcessingResult(
        effective_message="[Voice message transcription]: hello",
        note_url="https://notion.so/x",
        transcription="hello",
    )
    client = _client(handler, tmp_path, monkeypatch)
    resp = client.post("/api/upload", files={"file": ("rec.webm", b"abc", "audio/webm")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcription"] == "hello"
    assert body["note_url"] == "https://notion.so/x"
    assert handler.process_media.call_args.kwargs["mimetype"] == "audio/webm"


def test_non_audio_upload_skips_transcription(tmp_path, monkeypatch):
    handler = MagicMock()
    client = _client(handler, tmp_path, monkeypatch)
    resp = client.post("/api/upload", files={"file": ("a.txt", b"abc", "text/plain")})
    assert resp.status_code == 200
    assert "transcription" not in resp.json()
    handler.process_media.assert_not_called()
