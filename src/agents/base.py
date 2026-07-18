"""Base classes and models for agent definitions."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AgentDefinition:
    """
    Database model for agent definitions.

    Represents a CrewAI agent configuration stored in the database.
    """

    id: Optional[int] = None
    name: str = ""
    display_name: str = ""
    role: str = ""
    goal: str = ""
    backstory: str = ""
    tools: List[str] = field(default_factory=list)
    enabled: bool = True
    allow_delegation: bool = False
    priority: int = 5
    intent_keywords: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "AgentDefinition":
        """
        Create an AgentDefinition from a database row.

        Args:
            row: Database row as dictionary

        Returns:
            AgentDefinition instance
        """
        tools = row.get("tools", "[]")
        if isinstance(tools, str):
            tools = json.loads(tools)

        intent_keywords = row.get("intent_keywords", "[]")
        if isinstance(intent_keywords, str):
            intent_keywords = json.loads(intent_keywords)

        return cls(
            id=row.get("id"),
            name=row.get("name", ""),
            display_name=row.get("display_name", ""),
            role=row.get("role", ""),
            goal=row.get("goal", ""),
            backstory=row.get("backstory", ""),
            tools=tools,
            enabled=bool(row.get("enabled", True)),
            allow_delegation=bool(row.get("allow_delegation", False)),
            priority=row.get("priority", 5),
            intent_keywords=intent_keywords if intent_keywords else [],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for API responses.

        Returns:
            Dictionary representation
        """
        # Handle created_at - could be datetime or string from DB
        created_at_str = None
        if self.created_at:
            if isinstance(self.created_at, datetime):
                created_at_str = self.created_at.isoformat()
            else:
                created_at_str = self.created_at

        # Handle updated_at - could be datetime or string from DB
        updated_at_str = None
        if self.updated_at:
            if isinstance(self.updated_at, datetime):
                updated_at_str = self.updated_at.isoformat()
            else:
                updated_at_str = self.updated_at

        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "role": self.role,
            "goal": self.goal,
            "backstory": self.backstory,
            "tools": self.tools,
            "enabled": self.enabled,
            "allow_delegation": self.allow_delegation,
            "priority": self.priority,
            "intent_keywords": self.intent_keywords,
            "created_at": created_at_str,
            "updated_at": updated_at_str,
        }


# Default agent configurations for seeding.
# Backstories and tools are managed via database - these are structural defaults only.
DEFAULT_AGENTS = {
    "coordinator": {
        "name": "coordinator",
        "display_name": "Coordinator Agent",
        "role": "Task Coordinator",
        "goal": "Understand user intent, create an actionable plan, and delegate to specialist agents who MUST use their tools to fulfill the request",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": True,
        "priority": 10,
        "intent_keywords": [
            "coordinate",
            "plan",
            "organize",
            "help",
            "task",
            "delegate",
            "multi-step",
            "complex",
            "workflow",
        ],
    },
    "research": {
        "name": "research",
        "display_name": "Research Agent",
        "role": "Research Specialist",
        "goal": "Find and retrieve information from emails, files, notes, web sources, and web pages by ALWAYS using available tools",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 9,
        "intent_keywords": [
            "search",
            "find",
            "look",
            "email",
            "message",
            "file",
            "document",
            "notion",
            "information",
            "data",
            "web",
            "internet",
            "browse",
            "read",
            "attachment",
            "pdf",
            "database",
            "query",
            "list",
        ],
    },
    "communication": {
        "name": "communication",
        "display_name": "Communication Agent",
        "role": "Communication Specialist",
        "goal": "Compose and send messages, manage emails, and handle email classification by ALWAYS using available tools",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 7,
        "intent_keywords": [
            "send",
            "email",
            "draft",
            "whatsapp",
            "message",
            "compose",
            "write",
            "communication",
            "notify",
            "reply",
            "forward",
        ],
    },
    "writer": {
        "name": "writer",
        "display_name": "Content Writer Agent",
        "role": "Content Writer, Editor, and Document Generator",
        "goal": "Create, edit, and manage written content on Notion, and generate Word documents (.docx) by ALWAYS using available tools",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 6,
        "intent_keywords": [
            "write",
            "create",
            "document",
            "notion",
            "content",
            "note",
            "page",
            "edit",
            "update",
            "article",
            "report",
            "summary",
            "docx",
        ],
    },
    "file_handler": {
        "name": "file_handler",
        "display_name": "File Handler Agent",
        "role": "File Management Specialist",
        "goal": "Manage files across Nextcloud and OneDrive — list, search, read, upload, download, move, copy, and delete files",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 5,
        "intent_keywords": [
            "file",
            "upload",
            "download",
            "folder",
            "nextcloud",
            "onedrive",
            "move",
            "copy",
            "delete",
            "manage",
            "storage",
            "pdf",
            "read pdf",
            "extract",
            "document",
        ],
    },
    "planner": {
        "name": "planner",
        "display_name": "Planner Agent",
        "role": "Planning Specialist",
        "goal": "Manage calendars, schedule events, and help with time-based planning by ALWAYS using calendar tools",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 8,
        "intent_keywords": [
            "calendar",
            "schedule",
            "event",
            "meeting",
            "appointment",
            "plan",
            "time",
            "date",
            "reminder",
            "todo",
            "task",
        ],
    },
    "system": {
        "name": "system",
        "display_name": "System Agent",
        "role": "System Introspection & Self-Improvement Specialist",
        "goal": "Maintain and improve the assistant's self-knowledge by inspecting logs, reviewing conversations, extracting facts for memory, and refining personality from user preferences",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 3,
        "intent_keywords": [
            "log",
            "memory",
            "prompt",
            "soul",
            "conversation",
            "system",
            "debug",
            "settings",
            "configuration",
        ],
    },
    "navigator": {
        "name": "navigator",
        "display_name": "Navigator Agent",
        "role": "Geographic & Route Planning Specialist",
        "goal": "Find places, plan routes, estimate travel times, and answer location-based questions by ALWAYS using Google Places and Directions tools",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 4,
        "intent_keywords": [
            "place",
            "location",
            "direction",
            "route",
            "map",
            "nearby",
            "restaurant",
            "shop",
            "address",
            "travel",
            "distance",
            "gps",
            "navigate",
        ],
    },
    "browser": {
        "name": "browser",
        "display_name": "Browser Agent",
        "role": "Interactive Web Browsing Specialist",
        "goal": "Navigate and interact with web pages using accessibility tree structure",
        "backstory": "",
        "tools": [],
        "enabled": True,
        "allow_delegation": False,
        "priority": 2,
        "intent_keywords": [
            "browse",
            "website",
            "click",
            "page",
            "scrape",
            "extract",
            "open url",
            "visit",
            "screenshot",
        ],
    },
    "plugin_creator": {
        "name": "plugin_creator",
        "display_name": "Plugin Creator Agent",
        "role": "API Integration Specialist",
        "goal": "Install and verify Open Assistant plugins from OpenAPI specs, Swagger docs, or plugin JSON definitions",
        "backstory": "",
        "tools": ["install_plugin", "inspect_api_source", "test_plugin_connection"],
        "enabled": False,
        "allow_delegation": False,
        "priority": 0,
        "intent_keywords": [
            "plugin",
            "integration",
            "api",
            "openapi",
            "swagger",
            "connect",
            "add integration",
            "install plugin",
            "rest api",
            "new tool",
            "new integration",
            "connect service",
            "third party",
        ],
    },
}
