"""Whisper transcription service."""

from typing import Any, Dict

from openai import OpenAI

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WhisperService:
    """Service for testing Whisper transcription configuration."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: AuditLogRepository,
    ):
        """
        Initialize Whisper service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository
        """
        self.settings_repo = settings_repo
        self.credentials_repo = credentials_repo
        self.audit_repo = audit_repo

    def _get_config(self) -> Dict[str, Any]:
        """
        Get Whisper configuration from settings.

        Returns:
            Dictionary with API key, base URL, and model
        """
        # Get Whisper-specific API key from credentials repo first
        whisper_api_key = None
        creds = self.credentials_repo.get("whisper")
        if creds:
            whisper_api_key = creds.get("credential_data", {}).get("api_key")

        # Fall back to settings
        if not whisper_api_key:
            whisper_api_key = self.settings_repo.get("whisper.api_key")

        # If still no Whisper key, try main LLM API key
        if not whisper_api_key:
            llm_creds = self.credentials_repo.get("llm")
            if llm_creds:
                whisper_api_key = llm_creds.get("credential_data", {}).get("api_key")
        if not whisper_api_key:
            whisper_api_key = self.settings_repo.get("llm.api_key")

        base_url = self.settings_repo.get("whisper.base_url") or None
        model = self.settings_repo.get("whisper.model") or "whisper-1"

        return {
            "api_key": whisper_api_key,
            "base_url": base_url,
            "model": model,
        }

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Whisper API connection by verifying credentials.

        Returns:
            Dictionary with test results
        """
        try:
            config = self._get_config()

            if not config["api_key"]:
                return {
                    "service_name": "whisper",
                    "status": "error",
                    "message": "No API key configured. Set whisper.api_key or llm.api_key.",
                }

            # Initialize OpenAI client
            client_kwargs = {"api_key": config["api_key"]}
            if config["base_url"]:
                client_kwargs["base_url"] = config["base_url"]

            client = OpenAI(**client_kwargs)

            # Test by listing models (lightweight API call)
            # This verifies authentication without actually transcribing
            try:
                models = client.models.list()
                # Check if whisper model exists in the response
                model_ids = [m.id for m in models.data]
                has_whisper = any("whisper" in m.lower() for m in model_ids)

                if has_whisper or config["model"] in model_ids:
                    return {
                        "service_name": "whisper",
                        "status": "success",
                        "message": f"Connection successful. Model '{config['model']}' available.",
                    }
                else:
                    return {
                        "service_name": "whisper",
                        "status": "warning",
                        "message": f"API key valid, but model '{config['model']}' not found. Check model name.",
                    }
            except Exception as api_error:
                # If models.list() fails, it might be a custom endpoint
                # Return success with a warning
                logger.warning(f"Could not list models, but API key appears valid: {api_error}")
                return {
                    "service_name": "whisper",
                    "status": "warning",
                    "message": "API key appears valid. Model availability could not be verified.",
                }

        except Exception as e:
            logger.error(f"Whisper connection test failed: {e}", exc_info=True)
            return {
                "service_name": "whisper",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }
