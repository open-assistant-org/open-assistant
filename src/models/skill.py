"""Skill model for the skills-based LLM system.

A ``Skill`` is the *runtime* view of a row in the ``agent_definitions``
table.  The same table also has an *admin* view (``AgentDefinition`` in
``src/agents/base.py``) used by the REST API and admin UI.

Field mapping (DB → Skill):
  backstory       → context_prompt   (text injected into the LLM system prompt)
  role            → category         (grouping label)
  goal            → description      (brief capability summary)
  intent_keywords → intent_keywords  (keywords for automatic skill selection)
  tools           → tools            (tool names available to this skill)

Skills replace the previous CrewAI agent delegation model.  Instead of
routing between agents, the single LLM is given the context-prompts and
tools of all skills that match the request's intent, then executes a
tool-calling loop.  Parallel fan-out is achieved via the ``dispatch_task``
tool (``src/services/async_task_dispatcher.py``), which can pin a sub-task
to a specific skill via the ``pinned_skill`` param on ``handle_message``.
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """
    Skill model representing a specialized context + tools for the LLM.

    Skills replace the CrewAI agents. Instead of delegating between agents,
    the single LLM is provided with relevant skill contexts and tools based
    on the user's message intent.
    """

    id: int = Field(..., description="Skill database ID")
    name: str = Field(..., description="Unique skill name (e.g., 'research', 'communication')")
    display_name: str = Field(..., description="Human-readable name")
    category: str = Field(..., description="Skill category (from role field)")
    description: str = Field(
        ..., description="Brief description of what the skill does (from goal field)"
    )
    context_prompt: str = Field(
        ...,
        description="Detailed instructions for the LLM when using this skill (from backstory field)",
    )
    tools: List[str] = Field(
        default_factory=list, description="List of tool names available to this skill"
    )
    enabled: bool = Field(default=True, description="Whether this skill is active")
    priority: int = Field(
        default=5, description="Priority for skill selection (higher = selected first)"
    )
    intent_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords for intent matching to select this skill",
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "Skill":
        """
        Create a Skill instance from a database row (agent_definitions table).

        Field mapping:
        - backstory → context_prompt
        - role → category
        - goal → description
        - tools (JSON) → tools (List[str])
        - intent_keywords (JSON) → intent_keywords (List[str])

        Args:
            row: Database row dictionary

        Returns:
            Skill instance
        """
        # Parse JSON fields
        tools = json.loads(row["tools"]) if isinstance(row["tools"], str) else row["tools"]
        intent_keywords = (
            json.loads(row["intent_keywords"])
            if isinstance(row.get("intent_keywords"), str)
            else row.get("intent_keywords", [])
        )

        return cls(
            id=row["id"],
            name=row["name"],
            display_name=row["display_name"],
            category=row.get("category") or row["role"],
            description=row["goal"],
            context_prompt=row["backstory"],
            tools=tools if tools else [],
            enabled=bool(row["enabled"]),
            priority=row.get("priority", 5),
            intent_keywords=intent_keywords if intent_keywords else [],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def matches_intent(self, message: str) -> bool:
        """
        Check if this skill matches the user's message intent.

        Uses keyword matching: checks if any of the skill's intent_keywords
        appear in the message (case-insensitive).

        Args:
            message: User message text

        Returns:
            True if any keyword matches
        """
        if not self.intent_keywords:
            return False

        message_lower = message.lower()
        return any(keyword.lower() in message_lower for keyword in self.intent_keywords)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert skill to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "context_prompt": self.context_prompt,
            "tools": self.tools,
            "enabled": self.enabled,
            "priority": self.priority,
            "intent_keywords": self.intent_keywords,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
