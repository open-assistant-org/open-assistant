"""Pydantic models for agent API endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """Response model for a single agent definition."""

    id: int
    name: str
    display_name: str
    role: str
    goal: str
    backstory: str
    tools: List[str]
    enabled: bool
    allow_delegation: bool
    priority: int = 5
    intent_keywords: List[str] = []
    created_at: Optional[str] = None  # ISO format datetime string
    updated_at: Optional[str] = None  # ISO format datetime string

    class Config:
        from_attributes = True


class AgentListResponse(BaseModel):
    """Response model for listing agents."""

    agents: List[AgentResponse]
    total: int


class AgentUpdateRequest(BaseModel):
    """Request model for updating an agent."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, min_length=1, max_length=200)
    goal: Optional[str] = Field(None, min_length=1, max_length=500)
    backstory: Optional[str] = Field(None, min_length=1, max_length=5000)
    tools: Optional[List[str]] = None
    enabled: Optional[bool] = None
    allow_delegation: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=1)
    intent_keywords: Optional[List[str]] = None


class AgentCreateRequest(BaseModel):
    """Request model for creating a new agent."""

    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z_]+$")
    display_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=200)
    goal: str = Field(..., min_length=1, max_length=500)
    backstory: str = Field(default="", max_length=5000)
    tools: List[str] = Field(default_factory=list)
    priority: int = Field(default=100)
    enabled: bool = Field(default=True)
    allow_delegation: bool = Field(default=False)


class AgentReorderRequest(BaseModel):
    """Request model for reordering agents."""

    agent_order: List[str]  # List of agent names in priority order


class ToolAssignmentRequest(BaseModel):
    """Request model for assigning a tool to an agent."""

    tool_name: str
    agent_name: Optional[str] = None  # None to unassign


class BulkToolAssignmentRequest(BaseModel):
    """Request model for bulk tool assignment updates."""

    assignments: dict  # tool_name -> agent_name (or null)


class ToolAssignmentResponse(BaseModel):
    """Response model for tool assignments."""

    tool_name: str
    display_name: str
    description: str
    category: str
    service: str
    agent_name: Optional[str] = None


class GroupedToolsResponse(BaseModel):
    """Response model for tools grouped by service."""

    groups: dict  # service_name -> list of ToolAssignmentResponse
    agents: List[dict]  # simplified agent list for dropdowns


class AgentToggleRequest(BaseModel):
    """Request model for toggling agent enabled status."""

    enabled: bool


class AgentToolsResponse(BaseModel):
    """Response model for agent tools."""

    agent_name: str
    tools: List[str]


class AvailableToolResponse(BaseModel):
    """Response model for an available tool."""

    name: str
    description: str
    category: str


class AvailableToolsResponse(BaseModel):
    """Response model for listing available tools."""

    tools: List[AvailableToolResponse]
    total: int


class AgentInfoResponse(BaseModel):
    """Response model for runtime agent info."""

    name: str
    display_name: str
    role: str
    goal: str
    tools_count: int
    allow_delegation: bool


class CrewStatusResponse(BaseModel):
    """Response model for crew status."""

    initialized: bool
    agents: List[AgentInfoResponse]
    total_agents: int
