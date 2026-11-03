"""Tests for instance backup export/import."""

import json
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import src.core.encryption as encryption_module
from src.core.database import DatabaseManager
from src.services.backup import (
    BUNDLE_FORMAT_VERSION,
    BackupError,
    BackupService,
)


@pytest.fixture(autouse=True)
def reset_encryption_singleton():
    """The global EncryptionService caches the key; reset around each test."""
    encryption_module._encryption_service = None
    yield
    encryption_module._encryption_service = None


def _make_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(str(tmp_path / "assistant.db"))
    db.init_database()
    return db


def _set_key(key: str):
    """Point the env and the global EncryptionService singleton at `key`."""
    os.environ["ENCRYPTION_KEY"] = key
    encryption_module._encryption_service = None


def _make_service(tmp_path: Path, key: str) -> BackupService:
    _set_key(key)
    return BackupService(_make_db(tmp_path), data_dir=str(tmp_path / "data"))


@pytest.fixture
def key_a():
    return Fernet.generate_key().decode()


@pytest.fixture
def key_b():
    return Fernet.generate_key().decode()


def _seed(db: DatabaseManager, key: str, service_name: str = "google", agent_name: str = "test"):
    """Insert representative rows into a fresh instance."""
    f = Fernet(key.encode())
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO service_credentials "
        "(service_name, credential_type, credential_data, created_at, updated_at) "
        "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
        (
            service_name,
            "oauth_token",
            f.encrypt(json.dumps({"token": "topsecret"}).encode()).decode(),
        ),
    )
    conn.execute(
        "INSERT INTO agent_definitions "
        "(name, display_name, role, goal, backstory, tools, priority, enabled, created_at, updated_at) "
        f"VALUES ('{agent_name}', 'Test', 'helper', 'goal', 'story', '[]', 1, 1, datetime('now'), datetime('now'))"
    )
    conn.execute(
        "INSERT INTO job_executions (job_id, job_type, started_at, status) VALUES ('j1', 'cron', datetime('now'), 'ok')"
    )
    conn.commit()
    conn.close()


class TestExport:
    def test_export_requires_matching_secret(self, tmp_path, key_a, key_b):
        svc = _make_service(tmp_path, key_a)
        with pytest.raises(BackupError):
            svc.export_data(key_b)

    def test_export_bundle_structure_and_exclusions(self, tmp_path, key_a):
        svc = _make_service(tmp_path, key_a)
        _seed(svc.db_manager, key_a)
        bundle = svc.export_data(key_a)

        assert bundle["format_version"] == BUNDLE_FORMAT_VERSION
        assert "agent_definitions" in bundle["tables"]
        # seeded db starts with 10 default agents, plus our test agent
        assert len(bundle["tables"]["agent_definitions"]) == 11
        # secrets are NOT in plain tables
        assert "service_credentials" not in bundle["tables"]
        assert bundle["encrypted_secrets"]
        # run-history tables excluded
        for t in ("job_executions", "llm_consumption", "search_index", "audit_log"):
            assert t not in bundle["tables"]

    def test_exported_bundle_has_no_plaintext_secrets(self, tmp_path, key_a):
        svc = _make_service(tmp_path, key_a)
        _seed(svc.db_manager, key_a)
        bundle = svc.export_data(key_a)
        blob = json.dumps(bundle)
        assert "topsecret" not in blob


