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
    return BackupService(
        _make_db(tmp_path),
        data_dir=str(tmp_path / "data"),
        artifacts_dir=str(tmp_path / "data" / "artifacts"),
        outlook_token_cache_path=str(tmp_path / "data" / "outlook_token_cache.json"),
    )


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
        # history tables travel too (full move); migration bookkeeping does not
        for t in ("job_executions", "llm_consumption", "audit_log", "search_index"):
            assert t in bundle["tables"]
        assert len(bundle["tables"]["job_executions"]) == 1
        for t in ("schema_migrations", "sqlite_sequence"):
            assert t not in bundle["tables"]

    def test_export_includes_only_memory_rows_of_search_index(self, tmp_path, key_a):
        svc = _make_service(tmp_path, key_a)
        conn = svc.db_manager.get_connection()
        conn.execute(
            "INSERT INTO search_index (source, source_id, content, embedding) "
            "VALUES ('memory', 'memory_facts_2026-01-01', 'likes tea', ?), "
            "('conversations', 'c1', 'derived', NULL)",
            (b"\x00\x01\xff",),
        )
        conn.commit()
        conn.close()
        rows = svc.export_data(key_a)["tables"]["search_index"]
        assert [r["source"] for r in rows] == ["memory"]
        json.dumps(rows)  # BLOB embedding is JSON-safe

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

        # 10 pre-seeded defaults (updated in place) + our test agent
        assert summary["tables"]["agent_definitions"] == 11
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

    def test_import_ignores_columns_unknown_to_target(self, tmp_path, key_a):
        """Bundles from a newer schema (extra columns) still import."""
        src = _make_service(tmp_path / "src", key_a)
        _seed(src.db_manager, key_a)
        bundle = src.export_data(key_a)
        for row in bundle["tables"]["agent_definitions"]:
            row["column_from_newer_version"] = "x"
        dst = _make_service(tmp_path / "dst", key_a)
        summary = dst.import_data(bundle, key_a, mode="fail")
        assert summary["tables"]["agent_definitions"] == 11
        assert summary["ignored_columns"] == {"agent_definitions": ["column_from_newer_version"]}
        assert any("column_from_newer_version" in w for w in summary["warnings"])

    def test_import_rejects_sql_in_column_names(self, tmp_path, key_a):
        src = _make_service(tmp_path / "src", key_a)
        bundle = src.export_data(key_a)
        bundle["tables"]["settings"] = [{'x") VALUES (1); DROP TABLE settings; --': 1}]
        dst = _make_service(tmp_path / "dst", key_a)
        dst.import_data(bundle, key_a, mode="overwrite")
        conn = dst.db_manager.get_connection()
        conn.execute("SELECT COUNT(*) FROM settings").fetchone()  # table still exists
        conn.close()

    def test_customised_default_row_is_not_dropped(self, tmp_path, key_a):
        """A pre-seeded row edited on the source must win over the target's default."""
        src = _make_service(tmp_path / "src", key_a)
        conn = src.db_manager.get_connection()
        conn.execute("UPDATE agent_definitions SET goal = 'custom goal' WHERE name = 'coordinator'")
        conn.commit()
        conn.close()
        bundle = src.export_data(key_a)

        dst = _make_service(tmp_path / "dst", key_a)
        dst.import_data(bundle, key_a, mode="fail")
        conn = dst.db_manager.get_connection()
        goal = conn.execute(
            "SELECT goal FROM agent_definitions WHERE name = 'coordinator'"
        ).fetchone()[0]
        conn.close()
        assert goal == "custom goal"

    def test_memory_facts_and_history_migrate(self, tmp_path, key_a):
        src = _make_service(tmp_path / "src", key_a)
        _seed(src.db_manager, key_a)
        conn = src.db_manager.get_connection()
        conn.execute(
            "INSERT INTO search_index (source, source_id, content, embedding) "
            "VALUES ('memory', 'memory_facts_2026-01-01', 'likes tea', ?)",
            (b"\x00\x01\xff",),
        )
        conn.commit()
        conn.close()
        bundle = src.export_data(key_a)

        dst = _make_service(tmp_path / "dst", key_a)
        # target already ran a job and indexed something of its own
        conn = dst.db_manager.get_connection()
        conn.execute(
            "INSERT INTO job_executions (job_id, job_type, started_at, status) "
            "VALUES ('local', 'cron', datetime('now'), 'ok')"
        )
        conn.execute(
            "INSERT INTO search_index (source, source_id, content) VALUES ('conversations', 'x', 'y')"
        )
        conn.commit()
        conn.close()

        dst.import_data(bundle, key_a, mode="fail")
        dst.import_data(bundle, key_a, mode="fail")  # re-import does not duplicate
        conn = dst.db_manager.get_connection()
        mem = conn.execute(
            "SELECT content, embedding FROM search_index WHERE source = 'memory'"
        ).fetchall()
        jobs = conn.execute("SELECT job_id FROM job_executions ORDER BY job_id").fetchall()
        derived = conn.execute(
            "SELECT COUNT(*) FROM search_index WHERE source = 'conversations'"
        ).fetchone()[0]
        conn.close()
        assert [(r[0], r[1]) for r in mem] == [("likes tea", b"\x00\x01\xff")]
        assert [r[0] for r in jobs] == ["j1", "local"]
        assert derived == 1  # target's own derived index rows untouched

    def test_import_reports_version_mismatch(self, tmp_path, key_a):
        svc = _make_service(tmp_path, key_a)
        bundle = svc.export_data(key_a)
        bundle["app_version"] = "0.0.1"
        summary = svc.import_data(bundle, key_a, mode="overwrite")
        assert any("0.0.1" in w for w in summary["warnings"])
        assert summary["restart_required"] is True

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

    def test_binary_artifacts_and_outlook_cache_roundtrip(self, tmp_path, key_a):
        src_root = tmp_path / "src"
        svc = _make_service(src_root, key_a)
        art = src_root / "data" / "artifacts" / "a1"
        art.mkdir(parents=True)
        png = b"\x89PNG\r\n\x1a\n\x00\xff\xfe"
        (art / "img.png").write_bytes(png)
        (src_root / "data" / "outlook_token_cache.json").write_text('{"RefreshToken": "rt-secret"}')
        bundle = svc.export_data(key_a)
        assert "rt-secret" not in json.dumps(bundle)  # token cache is encrypted

        dst_root = tmp_path / "dst"
        dst = _make_service(dst_root, key_a)
        count = dst.import_data(bundle, key_a)["files"]
        assert count == 2
        assert (dst_root / "data" / "artifacts" / "a1" / "img.png").read_bytes() == png
        assert "rt-secret" in (dst_root / "data" / "outlook_token_cache.json").read_text()

    def test_v1_text_files_still_import(self, tmp_path, key_a):
        dst_root = tmp_path / "dst"
        dst = _make_service(dst_root, key_a)
        n = dst.import_data(
            {"format_version": 1, "tables": {}, "files": {"plugins/p.json": "{}"}}, key_a
        )["files"]
        assert n == 1
        assert (dst_root / "data" / "plugins" / "p.json").read_text() == "{}"

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


def test_backup_endpoints_disabled_on_managed_instances(monkeypatch):
    """Managed instances must not expose the credential-bearing backup API."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.backup import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setenv("MANAGED_API_KEY", "managed-key")
    assert client.post("/api/backup/export", json={"secret": "x"}).status_code == 404
    assert (
        client.post(
            "/api/backup/import",
            files={"bundle": ("b.json", b"{}")},
            data={"secret": "x"},
        ).status_code
        == 404
    )
