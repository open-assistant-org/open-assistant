"""Pydantic models for the MCP (Model Context Protocol) server integration.

Phase 1: remote MCP servers reached over Streamable HTTP, authenticated with
one or more **static** headers. Header *values* are never stored in the server
config JSON — only the header *names* live there; values are kept encrypted in
``service_credentials`` under ``mcp_{id}``.

Phase 2: local stdio servers launched as subprocesses (e.g. ``npx …`` or
``uvx …``). Sensitive environment variable values follow the same pattern —
only the var *names* are in the config JSON; values are stored encrypted.
"""

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Reserved header names the integration always manages itself.
_RESERVED_HEADERS = {"content-type", "accept"}


class McpAuthHeader(BaseModel):
    """Declares one auth header a server sends.

    Only the header ``name`` is persisted in the config; the matching value is
    stored encrypted in the credentials table keyed by this name.
    """

    name: str = Field(..., min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Header name cannot be empty")
        # RFC 7230 token characters — keep it strict but permissive enough for
        # real-world headers like "CF-Access-Client-Id".
        if not re.match(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$", v):
            raise ValueError(f"Invalid header name: {v!r}")
        if v.lower() in _RESERVED_HEADERS:
            raise ValueError(f"Header name '{v}' is reserved and cannot be set as an auth header")
        return v


class McpEnvVar(BaseModel):
    """Declares one environment variable a stdio server needs.

    Only the variable ``name`` is persisted in the config; the value is stored
    encrypted in the credentials table alongside header values.
    """

    name: str = Field(..., min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Env var name cannot be empty")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            raise ValueError(f"Invalid environment variable name: {v!r}")
        return v


class McpDiscoveredTool(BaseModel):
    """A tool discovered from an MCP server's ``tools/list`` response."""

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    """Complete definition of a configured MCP server.

    Persisted as ``data/mcp_servers/{id}.json``. Contains no secrets — auth
    header values and env var values live in ``service_credentials``.
    """

    id: str
    display_name: str
    description: str = ""
    icon: str = "🔌"
    transport: Literal["http", "stdio"] = "http"

    # HTTP transport fields
    url: Optional[str] = None
    # Names of the auth headers this server expects (values stored separately).
    auth_headers: List[McpAuthHeader] = Field(default_factory=list)

    # stdio transport fields
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    # Names of env vars the process needs (values stored separately).
    env_vars: List[McpEnvVar] = Field(default_factory=list)

    # Common
    # Intent keywords copied onto the generated agent/skill row for triggering.
    intent_keywords: List[str] = Field(default_factory=list)
    # Cached tool schemas from the last successful discovery, so startup can
    # register tools without contacting every server.
    discovered_tools: List[McpDiscoveredTool] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(
                "MCP server id must be lowercase letters, digits, and underscores, "
                "starting with a letter"
            )
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("MCP server url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "McpServerConfig":
        if self.transport == "http" and not self.url:
            raise ValueError("HTTP transport requires a URL")
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio transport requires a command")
        return self


# ============================================================================
# API request / response models
# ============================================================================


class McpAuthHeaderInput(BaseModel):
    """A header name + value pair submitted by the user when adding/updating."""

    name: str
    value: str


class McpEnvVarInput(BaseModel):
    """An env var name + value pair submitted by the user when adding/updating."""

    name: str
    value: str


class McpServerCreateRequest(BaseModel):
    """Request to add a new MCP server.

    Connects to the server, discovers its tools, persists the config, stores
    credentials securely, and creates a matching agent/skill row.
    """

    id: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    icon: str = "🔌"
    transport: Literal["http", "stdio"] = "http"
    # HTTP
    url: Optional[str] = None
    auth_headers: List[McpAuthHeaderInput] = Field(default_factory=list)
    # stdio
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env_vars: List[McpEnvVarInput] = Field(default_factory=list)
    # Common
    intent_keywords: List[str] = Field(default_factory=list)


class McpCredentialsRequest(BaseModel):
    """Update the stored credentials for an existing server.

    For HTTP servers: supply ``headers`` (name → value). Blank values preserve
    the existing secret. For stdio servers: supply ``env_vars`` (name → value).
    Both can be supplied together (for servers that use both transports or
    mixed credentials).
    """

    headers: List[McpAuthHeaderInput] = Field(default_factory=list)
    env_vars: List[McpEnvVarInput] = Field(default_factory=list)


class McpEnableRequest(BaseModel):
    enabled: bool


class McpServerListItem(BaseModel):
    """Summary of a configured MCP server for list views."""

    id: str
    display_name: str
    description: str
    icon: str
    transport: str
    # HTTP
    url: Optional[str] = None
    header_names: List[str] = Field(default_factory=list)
    # stdio
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env_var_names: List[str] = Field(default_factory=list)
    # Common
    enabled: bool
    has_credentials: bool
    intent_keywords: List[str] = Field(default_factory=list)
    tool_count: int = 0
    tool_names: List[str] = Field(default_factory=list)


class McpTestResult(BaseModel):
    success: bool
    message: str
    tool_count: Optional[int] = None
    tool_names: List[str] = Field(default_factory=list)
