"""Managed mode API endpoints.

These endpoints are only registered when MANAGED_API_KEY is set in the environment.
They allow the Open Assistant Platform to:
1. Poll usage metrics from each instance for billing purposes
2. Push credentials and settings to instances for dynamic configuration

Authentication: X-Managed-Key header must match MANAGED_API_KEY.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src import __version__
from src.core.database import DatabaseManager
from src.core.encryption import get_encryption_service
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.message import MessageRepository
from src.core.repositories.settings import SettingsRepository
from src.models.settings import (
    BulkCredentialPushRequest,
    CredentialsPushResponse,
    CredentialPushResult,
    CredentialResponse,
    ManagedConfigResponse,
    SettingsPushRequest,
    SettingsPushResponse,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/managed", tags=["managed"])

_MANAGED_API_KEY = os.getenv("MANAGED_API_KEY", "")


def _require_managed_key(request: Request) -> None:
    """Dependency: verify X-Managed-Key header."""
    key = request.headers.get("X-Managed-Key", "")
    if not key or key != _MANAGED_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Managed-Key",
        )


def _get_db(request: Request) -> DatabaseManager:
    return request.app.state.db_manager


@router.get("/health")
async def managed_health(
    _: None = Depends(_require_managed_key),
    db: DatabaseManager = Depends(_get_db),
) -> Dict[str, Any]:
    """Health check for the platform to verify the instance is reachable."""
    return {
        "status": "ok",
        "version": __version__,
        "instance_id": os.getenv("INSTANCE_ID", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/usage")
async def managed_usage(
    _: None = Depends(_require_managed_key),
    db: DatabaseManager = Depends(_get_db),
) -> Dict[str, Any]:
    """Return monthly token totals for the past 12 calendar months.

    The platform calls this endpoint hourly and uses the current month's
    tokens_total to set Stripe metered usage (action='set').

    Response format:
        {
            "monthly_usage": [
                {"year": 2026, "month": 1, "tokens_total": 12345},
                {"year": 2026, "month": 2, "tokens_total": 8901},
                ...
            ]
        }
    """
    message_repo = MessageRepository(db)
    raw = message_repo.get_monthly_token_totals(months=12)

    monthly_usage: List[Dict[str, Any]] = []
    for row in raw:
        monthly_usage.append(
            {
                "year": row["year"],
                "month": row["month"],
                "tokens_total": row["tokens_total"] or 0,
            }
        )

    # Always include the current month even if it has zero usage
    now = datetime.now(timezone.utc)
    has_current = any(m["year"] == now.year and m["month"] == now.month for m in monthly_usage)
    if not has_current:
        monthly_usage.append({"year": now.year, "month": now.month, "tokens_total": 0})

    return {"monthly_usage": monthly_usage}


@router.post("/credentials", response_model=CredentialsPushResponse)
async def push_credentials(
    body: BulkCredentialPushRequest,
    _: None = Depends(_require_managed_key),
    db: DatabaseManager = Depends(_get_db),
) -> CredentialsPushResponse:
    """Push credentials from the platform to the instance database.

    The platform calls this endpoint after provisioning to store API keys,
    OAuth secrets, and other credentials in the instance's encrypted database.

    Args:
        body: Bulk credential push request with list of credentials
        _: Auth dependency (validates X-Managed-Key)
        db: Database manager

    Returns:
        CredentialsPushResponse with stored/failed lists
    """
    encryption_service = get_encryption_service()
    credentials_repo = CredentialsRepository(db, encryption_service)

    stored: List[str] = []
    failed: List[CredentialPushResult] = []

    for cred in body.credentials:
        try:
            credentials_repo.store(
                service_name=cred.service_name,
                credential_type=cred.credential_type,
                credential_data=cred.credential_data,
                expires_at=cred.expires_at,
            )
            stored.append(cred.service_name)
            logger.info(f"Stored credential for service: {cred.service_name}")
        except Exception as e:
            logger.error(f"Failed to store credential for {cred.service_name}: {e}")
            failed.append(
                CredentialPushResult(
                    service_name=cred.service_name,
                    success=False,
                    error=str(e),
                )
            )

    return CredentialsPushResponse(stored=stored, failed=failed)


@router.post("/settings", response_model=SettingsPushResponse)
async def push_settings(
    body: SettingsPushRequest,
    _: None = Depends(_require_managed_key),
    db: DatabaseManager = Depends(_get_db),
) -> SettingsPushResponse:
    """Push settings from the platform to the instance database.

    The platform calls this endpoint after provisioning to store enabled flags
    and other non-sensitive configuration in the instance's database.

    Args:
        body: Settings push request with key-value pairs
        _: Auth dependency (validates X-Managed-Key)
        db: Database manager

    Returns:
        SettingsPushResponse with stored/failed lists
    """
    settings_repo = SettingsRepository(db)

    stored: List[str] = []
    failed: List[Dict[str, str]] = []

    for key, value in body.settings.items():
        try:
            # Infer value type
            value_type = "string"
            if isinstance(value, bool):
                value_type = "bool"
            elif isinstance(value, int):
                value_type = "int"
            elif isinstance(value, float):
                value_type = "float"
            elif isinstance(value, (dict, list)):
                value_type = "json"

            settings_repo.set(key, value, value_type=value_type)
            stored.append(key)
            logger.info(f"Stored setting: {key}")
        except Exception as e:
            logger.error(f"Failed to store setting {key}: {e}")
            failed.append({"key": key, "error": str(e)})

    return SettingsPushResponse(stored=stored, failed=failed)


@router.get("/config", response_model=ManagedConfigResponse)
async def get_managed_config(
    _: None = Depends(_require_managed_key),
    db: DatabaseManager = Depends(_get_db),
) -> ManagedConfigResponse:
    """Get current configuration state for verification.

    Returns credential metadata (no sensitive data) and current settings.
    Useful for the platform to verify configuration was applied correctly.

    Args:
        _: Auth dependency (validates X-Managed-Key)
        db: Database manager

    Returns:
        ManagedConfigResponse with credentials metadata and settings
    """
    encryption_service = get_encryption_service()
    credentials_repo = CredentialsRepository(db, encryption_service)
    settings_repo = SettingsRepository(db)

    # Get credential metadata (no sensitive data)
    credentials_metadata = credentials_repo.list_all_metadata()
    credentials = [
        CredentialResponse(
            service_name=c["service_name"],
            credential_type=c["credential_type"],
            expires_at=c.get("expires_at"),
            created_at=c["created_at"],
            updated_at=c["updated_at"],
        )
        for c in credentials_metadata
    ]

    # Get all settings as a flat dict
    all_settings = settings_repo.list_all()
    settings = {s["key"]: s["value"] for s in all_settings}

    return ManagedConfigResponse(
        credentials=credentials,
        settings=settings,
        instance_id=os.getenv("INSTANCE_ID"),
    )
