"""Tests for the managed backup endpoints and the user-facing backup lockout."""

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.managed as managed_module
import src.core.encryption as encryption_module
from src.api.backup import get_backup_service
from src.api.backup import router as backup_router
from src.core.database import DatabaseManager
from src.services.backup import BackupService

MANAGED_KEY = "managed-test-key"
BUNDLE_SECRET = "s" * 40


def _service(tmp_path: Path, key: str) -> BackupService:
    os.environ["ENCRYPTION_KEY"] = key
    encryption_module._encryption_service = None
    db = DatabaseManager(str(tmp_path / "assistant.db"))
    db.init_database()
    return BackupService(
        db,
        data_dir=str(tmp_path / "data"),
        artifacts_dir=str(tmp_path / "data" / "artifacts"),
        outlook_token_cache_path=str(tmp_path / "data" / "outlook_token_cache.json"),
    )


@pytest.fixture(autouse=True)
def reset_encryption():
    encryption_module._encryption_service = None
    yield
    encryption_module._encryption_service = None


def _managed_client(monkeypatch, service: BackupService) -> TestClient:
    monkeypatch.setattr(managed_module, "_MANAGED_API_KEY", MANAGED_KEY)
    monkeypatch.setattr(managed_module, "_backup_service", lambda db: service)
    app = FastAPI()
    app.state.db_manager = service.db_manager
    app.include_router(managed_module.router)
    return TestClient(app)


HEADERS = {"X-Managed-Key": MANAGED_KEY}


class TestManagedBackup:
    def test_requires_managed_key(self, tmp_path, monkeypatch):
        client = _managed_client(monkeypatch, _service(tmp_path, Fernet.generate_key().decode()))
        assert (
            client.post("/managed/backup/export", json={"secret": BUNDLE_SECRET}).status_code == 401
        )
        r = client.post(
            "/managed/backup/export",
            json={"secret": BUNDLE_SECRET},
            headers={"X-Managed-Key": "wrong"},
        )
        assert r.status_code == 401
        r = client.post(
            "/managed/backup/import",
            files={"bundle": ("b.json.gz", b"x")},
            data={"secret": BUNDLE_SECRET},
        )
        assert r.status_code == 401

    def test_export_rejects_short_secret(self, tmp_path, monkeypatch):
        client = _managed_client(monkeypatch, _service(tmp_path, Fernet.generate_key().decode()))
        r = client.post("/managed/backup/export", json={"secret": "short"}, headers=HEADERS)
        assert r.status_code == 400

    def test_export_import_roundtrip(self, tmp_path, monkeypatch):
        source = _service(tmp_path / "a", Fernet.generate_key().decode())
        bundle = _managed_client(monkeypatch, source).post(
            "/managed/backup/export", json={"secret": BUNDLE_SECRET}, headers=HEADERS
        )
        assert bundle.status_code == 200
        assert bundle.headers["content-type"] == "application/gzip"

        target = _service(tmp_path / "b", Fernet.generate_key().decode())
        r = _managed_client(monkeypatch, target).post(
            "/managed/backup/import",
            files={"bundle": ("b.json.gz", bundle.content)},
            data={"secret": BUNDLE_SECRET, "mode": "fail"},
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "imported"
        assert body["restart_required"] is True

    def test_import_wrong_secret_is_409(self, tmp_path, monkeypatch):
        source = _service(tmp_path / "a", Fernet.generate_key().decode())
        # Credentials must exist for the secrets section to be encrypted.
        conn = source.db_manager.get_connection()
        conn.execute(
            "INSERT INTO service_credentials "
            "(service_name, credential_type, credential_data, created_at, updated_at) "
            "VALUES ('x', 't', ?, datetime('now'), datetime('now'))",
            (source.encryption.encrypt_string("v"),),
        )
        conn.commit()
        conn.close()
        bundle = (
            _managed_client(monkeypatch, source)
            .post("/managed/backup/export", json={"secret": BUNDLE_SECRET}, headers=HEADERS)
            .content
        )
        target = _service(tmp_path / "b", Fernet.generate_key().decode())
        r = _managed_client(monkeypatch, target).post(
            "/managed/backup/import",
            files={"bundle": ("b.json.gz", bundle)},
            data={"secret": "z" * 40},
            headers=HEADERS,
        )
        assert r.status_code == 409

    def test_import_rejects_bad_mode_and_garbage(self, tmp_path, monkeypatch):
        client = _managed_client(monkeypatch, _service(tmp_path, Fernet.generate_key().decode()))
        r = client.post(
            "/managed/backup/import",
            files={"bundle": ("b", b"x")},
            data={"secret": BUNDLE_SECRET, "mode": "nope"},
            headers=HEADERS,
        )
        assert r.status_code == 400
        r = client.post(
            "/managed/backup/import",
            files={"bundle": ("b", b"not json")},
            data={"secret": BUNDLE_SECRET},
            headers=HEADERS,
        )
        assert r.status_code == 400


class TestUserBackupLockout:
    def _client(self, service):
        app = FastAPI()
        app.include_router(backup_router)
        app.dependency_overrides[get_backup_service] = lambda: service
        return TestClient(app)

    def test_forbidden_when_managed(self, tmp_path, monkeypatch):
        key = Fernet.generate_key().decode()
        client = self._client(_service(tmp_path, key))
        monkeypatch.setenv("MANAGED_API_KEY", "set")
        assert client.post("/api/backup/export", json={"secret": key}).status_code == 403
        r = client.post("/api/backup/import", files={"bundle": ("b", b"{}")}, data={"secret": key})
        assert r.status_code == 403

    def test_allowed_when_not_managed(self, tmp_path, monkeypatch):
        key = Fernet.generate_key().decode()
        client = self._client(_service(tmp_path, key))
        monkeypatch.delenv("MANAGED_API_KEY", raising=False)
        assert client.post("/api/backup/export", json={"secret": key}).status_code == 200
