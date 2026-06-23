"""
Database initialization and management module.
Handles database connection, migrations, and schema setup.
"""

import sqlite3
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and migrations."""

    def __init__(self, db_path: str = "data/assistant.db"):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.migrations_dir = Path(__file__).parent / "migrations"

    def init_database(self) -> None:
        """Initialize database with schema if not exists."""
        # Create data directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if database exists
        is_new_db = not self.db_path.exists()

        if is_new_db:
            logger.info(f"Creating new database at {self.db_path}")
            self._run_migrations()
        else:
            logger.info(f"Database already exists at {self.db_path}")
            self._check_migrations()

    def _run_migrations(self) -> None:
        """Run all pending migrations."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get list of applied migrations
        try:
            cursor.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            # Table doesn't exist yet, no migrations applied
            applied = set()

        # Get all migration files
        migration_files = sorted(self.migrations_dir.glob("*.sql"))

        for migration_file in migration_files:
            version = migration_file.stem
            if version not in applied:
                logger.info(f"Applying migration: {version}")
                self._apply_migration(cursor, migration_file)

        conn.commit()
        conn.close()

    def _check_migrations(self) -> None:
        """Check if all migrations are applied."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            logger.warning("Migration table doesn't exist, running migrations")
            conn.close()
            self._run_migrations()
            return

        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        for migration_file in migration_files:
            version = migration_file.stem
            if version not in applied:
                logger.info(f"Applying pending migration: {version}")
                self._apply_migration(cursor, migration_file)

        conn.commit()
        conn.close()

    def _apply_migration(self, cursor: sqlite3.Cursor, migration_file: Path) -> None:
        """
        Apply a single migration file.

        Args:
            cursor: Database cursor
            migration_file: Path to migration SQL file
        """
        with open(migration_file) as f:
            sql = f.read()

        cursor.executescript(sql)
        logger.info(f"Migration {migration_file.stem} applied successfully")

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get database connection with performance optimizations.

        Returns:
            SQLite connection object
        """
        # Set timeout to 30 seconds to avoid immediate locking errors
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrent access
        # WAL allows multiple readers and one writer simultaneously
        conn.execute("PRAGMA journal_mode = WAL")

        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        # Set synchronous to NORMAL for better performance
        # NORMAL is safe with WAL mode and much faster than FULL
        conn.execute("PRAGMA synchronous = NORMAL")

        # Increase cache size to 10MB for better performance
        conn.execute("PRAGMA cache_size = -10000")

        # Use memory for temporary tables
        conn.execute("PRAGMA temp_store = MEMORY")

        # Set busy timeout to handle lock contention
        conn.execute("PRAGMA busy_timeout = 30000")

        return conn

    def get_connection(self) -> sqlite3.Connection:
        """
        Public method to get database connection.

        Returns:
            SQLite connection object
        """
        return self._get_connection()

    def cleanup_old_data(self) -> None:
        """Clean up old data based on retention policies."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Clean old agent tasks (keep last 1000 per conversation)
        cursor.execute("""
            DELETE FROM agent_tasks
            WHERE id NOT IN (
                SELECT id FROM agent_tasks
                ORDER BY created_at DESC
                LIMIT 1000
            )
        """)

        # Clean old cron executions (keep last 100 per job)
        cursor.execute("""
            DELETE FROM cron_job_executions
            WHERE id NOT IN (
                SELECT id FROM cron_job_executions
                ORDER BY started_at DESC
                LIMIT 100
            )
        """)

        # Clean old audit logs (older than 30 days)
        cursor.execute("""
            DELETE FROM audit_log
            WHERE timestamp < datetime('now', '-30 days')
        """)

        deleted_tasks = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(f"Cleanup completed: removed old records")

    def backup_database(self, backup_path: Optional[str] = None) -> str:
        """
        Create a backup of the database.

        Args:
            backup_path: Optional custom backup path

        Returns:
            Path to backup file
        """
        if backup_path is None:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"data/backups/assistant_{timestamp}.db"

        backup_file = Path(backup_path)
        backup_file.parent.mkdir(parents=True, exist_ok=True)

        # Use SQLite backup API
        source = self._get_connection()
        dest = sqlite3.connect(str(backup_file))

        source.backup(dest)

        dest.close()
        source.close()

        logger.info(f"Database backed up to {backup_path}")
        return str(backup_path)

    def optimize_database(self) -> None:
        """
        Optimize database by running ANALYZE and VACUUM.

        This should be run periodically to maintain good query performance.
        Note: VACUUM requires exclusive lock and may take time on large databases.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Update statistics for query optimizer
            logger.info("Running ANALYZE to update query statistics...")
            cursor.execute("ANALYZE")

            # Defragment and reclaim unused space
            # Note: VACUUM requires exclusive lock
            logger.info("Running VACUUM to optimize database file...")
            cursor.execute("VACUUM")

            conn.commit()
            logger.info("Database optimization completed successfully")

        except sqlite3.OperationalError as e:
            logger.error(f"Database optimization failed: {e}")
            raise
        finally:
            conn.close()

    def check_wal_mode(self) -> bool:
        """
        Check if database is running in WAL mode.

        Returns:
            True if WAL mode is active, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()
        return mode.upper() == "WAL"


def init_database(db_path: str = "data/assistant.db") -> None:
    """
    Initialize the database with schema.

    Args:
        db_path: Path to database file
    """
    manager = DatabaseManager(db_path)
    manager.init_database()


def get_db_manager(db_path: str = "data/assistant.db") -> DatabaseManager:
    """
    Get database manager instance.

    Args:
        db_path: Path to database file

    Returns:
        DatabaseManager instance
    """
    return DatabaseManager(db_path)


if __name__ == "__main__":
    # Run database initialization
    import sys

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_database()
        print("Database initialized successfully")
    elif len(sys.argv) > 1 and sys.argv[1] == "backup":
        manager = get_db_manager()
        backup_path = manager.backup_database()
        print(f"Database backed up to: {backup_path}")
    elif len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        manager = get_db_manager()
        manager.cleanup_old_data()
        print("Database cleanup completed")
    elif len(sys.argv) > 1 and sys.argv[1] == "optimize":
        manager = get_db_manager()
        print("Optimizing database (this may take a few moments)...")
        manager.optimize_database()
        print("Database optimization completed")
    elif len(sys.argv) > 1 and sys.argv[1] == "check-wal":
        manager = get_db_manager()
        if manager.check_wal_mode():
            print("✓ Database is running in WAL mode (optimal for concurrent access)")
        else:
            print("✗ Database is NOT in WAL mode. WAL mode will be enabled on next connection.")
    else:
        print("Usage:")
        print("  python -m src.core.database init      - Initialize database")
        print("  python -m src.core.database backup    - Backup database")
        print("  python -m src.core.database cleanup   - Clean old data")
        print("  python -m src.core.database optimize  - Optimize database (ANALYZE + VACUUM)")
        print("  python -m src.core.database check-wal - Check if WAL mode is enabled")
