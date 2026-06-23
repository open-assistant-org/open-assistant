"""Base repository with common database operations."""

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.core.database import DatabaseManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseRepository:
    """Base repository class with common CRUD operations."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize repository.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def get_connection(self) -> sqlite3.Connection:
        """
        Get database connection.

        Returns:
            SQLite connection instance
        """
        return self.db.get_connection()

    def execute_query(
        self, query: str, params: Optional[Tuple[Any, ...]] = None, commit: bool = True
    ) -> sqlite3.Cursor:
        """
        Execute a SQL query.

        Args:
            query: SQL query string
            params: Query parameters tuple
            commit: Whether to commit the transaction

        Returns:
            Cursor with query results

        Raises:
            sqlite3.Error: If query execution fails
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if commit:
                conn.commit()

            return cursor
        except sqlite3.Error as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            conn.rollback()
            raise

    def fetch_one(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row as a dictionary.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Row as dictionary or None if not found
        """
        cursor = self.execute_query(query, params, commit=False)
        row = cursor.fetchone()

        if row is None:
            return None

        # Convert Row to dictionary
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))

    def fetch_all(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all rows as dictionaries.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            List of rows as dictionaries
        """
        cursor = self.execute_query(query, params, commit=False)
        rows = cursor.fetchall()

        if not rows:
            return []

        # Convert Rows to dictionaries
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def fetch_scalar(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> Any:
        """
        Fetch a single scalar value.

        Args:
            query: SQL query string (should return single value)
            params: Query parameters tuple

        Returns:
            Single scalar value or None
        """
        cursor = self.execute_query(query, params, commit=False)
        row = cursor.fetchone()
        return row[0] if row else None

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """
        Insert a row and return the last inserted row ID.

        Args:
            table: Table name
            data: Dictionary of column names and values

        Returns:
            Last inserted row ID
        """
        columns = list(data.keys())
        placeholders = ",".join(["?" for _ in columns])
        column_names = ",".join(columns)
        values = tuple(data.values())

        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

        cursor = self.execute_query(query, values)
        return cursor.lastrowid

    def update(
        self, table: str, data: Dict[str, Any], where_clause: str, where_params: Tuple[Any, ...]
    ) -> int:
        """
        Update rows and return number of affected rows.

        Args:
            table: Table name
            data: Dictionary of column names and values to update
            where_clause: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of affected rows
        """
        set_clause = ",".join([f"{col} = ?" for col in data.keys()])
        values = tuple(data.values()) + where_params

        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"

        cursor = self.execute_query(query, values)
        return cursor.rowcount

    def delete(self, table: str, where_clause: str, where_params: Tuple[Any, ...]) -> int:
        """
        Delete rows and return number of affected rows.

        Args:
            table: Table name
            where_clause: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of affected rows
        """
        query = f"DELETE FROM {table} WHERE {where_clause}"

        cursor = self.execute_query(query, where_params)
        return cursor.rowcount

    def exists(self, table: str, where_clause: str, where_params: Tuple[Any, ...]) -> bool:
        """
        Check if a row exists.

        Args:
            table: Table name
            where_clause: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            True if exists, False otherwise
        """
        query = f"SELECT 1 FROM {table} WHERE {where_clause} LIMIT 1"
        result = self.fetch_scalar(query, where_params)
        return result is not None
