"""Repository for settings operations."""

import json
from datetime import datetime
from typing import Any, List, Optional

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SettingsRepository(BaseRepository):
    """Repository for managing application settings."""

    def get(self, key: str) -> Optional[Any]:
        """
        Get a setting value by key.

        Args:
            key: Setting key

        Returns:
            Setting value (typed according to value_type) or None
        """
        query = "SELECT value, value_type FROM settings WHERE key = ?"
        result = self.fetch_one(query, (key,))

        if not result:
            return None

        value = result["value"]
        value_type = result["value_type"]

        # Convert value based on type
        if value_type == "int":
            return int(value)
        elif value_type == "bool":
            return value.lower() == "true"
        elif value_type == "json":
            return json.loads(value)
        else:  # string
            return value

    def set(
        self, key: str, value: Any, value_type: str = "string", description: Optional[str] = None
    ) -> bool:
        """
        Set a setting value (insert or update).

        Args:
            key: Setting key
            value: Setting value
            value_type: Value type (string, int, bool, json)
            description: Setting description

        Returns:
            True if successful
        """
        # Convert value to string
        if value_type == "json":
            value_str = json.dumps(value)
        elif value_type == "bool":
            value_str = "true" if value else "false"
        else:
            value_str = str(value)

        # Check if exists
        if self.exists("settings", "key = ?", (key,)):
            # Update
            data = {
                "value": value_str,
                "value_type": value_type,
                "updated_at": datetime.utcnow().isoformat(),
            }

            if description:
                data["description"] = description

            affected = self.update("settings", data, "key = ?", (key,))

            logger.info(f"Updated setting: {key}")
            return affected > 0
        else:
            # Insert
            data = {
                "key": key,
                "value": value_str,
                "value_type": value_type,
                "description": description,
                "updated_at": datetime.utcnow().isoformat(),
            }

            self.insert("settings", data)
            logger.info(f"Created setting: {key}")
            return True

    def delete(self, key: str) -> bool:
        """
        Delete a setting.

        Args:
            key: Setting key

        Returns:
            True if deleted, False otherwise
        """
        affected = super().delete("settings", "key = ?", (key,))

        if affected > 0:
            logger.info(f"Deleted setting: {key}")

        return affected > 0

    def list_all(self, prefix: Optional[str] = None) -> List[dict]:
        """
        List all settings, optionally filtered by key prefix.

        Args:
            prefix: Key prefix filter (e.g., "llm." to get all LLM settings)

        Returns:
            List of setting dictionaries
        """
        if prefix:
            query = """
                SELECT * FROM settings
                WHERE key LIKE ?
                ORDER BY key
            """
            params = (f"{prefix}%",)
        else:
            query = "SELECT * FROM settings ORDER BY key"
            params = None

        return self.fetch_all(query, params)

    def get_by_prefix(self, prefix: str) -> dict:
        """
        Get all settings with a prefix as a dictionary.

        Args:
            prefix: Key prefix (e.g., "llm.")

        Returns:
            Dictionary of key (without prefix) -> value
        """
        settings = self.list_all(prefix)
        result = {}

        prefix_len = len(prefix)

        for setting in settings:
            key = setting["key"][prefix_len:]  # Remove prefix
            value = setting["value"]
            value_type = setting["value_type"]

            # Convert value based on type
            if value_type == "int":
                result[key] = int(value)
            elif value_type == "bool":
                result[key] = value.lower() == "true"
            elif value_type == "json":
                result[key] = json.loads(value)
            else:
                result[key] = value

        return result
