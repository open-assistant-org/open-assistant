"""
Agent registry for managing agent definitions.
Provides CRUD operations for agent definitions stored in the database.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from src.agents.base import AgentDefinition, DEFAULT_AGENTS
from src.core.database import DatabaseManager

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Registry for managing agent definitions.

    Handles database operations for agent configurations and provides
    factory methods for creating CrewAI agents.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the agent registry.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager

    def get_all_agents(self) -> List[AgentDefinition]:
        """
        Get all agent definitions from database.

        Returns:
            List of AgentDefinition instances
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, display_name, role, goal, backstory,
                   tools, priority, intent_keywords, enabled, allow_delegation, created_at, updated_at
            FROM agent_definitions
            ORDER BY priority DESC, name ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [AgentDefinition.from_db_row(dict(row)) for row in rows]

    def get_enabled_agents(self) -> List[AgentDefinition]:
        """
        Get all enabled agent definitions.

        Returns:
            List of enabled AgentDefinition instances
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, display_name, role, goal, backstory,
                   tools, priority, intent_keywords, enabled, allow_delegation, created_at, updated_at
            FROM agent_definitions
            WHERE enabled = 1
            ORDER BY priority DESC, name ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [AgentDefinition.from_db_row(dict(row)) for row in rows]

    def get_agent_by_name(self, name: str) -> Optional[AgentDefinition]:
        """
        Get an agent definition by name.

        Args:
            name: Agent name (e.g., 'coordinator', 'research')

        Returns:
            AgentDefinition if found, None otherwise
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, name, display_name, role, goal, backstory,
                   tools, priority, intent_keywords, enabled, allow_delegation, created_at, updated_at
            FROM agent_definitions
            WHERE name = ?
        """,
            (name,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return AgentDefinition.from_db_row(dict(row))
        return None

    def get_agent_by_id(self, agent_id: int) -> Optional[AgentDefinition]:
        """
        Get an agent definition by ID.

        Args:
            agent_id: Agent database ID

        Returns:
            AgentDefinition if found, None otherwise
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, name, display_name, role, goal, backstory,
                   tools, priority, intent_keywords, enabled, allow_delegation, created_at, updated_at
            FROM agent_definitions
            WHERE id = ?
        """,
            (agent_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return AgentDefinition.from_db_row(dict(row))
        return None

    def update_agent(self, agent_id: int, updates: Dict) -> Optional[AgentDefinition]:
        """
        Update an agent definition.

        Args:
            agent_id: Agent database ID
            updates: Dictionary of fields to update

        Returns:
            Updated AgentDefinition if successful, None otherwise
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        # Build update query dynamically based on provided fields
        allowed_fields = {
            "display_name",
            "role",
            "goal",
            "backstory",
            "tools",
            "priority",
            "enabled",
            "allow_delegation",
            "intent_keywords",
        }

        update_fields = []
        values = []

        for field, value in updates.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = ?")
                if field in ("tools", "intent_keywords"):
                    values.append(json.dumps(value) if isinstance(value, list) else value)
                else:
                    values.append(value)

        if not update_fields:
            conn.close()
            return self.get_agent_by_id(agent_id)

        # Add updated_at timestamp
        update_fields.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        values.append(agent_id)

        query = f"""
            UPDATE agent_definitions
            SET {', '.join(update_fields)}
            WHERE id = ?
        """

        cursor.execute(query, values)
        conn.commit()
        conn.close()

        logger.info(f"Updated agent {agent_id} with fields: {list(updates.keys())}")
        return self.get_agent_by_id(agent_id)

    def toggle_agent(self, agent_id: int, enabled: bool) -> Optional[AgentDefinition]:
        """
        Enable or disable an agent.

        Args:
            agent_id: Agent database ID
            enabled: Whether to enable or disable

        Returns:
            Updated AgentDefinition if successful, None otherwise
        """
        return self.update_agent(agent_id, {"enabled": enabled})

    def reset_agent_to_default(self, name: str) -> Optional[AgentDefinition]:
        """
        Reset an agent to its default configuration.

        Args:
            name: Agent name to reset

        Returns:
            Reset AgentDefinition if successful, None otherwise
        """
        if name not in DEFAULT_AGENTS:
            logger.warning(f"No default configuration for agent: {name}")
            return None

        default = DEFAULT_AGENTS[name]
        agent = self.get_agent_by_name(name)

        if not agent:
            logger.warning(f"Agent not found: {name}")
            return None

        return self.update_agent(
            agent.id,
            {
                "display_name": default["display_name"],
                "role": default["role"],
                "goal": default["goal"],
                "backstory": default["backstory"],
                "tools": default["tools"],
                "enabled": default["enabled"],
                "allow_delegation": default["allow_delegation"],
            },
        )

    def get_agent_tools(self, name: str) -> List[str]:
        """
        Get the tool names assigned to an agent.

        Args:
            name: Agent name

        Returns:
            List of tool names
        """
        agent = self.get_agent_by_name(name)
        if agent:
            return agent.tools
        return []

    def create_agent(
        self,
        name: str,
        display_name: str,
        role: str,
        goal: str,
        backstory: str,
        tools: List[str] = None,
        priority: int = 5,
        enabled: bool = True,
        allow_delegation: bool = False,
        intent_keywords: List[str] = None,
    ) -> Optional[AgentDefinition]:
        """
        Create a new agent definition.

        Args:
            name: Unique agent name (slug)
            display_name: Human-readable display name
            role: CrewAI role string
            goal: CrewAI goal string
            backstory: Agent backstory / system prompt
            tools: List of tool name strings
            priority: Priority ordering (1-10, higher = selected first)
            enabled: Whether agent is enabled
            allow_delegation: Whether agent can delegate
            intent_keywords: List of intent keywords for skill matching

        Returns:
            Created AgentDefinition if successful, None otherwise
        """
        if tools is None:
            tools = []
        if intent_keywords is None:
            intent_keywords = []

        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO agent_definitions
                (name, display_name, role, goal, backstory, tools, priority, intent_keywords, enabled, allow_delegation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    display_name,
                    role,
                    goal,
                    backstory,
                    json.dumps(tools),
                    priority,
                    json.dumps(intent_keywords),
                    enabled,
                    allow_delegation,
                ),
            )
            conn.commit()
            agent_id = cursor.lastrowid
            conn.close()

            logger.info(f"Created agent: {name}")
            return self.get_agent_by_id(agent_id)

        except Exception as e:
            conn.close()
            logger.error(f"Failed to create agent {name}: {e}")
            return None

    def delete_agent(self, name: str) -> bool:
        """
        Delete an agent definition.

        Args:
            name: Agent name to delete

        Returns:
            True if deleted, False otherwise
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM agent_definitions WHERE name = ?", (name,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if deleted:
            logger.info(f"Deleted agent: {name}")
        else:
            logger.warning(f"Agent not found for deletion: {name}")

        return deleted

    def reorder_agents(self, agent_order: List[str]) -> bool:
        """
        Reorder agents by setting priorities.

        Args:
            agent_order: List of agent names in desired priority order

        Returns:
            True if successful
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        total = len(agent_order)
        for idx, name in enumerate(agent_order):
            priority = total - idx  # First in list = highest priority
            cursor.execute(
                "UPDATE agent_definitions SET priority = ?, updated_at = ? WHERE name = ?",
                (priority, datetime.utcnow().isoformat(), name),
            )

        conn.commit()
        conn.close()

        logger.info(f"Reordered agents: {agent_order}")
        return True

    def get_tool_assignments(self) -> Dict[str, Optional[str]]:
        """
        Get a mapping of tool_name -> agent_name for all tools assigned to agents.

        Returns:
            Dictionary mapping tool names to their assigned agent name (or None if unassigned)
        """
        agents = self.get_all_agents()
        assignments: Dict[str, Optional[str]] = {}

        for agent in agents:
            for tool_name in agent.tools:
                assignments[tool_name] = agent.name

        return assignments

    def assign_tool_to_agent(self, tool_name: str, agent_name: Optional[str]) -> bool:
        """
        Assign a tool to an agent, removing it from any other agent.

        Args:
            tool_name: Name of the tool to assign
            agent_name: Name of the agent to assign to, or None to unassign

        Returns:
            True if successful
        """
        agents = self.get_all_agents()

        for agent in agents:
            if tool_name in agent.tools:
                # Remove from current agent
                new_tools = [t for t in agent.tools if t != tool_name]
                self.update_agent(agent.id, {"tools": new_tools})

        if agent_name:
            # Add to new agent
            target = self.get_agent_by_name(agent_name)
            if target:
                new_tools = list(target.tools) + [tool_name]
                self.update_agent(target.id, {"tools": new_tools})

        return True

    def bulk_update_tool_assignments(self, assignments: Dict[str, Optional[str]]) -> bool:
        """
        Bulk update tool-to-agent assignments.

        Args:
            assignments: Dictionary mapping tool_name -> agent_name (or None to unassign)

        Returns:
            True if successful
        """
        agents = self.get_all_agents()
        managed_tools = set(assignments.keys())

        # Start with each agent's existing tools that are NOT managed by this update
        new_agent_tools: Dict[str, List[str]] = {
            agent.name: [t for t in agent.tools if t not in managed_tools] for agent in agents
        }

        # Apply the managed assignments
        for tool_name, agent_name in assignments.items():
            if agent_name and agent_name in new_agent_tools:
                new_agent_tools[agent_name].append(tool_name)

        # Update each agent's tools
        for agent in agents:
            if agent.name in new_agent_tools:
                self.update_agent(agent.id, {"tools": new_agent_tools[agent.name]})

        return True

    def seed_default_agents(self) -> None:
        """
        Seed the database with default agent definitions if they don't exist.

        This is called during database initialization to ensure
        all default agents are present.
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        for name, config in DEFAULT_AGENTS.items():
            cursor.execute("SELECT id FROM agent_definitions WHERE name = ?", (name,))
            if not cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO agent_definitions
                    (name, display_name, role, goal, backstory, tools, enabled, allow_delegation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        config["name"],
                        config["display_name"],
                        config["role"],
                        config["goal"],
                        config["backstory"],
                        json.dumps(config["tools"]),
                        config["enabled"],
                        config["allow_delegation"],
                    ),
                )
                logger.info(f"Seeded default agent: {name}")

        conn.commit()
        conn.close()


def get_agent_registry(db_manager: DatabaseManager) -> AgentRegistry:
    """
    Factory function to get an AgentRegistry instance.

    Args:
        db_manager: Database manager instance

    Returns:
        AgentRegistry instance
    """
    return AgentRegistry(db_manager)
