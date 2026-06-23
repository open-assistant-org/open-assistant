"""Settings API for configuration and credentials management."""

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from src.core.dependencies import get_audit_repo, get_credentials_repo, get_settings_repo
from src.core.llm_client import get_default_base_url
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.config import (
    SETTING_DEFINITIONS,
    ConfigCategory,
    get_setting_definition,
    get_settings_by_category,
)
from src.models.settings import (
    AuditLogEntry,
    AuditLogResponse,
    BulkSettingUpdateRequest,
    BulkSettingUpdateResponse,
    CategorySettingsResponse,
    ConnectionTestResponse,
    CredentialListResponse,
    CredentialResponse,
    CredentialStoreRequest,
    IntegrationSettingsResponse,
    IntegrationSettingsUpdateRequest,
    LLMConfigResponse,
    LLMConfigUpdateRequest,
    ManagedStatusResponse,
    SettingCategoryResponse,
    SettingDefinitionResponse,
    SettingDefinitionsResponse,
    SettingResponse,
    SettingsListResponse,
    SettingUpdateRequest,
    SettingValidationResponse,
    SettingWithDefinitionResponse,
    TestConnectionRequest,
)
from src.services.settings import SettingsService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ============================================================================
# SPECIFIC ROUTES - MUST BE BEFORE GENERIC /{key} ROUTE
# ============================================================================


@router.get("/categories", response_model=list[SettingCategoryResponse])
async def list_categories() -> list[SettingCategoryResponse]:
    """
    List all setting categories with counts.

    Returns:
        List of SettingCategoryResponse with category information
    """
    categories = []

    for category in ConfigCategory:
        # Skip bootstrap category (not shown in UI)
        if category == ConfigCategory.BOOTSTRAP:
            continue

        settings = get_settings_by_category(category)
        categories.append(
            SettingCategoryResponse(
                name=category.value,
                display_name=category.value.replace("_", " ").title(),
                count=len(settings),
            )
        )

    return categories


# Services that are completely hidden in managed mode
_MANAGED_HIDDEN_SERVICES = ["whatsapp"]

# Services with hidden fields in managed mode (only enable/disable and auth/test buttons shown)
_MANAGED_MANAGED_SERVICES = {
    "google": ["google.client_id", "google.client_secret", "google.project_id"],
    "google_navigator": ["google_navigator.places_api_key"],
    "brave": ["brave.api_key", "brave.results_limit", "brave.safe_search"],
    "browser": [
        "browser.headless",
        "browser.viewport_width",
        "browser.viewport_height",
        "browser.screenshot_quality",
    ],
    "whisper": ["whisper.api_key", "whisper.base_url", "whisper.model"],
    "mistral_ocr": [
        "mistral_ocr.api_key",
        "mistral_ocr.base_url",
        "mistral_ocr.model",
        "mistral_ocr.notion_database_id",
    ],
}


def _apply_timezone_change(request: Request, settings_repo: SettingsRepository) -> None:
    """Propagate a ``user.timezone`` change to live consumers.

    Updates log timestamp rendering and reschedules existing cron jobs so the
    new timezone takes effect immediately, without an application restart.
    """
    from src.utils.logger import get_logger as _get_logger
    from src.utils.logger import set_log_timezone

    tz_name = settings_repo.get("user.timezone") or os.getenv("USER_TIMEZONE") or "UTC"

    # Update log timestamp timezone
    set_log_timezone(tz_name)

    # Reschedule cron jobs so next-run times reflect the new timezone
    cron_service = getattr(request.app.state, "cron_job_service", None)
    if cron_service:
        try:
            cron_service.reschedule_all_jobs()
        except Exception as e:
            _get_logger(__name__).error(
                f"Failed to reschedule cron jobs after timezone change: {e}"
            )


@router.get("/managed-status", response_model=ManagedStatusResponse)
async def get_managed_status() -> ManagedStatusResponse:
    """
    Get managed instance status.

    Returns:
        ManagedStatusResponse indicating if this is a managed instance
        and which services/fields are hidden.
    """
    is_managed = bool(os.getenv("MANAGED_API_KEY", ""))

    return ManagedStatusResponse(
        is_managed=is_managed,
        hidden_services=_MANAGED_HIDDEN_SERVICES if is_managed else [],
        managed_fields=_MANAGED_MANAGED_SERVICES if is_managed else {},
    )


