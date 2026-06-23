"""Tests for database migration handling.

Covers:
- Every migration applies on a fresh database and registers itself (by filename)
  in ``schema_migrations`` — guards against version-string typos that make a
  migration silently re-run on every startup.
- Migration 052 (table rebuild) is safe when the lock columns already exist,
  e.g. from a previous partial run where executescript committed the ALTER TABLE
  but crashed before recording the migration version.
"""

from pathlib import Path

from src.core.database import DatabaseManager

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "src" / "core" / "migrations"


def _migration_versions():
    """All migration versions as derived from their file names (stems)."""
    return sorted(p.stem for p in MIGRATIONS_DIR.glob("*.sql"))


def _applied_versions(db_manager):
    conn = db_manager.get_connection()
    try:
        return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()


def _columns(db_manager, table):
    conn = db_manager.get_connection()
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_all_migrations_execute_and_register_on_fresh_db(test_db_path):
    """Every migration runs on a fresh DB and is registered by its file name.

    1. ``init_database()`` must execute the full migration set without error.
    2. Each migration file's name (stem) must appear in ``schema_migrations``;
       the runner keys off the file name, so a migration registering a different
       version string would re-run on every startup.
    """
    db = DatabaseManager(str(test_db_path))

    db.init_database()

    file_versions = _migration_versions()
    assert file_versions, "no migration files found"

    applied = _applied_versions(db)
    unregistered = [v for v in file_versions if v not in applied]
    assert not unregistered, (
        "migrations executed but not registered in schema_migrations "
        f"(file name != recorded version?): {unregistered}"
    )


def test_052_rebuild_is_safe_when_lock_columns_already_exist(clean_temp_db):
    """Re-running migration 052 succeeds even when the lock columns are present.

    Reproduces the 1.0.8 -> 1.0.9 upgrade crash: on a database where a previous
    run of 052 committed the table changes but crashed before recording the
    migration, the runner will attempt 052 again. The table-rebuild approach
    must complete without error and leave the lock columns in place.
    """
    db = clean_temp_db
    version = "052_add_cron_execution_lock_columns"

    assert "execution_lock_instance" in _columns(db, "cron_jobs")
    assert version in _applied_versions(db)

    # Simulate partial previous run: columns exist but migration not recorded.
    conn = db.get_connection()
    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
    conn.commit()
    conn.close()

    # Must not raise — the rebuild drops and recreates the table cleanly.
    db._check_migrations()

    assert version in _applied_versions(db)
    assert "execution_lock_instance" in _columns(db, "cron_jobs")
    assert "execution_lock_acquired_at" in _columns(db, "cron_jobs")
