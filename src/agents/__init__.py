"""
AI agents for task execution and automation.
This module provides agent registry for the skills-based open assistant.
"""

from src.agents.base import AgentDefinition, DEFAULT_AGENTS
from src.agents.registry import AgentRegistry, get_agent_registry

__all__ = [
    "AgentDefinition",
    "DEFAULT_AGENTS",
    "AgentRegistry",
    "get_agent_registry",
]
