"""Pydantic models for the MCP (Model Context Protocol) server integration.

Phase 1 scope: remote MCP servers reached over Streamable HTTP, authenticated
with one or more **static** headers (no OAuth). Header *values* are never stored
in the server config JSON — only the header *names* live there. The values are
kept encrypted in ``service_credentials`` under ``mcp_{id}``, which lets a single
server carry several secret headers (e.g. Cloudflare Access needs both
``CF-Access-Client-Id`` and ``CF-Access-Client-Secret``).
"""

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

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


class McpDiscoveredTool(BaseModel):
    """A tool discovered from an MCP server's ``tools/list`` response."""

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    """Complete definition of a configured MCP server.

    Persisted as ``data/mcp_servers/{id}.json``. Contains no secrets — auth
    header values live in ``service_credentials``.
    """

    id: str
    display_name: str
    description: str = ""
    icon: str = "🔌"
    transport: Literal["http"] = "http"  # Phase 1: Streamable HTTP only
    url: str
    # Names of the auth headers this server expects (values stored separately).
    auth_headers: List[McpAuthHeader] = Field(default_factory=list)
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
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("MCP server url must start with http:// or https://")
        return v


# ============================================================================
# API request / response models
# ============================================================================


class McpAuthHeaderInput(BaseModel):
    """A header name + value pair submitted by the user when adding/updating."""

    name: str
    value: str


class McpServerCreateRequest(BaseModel):
    """Request to add a new MCP server.

    Connects to the server, discovers its tools, persists the config, stores the
    header values securely, and creates a matching agent/skill row.
    """

    id: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    icon: str = "🔌"
    url: str
    auth_headers: List[McpAuthHeaderInput] = Field(default_factory=list)
    intent_keywords: List[str] = Field(default_factory=list)


class McpCredentialsRequest(BaseModel):
    """Update the stored auth header values for an existing server.

    ``headers`` maps header name -> value. Supplying a value replaces it; the set
    of header names is taken from the server config.
    """

    headers: List[McpAuthHeaderInput] = Field(default_factory=list)


class McpEnableRequest(BaseModel):
    enabled: bool


class McpServerListItem(BaseModel):
    """Summary of a configured MCP server for list views."""

    id: str
    display_name: str
    description: str
    icon: str
    transport: str
    url: str
    enabled: bool
    has_credentials: bool
    header_names: List[str] = Field(default_factory=list)
    intent_keywords: List[str] = Field(default_factory=list)
    tool_count: int = 0
    tool_names: List[str] = Field(default_factory=list)


class McpTestResult(BaseModel):
    success: bool
    message: str
    tool_count: Optional[int] = None
    tool_names: List[str] = Field(default_factory=list)