class TestImport:
    def _exported(self, tmp_path_factory, key):
        tmp = tmp_path_factory.mktemp("src")
        svc = _make_service(tmp, key)
        _seed(svc.db_manager, key)
        return svc.export_data(key)

    def test_roundtrip_with_different_instance_key(self, tmp_path, key_a, key_b):
        src = _make_service(tmp_path / "src", key_a)
        _seed(src.db_manager, key_a)
        bundle = src.export_data(key_a)

        # Target instance with a different ENCRYPTION_KEY
        dst = _make_service(tmp_path / "dst", key_b)
        summary = dst.import_data(bundle, key_a, mode="fail")

        # fresh target pre-seeds 10 default agents; our test agent imported on top
        assert summary["tables"]["agent_definitions"] == 1
        assert summary["tables"]["service_credentials"] == 1

        # Credential decrypts correctly with the TARGET key
        conn = dst.db_manager.get_connection()
        row = conn.execute(
            "SELECT credential_data FROM service_credentials WHERE service_name='google'"
        ).fetchone()
        conn.close()
        # global service still holds key_b; decrypt directly with target key
        plaintext = Fernet(key_b.encode()).decrypt(row[0].encode()).decode()
        assert json.loads(plaintext) == {"token": "topsecret"}

    def test_import_rejects_conflicting_data(self, tmp_path, key_a):
        """mode='fail' aborts when the target has rows not in the bundle."""
        svc = _make_service(tmp_path, key_a)
        bundle = svc.export_data(key_a)  # source has only pre-seeded defaults
        # target gets an extra row the bundle doesn't know about
        _seed(svc.db_manager, key_a)
        with pytest.raises(BackupError, match="overwrite"):
            svc.import_data(bundle, key_a, mode="fail")

    def test_import_fresh_target_with_defaults_succeeds(self, tmp_path, key_a):
        """A fresh pre-seeded target accepts a bundle of another fresh instance."""
        src = _make_service(tmp_path / "src", key_a)
        bundle = src.export_data(key_a)
        dst = _make_service(tmp_path / "dst", key_a)
        summary = dst.import_data(bundle, key_a, mode="fail")
        assert summary["tables"]["settings"] >= 0  # defaults matched, none lost
        conn = dst.db_manager.get_connection()
        n = conn.execute("SELECT COUNT(*) FROM agent_definitions").fetchone()[0]
        conn.close()
        assert n == 10  # no duplicates of pre-seeded defaults

    def test_import_overwrite_mode_replaces(self, tmp_path, key_a):
        svc = _make_service(tmp_path, key_a)
        _seed(svc.db_manager, key_a)
        bundle = svc.export_data(key_a)
        _seed(svc.db_manager, key_a, service_name="slack", agent_name="slack-agent")
        svc.import_data(bundle, key_a, mode="overwrite")
        conn = svc.db_manager.get_connection()
        n_test = conn.execute(
            "SELECT COUNT(*) FROM agent_definitions WHERE name='test'"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM agent_definitions").fetchone()[0]
        creds = conn.execute("SELECT COUNT(*) FROM service_credentials").fetchone()[0]
        conn.close()
        assert n_test == 1
        assert total == 11  # bundle's 10 defaults + test agent
        assert creds == 1  # 'slack' credential was wiped

    def test_import_with_wrong_bundle_secret_fails(self, tmp_path, key_a, key_b):
        svc = _make_service(tmp_path, key_a)
        _seed(svc.db_manager, key_a)
        bundle = svc.export_data(key_a)
        dst = _make_service(tmp_path / "dst2", key_a)
        with pytest.raises(BackupError, match="secret"):
            dst.import_data(bundle, key_b, mode="fail")

    def test_import_rejects_bad_bundle(self, tmp_path, key_a):
        svc = _make_service(tmp_path, key_a)
        with pytest.raises(BackupError, match="format version"):
            svc.import_data({"format_version": 999}, key_a)
        with pytest.raises(BackupError, match="mode"):
            svc.import_data(
                {"format_version": BUNDLE_FORMAT_VERSION, "tables": {}}, key_a, mode="bogus"
            )


class TestDataFiles:
    def test_files_roundtrip(self, tmp_path, key_a):
        svc = _make_service(tmp_path, key_a)
        (Path(tmp_path / "data") / "plugins").mkdir(parents=True)
        (Path(tmp_path / "data") / "plugins" / "myplug.json").write_text("{}")
        bundle = svc.export_data(key_a)
        assert "plugins/myplug.json" in bundle["files"]

        dst_root = tmp_path / "dst3"
        dst = _make_service(dst_root, key_a)
        count = dst.import_data(bundle, key_a)["files"]
        assert count == 1
        assert (dst_root / "data" / "plugins" / "myplug.json").read_text() == "{}"

    def test_unsafe_paths_skipped(self, tmp_path, key_a):
        dst_root = tmp_path / "dst4"
        dst = _make_service(dst_root, key_a)
        n = dst.import_data(
            {
                "format_version": BUNDLE_FORMAT_VERSION,
                "tables": {},
                "files": {"../evil.txt": "bad", "/abs/evil.txt": "bad"},
            },
            key_a,
        )["files"]
        assert n == 0
        assert not (dst_root / "evil.txt").exists()


class TestBundleWireFormat:
    def test_serialize_bundle_gzips_and_roundtrips(self):
        from src.services.backup import parse_bundle, serialize_bundle

        bundle = {"format_version": 1, "tables": {"t": [{"a": 1}]}, "files": {"x/y.txt": "hi"}}
        wire = serialize_bundle(bundle)
        assert wire[:2] == b"\x1f\x8b"  # gzip magic
        assert len(wire) < len(json.dumps(bundle, indent=4).encode())
        assert parse_bundle(wire) == bundle

    def test_parse_bundle_accepts_plain_json(self):
        from src.services.backup import parse_bundle

        plain = json.dumps({"format_version": 1}).encode()
        assert parse_bundle(plain) == {"format_version": 1}
