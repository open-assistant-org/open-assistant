"""Tests for the signed, expiring JWT helpers in src.core.jwt."""

import warnings
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from cryptography.fernet import Fernet

from src.core.jwt import (
    ALGORITHM,
    create_artifact_token,
    create_artifact_unlock_token,
    create_oauth_state,
    verify_artifact_token,
    verify_artifact_unlock_token,
    verify_oauth_state,
)


@pytest.fixture
def secret(monkeypatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    return key


def _sign(payload: dict, key: str, algorithm: str = ALGORITHM) -> str:
    return pyjwt.encode(payload, key, algorithm=algorithm)


def _exp(seconds: int = 60) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


class TestRoundTrip:
    def test_oauth_state(self, secret):
        state = create_oauth_state("my-instance")
        assert verify_oauth_state(state)
        payload = pyjwt.decode(state, secret, algorithms=[ALGORITHM])
        assert payload["instance_id"] == "my-instance"

    def test_artifact_token(self, secret):
        assert verify_artifact_token(create_artifact_token("a1")) == "a1"

    def test_artifact_unlock_token(self, secret):
        token = create_artifact_unlock_token("a1")
        assert verify_artifact_unlock_token(token, "a1")
        assert not verify_artifact_unlock_token(token, "a2")

    def test_fernet_key_has_no_key_length_warning(self, secret):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert verify_oauth_state(create_oauth_state())


class TestRejection:
    def test_wrong_purpose(self, secret):
        token = create_artifact_token("a1")
        assert not verify_oauth_state(token)
        assert not verify_artifact_unlock_token(token, "a1")
        assert verify_artifact_token(create_oauth_state()) is None

    def test_expired(self, secret):
        token = _sign({"purpose": "oauth_state", "exp": _exp(-10)}, secret)
        assert not verify_oauth_state(token)

    def test_wrong_secret(self, secret):
        token = _sign({"purpose": "oauth_state", "exp": _exp()}, Fernet.generate_key().decode())
        assert not verify_oauth_state(token)

    def test_tampered_signature(self, secret):
        header, payload, signature = create_oauth_state().split(".")
        flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
        assert not verify_oauth_state(f"{header}.{payload}.{flipped}")

    def test_alg_none(self, secret):
        token = pyjwt.encode({"purpose": "oauth_state", "exp": _exp()}, None, algorithm="none")
        assert not verify_oauth_state(token)

    def test_other_hmac_algorithm(self, secret):
        token = _sign({"purpose": "oauth_state", "exp": _exp()}, secret, "HS512")
        assert not verify_oauth_state(token)

    def test_garbage(self, secret):
        assert not verify_oauth_state("not-a-jwt")
        assert verify_artifact_token("") is None
