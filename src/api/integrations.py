"""Integration status and tools API."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from src.core.dependencies import get_credentials_repo, get_settings_repo
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.core.tools.registry import get_tool_registry

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("/status")
async def get_integrations_status(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> Dict[str, Any]:
    """
    Get status of all integrations.

    Returns:
        Dictionary with integration status and available tools
    """
    # Define integrations with their display names and settings keys
    integrations_config = [
        {"id": "google", "name": "Google", "setting": "google.enabled", "credential": "google"},
        {"id": "outlook", "name": "Outlook", "setting": "outlook.enabled", "credential": "outlook"},
        {"id": "notion", "name": "Notion", "setting": "notion.enabled", "credential": "notion"},
        {
            "id": "nextcloud",
            "name": "Nextcloud",
            "setting": "nextcloud.enabled",
            "credential": "nextcloud",
        },
        {
            "id": "whatsapp",
            "name": "WhatsApp",
            "setting": "whatsapp.enabled",
            "credential": "whatsapp",
        },
        {
            "id": "slack",
            "name": "Slack",
            "setting": "slack.enabled",
            "credential": "slack",
        },
        {
            "id": "whisper",
            "name": "Whisper",
            "setting": "whisper.enabled",
            "credential": "whisper",
        },
        {
            "id": "mistral_ocr",
            "name": "Mistral OCR",
            "setting": "mistral_ocr.enabled",
            "credential": "mistral_ocr",
        },
        {
            "id": "google_ads",
            "name": "Google Ads",
            "setting": "google_ads.enabled",
            "credential": "google_ads",
        },
        {
            "id": "google_news",
            "name": "Google News",
            "setting": "google_news.enabled",
            "credential": None,  # No API key required
        },
        {
            "id": "yahoo_finance",
            "name": "Yahoo Finance",
            "setting": "yahoo_finance.enabled",
            "credential": None,  # No API key required
        },
    ]

    status = {}
    for config in integrations_config:
        enabled = settings_repo.get(config["setting"])

        # Integrations without credentials (e.g. Google News, Yahoo Finance) are always "configured"
        if config["credential"] is None:
            has_credentials = True
        else:
            has_credentials = credentials_repo.get(config["credential"]) is not None

        status[config["id"]] = {
            "name": config["name"],
            "enabled": bool(enabled),
            "configured": has_credentials,
            "available": bool(enabled) and has_credentials,
        }

    # Get available tools
    registry = get_tool_registry()
    available_tools = registry.list_tools(settings_repo, enabled_only=True)

    return {
        "integrations": status,
        "available_tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "service": tool.name.split("_")[0],  # Extract service name from tool name
            }
            for tool in available_tools
        ],
    }


@router.get("/tools")
async def list_tools(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> List[Dict[str, Any]]:
    """List all available tools with their schemas."""
    registry = get_tool_registry()
    tools = registry.get_openai_tools(settings_repo)
    return tools
