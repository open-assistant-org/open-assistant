"""Pydantic models for the MCP (Model Context Protocol) server integration.

HTTP-only transport with three auth modes:
- ``none``: no authentication headers added
- ``header``: one or more static auth headers (values stored encrypted)
- ``oauth2``: OAuth 2.1 PKCE authorization-code flow, with either dynamic
  client registration (RFC 7591) or a pre-registered client ID (and optional
  secret). Access/refresh tokens and the client secret are stored encrypted.
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
    # Methods the token endpoint accepts for client authentication
    # (e.g. "client_secret_basic", "client_secret_post", "none").
    token_endpoint_auth_methods_supported: List[str] = Field(default_factory=list)
    # Canonical resource URI of the MCP server (RFC 8707 ``resource`` parameter).
    resource: Optional[str] = None


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
    # Pre-registered OAuth client ID (public, not a secret). When set, dynamic
    # client registration is skipped. The matching client secret, if any, is
    # stored encrypted in ``service_credentials``.
    oauth_client_id: Optional[str] = None
    # Cached OAuth server metadata (discovered at add time, refreshed on demand).
    oauth_metadata: Optional[McpOAuthMetadata] = None

    # Intent keywords copied onto the generated agent/skill row for triggering.
    intent_keywords: List[str] = Field(default_factory=list)
    # Optional system-prompt text injected when this server's tools are active.
    # When empty the service generates a default backstory.
    backstory: Optional[str] = None
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

    For ``auth_type="oauth2"``: discovers OAuth metadata, persists config, and
    creates an agent row with empty tools. Supply ``oauth_client_id`` (and
    ``oauth_client_secret`` for confidential clients) when the provider does
    not support dynamic client registration; otherwise a client is registered
    dynamically when the flow starts. The user
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
    oauth_client_id: Optional[str] = Field(default=None, max_length=500)
    oauth_client_secret: Optional[str] = Field(default=None, max_length=2000)
    intent_keywords: List[str] = Field(default_factory=list)
    backstory: Optional[str] = Field(default=None, max_length=2000)


class McpCredentialsRequest(BaseModel):
    """Update the stored credentials for a server.

    For ``header`` auth: supply ``headers`` (name → value). Blank values
    preserve the existing secret.

    For ``oauth2`` auth: supply ``oauth_client_id`` to switch to (or change) a
    pre-registered client — an empty string goes back to dynamic registration —
    and ``oauth_client_secret`` to set its secret (a blank value keeps the
    existing one). Changing the client clears stored tokens, so the server must
    be re-authorized.
    """

    headers: List[McpAuthHeaderInput] = Field(default_factory=list)
    oauth_client_id: Optional[str] = Field(default=None, max_length=500)
    oauth_client_secret: Optional[str] = Field(default=None, max_length=2000)


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
    # Pre-registered client ID, or None when a client is registered dynamically.
    oauth_client_id: Optional[str] = None
    # True when a client secret is stored (the secret itself is never returned).
    oauth_has_client_secret: bool = False
    enabled: bool
    has_credentials: bool
    intent_keywords: List[str] = Field(default_factory=list)
    backstory: Optional[str] = None
    tool_count: int = 0
    tool_names: List[str] = Field(default_factory=list)


class McpServerUpdateRequest(BaseModel):
    """Request to update mutable fields of an existing MCP server.

    Only ``display_name``, ``intent_keywords``, and ``backstory`` may be
    changed here. To change auth headers use ``/credentials``; to re-discover
    tools use ``/refresh``; to change enable state use ``/enable``.
    """

    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    intent_keywords: Optional[List[str]] = None
    backstory: Optional[str] = Field(default=None, max_length=2000)


class McpTestResult(BaseModel):
    success: bool
    message: str
    tool_count: Optional[int] = None
    tool_names: List[str] = Field(default_factory=list)
