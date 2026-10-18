"""Tests for MemoryService LLM API key resolution.

The Settings UI stores ``llm.api_key`` encrypted in service_credentials, not in
the settings table, so summarization must read it from there.
"""

from unittest.mock import MagicMock

import pytest

from src.services.memory import MemoryService


def _service(settings=None, cred=None):
    settings = settings or {}
    settings_repo = MagicMock()
    settings_repo.get.side_effect = lambda key: settings.get(key)
    credentials_repo = MagicMock()
    credentials_repo.get.return_value = cred
    return MemoryService(
        message_repo=MagicMock(),
        memory_repo=MagicMock(),
        conversation_repo=MagicMock(),
        prompts_repo=MagicMock(),
        settings_repo=settings_repo,
        db_manager=MagicMock(),
        credentials_repo=credentials_repo,
    )


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)


def test_api_key_read_from_credentials():
    svc = _service(cred={"credential_data": {"api_key": "sk-cred"}})
    assert svc._get_api_key() == "sk-cred"
    assert svc._get_llm_client().config.api_key == "sk-cred"
    assert svc._get_worker_llm_client().config.api_key == "sk-cred"


def test_api_key_legacy_value_format():
    svc = _service(cred={"credential_data": {"value": "sk-legacy"}})
    assert svc._get_api_key() == "sk-legacy"


def test_api_key_credentials_take_precedence(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-env")
    svc = _service(
        settings={"llm.api_key": "sk-settings"},
        cred={"credential_data": {"api_key": "sk-cred"}},
    )
    assert svc._get_api_key() == "sk-cred"


def test_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-env")
    assert _service()._get_api_key() == "sk-env"


def test_missing_api_key_raises():
    with pytest.raises(ValueError, match="LLM_API_KEY not configured"):
        _service()._get_llm_client()


def test_credentials_error_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-env")
    svc = _service()
    svc.credentials_repo.get.side_effect = RuntimeError("decrypt failed")
    assert svc._get_api_key() == "sk-env"
