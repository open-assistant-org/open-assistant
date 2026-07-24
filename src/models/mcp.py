"""Pydantic models for the MCP (Model Context Protocol) server integration.

HTTP-only transport with three auth modes:
- ``none``: no authentication headers added
- ``header``: one or more static auth headers (values stored encrypted)
- ``oauth2``: OAuth 2.1 PKCE authorization-code flow with dynamic client
  registration (RFC 7591). Access/refresh tokens stored encrypted.
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


class McpOAuthMetadata(BaseModel):
    """Cached OAuth 2.1 server metadata for an MCP server."""

    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: Optional[str] = None
    scopes_supported: List[str] = Field(default_factory=list)


class McpDiscoveredTool(BaseModel):
    """A tool discovered from an MCP server's ``tools/list`` response."""

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    """Complete definition of a configured MCP server.

    Persisted as ``data/mcp_servers/{id}.json``. Contains no secrets — auth
    header values and OAuth tokens live in ``service_credentials``.
    """

    id: str
    display_name: str
    description: str = ""
    icon: str = "🔌"
    transport: Literal["http"] = "http"
    url: str

    # Authentication mode
    auth_type: Literal["none", "header", "oauth2"] = "header"
    # Names of the auth headers this server expects (values stored separately).
    # Only used when auth_type == "header".
    auth_headers: List[McpAuthHeader] = Field(default_factory=list)
    # Requested OAuth scopes. Only used when auth_type == "oauth2".
    oauth_scopes: List[str] = Field(default_factory=list)
    # Cached OAuth server metadata (discovered at add time, refreshed on demand).
    oauth_metadata: Optional[McpOAuthMetadata] = None

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

    @model_validator(mode="after")
    def validate_auth_fields(self) -> "McpServerConfig":
        if self.auth_type == "header" and not self.auth_headers:
            # Allow header auth with no headers defined yet (added via credentials
            # update after the fact).
            pass
        return self


# ============================================================================
# API request / response models
# ============================================================================


class McpAuthHeaderInput(BaseModel):
    """A header name + value pair submitted by the user when adding/updating."""

    name: str
    value: str


class McpServerCreateRequest(BaseModel):
    """Request to add a new MCP server.

    For ``auth_type="header"``: connects using the supplied headers, discovers
    tools, persists config/credentials, and creates a matching agent/skill row.

    For ``auth_type="oauth2"``: discovers OAuth metadata, registers a dynamic
    client, persists config, and creates an agent row with empty tools. The user
    must then authorise via ``/api/mcp/{id}/oauth/start`` before tools can be
    discovered and used.

    For ``auth_type="none"``: connects without authentication and discovers tools
    immediately.
    """

    id: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    icon: str = "🔌"
    url: str
    auth_type: Literal["none", "header", "oauth2"] = "header"
    auth_headers: List[McpAuthHeaderInput] = Field(default_factory=list)
    oauth_scopes: List[str] = Field(default_factory=list)
    intent_keywords: List[str] = Field(default_factory=list)


class McpCredentialsRequest(BaseModel):
    """Update the stored static auth header values for a server.

    For ``header`` auth: supply ``headers`` (name → value). Blank values
    preserve the existing secret.
    """

    headers: List[McpAuthHeaderInput] = Field(default_factory=list)


class McpEnableRequest(BaseModel):
    enabled: bool


class McpOAuthStartRequest(BaseModel):
    """Request to start an OAuth 2.1 authorization flow."""

    redirect_uri: str


class McpOAuthStartResponse(BaseModel):
    """Response containing the URL to redirect the user to."""

    auth_url: str
    state: str


class McpServerListItem(BaseModel):
    """Summary of a configured MCP server for list views."""

    id: str
    display_name: str
    description: str
    icon: str
    transport: str
    url: str
    auth_type: str
    header_names: List[str] = Field(default_factory=list)
    oauth_scopes: List[str] = Field(default_factory=list)
    oauth_authorized: bool = False
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
