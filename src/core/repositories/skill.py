"""Repository for skill operations."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.repositories.base import BaseRepository
from src.models.skill import Skill
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SkillRepository(BaseRepository):
    """Repository for managing skills (from agent_definitions table)."""

    def get_all_skills(self) -> List[Skill]:
        """
        Get all skills ordered by priority (highest first).

        Returns:
            List of Skill instances
        """
        query = """
            SELECT id, name, display_name, role, goal, backstory, tools, enabled,
                   priority, intent_keywords, category, created_at, updated_at
            FROM agent_definitions
            ORDER BY priority DESC, name ASC
        """
        rows = self.fetch_all(query)
        return [Skill.from_db_row(row) for row in rows]

    def get_enabled_skills(self) -> List[Skill]:
        """
        Get only enabled skills ordered by priority (highest first).

        Returns:
            List of enabled Skill instances
        """
        query = """
            SELECT id, name, display_name, role, goal, backstory, tools, enabled,
                   priority, intent_keywords, category, created_at, updated_at
            FROM agent_definitions
            WHERE enabled = 1
            ORDER BY priority DESC, name ASC
        """
        rows = self.fetch_all(query)
        return [Skill.from_db_row(row) for row in rows]

    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        """
        Get a skill by its name.

        Args:
            name: Skill name

        Returns:
            Skill instance or None if not found
        """
        query = """
            SELECT id, name, display_name, role, goal, backstory, tools, enabled,
                   priority, intent_keywords, category, created_at, updated_at
            FROM agent_definitions
            WHERE name = ?
        """
        row = self.fetch_one(query, (name,))
        return Skill.from_db_row(row) if row else None

    def get_skill_by_id(self, skill_id: int) -> Optional[Skill]:
        """
        Get a skill by its ID.

        Args:
            skill_id: Skill ID

        Returns:
            Skill instance or None if not found
        """
        query = """
            SELECT id, name, display_name, role, goal, backstory, tools, enabled,
                   priority, intent_keywords, category, created_at, updated_at
            FROM agent_definitions
            WHERE id = ?
        """
        row = self.fetch_one(query, (skill_id,))
        return Skill.from_db_row(row) if row else None

    def update_skill(self, skill_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update a skill with the provided fields.

        Handles JSON serialization for tools and intent_keywords fields.

        Args:
            skill_id: Skill ID to update
            updates: Dictionary of field updates (maps Skill model fields to DB fields)

        Returns:
            True if successful

        Raises:
            ValueError: If skill not found
        """
        # Check if skill exists
        if not self.exists("agent_definitions", "id = ?", (skill_id,)):
            raise ValueError(f"Skill with ID {skill_id} not found")

        # Map Skill model fields to database fields
        db_updates = {}

        if "display_name" in updates:
            db_updates["display_name"] = updates["display_name"]
        if "category" in updates:
            db_updates["category"] = updates["category"]
            # Also update role for backward compatibility
            db_updates["role"] = updates["category"]
        if "description" in updates:
            # description -> goal
            db_updates["goal"] = updates["description"]
        if "context_prompt" in updates:
            # context_prompt -> backstory
            db_updates["backstory"] = updates["context_prompt"]
        if "tools" in updates:
            # Serialize list to JSON
            db_updates["tools"] = json.dumps(updates["tools"])
        if "enabled" in updates:
            db_updates["enabled"] = int(updates["enabled"])
        if "priority" in updates:
            db_updates["priority"] = updates["priority"]
        if "intent_keywords" in updates:
            # Serialize list to JSON
            db_updates["intent_keywords"] = json.dumps(updates["intent_keywords"])

        # Always update timestamp
        db_updates["updated_at"] = datetime.utcnow().isoformat()

        affected = self.update("agent_definitions", db_updates, "id = ?", (skill_id,))

        logger.info(f"Updated skill ID {skill_id}: {list(db_updates.keys())}")
        return affected > 0

    def toggle_skill(self, skill_id: int, enabled: bool) -> bool:
        """
        Enable or disable a skill.

        Args:
            skill_id: Skill ID
            enabled: Whether to enable (True) or disable (False)

        Returns:
            True if successful

        Raises:
            ValueError: If skill not found
        """
        if not self.exists("agent_definitions", "id = ?", (skill_id,)):
            raise ValueError(f"Skill with ID {skill_id} not found")

        affected = self.update(
            "agent_definitions",
            {
                "enabled": int(enabled),
                "updated_at": datetime.utcnow().isoformat(),
            },
            "id = ?",
            (skill_id,),
        )

        status = "enabled" if enabled else "disabled"
        logger.info(f"Skill ID {skill_id} {status}")
        return affected > 0

    def create_skill(self, skill_data: Dict[str, Any]) -> Skill:
        """
        Create a new skill.

        Args:
            skill_data: Skill data dictionary with model field names

        Returns:
            Created Skill instance

        Raises:
            ValueError: If required fields are missing or name already exists
        """
        # Check required fields
        required = ["name", "display_name", "category", "description", "context_prompt"]
        for field in required:
            if field not in skill_data:
                raise ValueError(f"Missing required field: {field}")

        # Check for duplicate name
        if self.exists("agent_definitions", "name = ?", (skill_data["name"],)):
            raise ValueError(f"Skill with name '{skill_data['name']}' already exists")

        # Map to database fields
        db_data = {
            "name": skill_data["name"],
            "display_name": skill_data["display_name"],
            "role": skill_data["category"],
            "category": skill_data["category"],
            "goal": skill_data["description"],
            "backstory": skill_data["context_prompt"],
            "tools": json.dumps(skill_data.get("tools", [])),
            "enabled": int(skill_data.get("enabled", True)),
            "allow_delegation": 0,  # Skills don't use delegation
            "priority": skill_data.get("priority", 5),
            "intent_keywords": json.dumps(skill_data.get("intent_keywords", [])),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        skill_id = self.insert("agent_definitions", db_data)
        logger.info(f"Created skill: {skill_data['name']} (ID: {skill_id})")

        # Return the created skill
        skill = self.get_skill_by_id(skill_id)
        if not skill:
            raise RuntimeError(f"Failed to retrieve created skill with ID {skill_id}")

        return skill

    def get_skills_by_keywords(self, message: str, max_skills: int = 5) -> List[Skill]:
        """
        Get skills that match the message intent, ordered by priority.

        Uses keyword matching: checks if any skill's intent_keywords appear
        in the message.

        Args:
            message: User message text
            max_skills: Maximum number of skills to return

        Returns:
            List of matching Skill instances (up to max_skills)
        """
        # Get all enabled skills
        skills = self.get_enabled_skills()

        # Filter by intent match
        matching_skills = [skill for skill in skills if skill.matches_intent(message)]

        # If no matches, return top N by priority
        if not matching_skills:
            logger.info(
                f"No intent keyword matches for message, returning top {max_skills} skills by priority"
            )
            return skills[:max_skills]

        # Return matches (already sorted by priority from get_enabled_skills)
        logger.info(
            f"Found {len(matching_skills)} skills matching intent: "
            f"{[s.name for s in matching_skills[:max_skills]]}"
        )
        return matching_skills[:max_skills]
