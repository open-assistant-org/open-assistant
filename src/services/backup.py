"""Backup service for exporting and importing all instance data.

Produces a portable JSON bundle that can be migrated between servers. Secrets
(``service_credentials.credential_data``) are decrypted with the source
instance's encryption key and re-encrypted with a key derived from the
user-provided backend secret, so the bundle never contains plaintext secrets
and remains valid on a target instance that uses a different ENCRYPTION_KEY.
"""

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from src.core.encryption import get_encryption_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

BUNDLE_FORMAT_VERSION = 1

# Tables excluded from export/import: run-history and derived/index data that
# is not needed to migrate an instance.
EXCLUDED_TABLES = {
    "schema_migrations",
    "sqlite_sequence",
    "job_executions",
    "llm_consumption",
    "search_index",
    "audit_log",
}

# Directories under data/ included in the bundle (files only, recursive).
INCLUDED_DATA_DIRS = ["plugins", "mcp_servers"]

# Number of PBKDF2 iterations for deriving the bundle key from the secret.
_PBKDF2_ITERATIONS = 600_000


class BackupError(Exception):
    """Raised when an export or import cannot be completed."""


def _derive_fernet_key(secret: str) -> Fernet:
    """Derive a Fernet instance from the user-provided secret (PBKDF2)."""
    import base64

    digest = hashlib.pbkdf2_hmac(
        "sha256", secret.encode(), b"open-assistant-backup", _PBKDF2_ITERATIONS
    )
    return Fernet(base64.urlsafe_b64encode(digest).decode())


