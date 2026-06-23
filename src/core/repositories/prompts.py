"""Repository for prompts operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PromptsRepository(BaseRepository):
    """Repository for managing assistant prompts (system prompt, memory, soul)."""

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a prompt by key.

        Args:
            key: Prompt key (system_prompt_default, system_prompt_custom, memory, soul)

        Returns:
            Prompt dictionary or None
        """
        query = (
            "SELECT id, key, value, description, created_at, updated_at FROM prompts WHERE key = ?"
        )
        return self.fetch_one(query, (key,))

    def get_value(self, key: str) -> Optional[str]:
        """
        Get just the value of a prompt by key.

        Args:
            key: Prompt key

        Returns:
            Prompt value string or None
        """
        result = self.fetch_scalar("SELECT value FROM prompts WHERE key = ?", (key,))
        return result

    def set(self, key: str, value: str) -> bool:
        """
        Update a prompt value.

        Args:
            key: Prompt key
            value: New prompt value

        Returns:
            True if successful
        """
        if self.exists("prompts", "key = ?", (key,)):
            affected = self.update(
                "prompts",
                {"value": value, "updated_at": datetime.utcnow().isoformat()},
                "key = ?",
                (key,),
            )
            logger.info(f"Updated prompt: {key}")
            return affected > 0
        else:
            self.insert(
                "prompts",
                {
                    "key": key,
                    "value": value,
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            logger.info(f"Created prompt: {key}")
            return True

    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all prompts.

        Returns:
            List of prompt dictionaries
        """
        query = (
            "SELECT id, key, value, description, created_at, updated_at FROM prompts ORDER BY id"
        )
        return self.fetch_all(query)
