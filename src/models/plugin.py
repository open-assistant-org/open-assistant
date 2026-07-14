"""Pydantic models for the plugin system."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Primitive parameter types (also the allowed element types for arrays).
PARAM_PRIMITIVE_TYPES = {"string", "integer", "number", "boolean"}
# Full set of allowed parameter types (primitives + array).
PARAM_TYPES = PARAM_PRIMITIVE_TYPES | {"array"}


class PluginParameterItems(BaseModel):
    """Element-type descriptor for an ``array``-typed parameter.

    Only single-level arrays of primitives are supported; nested arrays and
    objects are intentionally disallowed for now.
    """

    type: Literal["string", "integer", "number", "boolean"]


class PluginEndpointParameter(BaseModel):
    """A parameter for a plugin endpoint."""

    name: str
    type: str = "string"  # "string", "integer", "number", "boolean", "array"
    description: str
    required: bool = True
    in_: str = Field("query", alias="in")  # "path", "query", "body", "header"
    default: Optional[Any] = None
    # Required when type == "array"; describes the array element type.
    items: Optional[PluginParameterItems] = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _validate_type_and_items(self) -> "PluginEndpointParameter":
        if self.type not in PARAM_TYPES:
            allowed = ", ".join(sorted(PARAM_TYPES))
            raise ValueError(
                f"Parameter '{self.name}' has invalid type '{self.type}'. "
                f"Must be one of: {allowed}."
            )

        if self.type == "array":
            if self.items is None:
                raise ValueError(
                    f"Parameter '{self.name}' has type 'array' but is missing the required "
                    f"'items' field describing the element type "
                    f'(e.g. "items": {{"type": "integer"}}).'
                )
            if self.in_ in ("path", "header"):
                raise ValueError(
                    f"Parameter '{self.name}' has type 'array' with in='{self.in_}', which is "
                    f"not supported. Array parameters are only meaningful for in='body' "
                    f"(JSON array in the request body) or in='query' (repeated query params)."
                )
        elif self.items is not None:
            raise ValueError(
                f"Parameter '{self.name}' defines 'items' but its type is '{self.type}', not "
                f"'array'. The 'items' field is only allowed when type is 'array'."
            )

        return self


class PluginEndpoint(BaseModel):
    """A single REST endpoint exposed as an LLM tool."""

    name: (
        str  # tool suffix, e.g. "list_work_items" → tool name "plugin_azure_devops_list_work_items"
    )
    display_name: str
    description: str
    method: str = "GET"  # GET, POST, PUT, PATCH, DELETE
    path: str  # e.g. "/{organization}/{project}/_apis/wit/wiql"
    parameters: List[PluginEndpointParameter] = []

    @field_validator("method")
    @classmethod
    def uppercase_method(cls, v: str) -> str:
        return v.upper()


class PluginAuth(BaseModel):
    """Authentication configuration for a plugin."""

    type: Literal["bearer", "header", "basic", "api_key_with_jwt"]
    # For type="header": the HTTP header name to send the token as
    header_name: Optional[str] = None
    # For type="basic" with a fixed password (e.g. Toggl uses "api_token" as password)
    fixed_password: Optional[str] = None
    # For type="api_key_with_jwt": static API key header (e.g. "X-apikey")
    api_key_header: Optional[str] = None
    # For type="api_key_with_jwt": path to POST credentials to (e.g. "/token")
    token_endpoint: Optional[str] = None
    # For type="api_key_with_jwt": JSON field in the login response containing the JWT
    token_field: Optional[str] = None
    # For type="api_key_with_jwt": prefix for the Authorization header (e.g. "Access_Token")
    token_prefix: Optional[str] = None


class PluginConfigField(BaseModel):
    """A configuration field the user must fill in (non-auth, e.g. org name, site URL)."""

    key: str  # stored as setting key "plugin.{plugin_id}.{key}"
    display_name: str
    description: Optional[str] = None
    required: bool = True
    sensitive: bool = False  # if True, stored in service_credentials instead of settings
    placeholder: Optional[str] = None


class PluginDefinition(BaseModel):
    """Complete definition of a plugin integration."""

    id: str  # lowercase + underscores, e.g. "azure_devops"
    display_name: str
    description: str
    icon: str = "🔌"
    base_url: str  # e.g. "https://dev.azure.com"
    auth: PluginAuth
    config_fields: List[PluginConfigField] = []
    endpoints: List[PluginEndpoint]

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        import re

        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(
                "Plugin id must be lowercase letters, digits, and underscores, starting with a letter"
            )
        return v

    @field_validator("endpoints")
    @classmethod
    def at_least_one_endpoint(cls, v: List[PluginEndpoint]) -> List[PluginEndpoint]:
        if not v:
            raise ValueError("Plugin must define at least one endpoint")
        return v


# ============================================================================
# API request / response models
# ============================================================================


class PluginListItem(BaseModel):
    """Summary of a plugin for list views."""

    id: str
    display_name: str
    description: str
    icon: str
    enabled: bool
    is_builtin: bool
    has_credentials: bool
    auth_type: str
    has_fixed_password: bool = False
    endpoint_count: int
    config_fields: List[Dict[str, Any]] = []


class PluginConfigResponse(BaseModel):
    """Current configuration values for a plugin (non-sensitive only)."""

    id: str
    config_values: Dict[str, str]
    has_credentials: bool


class PluginEnableRequest(BaseModel):
    enabled: bool


class PluginCredentialsRequest(BaseModel):
    """Credentials and config values submitted by the user."""

    # Auth credentials
    token: Optional[str] = None  # bearer / header / basic-username
    username: Optional[str] = None  # basic auth username / api_key_with_jwt username
    password: Optional[str] = None  # basic auth password / api_key_with_jwt password
    api_key: Optional[str] = None  # api_key_with_jwt static API key
    # Config field values (key → value)
    config: Dict[str, str] = {}


class PluginTestResult(BaseModel):
    success: bool
    message: str