class BackupService:
    """Service for exporting and importing instance data."""

    def __init__(self, db_manager, data_dir: str = "data"):
        self.db_manager = db_manager
        self.data_dir = Path(data_dir)

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def export_data(self, secret: str) -> dict[str, Any]:
        """Export all instance data as a portable bundle.

        Args:
            secret: The instance backend secret (ENCRYPTION_KEY). Verified
                against the instance key before any secrets are decrypted.

        Returns:
            Bundle dict, ready to be serialized to JSON.

        Raises:
            BackupError: If the secret does not match the instance key.
        """
        self._verify_instance_secret(secret)
        bundle_key = _derive_fernet_key(secret)

        conn = self._connect()
        try:
            tables = self._list_tables(conn)
            bundle_tables: dict[str, Any] = {}
            for table in tables:
                if table in EXCLUDED_TABLES:
                    continue
                bundle_tables[table] = self._dump_table(conn, table)

            secrets_payload = bundle_tables.pop("service_credentials", None)
        finally:
            conn.close()

        encrypted_secrets = None
        if secrets_payload is not None:
            # Decrypt each credential blob with the instance key, then encrypt
            # the whole secrets section with the bundle key.
            decrypted_rows = []
            for row in secrets_payload:
                row = dict(row)
                try:
                    plaintext = self.encryption.decrypt_string(row["credential_data"])
                except ValueError as e:
                    raise BackupError(
                        f"Failed to decrypt credential for service "
                        f"'{row.get('service_name')}': {e}"
                    ) from e
                row["credential_data"] = plaintext
                decrypted_rows.append(row)
            encrypted_secrets = bundle_key.encrypt(
                json.dumps({"service_credentials": decrypted_rows}).encode()
            ).decode()

        files = self._collect_data_files()

        return {
            "format_version": BUNDLE_FORMAT_VERSION,
            "app_version": self._app_version(),
            "exported_at": datetime.now(UTC).isoformat(),
            "tables": bundle_tables,
            "encrypted_secrets": encrypted_secrets,
            "files": files,
        }

    # ------------------------------------------------------------------ #
    # Import
    # ------------------------------------------------------------------ #

    def import_data(
        self, bundle: dict[str, Any], secret: str, mode: str = "fail"
    ) -> dict[str, Any]:
        """Import a bundle into this instance.

        Args:
            bundle: Bundle dict as produced by ``export_data``.
            secret: The backend secret of the *source* instance (used to
                decrypt the bundle's secrets section).
            mode: Conflict policy. ``fail`` (default) aborts if the target
                contains rows in included tables that are not in the bundle
                (i.e. data would be lost); pre-seeded default rows identical
                to bundle rows are fine. ``overwrite`` clears included tables
                before importing.

        Returns:
            Summary dict with per-table imported row counts.

        Raises:
            BackupError: On invalid bundle, wrong secret, or conflicting data.
        """
        if mode not in ("fail", "overwrite"):
            raise BackupError(f"Invalid mode '{mode}', expected 'fail' or 'overwrite'")

        self._validate_bundle(bundle)

        bundle_key = _derive_fernet_key(secret)

        if bundle.get("encrypted_secrets"):
            try:
                secrets_json = bundle_key.decrypt(bundle["encrypted_secrets"].encode()).decode()
            except Exception as e:
                raise BackupError("Wrong backend secret: cannot decrypt bundle secrets") from e
            secrets = json.loads(secrets_json).get("service_credentials", [])
        else:
            secrets = []

        # Re-encrypt credentials with *this* instance's key.
        for row in secrets:
            row["credential_data"] = self.encryption.encrypt_string(row["credential_data"])

        tables = dict(bundle["tables"])
        if secrets:
            tables["service_credentials"] = secrets

        conn = self._connect()
        try:
            summary = self._import_tables(conn, tables, mode)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        imported_files = self._restore_data_files(bundle.get("files", {}))

        return {"tables": summary, "files": imported_files}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @property
    def encryption(self):
        if not hasattr(self, "_encryption"):
            self._encryption = get_encryption_service()
        return self._encryption

    def _app_version(self) -> str:
        try:
            import tomllib

            pyproject = Path(__file__).parents[2] / "pyproject.toml"
            with open(pyproject, "rb") as f:
                return tomllib.load(f)["project"]["version"]
        except Exception:
            return "unknown"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_manager.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _verify_instance_secret(self, secret: str) -> None:
        """Ensure the caller knows this instance's ENCRYPTION_KEY."""
        import base64

        instance_key = os.getenv("SECURITY_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")
        if not instance_key:
            # Derive from the configured service's key material as a fallback.
            try:
                raw = self.encryption.fernet._Fernet__key  # type: ignore[attr-defined]
                instance_key = base64.urlsafe_b64encode(raw).decode()
            except Exception as e:
                raise BackupError("Instance encryption key is not configured") from e
        if secret != instance_key:
            raise BackupError("Provided secret does not match the instance encryption key")

    def _list_tables(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return [r[0] for r in rows]

    def _dump_table(self, conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        return [dict(r) for r in rows]

    def _collect_data_files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        for dirname in INCLUDED_DATA_DIRS:
            base = self.data_dir / dirname
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(self.data_dir).as_posix()
                    files[rel] = path.read_text(encoding="utf-8", errors="replace")
        return files

    def _restore_data_files(self, files: dict[str, str]) -> int:
        count = 0
        for rel, content in files.items():
            rel_path = Path(rel)
            if not self._is_safe_rel_path(rel_path):
                logger.warning(f"Skipping unsafe path in bundle: {rel}")
                continue
            dest = self.data_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            count += 1
        return count

    @staticmethod
    def _is_safe_rel_path(rel_path: Path) -> bool:
        parts = rel_path.parts
        if not parts or rel_path.is_absolute() or ".." in parts:
            return False
        return parts[0] in INCLUDED_DATA_DIRS

    def _validate_bundle(self, bundle: dict[str, Any]) -> None:
        if not isinstance(bundle, dict):
            raise BackupError("Bundle must be a JSON object")
        if bundle.get("format_version") != BUNDLE_FORMAT_VERSION:
            raise BackupError(
                f"Unsupported bundle format version {bundle.get('format_version')!r}, "
                f"expected {BUNDLE_FORMAT_VERSION}"
            )
        if "tables" not in bundle:
            raise BackupError("Bundle is missing 'tables'")

    def _import_tables(
        self, conn: sqlite3.Connection, tables: dict[str, Any], mode: str
    ) -> dict[str, int]:
        existing_tables = set(self._list_tables(conn))
        summary: dict[str, int] = {}

        # Conflict check up front so we never partially import. Fresh
        # instances come pre-seeded with default rows; those are fine as long
        # as they also exist in the bundle. Any *extra* target row would be
        # lost by the import, so abort unless mode='overwrite'.
        if mode == "fail":
            conflicts = []
            for table in tables:
                if table in existing_tables:
                    extra = self._count_rows_not_in_bundle(conn, table, tables[table])
                    if extra:
                        conflicts.append(f"{table} ({extra} rows)")
            if conflicts:
                raise BackupError(
                    "Target instance has data not present in the bundle: "
                    + ", ".join(sorted(conflicts))
                    + ". Use mode='overwrite' to replace it."
                )
        elif mode == "overwrite":
            for table in tables:
                if table in existing_tables:
                    conn.execute(f'DELETE FROM "{table}"')

        for table, rows in tables.items():
            if table not in existing_tables:
                logger.warning(f"Skipping unknown table in bundle: {table}")
                continue
            if not isinstance(rows, list):
                raise BackupError(f"Bundle table '{table}' must be a list of rows")
            if not rows:
                summary[table] = 0
                continue
            if not all(isinstance(row, dict) for row in rows):
                raise BackupError(f"Bundle table '{table}' contains a non-object row")
            count = 0
            for row in rows:
                cols = list(row.keys())
                placeholders = ", ".join(f":{c}" for c in cols)
                col_names = ", ".join(f'"{c}"' for c in cols)
                # OR IGNORE: identical pre-seeded default rows already on the
                # target are skipped instead of raising (or being duplicated).
                cursor = conn.execute(
                    f'INSERT OR IGNORE INTO "{table}" ({col_names}) VALUES ({placeholders})',
                    row,
                )
                count += cursor.rowcount if cursor.rowcount > 0 else 0
            summary[table] = count
        return summary

    def _count_rows_not_in_bundle(
        self, conn: sqlite3.Connection, table: str, bundle_rows: list[dict[str, Any]]
    ) -> int:
        """Count target rows that the bundle would not carry over."""
        pk_cols = self._primary_key_columns(conn, table)
        if not pk_cols:
            # No primary key to compare on: conservatively treat any target
            # row as potential conflict.
            return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

        bundle_keys = {
            tuple(row.get(c) for c in pk_cols) for row in bundle_rows if isinstance(row, dict)
        }
        count = 0
        for row in conn.execute(f'SELECT * FROM "{table}"'):
            key = tuple(row[c] for c in pk_cols)
            if key not in bundle_keys:
                count += 1
        return count

    @staticmethod
    def _primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
        info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [r["name"] for r in info if r["pk"]] or [
            r["name"] for r in info if r["notnull"] and r["type"].upper() == "INTEGER"
        ]
