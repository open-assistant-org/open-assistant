"""Tests for the CrewAI agent management module."""

import json
import pytest

from src.agents.base import AgentDefinition, DEFAULT_AGENTS
from src.agents.registry import AgentRegistry


class TestAgentDefinition:
    """Tests for the AgentDefinition model."""

    def test_from_db_row(self):
        """Test creating AgentDefinition from a database row."""
        row = {
            "id": 1,
            "name": "test_agent",
            "display_name": "Test Agent",
            "role": "Test Role",
            "goal": "Test Goal",
            "backstory": "Test backstory",
            "tools": '["tool1", "tool2"]',
            "enabled": True,
            "allow_delegation": False,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

        agent = AgentDefinition.from_db_row(row)

        assert agent.id == 1
        assert agent.name == "test_agent"
        assert agent.display_name == "Test Agent"
        assert agent.role == "Test Role"
        assert agent.goal == "Test Goal"
        assert agent.backstory == "Test backstory"
        assert agent.tools == ["tool1", "tool2"]
        assert agent.enabled is True
        assert agent.allow_delegation is False

    def test_from_db_row_with_list_tools(self):
        """Test creating AgentDefinition when tools is already a list."""
        row = {
            "id": 1,
            "name": "test_agent",
            "display_name": "Test Agent",
            "role": "Test Role",
            "goal": "Test Goal",
            "backstory": "Test backstory",
            "tools": ["tool1", "tool2"],
            "enabled": True,
            "allow_delegation": False,
        }

        agent = AgentDefinition.from_db_row(row)
        assert agent.tools == ["tool1", "tool2"]

    def test_to_dict(self):
        """Test converting AgentDefinition to dictionary."""
        agent = AgentDefinition(
            id=1,
            name="test_agent",
            display_name="Test Agent",
            role="Test Role",
            goal="Test Goal",
            backstory="Test backstory",
            tools=["tool1"],
            enabled=True,
            allow_delegation=False,
        )

        result = agent.to_dict()

        assert result["id"] == 1
        assert result["name"] == "test_agent"
        assert result["display_name"] == "Test Agent"
        assert result["tools"] == ["tool1"]
        assert result["enabled"] is True

    def test_default_agents_exist(self):
        """Test that default agents are defined."""
        assert "coordinator" in DEFAULT_AGENTS
        assert "research" in DEFAULT_AGENTS
        assert "communication" in DEFAULT_AGENTS
        assert "planner" in DEFAULT_AGENTS

    def test_coordinator_has_delegation(self):
        """Test that coordinator agent allows delegation."""
        coordinator = DEFAULT_AGENTS["coordinator"]
        assert coordinator["allow_delegation"] is True

    def test_specialist_agents_no_delegation(self):
        """Test that specialist agents don't allow delegation."""
        for name, config in DEFAULT_AGENTS.items():
            if name != "coordinator":
                assert config["allow_delegation"] is False, f"{name} should not allow delegation"


class TestAgentRegistry:
    """Tests for the AgentRegistry class."""

    def test_get_all_agents(self, clean_temp_db):
        """Test retrieving all agents from database."""
        registry = AgentRegistry(clean_temp_db)

        agents = registry.get_all_agents()

        # Should have at least the core agents
        assert len(agents) >= 4

        agent_names = [a.name for a in agents]
        assert "coordinator" in agent_names
        assert "research" in agent_names
        assert "communication" in agent_names
        assert "planner" in agent_names

    def test_get_enabled_agents(self, clean_temp_db):
        """Test retrieving only enabled agents."""
        registry = AgentRegistry(clean_temp_db)

        agents = registry.get_enabled_agents()

        # All returned agents should be enabled
        for agent in agents:
            assert agent.enabled is True

        # Should have at least the core enabled agents
        agent_names = [a.name for a in agents]
        assert "coordinator" in agent_names
        assert "research" in agent_names

    def test_get_agent_by_name(self, clean_temp_db):
        """Test retrieving an agent by name."""
        registry = AgentRegistry(clean_temp_db)

        agent = registry.get_agent_by_name("coordinator")

        assert agent is not None
        assert agent.name == "coordinator"
        assert agent.display_name == "Coordinator Agent"
        assert agent.allow_delegation is True

    def test_get_agent_by_name_not_found(self, clean_temp_db):
        """Test retrieving a non-existent agent."""
        registry = AgentRegistry(clean_temp_db)

        agent = registry.get_agent_by_name("nonexistent")

        assert agent is None

    def test_update_agent(self, clean_temp_db):
        """Test updating an agent's configuration."""
        registry = AgentRegistry(clean_temp_db)

        # Get coordinator agent
        agent = registry.get_agent_by_name("coordinator")
        assert agent is not None

        # Update the goal
        updated = registry.update_agent(agent.id, {"goal": "New test goal"})

        assert updated is not None
        assert updated.goal == "New test goal"

        # Verify persistence
        fetched = registry.get_agent_by_name("coordinator")
        assert fetched.goal == "New test goal"

    def test_toggle_agent(self, clean_temp_db):
        """Test enabling/disabling an agent."""
        registry = AgentRegistry(clean_temp_db)

        # Get research agent
        agent = registry.get_agent_by_name("research")
        assert agent.enabled is True

        # Disable it
        updated = registry.toggle_agent(agent.id, False)
        assert updated.enabled is False

        # Verify persistence
        fetched = registry.get_agent_by_name("research")
        assert fetched.enabled is False

        # Re-enable
        updated = registry.toggle_agent(agent.id, True)
        assert updated.enabled is True

    def test_reset_agent_to_default(self, clean_temp_db):
        """Test resetting an agent to its default configuration."""
        registry = AgentRegistry(clean_temp_db)

        # Get coordinator and modify it
        agent = registry.get_agent_by_name("coordinator")
        registry.update_agent(agent.id, {"goal": "Modified goal", "role": "Modified role"})

        # Verify modification
        modified = registry.get_agent_by_name("coordinator")
        assert modified.goal == "Modified goal"

        # Reset to default
        reset = registry.reset_agent_to_default("coordinator")

        assert reset is not None
        assert reset.goal == DEFAULT_AGENTS["coordinator"]["goal"]
        assert reset.role == DEFAULT_AGENTS["coordinator"]["role"]

    def test_reset_nonexistent_agent(self, clean_temp_db):
        """Test resetting a non-existent agent returns None."""
        registry = AgentRegistry(clean_temp_db)

        result = registry.reset_agent_to_default("nonexistent")

        assert result is None

    def test_get_agent_tools(self, clean_temp_db):
        """Test getting tools assigned to an agent."""
        registry = AgentRegistry(clean_temp_db)

        tools = registry.get_agent_tools("research")

        assert isinstance(tools, list)
        assert len(tools) > 0
        assert "google_search_emails" in tools

    def test_get_agent_tools_not_found(self, clean_temp_db):
        """Test getting tools for non-existent agent returns empty list."""
        registry = AgentRegistry(clean_temp_db)

        tools = registry.get_agent_tools("nonexistent")

        assert tools == []

    def test_update_agent_tools(self, clean_temp_db):
        """Test updating an agent's tool list."""
        registry = AgentRegistry(clean_temp_db)

        agent = registry.get_agent_by_name("coordinator")
        new_tools = ["tool1", "tool2", "tool3"]

        updated = registry.update_agent(agent.id, {"tools": new_tools})

        assert updated.tools == new_tools

        # Verify persistence
        fetched = registry.get_agent_by_name("coordinator")
        assert fetched.tools == new_tools
