"""Pydantic models for settings operations."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SettingResponse(BaseModel):
    """Setting response model."""

    key: str = Field(..., description="Setting key")
    value: Any = Field(..., description="Setting value")
    value_type: str = Field(..., description="Value type (string, int, bool, json)")
    description: Optional[str] = Field(None, description="Setting description")
    updated_at: str = Field(..., description="Last update timestamp")


class SettingUpdateRequest(BaseModel):
    """Setting update request model."""

    value: Any = Field(..., description="Setting value")
    value_type: str = Field(default="string", description="Value type (string, int, bool, json)")
    description: Optional[str] = Field(None, description="Setting description")


class SettingsListResponse(BaseModel):
    """Settings list response model."""

    settings: List[SettingResponse] = Field(..., description="List of settings")


class LLMConfigResponse(BaseModel):
    """LLM configuration response model."""

    provider: str = Field(..., description="LLM provider")
    model: str = Field(..., description="Model identifier")
    base_url: str = Field(..., description="API base URL")
    temperature: float = Field(..., description="Sampling temperature")
    max_tokens: int = Field(..., description="Maximum tokens")
    media_model: Optional[str] = Field(None, description="Vision model for image processing")
    worker_model: Optional[str] = Field(None, description="Model for background worker tasks")
    writer_model: Optional[str] = Field(None, description="Model for document composition")


class LLMConfigUpdateRequest(BaseModel):
    """LLM configuration update request model."""

    provider: Optional[str] = Field(None, description="LLM provider")
    model: Optional[str] = Field(None, description="Model identifier")
    api_key: Optional[str] = Field(None, description="API key")
    base_url: Optional[str] = Field(None, description="API base URL")
    temperature: Optional[float] = Field(None, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens")
    media_model: Optional[str] = Field(None, description="Vision model for image processing")
    worker_model: Optional[str] = Field(None, description="Model for background worker tasks")
    writer_model: Optional[str] = Field(None, description="Model for document composition")


class CredentialStoreRequest(BaseModel):
    """Credential store request model."""

    service_name: str = Field(..., description="Service name (google, outlook, etc.)")
    credential_type: str = Field(
        ..., description="Credential type (oauth_token, api_key, app_password)"
    )
    credential_data: Dict[str, Any] = Field(..., description="Credential data dictionary")
    expires_at: Optional[str] = Field(None, description="Expiration timestamp (ISO format)")


class CredentialResponse(BaseModel):
    """Credential response model (metadata only)."""

    service_name: str = Field(..., description="Service name")
    credential_type: str = Field(..., description="Credential type")
    expires_at: Optional[str] = Field(None, description="Expiration timestamp")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class CredentialListResponse(BaseModel):
    """Credential list response model."""

    credentials: List[CredentialResponse] = Field(..., description="List of credentials")


class ConnectionTestResponse(BaseModel):
    """Connection test response model."""

    service_name: str = Field(..., description="Service name")
    status: str = Field(..., description="Status (connected, disconnected, error)")
    message: str = Field(..., description="Status message")
    tested_at: str = Field(..., description="Test timestamp")


class IntegrationSettingsResponse(BaseModel):
    """Integration settings response model."""

    service_name: str = Field(..., description="Service name")
    enabled: bool = Field(..., description="Whether integration is enabled")
    has_credentials: bool = Field(..., description="Whether credentials exist")
    credential_type: Optional[str] = Field(None, description="Credential type")
    credential_expires_at: Optional[str] = Field(None, description="Credential expiration")
    settings: Dict[str, Any] = Field(..., description="Integration-specific settings")


class IntegrationSettingsUpdateRequest(BaseModel):
    """Integration settings update request model."""

    enabled: Optional[bool] = Field(None, description="Enable/disable integration")
    settings: Dict[str, Any] = Field(..., description="Settings to update")


class SettingDefinitionResponse(BaseModel):
    """Setting definition for UI generation."""

    key: str = Field(..., description="Setting key")
    display_name: str = Field(..., description="Display name for UI")
    description: str = Field(..., description="Setting description")
    value_type: str = Field(..., description="Value type (string, int, float, bool, json)")
    category: str = Field(..., description="Category (application, llm, etc.)")
    is_sensitive: bool = Field(..., description="Whether value is sensitive")
    is_required: bool = Field(..., description="Whether value is required")
    default_value: Optional[Any] = Field(None, description="Default value")
    validation_regex: Optional[str] = Field(None, description="Regex for validation")
    min_value: Optional[float] = Field(None, description="Minimum value (for numbers)")
    max_value: Optional[float] = Field(None, description="Maximum value (for numbers)")
    options: Optional[List[str]] = Field(None, description="Valid options (for enums)")
    display_order: int = Field(..., description="Display order within category")
    placeholder: Optional[str] = Field(None, description="Placeholder text")
    help_url: Optional[str] = Field(None, description="Documentation URL")
    ui_widget: str = Field(..., description="UI widget type")


class SettingWithDefinitionResponse(BaseModel):
    """Setting value with its definition."""

    key: str = Field(..., description="Setting key")
    value: Any = Field(..., description="Current value")
    source: str = Field(..., description="Value source (db, env, default)")
    definition: SettingDefinitionResponse = Field(..., description="Setting definition")


class CategorySettingsResponse(BaseModel):
    """Settings grouped by category."""

    category: str = Field(..., description="Category name")
    settings: List[SettingWithDefinitionResponse] = Field(..., description="Settings in category")


class SettingCategoryResponse(BaseModel):
    """Category information."""

    name: str = Field(..., description="Category name")
    display_name: str = Field(..., description="Display name")
    count: int = Field(..., description="Number of settings in category")


class SettingDefinitionsResponse(BaseModel):
    """All setting definitions."""

    definitions: List[SettingDefinitionResponse] = Field(..., description="Setting definitions")


class BulkSettingUpdateRequest(BaseModel):
    """Bulk setting update request."""

    settings: Dict[str, Any] = Field(..., description="Dictionary of key-value pairs to update")


class BulkSettingUpdateResponse(BaseModel):
    """Bulk setting update response."""

    updated: List[str] = Field(..., description="Successfully updated keys")
    failed: List[Dict[str, str]] = Field(..., description="Failed updates with errors")


class TestConnectionRequest(BaseModel):
    """Connection test request model."""

    service_name: str = Field(..., description="Service name to test")
    timeout: Optional[int] = Field(default=10, description="Test timeout in seconds", ge=1, le=60)


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    id: int = Field(..., description="Entry ID")
    timestamp: str = Field(..., description="Event timestamp")
    event_type: str = Field(..., description="Event type")
    action: str = Field(..., description="Action performed")
    service_name: Optional[str] = Field(None, description="Service name")
    success: bool = Field(..., description="Whether action succeeded")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    user_id: Optional[str] = Field(None, description="User ID who performed action")
    ip_address: Optional[str] = Field(None, description="IP address")


class AuditLogResponse(BaseModel):
    """Audit log response model."""

    entries: List[AuditLogEntry] = Field(..., description="Audit log entries")
    total: int = Field(..., description="Total number of entries")
    limit: int = Field(..., description="Limit used for query")


class ValidationErrorDetail(BaseModel):
    """Validation error detail."""

    field: str = Field(..., description="Field with error")
    message: str = Field(..., description="Error message")


class SettingValidationResponse(BaseModel):
    """Setting validation response."""

    valid: bool = Field(..., description="Whether validation passed")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    success: bool = Field(default=False, description="Whether save succeeded")


class OAuthInitiateResponse(BaseModel):
    """OAuth initiation response model."""

    auth_url: str = Field(..., description="OAuth authorization URL")
    state: Optional[str] = Field(None, description="CSRF state token")


class DeviceCodeResponse(BaseModel):
    """Device code flow response model."""

    user_code: str = Field(..., description="Code user enters")
    verification_uri: str = Field(..., description="URL to visit")
    device_code: str = Field(..., description="Device code for polling")
    expires_in: int = Field(..., description="Seconds until expiration")
    interval: int = Field(default=5, description="Polling interval in seconds")


# ============================================================================
# PROMPTS MODELS
# ============================================================================


class PromptResponse(BaseModel):
    """Prompt response model."""

    id: int = Field(..., description="Prompt ID")
    key: str = Field(..., description="Prompt key")
    value: str = Field(..., description="Prompt value")
    description: Optional[str] = Field(None, description="Prompt description")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class PromptUpdateRequest(BaseModel):
    """Prompt update request model."""

    value: str = Field(..., description="New prompt value")


class PromptsListResponse(BaseModel):
    """Prompts list response model."""

    prompts: List[PromptResponse] = Field(..., description="List of prompts")


class ManagedStatusResponse(BaseModel):
    """Managed instance status response model."""

    is_managed: bool = Field(..., description="Whether this is a managed instance")
    hidden_services: List[str] = Field(
        default_factory=list,
        description="Services hidden in managed mode",
    )
    managed_fields: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Fields hidden per service in managed mode",
    )


# ============================================================================
# MANAGED ENDPOINTS MODELS (for platform push)
# ============================================================================


class CredentialPushRequest(BaseModel):
    """Single credential push request for managed endpoints."""

    service_name: str = Field(..., description="Service name (e.g., 'brave', 'google', 'llm')")
    credential_type: str = Field(
        ..., description="Credential type (oauth_token, api_key, app_password)"
    )
    credential_data: Dict[str, Any] = Field(
        ...,
        description="Credential data dictionary (e.g., {'value': '...'} or {'client_id': '...', 'client_secret': '...'})",
    )
    expires_at: Optional[str] = Field(None, description="Expiration timestamp (ISO format)")


class BulkCredentialPushRequest(BaseModel):
    """Bulk credential push request for managed endpoints."""

    credentials: List[CredentialPushRequest] = Field(
        ..., description="List of credentials to store"
    )


class CredentialPushResult(BaseModel):
    """Result of pushing a single credential."""

    service_name: str = Field(..., description="Service name")
    success: bool = Field(..., description="Whether the credential was stored successfully")
    error: Optional[str] = Field(None, description="Error message if failed")


class CredentialsPushResponse(BaseModel):
    """Response for bulk credential push."""

    stored: List[str] = Field(..., description="Successfully stored service names")
    failed: List[CredentialPushResult] = Field(
        default_factory=list, description="Failed credential pushes"
    )


class SettingsPushRequest(BaseModel):
    """Settings push request for managed endpoints."""

    settings: Dict[str, Any] = Field(
        ..., description="Dictionary of setting key-value pairs (e.g., {'brave.enabled': True})"
    )


class SettingsPushResponse(BaseModel):
    """Response for settings push."""

    stored: List[str] = Field(..., description="Successfully stored setting keys")
    failed: List[Dict[str, str]] = Field(
        default_factory=list, description="Failed setting updates with errors"
    )


class ManagedConfigResponse(BaseModel):
    """Response for managed config status endpoint."""

    credentials: List[CredentialResponse] = Field(
        ..., description="List of credential metadata (no sensitive data)"
    )
    settings: Dict[str, Any] = Field(..., description="Current settings values")
    instance_id: Optional[str] = Field(None, description="Instance ID from MANAGED_MODE")
