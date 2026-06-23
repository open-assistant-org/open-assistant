"""Tool registry for managing available LLM tools."""

from typing import Any, Callable, Dict, List, Optional

from src.core.repositories.settings import SettingsRepository
from src.core.tools.schema import ToolSchema


class Tool:
    """Represents an executable tool."""

    def __init__(
        self,
        schema: ToolSchema,
        executor: Optional[Callable] = None,
        service_name: str = "",
        requires_auth: bool = True,
    ):
        """
        Initialize tool.

        Args:
            schema: Tool schema definition
            executor: Function to execute the tool (can be None for registry registration)
            service_name: Name of the service this tool belongs to
            requires_auth: Whether this tool requires authentication
        """
        self.schema = schema
        self.executor = executor
        self.service_name = service_name
        self.requires_auth = requires_auth

    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        if self.executor is None:
            raise RuntimeError(f"Tool {self.schema.name} has no executor configured")
        return await self.executor(**kwargs)


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        """
        Register a tool.

        Args:
            tool: Tool instance to register
        """
        self._tools[tool.schema.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(
        self, settings_repo: SettingsRepository, enabled_only: bool = True
    ) -> List[ToolSchema]:
        """
        List available tool schemas with per-tool filtering.

        Args:
            settings_repo: Settings repository to check enabled integrations
            enabled_only: Only return tools for enabled integrations

        Returns:
            List of tool schemas
        """
        if not enabled_only:
            return [tool.schema for tool in self._tools.values()]

        # Map service names to their settings keys
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
            "google_news": "google_news.enabled",
            "yahoo_finance": "yahoo_finance.enabled",
        }

        # Check which integrations are enabled
        enabled_tools = []
        for tool in self._tools.values():
            # System and search tools are always available
            if tool.service_name in ("system", "search"):
                enabled_tools.append(tool.schema)
                continue

            # Plugin tools: check plugin.{id}.enabled
            if tool.service_name.startswith("plugin_"):
                plugin_id = tool.service_name[len("plugin_") :]
                setting_key = f"plugin.{plugin_id}.enabled"
            else:
                # Get the settings key for this service
                setting_key = service_to_setting.get(
                    tool.service_name, f"{tool.service_name}.enabled"
                )

            # Check if integration is enabled
            service_enabled = settings_repo.get(setting_key)
            # Handle both bool and string storage: "false" as string is truthy in Python
            if service_enabled is None:
                continue
            if isinstance(service_enabled, bool) and not service_enabled:
                continue
            if isinstance(service_enabled, str) and service_enabled.lower() != "true":
                continue

            # Service is enabled — all its tools are available.
            # Per-agent filtering happens downstream via agent tool assignments.
            enabled_tools.append(tool.schema)

        return enabled_tools

    def unregister_by_prefix(self, prefix: str) -> int:
        """Remove all tools whose names start with *prefix*. Returns count removed."""
        to_remove = [name for name in self._tools if name.startswith(prefix)]
        for name in to_remove:
            del self._tools[name]
        return len(to_remove)

    def get_openai_tools(self, settings_repo: SettingsRepository) -> List[Dict[str, Any]]:
        """
        Get tools in OpenAI format for API calls.

        Args:
            settings_repo: Settings repository to check enabled integrations

        Returns:
            List of tool definitions in OpenAI format
        """
        schemas = self.list_tools(settings_repo, enabled_only=True)
        return [schema.to_openai_format() for schema in schemas]


# Global registry instance
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """
    Get global tool registry.

    Returns:
        Singleton ToolRegistry instance
    """
    return _registry
