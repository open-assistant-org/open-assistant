"""Tests for the voice message transcription endpoint."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.whisper as whisper_module
from src.core.dependencies import get_settings_service

AUDIO = b"\x1aE\xdf\xa3 not really webm, the transcriber is stubbed"


class FakeSettings:
    def __init__(self, **values):
        self.values = values

    def get_config_with_fallback(self, key, default=None):
        return self.values.get(key, default)


def _client(monkeypatch, settings: FakeSettings, transcript="Hello there") -> tuple:
    calls = []

    def fake_transcribe(**kwargs):
        calls.append(kwargs)
        if isinstance(transcript, Exception):
            raise transcript
        return transcript

    monkeypatch.setattr(whisper_module, "transcribe_audio", fake_transcribe)
    app = FastAPI()
    app.include_router(whisper_module.router)
    app.dependency_overrides[get_settings_service] = lambda: settings
    return TestClient(app), calls


def _post(client, content=AUDIO, mimetype="audio/webm;codecs=opus"):
    return client.post("/api/whisper/transcribe", files={"file": ("voice.webm", content, mimetype)})


ENABLED = {"whisper.enabled": True, "whisper.api_key": "sk-whisper"}


class TestTranscribe:
    def test_returns_the_transcript_of_the_uploaded_recording(self, monkeypatch):
        settings = FakeSettings(**ENABLED, **{"whisper.model": "whisper-large"})
        client, calls = _client(monkeypatch, settings)

        r = _post(client)

        assert r.status_code == 200
        assert r.json() == {"text": "Hello there"}
        assert base64.b64decode(calls[0]["audio_base64"]) == AUDIO
        assert calls[0]["mimetype"] == "audio/webm;codecs=opus"
        assert calls[0]["filename"] == "voice.webm"
        assert calls[0]["api_key"] == "sk-whisper"
        assert calls[0]["base_url"] is None
        assert calls[0]["model"] == "whisper-large"

    def test_falls_back_to_the_llm_key(self, monkeypatch):
        settings = FakeSettings(**{"whisper.enabled": True, "llm.api_key": "sk-llm"})
        client, calls = _client(monkeypatch, settings)

        assert _post(client).status_code == 200
        assert calls[0]["api_key"] == "sk-llm"

    @pytest.mark.parametrize(
        "values",
        [{}, {"whisper.enabled": False, "whisper.api_key": "sk"}, {"whisper.enabled": True}],
    )
    def test_refuses_when_whisper_is_not_set_up(self, monkeypatch, values):
        client, calls = _client(monkeypatch, FakeSettings(**values))

        r = _post(client)

        assert r.status_code == 503
        assert calls == []

    def test_refuses_files_that_are_not_audio(self, monkeypatch):
        client, calls = _client(monkeypatch, FakeSettings(**ENABLED))

        assert _post(client, mimetype="application/pdf").status_code == 415
        assert calls == []

    def test_refuses_an_empty_recording(self, monkeypatch):
        client, calls = _client(monkeypatch, FakeSettings(**ENABLED))

        assert _post(client, content=b"").status_code == 400
        assert calls == []

    def test_refuses_a_recording_over_the_limit(self, monkeypatch):
        monkeypatch.setattr(whisper_module, "MAX_AUDIO_SIZE", 8)
        client, calls = _client(monkeypatch, FakeSettings(**ENABLED))

        assert _post(client).status_code == 413
        assert calls == []

    def test_reports_a_failed_transcription_without_leaking_the_cause(self, monkeypatch):
        client, _ = _client(
            monkeypatch, FakeSettings(**ENABLED), transcript=ValueError("invalid key sk-whisper")
        )

        r = _post(client)

        assert r.status_code == 502
        assert "sk-whisper" not in r.text

    def test_reports_silence(self, monkeypatch):
        client, _ = _client(monkeypatch, FakeSettings(**ENABLED), transcript="")

        assert _post(client).status_code == 422
