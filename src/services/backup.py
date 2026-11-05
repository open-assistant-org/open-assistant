"""Backup service for exporting and importing all instance data.

Produces a portable JSON bundle that can be migrated between servers. Secrets
(``service_credentials.credential_data`` and on-disk token caches) are
decrypted with the source instance's encryption key and re-encrypted with a
key derived from the user-provided backend secret, so the bundle never
contains plaintext secrets and remains valid on a target instance that uses a
different ENCRYPTION_KEY.
"""

import base64
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

# v2: binary-safe values (BLOBs and data files are base64-encoded), history
# tables, memory facts, artifact files and the Outlook token cache included.
BUNDLE_FORMAT_VERSION = 2
SUPPORTED_BUNDLE_FORMAT_VERSIONS = {1, 2}

# Tables never exported: SQLite/migration bookkeeping that belongs to the
# target's own schema.
EXCLUDED_TABLES = {
    "schema_migrations",
    "sqlite_sequence",
}

# Tables of which only a subset of rows is primary data. Maps table ->
# (row filter, natural key columns). ``search_index`` is mostly a derived
# index that the target rebuilds on its own, but long-term memory facts
# (source='memory') live *only* there.
PARTIAL_TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "search_index": ("source = 'memory'", ("source", "source_id")),
}

# Append-only history/log tables. A target instance writes its own entries as
# soon as it runs, so these never count as conflicts: in ``fail`` mode bundle
# rows are merged in (exact duplicates skipped) instead of aborting.
HISTORY_TABLES = {"job_executions", "llm_consumption", "audit_log"}

# Tables left out of platform-driven (managed) transfers. The platform bills
# each instance from its own ``llm_consumption`` ledger, so copying it to
# another instance would bill the same tokens twice, and restoring it onto the
# same instance would roll the current month back.
MANAGED_EXCLUDED_TABLES = frozenset({"llm_consumption"})

# Directories under data/ included in the bundle (files only, recursive).
INCLUDED_DATA_DIRS = ["plugins", "mcp_servers", "artifacts"]

# MSAL token cache written by the Outlook integration (src/services/outlook.py,
# src/api/auth.py). It holds plaintext refresh tokens, so it travels in the
# encrypted secrets section.
OUTLOOK_TOKEN_CACHE_PATH = "data/outlook_token_cache.json"
_SECRET_FILE_OUTLOOK = "outlook_token_cache.json"

# Marker used to carry BLOB values through JSON.
_BYTES_KEY = "__bytes_b64__"

# Number of PBKDF2 iterations for deriving the bundle key from the secret.
_PBKDF2_ITERATIONS = 600_000


class BackupError(Exception):
    """Raised when an export or import cannot be completed."""


# Wire format helpers ---------------------------------------------------------


def serialize_bundle(bundle: dict[str, Any]) -> bytes:
    """Serialize a bundle to compact gzip-compressed bytes for transfer."""
    import gzip

    payload = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return gzip.compress(payload, mtime=0)


def parse_bundle(data: bytes) -> dict[str, Any]:
    """Parse a bundle from raw upload bytes (plain or gzip-compressed JSON)."""
    import gzip

    if data[:2] == b"\x1f\x8b":  # gzip magic
        data = gzip.decompress(data)
    return json.loads(data.decode("utf-8"))


def _derive_fernet_key(secret: str) -> Fernet:
    """Derive a Fernet instance from the user-provided secret (PBKDF2)."""
    digest = hashlib.pbkdf2_hmac(
        "sha256", secret.encode(), b"open-assistant-backup", _PBKDF2_ITERATIONS
    )
    return Fernet(base64.urlsafe_b64encode(digest).decode())


def _encode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {_BYTES_KEY: base64.b64encode(value).decode("ascii")}
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {_BYTES_KEY}:
        return base64.b64decode(value[_BYTES_KEY])
    return value


