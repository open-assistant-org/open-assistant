"""API endpoints for agent management."""

from fastapi import APIRouter, Depends, HTTPException, Request

from src.agents.registry import AgentRegistry
from src.core.dependencies import get_agent_registry, get_settings_repo
from src.core.repositories.settings import SettingsRepository
from src.core.tools.metadata import TOOL_METADATA, get_tool_service, get_all_tools_grouped
from src.models.agents import (
    AgentCreateRequest,
    AgentListResponse,
    AgentReorderRequest,
    AgentResponse,
    AgentToggleRequest,
    AgentToolsResponse,
    AgentUpdateRequest,
    AvailableToolResponse,
    AvailableToolsResponse,
    BulkToolAssignmentRequest,
    GroupedToolsResponse,
    ToolAssignmentRequest,
    ToolAssignmentResponse,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents(
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentListResponse:
    """
    List all agent definitions.

    Args:
        agent_registry: Agent registry (injected)

    Returns:
        AgentListResponse with all agents
    """
    agents = agent_registry.get_all_agents()
    agent_responses = [AgentResponse(**agent.to_dict()) for agent in agents]

    return AgentListResponse(agents=agent_responses, total=len(agent_responses))


@router.get("/enabled", response_model=AgentListResponse)
async def list_enabled_agents(
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentListResponse:
    """
    List all enabled agent definitions.

    Args:
        agent_registry: Agent registry (injected)

    Returns:
        AgentListResponse with enabled agents only
    """
    agents = agent_registry.get_enabled_agents()
    agent_responses = [AgentResponse(**agent.to_dict()) for agent in agents]

    return AgentListResponse(agents=agent_responses, total=len(agent_responses))


@router.get("/tools", response_model=AvailableToolsResponse)
async def list_available_tools() -> AvailableToolsResponse:
    """
    List all available tools that can be assigned to agents.

    Returns:
        AvailableToolsResponse with all tools
    """
    tools = []
    for tool in TOOL_METADATA.values():
        tools.append(
            AvailableToolResponse(
                name=tool.name,
                description=tool.description,
                category=tool.category,
            )
        )

    return AvailableToolsResponse(tools=tools, total=len(tools))


@router.get("/tools-grouped", response_model=GroupedToolsResponse)
async def get_tools_grouped(
    request: Request,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> GroupedToolsResponse:
    """
    Get all tools grouped by service/integration with current agent assignments.
    Only includes tools from enabled services (including enabled plugins).

    Returns:
        GroupedToolsResponse with tools grouped by service
    """
    # Map service names to their enabled setting keys
    service_to_setting = {
        "google": "google.enabled",
        "google_navigator": "google_navigator.enabled",
        "google_ads": "google_ads.enabled",
        "outlook": "outlook.enabled",
        "notion": "notion.enabled",
        "nextcloud": "nextcloud.enabled",
        "whatsapp": "whatsapp.enabled",
        "brave": "brave.enabled",
        "browser": "browser.enabled",
        "yahoo_finance": "yahoo_finance.enabled",
        "google_news": "google_news.enabled",
    }

    # Get current tool-to-agent assignments
    assignments = agent_registry.get_tool_assignments()

    # Get all tools grouped by service
    grouped = get_all_tools_grouped()

    # Build response, filtering out disabled services
    groups = {}
    for service, tools in grouped.items():
        # System tools are always available; others require their service to be enabled
        if service != "system":
            setting_key = service_to_setting.get(service, f"{service}.enabled")
            if not settings_repo.get(setting_key):
                continue

        groups[service] = [
            ToolAssignmentResponse(
                tool_name=tool.name,
                display_name=tool.display_name,
                description=tool.description,
                category=tool.category,
                service=service,
                agent_name=assignments.get(tool.name),
            ).model_dump()
            for tool in tools
        ]

    # Append enabled plugin tools
    plugin_service = getattr(request.app.state, "plugin_service", None)
    if plugin_service:
        plugin_groups = plugin_service.get_tool_metadata()
        for group_key, tools in plugin_groups.items():
            groups[group_key] = [
                ToolAssignmentResponse(
                    tool_name=t["name"],
                    display_name=t["display_name"],
                    description=t["description"],
                    category=t["category"],
                    service=group_key,
                    agent_name=assignments.get(t["name"]),
                ).model_dump()
                for t in tools
            ]

    # Build simplified agent list for dropdowns
    agents = agent_registry.get_all_agents()
    agent_list = [{"name": a.name, "display_name": a.display_name} for a in agents]

    return GroupedToolsResponse(groups=groups, agents=agent_list)


@router.post("", response_model=AgentResponse)
async def create_agent(
    request: AgentCreateRequest,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentResponse:
    """
    Create a new agent definition.

    Args:
        request: Agent creation request
        agent_registry: Agent registry (injected)

    Returns:
        AgentResponse with created agent

    Raises:
        HTTPException: If agent name already exists
    """
    existing = agent_registry.get_agent_by_name(request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Agent '{request.name}' already exists")

    agent = agent_registry.create_agent(
        name=request.name,
        display_name=request.display_name,
        role=request.role,
        goal=request.goal,
        backstory=request.backstory,
        tools=request.tools,
        priority=request.priority,
        enabled=request.enabled,
        allow_delegation=request.allow_delegation,
    )

    if not agent:
        raise HTTPException(status_code=500, detail="Failed to create agent")

    logger.info(f"Agent '{request.name}' created")
    return AgentResponse(**agent.to_dict())


@router.post("/reorder")
async def reorder_agents(
    request: AgentReorderRequest,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
):
    """
    Reorder agents by setting priorities.

    Args:
        request: Reorder request with list of agent names in priority order
        agent_registry: Agent registry (injected)

    Returns:
        Success message
    """
    agent_registry.reorder_agents(request.agent_order)
    return {"status": "ok", "message": "Agents reordered"}


@router.put("/tool-assignment")
async def update_tool_assignment(
    request: ToolAssignmentRequest,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
):
    """
    Assign a tool to a specific agent (removing from previous agent if any).

    Args:
        request: Tool assignment request
        agent_registry: Agent registry (injected)

    Returns:
        Success message
    """
    agent_registry.assign_tool_to_agent(request.tool_name, request.agent_name)
    return {
        "status": "ok",
        "message": f"Tool '{request.tool_name}' assigned to '{request.agent_name}'",
    }


@router.put("/tool-assignments-bulk")
async def bulk_update_tool_assignments(
    request: BulkToolAssignmentRequest,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
):
    """
    Bulk update all tool-to-agent assignments.

    Args:
        request: Bulk assignment request
        agent_registry: Agent registry (injected)

    Returns:
        Success message
    """
    agent_registry.bulk_update_tool_assignments(request.assignments)
    return {"status": "ok", "message": "Tool assignments updated"}


@router.delete("/{agent_name}")
async def delete_agent(
    agent_name: str,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
):
    """
    Delete an agent definition.

    Args:
        agent_name: Agent name to delete
        agent_registry: Agent registry (injected)

    Returns:
        Success message

    Raises:
        HTTPException: If agent not found or is coordinator
    """
    if agent_name == "coordinator":
        raise HTTPException(status_code=400, detail="Coordinator agent cannot be deleted")

    deleted = agent_registry.delete_agent(agent_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    logger.info(f"Agent '{agent_name}' deleted")
    return {"status": "ok", "message": f"Agent '{agent_name}' deleted"}


@router.get("/{agent_name}", response_model=AgentResponse)
async def get_agent(
    agent_name: str,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentResponse:
    """
    Get an agent definition by name.

    Args:
        agent_name: Agent name (e.g., 'coordinator', 'research')
        agent_registry: Agent registry (injected)

    Returns:
        AgentResponse with agent details

    Raises:
        HTTPException: If agent not found
    """
    agent = agent_registry.get_agent_by_name(agent_name)

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    return AgentResponse(**agent.to_dict())


@router.get("/{agent_name}/tools", response_model=AgentToolsResponse)
async def get_agent_tools(
    agent_name: str,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentToolsResponse:
    """
    Get tools assigned to an agent.

    Args:
        agent_name: Agent name
        agent_registry: Agent registry (injected)

    Returns:
        AgentToolsResponse with tool list

    Raises:
        HTTPException: If agent not found
    """
    agent = agent_registry.get_agent_by_name(agent_name)

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    return AgentToolsResponse(agent_name=agent_name, tools=agent.tools)


@router.put("/{agent_name}", response_model=AgentResponse)
async def update_agent(
    agent_name: str,
    request: AgentUpdateRequest,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentResponse:
    """
    Update an agent definition.

    Args:
        agent_name: Agent name
        request: Update request with fields to change
        agent_registry: Agent registry (injected)

    Returns:
        AgentResponse with updated agent

    Raises:
        HTTPException: If agent not found or update fails
    """
    agent = agent_registry.get_agent_by_name(agent_name)

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # Build updates dict from non-None values
    updates = request.model_dump(exclude_none=True)

    if not updates:
        # No changes, return current state
        return AgentResponse(**agent.to_dict())

    updated_agent = agent_registry.update_agent(agent.id, updates)

    if not updated_agent:
        raise HTTPException(status_code=500, detail="Failed to update agent")

    logger.info(f"Agent '{agent_name}' updated: {list(updates.keys())}")
    return AgentResponse(**updated_agent.to_dict())


@router.post("/{agent_name}/toggle", response_model=AgentResponse)
async def toggle_agent(
    agent_name: str,
    request: AgentToggleRequest,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentResponse:
    """
    Enable or disable an agent.

    Args:
        agent_name: Agent name
        request: Toggle request with enabled status
        agent_registry: Agent registry (injected)

    Returns:
        AgentResponse with updated agent

    Raises:
        HTTPException: If agent not found or is coordinator
    """
    agent = agent_registry.get_agent_by_name(agent_name)

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # Prevent disabling coordinator
    if agent_name == "coordinator" and not request.enabled:
        raise HTTPException(status_code=400, detail="Coordinator agent cannot be disabled")

    updated_agent = agent_registry.toggle_agent(agent.id, request.enabled)

    if not updated_agent:
        raise HTTPException(status_code=500, detail="Failed to toggle agent")

    status = "enabled" if request.enabled else "disabled"
    logger.info(f"Agent '{agent_name}' {status}")

    return AgentResponse(**updated_agent.to_dict())


@router.post("/{agent_name}/reset", response_model=AgentResponse)
async def reset_agent(
    agent_name: str,
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentResponse:
    """
    Reset an agent to its default configuration.

    Args:
        agent_name: Agent name
        agent_registry: Agent registry (injected)

    Returns:
        AgentResponse with reset agent

    Raises:
        HTTPException: If agent not found or has no default
    """
    reset_agent = agent_registry.reset_agent_to_default(agent_name)

    if not reset_agent:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{agent_name}' not found or has no default configuration",
        )

    logger.info(f"Agent '{agent_name}' reset to default")
    return AgentResponse(**reset_agent.to_dict())
