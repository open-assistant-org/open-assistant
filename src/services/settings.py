"""Settings service for application configuration management."""

import os
import re
from typing import Any, Dict, List, Optional

from src.core.llm_client import get_default_base_url
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.config import (
    SETTING_DEFINITIONS,
    ConfigCategory,
    get_env_to_db_key_mapping,
    get_setting_definition,
    get_settings_by_category,
    get_sensitive_settings,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SettingsService:
    """Service for managing application settings and credentials."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        """
        Initialize settings service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository (optional)
        """
        self.settings_repo = settings_repo
        self.credentials_repo = credentials_repo
        self.audit_repo = audit_repo

    def get_llm_config(self) -> Dict[str, Any]:
        """
        Get LLM configuration.

        Returns:
            Dictionary with LLM configuration
        """
        # Try database first, fall back to environment variables
        config = self.settings_repo.get_by_prefix("llm.")

        if not config:
            # Fall back to environment variables
            provider = os.getenv("LLM_PROVIDER", "openrouter")
            config = {
                "provider": provider,
                "model": os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4.6"),
                "api_key": os.getenv("LLM_API_KEY", ""),
                "base_url": os.getenv("LLM_BASE_URL") or get_default_base_url(provider),
                "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
                "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
            }

        # API key is sensitive and stored in credentials repo, not settings
        if not config.get("api_key"):
            cred = self.credentials_repo.get("llm")
            if cred:
                config["api_key"] = cred.get("credential_data", {}).get("api_key", "")

        return config

    def update_llm_config(self, config: Dict[str, Any]) -> bool:
        """
        Update LLM configuration.

        Args:
            config: Dictionary with LLM configuration

        Returns:
            True if successful
        """
        try:
            for key, value in config.items():
                if key == "api_key":
                    # Skip API key (stored separately)
                    continue

                value_type = "string"
                if isinstance(value, int):
                    value_type = "int"
                elif isinstance(value, bool):
                    value_type = "bool"
                elif isinstance(value, (dict, list)):
                    value_type = "json"

                self.settings_repo.set(f"llm.{key}", value, value_type=value_type)

            logger.info("Updated LLM configuration")
            return True

        except Exception as e:
            logger.error(f"Failed to update LLM config: {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        value = self.settings_repo.get(key)
        return value if value is not None else default

    def set_setting(
        self, key: str, value: Any, value_type: str = "string", description: Optional[str] = None
    ) -> bool:
        """
        Set a setting value.

        Args:
            key: Setting key
            value: Setting value
            value_type: Value type (string, int, bool, json)
            description: Optional description

        Returns:
            True if successful
        """
        try:
            self.settings_repo.set(key, value, value_type, description)
            logger.info(f"Set setting: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            return False

    def delete_setting(self, key: str) -> bool:
        """
        Delete a setting.

        Args:
            key: Setting key

        Returns:
            True if deleted
        """
        return self.settings_repo.delete(key)

    def list_settings(self, prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all settings.

        Args:
            prefix: Optional key prefix filter

        Returns:
            List of setting dictionaries
        """
        return self.settings_repo.list_all(prefix)

    def store_credential(
        self,
        service_name: str,
        credential_type: str,
        credential_data: Dict[str, Any],
        expires_at: Optional[str] = None,
    ) -> bool:
        """
        Store encrypted credentials for a service.

        Args:
            service_name: Service name (google, outlook, etc.)
            credential_type: Credential type (oauth_token, api_key, app_password)
            credential_data: Credential data dictionary
            expires_at: Optional expiration timestamp

        Returns:
            True if successful
        """
        try:
            self.credentials_repo.store(service_name, credential_type, credential_data, expires_at)
            logger.info(f"Stored credentials for service: {service_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to store credentials for {service_name}: {e}")
            return False

    def get_credential(self, service_name: str) -> Optional[Dict[str, Any]]:
        """
        Get decrypted credentials for a service.

        Args:
            service_name: Service name

        Returns:
            Dictionary with credential_type and credential_data, or None
        """
        return self.credentials_repo.get(service_name)

    def delete_credential(self, service_name: str) -> bool:
        """
        Delete credentials for a service.

        Args:
            service_name: Service name

        Returns:
            True if deleted
        """
        success = self.credentials_repo.delete(service_name)
        if success:
            logger.info(f"Deleted credentials for service: {service_name}")
        return success

    def list_credentials(self) -> List[Dict[str, Any]]:
        """
        List all service credentials (metadata only, no sensitive data).

        Returns:
            List of credential metadata
        """
        return self.credentials_repo.list_all_metadata()

    def test_connection(self, service_name: str) -> Dict[str, Any]:
        """
        Test connection to a service.

        Args:
            service_name: Service name

        Returns:
            Dictionary with test results
        """
        # Get credentials
        creds = self.get_credential(service_name)

        if not creds:
            return {
                "service_name": service_name,
                "status": "error",
                "message": "No credentials found",
            }

        # Check if expired
        if self.credentials_repo.is_expired(service_name):
            return {
                "service_name": service_name,
                "status": "error",
                "message": "Credentials expired",
            }

        # Validate credential structure
        credential_data = creds.get("credential_data", {})
        credential_type = creds.get("credential_type")

        # Basic validation based on credential type
        if credential_type == "api_key":
            if not credential_data.get("value"):
                return {
                    "service_name": service_name,
                    "status": "error",
                    "message": "API key is empty or invalid",
                }
        elif credential_type == "oauth_token":
            if not credential_data.get("access_token"):
                return {
                    "service_name": service_name,
                    "status": "error",
                    "message": "OAuth token is missing access_token",
                }
        elif credential_type == "app_password":
            if not credential_data.get("value"):
                return {
                    "service_name": service_name,
                    "status": "error",
                    "message": "App password is empty or invalid",
                }

        # Service-specific connection tests
        try:
            if service_name == "llm":
                return self._test_llm_connection(credential_data)
            else:
                # For other services, credentials are valid but actual connection test not implemented
                return {
                    "service_name": service_name,
                    "status": "warning",
                    "message": f"Credentials configured but connection test not implemented for {service_name}",
                }
        except Exception as e:
            logger.error(f"Connection test failed for {service_name}: {e}")
            return {
                "service_name": service_name,
                "status": "error",
                "message": f"Connection test error: {str(e)}",
            }

    def _test_llm_connection(self, credential_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test LLM API connection.

        Args:
            credential_data: LLM credential data

        Returns:
            Test result dictionary
        """
        try:
            import openai

            # Get LLM config
            config = self.get_llm_config()
            provider = config.get("provider", "openrouter")
            base_url = config.get("base_url") or get_default_base_url(provider)

            # Ollama, vLLM, and custom providers don't require an API key
            api_key = credential_data.get("value") or (
                "EMPTY" if provider in ("ollama", "vllm", "custom") else None
            )

            client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
            )

            # Make a minimal test call
            response = client.chat.completions.create(
                model=config.get("model", "anthropic/claude-sonnet-4.6"),
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
            )

            return {
                "service_name": "llm",
                "status": "success",
                "message": "LLM connection successful",
            }
        except Exception as e:
            return {
                "service_name": "llm",
                "status": "error",
                "message": f"LLM connection failed: {str(e)}",
            }

    def get_integration_settings(self, service_name: str) -> Dict[str, Any]:
        """
        Get settings for an integration.

        Args:
            service_name: Service name (google, outlook, etc.)

        Returns:
            Dictionary with integration settings
        """
        prefix = f"{service_name}."
        settings = self.settings_repo.get_by_prefix(prefix)

        # Add enabled status from environment or settings
        if "enabled" not in settings:
            env_key = f"{service_name.upper()}_ENABLED"
            settings["enabled"] = os.getenv(env_key, "false").lower() == "true"

        # Add credential status
        creds = self.credentials_repo.get_metadata(service_name)
        settings["has_credentials"] = creds is not None

        if creds:
            settings["credential_type"] = creds["credential_type"]
            settings["credential_expires_at"] = creds.get("expires_at")

        return settings

    def update_integration_settings(self, service_name: str, settings: Dict[str, Any]) -> bool:
        """
        Update settings for an integration.

        Args:
            service_name: Service name
            settings: Dictionary with settings to update

        Returns:
            True if successful
        """
        try:
            for key, value in settings.items():
                if key in ["has_credentials", "credential_type", "credential_expires_at"]:
                    # Skip read-only fields
                    continue

                full_key = f"{service_name}.{key}"

                value_type = "string"
                if isinstance(value, bool):
                    value_type = "bool"
                elif isinstance(value, int):
                    value_type = "int"
                elif isinstance(value, (dict, list)):
                    value_type = "json"

                self.settings_repo.set(full_key, value, value_type)

            logger.info(f"Updated settings for integration: {service_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update integration settings: {e}")
            return False

    # ========================================================================
    # CONFIGURATION VALUE RETRIEVAL
    # ========================================================================

    def get_config_with_fallback(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with fallback chain: DB → ENV → default.

        This is the core method for retrieving configuration values. It checks
        the database first, then environment variables, then uses the default.

        Args:
            key: Setting key (e.g., "llm.provider")
            default: Default value if not found anywhere

        Returns:
            Configuration value from DB, ENV, or default
        """
        # Get setting definition for metadata
        definition = get_setting_definition(key)

        # Bootstrap settings always come from ENV only
        if definition and definition.category == ConfigCategory.BOOTSTRAP:
            env_value = os.getenv(definition.env_var_name)
            return env_value if env_value is not None else default

        # For sensitive settings, skip settings table and check credentials first
        # (Sensitive settings are stored encrypted in credentials, not settings table)
        if definition and definition.is_sensitive:
            service_name = key.split(".")[0]
            setting_key = key.split(".", 1)[1] if "." in key else "value"
            cred = self.credentials_repo.get(service_name)
            if cred:
                # Look up by specific setting key within credential_data
                cred_value = cred.get("credential_data", {}).get(setting_key)
                if cred_value is not None:
                    return cred_value
                # Fallback to "value" key for backward compatibility with old format
                cred_value = cred.get("credential_data", {}).get("value")
                if cred_value is not None:
                    return cred_value

        # Check database for non-sensitive settings
        db_value = self.settings_repo.get(key)
        if db_value is not None and db_value != "":
            return db_value

        # Fall back to environment variable (not for sensitive integration secrets)
        if definition and definition.env_var_name and not definition.is_sensitive:
            env_value = os.getenv(definition.env_var_name)
            if env_value is not None:
                # Convert ENV value to proper type
                return self._convert_env_value(env_value, definition.value_type)

        # Fall back to definition default
        if definition and definition.default_value is not None:
            return definition.default_value

        # Finally, use provided default
        return default

    def _convert_env_value(self, value: str, value_type: str) -> Any:
        """
        Convert environment variable string to typed value.

        Args:
            value: String value from environment
            value_type: Target type

        Returns:
            Converted value
        """
        if value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "bool":
            return value.lower() in ("true", "1", "yes", "on")
        elif value_type == "json":
            import json

            return json.loads(value)
        else:
            return value

    def _infer_credential_type(self, key: str) -> str:
        """
        Infer credential type from setting key.

        Args:
            key: Setting key (e.g., "llm.api_key", "google.access_token")

        Returns:
            Credential type (api_key, oauth_token, or app_password)
        """
        key_lower = key.lower()

        if "token" in key_lower or "oauth" in key_lower:
            return "oauth_token"
        elif "password" in key_lower:
            return "app_password"
        else:
            # Default to api_key for keys containing "key" or unknown types
            return "api_key"

    def get_all_settings_grouped(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all settings organized by category.

        Returns:
            Dictionary mapping category names to setting dictionaries
        """
        result = {}

        for category in ConfigCategory:
            # Skip bootstrap settings (they don't go in DB)
            if category == ConfigCategory.BOOTSTRAP:
                continue

            category_settings = {}
            definitions = get_settings_by_category(category)

            for key, definition in definitions.items():
                value = self.get_config_with_fallback(key)
                if value is not None:
                    category_settings[key] = {
                        "value": value,
                        "definition": {
                            "display_name": definition.display_name,
                            "description": definition.description,
                            "value_type": definition.value_type,
                            "is_sensitive": definition.is_sensitive,
                            "is_required": definition.is_required,
                            "ui_widget": definition.ui_widget,
                            "options": definition.options,
                            "min_value": definition.min_value,
                            "max_value": definition.max_value,
                        },
                    }

            if category_settings:
                result[category.value] = category_settings

        return result

    def validate_and_set(
        self, key: str, value: Any, user_id: Optional[str] = None, ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate and set a configuration value.

        Args:
            key: Setting key
            value: Value to set
            user_id: User ID making the change (for audit)
            ip_address: IP address (for audit)

        Returns:
            Dictionary with validation result and any errors
        """
        result = {"valid": False, "errors": [], "warnings": []}

        # Get setting definition
        definition = get_setting_definition(key)
        if not definition:
            result["errors"].append(f"Unknown setting key: {key}")
            return result

        # Bootstrap settings cannot be changed via API
        if definition.category == ConfigCategory.BOOTSTRAP:
            result["errors"].append("Bootstrap settings cannot be changed via API")
            return result

        # Type validation
        try:
            if definition.value_type == "int":
                value = int(value)
            elif definition.value_type == "float":
                value = float(value)
            elif definition.value_type == "bool":
                if isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes", "on")
                else:
                    value = bool(value)
        except (ValueError, TypeError) as e:
            result["errors"].append(f"Invalid type: expected {definition.value_type}, error: {e}")
            return result

        # Range validation for numbers
        if definition.value_type in ("int", "float"):
            if definition.min_value is not None and value < definition.min_value:
                result["errors"].append(f"Value must be at least {definition.min_value}")
                return result
            if definition.max_value is not None and value > definition.max_value:
                result["errors"].append(f"Value must be at most {definition.max_value}")
                return result

        # Options validation (enum)
        if definition.options and value not in definition.options:
            result["errors"].append(f"Value must be one of: {', '.join(definition.options)}")
            return result

        # Regex validation for strings
        if definition.validation_regex and definition.value_type == "string":
            if not re.match(definition.validation_regex, str(value)):
                result["errors"].append(
                    f"Value does not match required pattern: {definition.validation_regex}"
                )
                return result

        # Required validation
        if definition.is_required and (value is None or value == ""):
            result["errors"].append("This setting is required and cannot be empty")
            return result

        # All validations passed
        result["valid"] = True

        # Get old value for audit
        old_value = self.get_config_with_fallback(key)

        # Store the value
        try:
            if definition.is_sensitive:
                # Sensitive values go to credentials
                # Store multiple sensitive settings per service in one credential_data dict
                # e.g., slack has bot_token, signing_secret, app_token
                service_name = key.split(".")[0]
                setting_key = key.split(".", 1)[1] if "." in key else "value"
                credential_type = self._infer_credential_type(key)

                # Get existing credential data and merge
                existing = self.credentials_repo.get(service_name)
                if existing:
                    credential_data = existing.get("credential_data", {})
                else:
                    credential_data = {}

                credential_data[setting_key] = value

                self.credentials_repo.store(
                    service_name=service_name,
                    credential_type=credential_type,
                    credential_data=credential_data,
                    expires_at=None,
                )
            else:
                # Non-sensitive values go to settings
                self.settings_repo.set(
                    key, value, value_type=definition.value_type, description=definition.description
                )

            # Audit the change
            self.audit_setting_change(
                key=key,
                old_value=old_value,
                new_value=value,
                user_id=user_id,
                ip_address=ip_address,
            )

            result["success"] = True

        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            result["valid"] = False
            result["errors"].append(f"Failed to save: {str(e)}")

        return result

    def audit_setting_change(
        self,
        key: str,
        old_value: Any,
        new_value: Any,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Audit a setting change.

        Args:
            key: Setting key
            old_value: Previous value
            new_value: New value
            user_id: User ID making the change
            ip_address: IP address
        """
        if not self.audit_repo:
            return

        definition = get_setting_definition(key)

        # Mask sensitive values in audit log
        if definition and definition.is_sensitive:
            old_value_masked = "***MASKED***" if old_value else None
            new_value_masked = "***MASKED***"
        else:
            old_value_masked = old_value
            new_value_masked = new_value

        self.audit_repo.log_event(
            event_type="setting_change",
            action=f"update_{key}",
            success=True,
            details={
                "key": key,
                "old_value": old_value_masked,
                "new_value": new_value_masked,
                "user_id": user_id,
                "ip_address": ip_address,
                "category": definition.category.value if definition else "unknown",
            },
        )

        logger.info(f"Setting changed: {key} (user: {user_id or 'system'})")