class BackupService:
    """Service for exporting and importing instance data."""

    def __init__(
        self,
        db_manager,
        data_dir: str = "data",
        artifacts_dir: str | None = None,
        outlook_token_cache_path: str = OUTLOOK_TOKEN_CACHE_PATH,
    ):
        self.db_manager = db_manager
        self.data_dir = Path(data_dir)
        # Mirrors src.utils.tmp.get_artifacts_dir(), but anchored on data_dir.
        self.artifacts_dir = Path(
            artifacts_dir or os.getenv("ARTIFACTS_DIR") or self.data_dir / "artifacts"
        )
        self.outlook_token_cache_path = Path(outlook_token_cache_path)

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
        return self._build_bundle(secret)

    def export_for_transfer(self, bundle_secret: str) -> dict[str, Any]:
        """Export a bundle for a platform-driven (managed) transfer.

        The caller is authenticated by the managed API key, so the instance
        ``ENCRYPTION_KEY`` is not required: the bundle's secrets section is
        encrypted with a key derived from *bundle_secret* instead. Tables in
        :data:`MANAGED_EXCLUDED_TABLES` are left out.
        """
        return self._build_bundle(bundle_secret, exclude_tables=MANAGED_EXCLUDED_TABLES)

    def _build_bundle(
        self, bundle_secret: str, exclude_tables: frozenset[str] = frozenset()
    ) -> dict[str, Any]:
        """Dump the instance into a bundle whose secrets use *bundle_secret*."""
        bundle_key = _derive_fernet_key(bundle_secret)

        conn = self._connect()
        try:
            tables = self._list_tables(conn)
            bundle_tables: dict[str, Any] = {}
            for table in tables:
                if table in EXCLUDED_TABLES or table in exclude_tables:
                    continue
                bundle_tables[table] = self._dump_table(conn, table)

            secrets_payload = bundle_tables.pop("service_credentials", None)
        finally:
            conn.close()

        # Decrypt each credential blob with the instance key; the whole
        # secrets section is then encrypted with the bundle key.
        decrypted_rows = []
        for row in secrets_payload or []:
            row = dict(row)
            try:
                plaintext = self.encryption.decrypt_string(row["credential_data"])
            except ValueError as e:
                raise BackupError(
                    f"Failed to decrypt credential for service " f"'{row.get('service_name')}': {e}"
                ) from e
            row["credential_data"] = plaintext
            decrypted_rows.append(row)

        secret_files: dict[str, str] = {}
        if self.outlook_token_cache_path.is_file():
            secret_files[_SECRET_FILE_OUTLOOK] = self.outlook_token_cache_path.read_text(
                encoding="utf-8"
            )

        encrypted_secrets = None
        if secrets_payload is not None or secret_files:
            encrypted_secrets = bundle_key.encrypt(
                json.dumps({"service_credentials": decrypted_rows, "files": secret_files}).encode()
            ).decode()

        return {
            "format_version": BUNDLE_FORMAT_VERSION,
            "app_version": self._app_version(),
            "exported_at": datetime.now(UTC).isoformat(),
            "tables": bundle_tables,
            "encrypted_secrets": encrypted_secrets,
            "files": self._collect_data_files(),
        }

    # ------------------------------------------------------------------ #
    # Import
    # ------------------------------------------------------------------ #

    def import_data(
        self,
        bundle: dict[str, Any],
        secret: str,
        mode: str = "fail",
        exclude_tables: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        """Import a bundle into this instance.

        Args:
            bundle: Bundle dict as produced by ``export_data``.
            secret: The backend secret of the *source* instance (used to
                decrypt the bundle's secrets section).
            mode: Conflict policy. ``fail`` (default) aborts if the target
                contains rows in included tables that are not in the bundle
                (i.e. data would be lost); pre-seeded default rows are fine and
                are updated to the bundle's version. ``overwrite`` clears
                included tables before importing.
            exclude_tables: Tables to skip even if the bundle contains them.
                They are neither cleared nor written on this instance.

        Returns:
            Summary dict with per-table imported row counts, the number of
            restored files, columns that could not be imported and warnings.

        Raises:
            BackupError: On invalid bundle, wrong secret, or conflicting data.
        """
        if mode not in ("fail", "overwrite"):
            raise BackupError(f"Invalid mode '{mode}', expected 'fail' or 'overwrite'")

        self._validate_bundle(bundle)

        bundle_key = _derive_fernet_key(secret)

        secrets: list[dict[str, Any]] | None = None
        secret_files: dict[str, str] = {}
        if bundle.get("encrypted_secrets"):
            try:
                secrets_json = bundle_key.decrypt(bundle["encrypted_secrets"].encode()).decode()
            except Exception as e:
                raise BackupError("Wrong backend secret: cannot decrypt bundle secrets") from e
            payload = json.loads(secrets_json)
            secrets = payload.get("service_credentials", [])
            secret_files = payload.get("files", {}) or {}

        # Re-encrypt credentials with *this* instance's key.
        for row in secrets or []:
            row["credential_data"] = self.encryption.encrypt_string(row["credential_data"])

        tables = dict(bundle["tables"])
        skipped_tables = sorted(t for t in tables if t in exclude_tables)
        for table in skipped_tables:
            del tables[table]
        if secrets is not None:
            tables["service_credentials"] = secrets

        ignored_columns: dict[str, list[str]] = {}
        conn = self._connect()
        try:
            summary = self._import_tables(conn, tables, mode, ignored_columns)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        imported_files = self._restore_data_files(bundle.get("files", {}))
        if _SECRET_FILE_OUTLOOK in secret_files:
            self.outlook_token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.outlook_token_cache_path.write_text(
                secret_files[_SECRET_FILE_OUTLOOK], encoding="utf-8"
            )
            imported_files += 1

        warnings = []
        source_version = bundle.get("app_version")
        target_version = self._app_version()
        if source_version and source_version != target_version:
            warnings.append(
                f"Bundle was exported from version {source_version}, this instance runs "
                f"{target_version}. Run the same version on both sides for a lossless move."
            )
        if skipped_tables:
            warnings.append(
                f"Tables skipped for this instance (left unchanged): {', '.join(skipped_tables)}"
            )
        for table, cols in sorted(ignored_columns.items()):
            warnings.append(
                f"Columns not present on this instance were not imported: "
                f"{table}.{', '.join(cols)}"
            )

        return {
            "tables": summary,
            "files": imported_files,
            "ignored_columns": ignored_columns,
            "warnings": warnings,
            # Schedulers, plugin and MCP tool registries are loaded at startup.
            "restart_required": True,
        }

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
        conn = sqlite3.connect(str(self.db_manager.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        # Rows are written table by table in arbitrary order and REPLACE must
        # not cascade-delete children, so foreign keys stay off here.
        conn.execute("PRAGMA foreign_keys = OFF")
        return conn

    def _verify_instance_secret(self, secret: str) -> None:
        """Ensure the caller knows this instance's ENCRYPTION_KEY."""
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

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}

    def _dump_table(self, conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
        where = f" WHERE {PARTIAL_TABLES[table][0]}" if table in PARTIAL_TABLES else ""
        rows = conn.execute(f'SELECT * FROM "{table}"{where}').fetchall()
        return [{k: _encode_value(r[k]) for k in r.keys()} for r in rows]

    def _data_dir_bases(self) -> dict[str, Path]:
        bases = {name: self.data_dir / name for name in INCLUDED_DATA_DIRS}
        bases["artifacts"] = self.artifacts_dir
        return bases

    def _collect_data_files(self) -> dict[str, dict[str, str]]:
        files: dict[str, dict[str, str]] = {}
        for dirname, base in self._data_dir_bases().items():
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    rel = (Path(dirname) / path.relative_to(base)).as_posix()
                    files[rel] = {"b64": base64.b64encode(path.read_bytes()).decode("ascii")}
        return files

    def _restore_data_files(self, files: dict[str, Any]) -> int:
        bases = self._data_dir_bases()
        count = 0
        for rel, content in files.items():
            rel_path = Path(rel)
            if not self._is_safe_rel_path(rel_path):
                logger.warning(f"Skipping unsafe path in bundle: {rel}")
                continue
            if isinstance(content, str):  # format v1: text content
                data = content.encode("utf-8")
            elif isinstance(content, dict) and isinstance(content.get("b64"), str):
                data = base64.b64decode(content["b64"])
            else:
                logger.warning(f"Skipping malformed file entry in bundle: {rel}")
                continue
            base = bases[rel_path.parts[0]]
            dest = base.joinpath(*rel_path.parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Refuse to write through a symlink that points outside the base.
            if not dest.resolve().is_relative_to(base.resolve()):
                logger.warning(f"Skipping path escaping its directory: {rel}")
                continue
            dest.write_bytes(data)
            count += 1
        return count

    @staticmethod
    def _is_safe_rel_path(rel_path: Path) -> bool:
        parts = rel_path.parts
        if len(parts) < 2 or rel_path.is_absolute() or ".." in parts:
            return False
        return parts[0] in INCLUDED_DATA_DIRS

    def _validate_bundle(self, bundle: dict[str, Any]) -> None:
        if not isinstance(bundle, dict):
            raise BackupError("Bundle must be a JSON object")
        if bundle.get("format_version") not in SUPPORTED_BUNDLE_FORMAT_VERSIONS:
            raise BackupError(
                f"Unsupported bundle format version {bundle.get('format_version')!r}, "
                f"expected one of {sorted(SUPPORTED_BUNDLE_FORMAT_VERSIONS)}"
            )
        if not isinstance(bundle.get("tables"), dict):
            raise BackupError("Bundle is missing 'tables'")

    def _import_tables(
        self,
        conn: sqlite3.Connection,
        tables: dict[str, Any],
        mode: str,
        ignored_columns: dict[str, list[str]],
    ) -> dict[str, int]:
        existing_tables = set(self._list_tables(conn)) - EXCLUDED_TABLES
        summary: dict[str, int] = {}

        for table, rows in tables.items():
            if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                raise BackupError(f"Bundle table '{table}' must be a list of row objects")

        # Conflict check up front so we never partially import. Fresh
        # instances come pre-seeded with default rows; those are fine as long
        # as they also exist in the bundle. Any *extra* target row would be
        # lost by the import, so abort unless mode='overwrite'.
        if mode == "fail":
            conflicts = []
            for table in tables:
                if table in existing_tables and table not in HISTORY_TABLES:
                    extra = self._count_rows_not_in_bundle(conn, table, tables[table])
                    if extra:
                        conflicts.append(f"{table} ({extra} rows)")
            if conflicts:
                raise BackupError(
                    "Target instance has data not present in the bundle: "
                    + ", ".join(sorted(conflicts))
                    + ". Use mode='overwrite' to replace it."
                )
        else:
            for table in tables:
                if table in existing_tables:
                    where = f" WHERE {PARTIAL_TABLES[table][0]}" if table in PARTIAL_TABLES else ""
                    conn.execute(f'DELETE FROM "{table}"{where}')

        for table, rows in tables.items():
            if table not in existing_tables:
                logger.warning(f"Skipping unknown table in bundle: {table}")
                continue

            # Only write columns this schema has: bundle keys are untrusted
            # input (they end up in SQL) and a bundle from another app version
            # may carry columns the target doesn't know.
            target_cols = self._table_columns(conn, table)
            unknown = sorted({c for row in rows for c in row} - target_cols)
            if unknown:
                logger.warning(f"Ignoring columns not in target table '{table}': {unknown}")
                ignored_columns[table] = unknown

            # Surrogate ids of merged rows may collide with the target's own.
            drop_id = table in PARTIAL_TABLES or (table in HISTORY_TABLES and mode == "fail")

            count = 0
            for raw in rows:
                row = {
                    k: _decode_value(v)
                    for k, v in raw.items()
                    if k in target_cols and not (drop_id and k == "id")
                }
                if not row:
                    continue
                if (
                    table in HISTORY_TABLES
                    and mode == "fail"
                    and self._row_exists(conn, table, row)
                ):
                    continue
                cols = list(row)
                col_names = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join("?" for _ in cols)
                # OR REPLACE: rows matching a pre-seeded target row (same key)
                # take the bundle's version, so customised defaults survive.
                conn.execute(
                    f'INSERT OR REPLACE INTO "{table}" ({col_names}) VALUES ({placeholders})',
                    [row[c] for c in cols],
                )
                count += 1
            summary[table] = count
        return summary

    @staticmethod
    def _row_exists(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> bool:
        cond = " AND ".join(f'"{c}" IS ?' for c in row)
        return (
            conn.execute(
                f'SELECT 1 FROM "{table}" WHERE {cond} LIMIT 1', list(row.values())
            ).fetchone()
            is not None
        )

    def _count_rows_not_in_bundle(
        self, conn: sqlite3.Connection, table: str, bundle_rows: list[dict[str, Any]]
    ) -> int:
        """Count target rows that the bundle would not carry over."""
        where = ""
        if table in PARTIAL_TABLES:
            where = f" WHERE {PARTIAL_TABLES[table][0]}"
            key_cols = list(PARTIAL_TABLES[table][1])
        else:
            key_cols = self._primary_key_columns(conn, table)
        if not key_cols:
            # No primary key to compare on: conservatively treat any target
            # row as potential conflict.
            return conn.execute(f'SELECT COUNT(*) FROM "{table}"{where}').fetchone()[0]

        bundle_keys = {tuple(row.get(c) for c in key_cols) for row in bundle_rows}
        count = 0
        for row in conn.execute(f'SELECT * FROM "{table}"{where}'):
            key = tuple(row[c] for c in key_cols)
            if key not in bundle_keys:
                count += 1
        return count

    @staticmethod
    def _primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
        info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [r["name"] for r in info if r["pk"]] or [
            r["name"] for r in info if r["notnull"] and r["type"].upper() == "INTEGER"
        ]