@router.get("/category/{category}", response_model=CategorySettingsResponse)
async def get_category_settings(
    category: str,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> CategorySettingsResponse:
    """
    Get all settings for a specific category.

    Args:
        category: Category name
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        CategorySettingsResponse with settings in the category

    Raises:
        HTTPException: If category not found
    """
    try:
        category_enum = ConfigCategory(category)
    except ValueError:
        raise HTTPException(status_code=404, detail="Category not found")

    category_definitions = get_settings_by_category(category_enum)

    # Batch load: 2 queries for the whole category instead of 2 per setting (N+1).
    # 1. All DB rows for this category in one SELECT … LIKE query.
    db_settings: dict = {}
    for row in settings_repo.list_all(f"{category}."):
        raw, vtype = row["value"], row["value_type"]
        if vtype == "int":
            db_settings[row["key"]] = int(raw)
        elif vtype == "bool":
            db_settings[row["key"]] = raw.lower() == "true"
        elif vtype == "json":
            db_settings[row["key"]] = json.loads(raw)
        else:
            db_settings[row["key"]] = raw

    # 2. All credential metadata indexed by service_name (no decryption).
    cred_meta: dict = {m["service_name"]: m for m in credentials_repo.list_all_metadata()}

    settings_list = []
    for key, definition in category_definitions.items():
        if definition.is_sensitive:
            service_name = key.split(".")[0]
            has_db_cred = service_name in cred_meta
            env_value = os.getenv(definition.env_var_name) if definition.env_var_name else None
            has_value = has_db_cred or bool(env_value)
            display_value = "***MASKED***" if has_value else definition.default_value
            source = "db" if has_db_cred else ("env" if env_value else "default")
        else:
            if key in db_settings:
                display_value = db_settings[key]
                source = "db"
            else:
                env_value = os.getenv(definition.env_var_name) if definition.env_var_name else None
                if env_value is not None:
                    display_value = env_value
                    source = "env"
                else:
                    display_value = definition.default_value
                    source = "default"

        settings_list.append(
            SettingWithDefinitionResponse(
                key=key,
                value=display_value,
                source=source,
                definition=SettingDefinitionResponse(
                    key=definition.key,
                    display_name=definition.display_name,
                    description=definition.description,
                    value_type=definition.value_type,
                    category=definition.category.value,
                    is_sensitive=definition.is_sensitive,
                    is_required=definition.is_required,
                    default_value=definition.default_value,
                    validation_regex=definition.validation_regex,
                    min_value=definition.min_value,
                    max_value=definition.max_value,
                    options=definition.options,
                    display_order=definition.display_order,
                    placeholder=definition.placeholder,
                    help_url=definition.help_url,
                    ui_widget=definition.ui_widget,
                ),
            )
        )

    # Sort by display order
    settings_list.sort(key=lambda s: s.definition.display_order)

    return CategorySettingsResponse(category=category, settings=settings_list)


@router.get("/definitions", response_model=SettingDefinitionsResponse)
async def get_definitions() -> SettingDefinitionsResponse:
    """
    Get all setting definitions for UI generation.

    Returns:
        SettingDefinitionsResponse with all setting definitions
    """
    definitions_list = []

    for key, definition in SETTING_DEFINITIONS.items():
        # Skip bootstrap settings (not shown in UI)
        if definition.category == ConfigCategory.BOOTSTRAP:
            continue

        definitions_list.append(
            SettingDefinitionResponse(
                key=definition.key,
                display_name=definition.display_name,
                description=definition.description,
                value_type=definition.value_type,
                category=definition.category.value,
                is_sensitive=definition.is_sensitive,
                is_required=definition.is_required,
                default_value=definition.default_value,
                validation_regex=definition.validation_regex,
                min_value=definition.min_value,
                max_value=definition.max_value,
                options=definition.options,
                display_order=definition.display_order,
                placeholder=definition.placeholder,
                help_url=definition.help_url,
                ui_widget=definition.ui_widget,
            )
        )

    return SettingDefinitionsResponse(definitions=definitions_list)


# ============================================================================
# GENERIC ROUTES - MUST BE AFTER SPECIFIC ROUTES
# ============================================================================


@router.get("", response_model=SettingsListResponse)
async def list_settings(
    prefix: str = None,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> SettingsListResponse:
    """
    List all settings.

    Args:
        prefix: Optional key prefix filter
        settings_repo: Settings repository (injected)

    Returns:
        SettingsListResponse with list of settings
    """
    settings_list = settings_repo.list_all(prefix)
    settings_responses = [SettingResponse(**s) for s in settings_list]

    return SettingsListResponse(settings=settings_responses)


@router.get("/credentials", response_model=CredentialListResponse)
async def list_credentials(
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> CredentialListResponse:
    """
    List all service credentials (metadata only).

    Args:
        credentials_repo: Credentials repository (injected)

    Returns:
        CredentialListResponse with list of credentials
    """
    credentials_list = credentials_repo.list_all_metadata()
    credential_responses = [CredentialResponse(**c) for c in credentials_list]

    return CredentialListResponse(credentials=credential_responses)


@router.get("/audit", response_model=AuditLogResponse)
async def get_audit_log(
    limit: int = 100,
    event_type: str = None,
    service_name: str = None,
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> AuditLogResponse:
    """
    Get audit log for configuration changes.

    Args:
        limit: Maximum number of entries to return
        event_type: Filter by event type
        service_name: Filter by service name
        audit_repo: Audit log repository (injected)

    Returns:
        AuditLogResponse with audit log entries
    """
    entries = audit_repo.get_recent(limit=limit, event_type=event_type, service_name=service_name)

    audit_entries = []
    for entry in entries:
        audit_entries.append(
            AuditLogEntry(
                id=entry["id"],
                timestamp=entry["timestamp"],
                event_type=entry["event_type"],
                action=entry["action"],
                service_name=entry.get("service_name"),
                success=entry["success"],
                details=(
                    json.loads(entry["details"])
                    if isinstance(entry.get("details"), str)
                    else entry.get("details")
                ),
                error_message=entry.get("error_message"),
                user_id=entry.get("user_id"),
                ip_address=entry.get("ip_address"),
            )
        )

    return AuditLogResponse(entries=audit_entries, total=len(audit_entries), limit=limit)


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> SettingResponse:
    """
    Get a specific setting.

    Args:
        key: Setting key
        settings_repo: Settings repository (injected)

    Returns:
        SettingResponse with setting details

    Raises:
        HTTPException: If setting not found
    """
    value = settings_repo.get(key)

    if value is None:
        raise HTTPException(status_code=404, detail="Setting not found")

    # Get full setting details
    settings_list = settings_repo.list_all()
    setting_dict = next((s for s in settings_list if s["key"] == key), None)

    if not setting_dict:
        raise HTTPException(status_code=404, detail="Setting not found")

    return SettingResponse(**setting_dict)


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    request: SettingUpdateRequest,
    http_request: Request,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> SettingResponse:
    """
    Update a setting.

    Args:
        key: Setting key
        request: Setting update request
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        SettingResponse with updated setting

    Raises:
        HTTPException: If update fails
    """
    try:
        # Use SettingsService to properly handle sensitive credentials
        settings_service = SettingsService(settings_repo, credentials_repo)
        result = settings_service.validate_and_set(key, request.value)

        if not result.get("valid") or not result.get("success"):
            errors = result.get("errors", ["Failed to update setting"])
            raise HTTPException(status_code=400, detail=", ".join(errors))

        # Propagate timezone changes to logging and the cron scheduler
        if key == "user.timezone":
            _apply_timezone_change(http_request, settings_repo)

        # Return updated setting
        # For sensitive settings, construct response from definition since they're stored in credentials
        definition = get_setting_definition(key)
        if definition and definition.is_sensitive:
            return SettingResponse(
                key=key,
                value="***MASKED***",  # Don't return sensitive values
                value_type=definition.value_type,
                description=definition.description,
                updated_at=datetime.utcnow().isoformat(),
            )

        # For non-sensitive settings, retrieve from settings table
        settings_list = settings_repo.list_all()
        setting_dict = next((s for s in settings_list if s["key"] == key), None)

        if not setting_dict:
            raise HTTPException(status_code=404, detail="Setting not found after update")

        return SettingResponse(**setting_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update setting: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update setting: {str(e)}")


@router.delete("/{key}")
async def delete_setting(
    key: str,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> dict:
    """
    Delete a setting.

    Args:
        key: Setting key
        settings_repo: Settings repository (injected)

    Returns:
        Success message

    Raises:
        HTTPException: If setting not found
    """
    success = settings_repo.delete(key)

    if not success:
        raise HTTPException(status_code=404, detail="Setting not found")

    return {"message": "Setting deleted successfully"}


@router.get("/llm/config", response_model=LLMConfigResponse)
async def get_llm_config(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> LLMConfigResponse:
    """
    Get LLM configuration.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        LLMConfigResponse with LLM configuration
    """
    settings_service = SettingsService(settings_repo, credentials_repo)
    config = settings_service.get_llm_config()

    # Remove API key from response
    config.pop("api_key", None)

    return LLMConfigResponse(**config)


@router.put("/llm/config", response_model=LLMConfigResponse)
async def update_llm_config(
    request: LLMConfigUpdateRequest,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> LLMConfigResponse:
    """
    Update LLM configuration.

    Args:
        request: LLM config update request
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        LLMConfigResponse with updated configuration

    Raises:
        HTTPException: If update fails
    """
    settings_service = SettingsService(settings_repo, credentials_repo)

    # Convert request to dict, excluding None values
    config_dict = request.model_dump(exclude_none=True)

    success = settings_service.update_llm_config(config_dict)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update LLM config")

    # Return updated config
    config = settings_service.get_llm_config()
    config.pop("api_key", None)

    return LLMConfigResponse(**config)


@router.post("/credentials", response_model=CredentialResponse)
async def store_credential(
    request: CredentialStoreRequest,
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> CredentialResponse:
    """
    Store encrypted credentials for a service.

    Args:
        request: Credential store request
        credentials_repo: Credentials repository (injected)
        settings_repo: Settings repository (injected)

    Returns:
        CredentialResponse with credential metadata

    Raises:
        HTTPException: If storage fails
    """
    settings_service = SettingsService(settings_repo, credentials_repo)

    success = settings_service.store_credential(
        service_name=request.service_name,
        credential_type=request.credential_type,
        credential_data=request.credential_data,
        expires_at=request.expires_at,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to store credentials")

    # Return metadata
    metadata = credentials_repo.get_metadata(request.service_name)

    if not metadata:
        raise HTTPException(status_code=404, detail="Credential not found after creation")

    return CredentialResponse(**metadata)


@router.delete("/credentials/{service_name}")
async def delete_credential(
    service_name: str,
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> dict:
    """
    Delete credentials for a service.

    Args:
        service_name: Service name
        credentials_repo: Credentials repository (injected)
        settings_repo: Settings repository (injected)

    Returns:
        Success message

    Raises:
        HTTPException: If credentials not found
    """
    settings_service = SettingsService(settings_repo, credentials_repo)
    success = settings_service.delete_credential(service_name)

    if not success:
        raise HTTPException(status_code=404, detail="Credentials not found")

    return {"message": "Credentials deleted successfully"}


@router.post("/credentials/{service_name}/test", response_model=ConnectionTestResponse)
async def test_connection(
    service_name: str,
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> ConnectionTestResponse:
    """
    Test connection to a service.

    Args:
        service_name: Service name
        credentials_repo: Credentials repository (injected)
        settings_repo: Settings repository (injected)

    Returns:
        ConnectionTestResponse with test results
    """
    settings_service = SettingsService(settings_repo, credentials_repo)
    result = settings_service.test_connection(service_name)

    return ConnectionTestResponse(
        service_name=result["service_name"],
        status=result["status"],
        message=result["message"],
        tested_at=datetime.utcnow().isoformat(),
    )


@router.get("/integrations/{service_name}", response_model=IntegrationSettingsResponse)
async def get_integration_settings(
    service_name: str,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> IntegrationSettingsResponse:
    """
    Get settings for an integration.

    Args:
        service_name: Service name (google, outlook, etc.)
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        IntegrationSettingsResponse with integration settings
    """
    settings_service = SettingsService(settings_repo, credentials_repo)
    settings_dict = settings_service.get_integration_settings(service_name)

    return IntegrationSettingsResponse(service_name=service_name, **settings_dict)


@router.put("/integrations/{service_name}", response_model=IntegrationSettingsResponse)
async def update_integration_settings(
    service_name: str,
    request: IntegrationSettingsUpdateRequest,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> IntegrationSettingsResponse:
    """
    Update settings for an integration.

    Args:
        service_name: Service name
        request: Integration settings update request
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        IntegrationSettingsResponse with updated settings

    Raises:
        HTTPException: If update fails
    """
    settings_service = SettingsService(settings_repo, credentials_repo)

    success = settings_service.update_integration_settings(service_name, request.settings)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update integration settings")

    # Return updated settings
    settings_dict = settings_service.get_integration_settings(service_name)

    return IntegrationSettingsResponse(service_name=service_name, **settings_dict)


# ============================================================================
# TESTING ENDPOINTS
# ============================================================================


@router.post("/test-llm", response_model=ConnectionTestResponse)
async def test_llm_connection(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> ConnectionTestResponse:
    """
    Test LLM connection with current settings.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        ConnectionTestResponse with test results
    """
    settings_service = SettingsService(settings_repo, credentials_repo)

    # Use the same fallback chain as chat to get API key (DB → credentials → ENV)
    api_key = settings_service.get_config_with_fallback("llm.api_key")

    # Get other settings
    provider = settings_service.get_config_with_fallback("llm.provider", "openrouter")
    model = settings_service.get_config_with_fallback("llm.model", "anthropic/claude-3.5-sonnet")
    base_url = settings_service.get_config_with_fallback("llm.base_url") or get_default_base_url(
        provider
    )

    # Ollama, vLLM, and custom providers don't require an API key
    keyless_providers = ("ollama", "vllm", "custom")
    if not api_key and provider not in keyless_providers:
        return ConnectionTestResponse(
            service_name="llm",
            status="error",
            message="API key not configured",
            tested_at=datetime.utcnow().isoformat(),
        )

    # Keyless providers ignore the API key value — use a placeholder so the
    # OpenAI SDK doesn't complain about a missing key
    effective_api_key = api_key or "EMPTY"

    # Perform actual connection test
    try:
        import openai

        # Debug logging
        logger.info(f"LLM test - provider: {provider}, base_url: {base_url}, model: {model}")
        logger.info(
            f"LLM test - api_key prefix: {api_key[:10]}..."
            if api_key
            else "No API key (keyless provider)"
        )

        client = openai.OpenAI(
            api_key=effective_api_key,
            base_url=base_url,
        )

        # Make a minimal test call
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
        )

        return ConnectionTestResponse(
            service_name="llm",
            status="success",
            message="Connection successful",
            tested_at=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.error(f"LLM connection test failed: {e}")
        return ConnectionTestResponse(
            service_name="llm",
            status="error",
            message=f"Connection failed: {str(e)}",
            tested_at=datetime.utcnow().isoformat(),
        )


@router.post("/reset/{key}", response_model=SettingResponse)
async def reset_setting(
    key: str,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> SettingResponse:
    """
    Reset a setting to its default value.

    Args:
        key: Setting key
        settings_repo: Settings repository (injected)

    Returns:
        SettingResponse with reset setting

    Raises:
        HTTPException: If setting not found or reset fails
    """
    definition = get_setting_definition(key)

    if not definition:
        raise HTTPException(status_code=404, detail="Setting not found")

    if definition.category == ConfigCategory.BOOTSTRAP:
        raise HTTPException(status_code=400, detail="Bootstrap settings cannot be reset via API")

    # Delete from database (will fall back to default)
    settings_repo.delete(key)

    # Return current value (which will be the default)
    value = definition.default_value

    return SettingResponse(
        key=key,
        value=value,
        value_type=definition.value_type,
        description=definition.description,
        updated_at=datetime.utcnow().isoformat(),
    )


@router.post("/bulk-update", response_model=BulkSettingUpdateResponse)
async def bulk_update_settings(
    request: BulkSettingUpdateRequest,
    http_request: Request,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> BulkSettingUpdateResponse:
    """
    Update multiple settings at once.

    Args:
        request: Bulk update request with settings dictionary
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        BulkSettingUpdateResponse with results
    """
    settings_service = SettingsService(settings_repo, credentials_repo)

    updated = []
    failed = []

    for key, value in request.settings.items():
        try:
            result = settings_service.validate_and_set(key, value)

            if result.get("valid") and result.get("success"):
                updated.append(key)
            else:
                failed.append({"key": key, "error": ", ".join(result.get("errors", []))})

        except Exception as e:
            logger.error(f"Failed to update {key}: {e}")
            failed.append({"key": key, "error": str(e)})

    # Propagate timezone changes to logging and the cron scheduler
    if "user.timezone" in updated:
        _apply_timezone_change(http_request, settings_repo)

    return BulkSettingUpdateResponse(updated=updated, failed=failed)


@router.post("/validate/{key}", response_model=SettingValidationResponse)
async def validate_setting(
    key: str,
    request: SettingUpdateRequest,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> SettingValidationResponse:
    """
    Validate a setting value without saving.

    Args:
        key: Setting key
        request: Setting value to validate
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)

    Returns:
        SettingValidationResponse with validation results
    """
    settings_service = SettingsService(settings_repo, credentials_repo)

    # Validate without saving by checking first
    result = settings_service.validate_and_set(key, request.value)

    return SettingValidationResponse(
        valid=result.get("valid", False),
        errors=result.get("errors", []),
        warnings=result.get("warnings", []),
        success=False,  # Not saved, just validated
    )
