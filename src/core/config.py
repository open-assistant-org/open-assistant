"""Configuration management with environment variable support."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    url: str = Field(default="sqlite:///data/assistant.db", description="Database connection URL")

    model_config = SettingsConfigDict(env_prefix="DATABASE_")


class SecurityConfig(BaseSettings):
    """Security configuration."""

    encryption_key: Optional[str] = Field(
        default=None, description="Encryption key for sensitive data"
    )

    model_config = SettingsConfigDict(env_prefix="SECURITY_")


class GeneralConfig(BaseSettings):
    """General application configuration."""

    log_level: str = Field(default="INFO", description="Logging level")
    environment: str = Field(
        default="development", description="Environment (development/production)"
    )
    data_dir: str = Field(default="data", description="Data directory path")
    tmp_dir: str = Field(default="tmp", description="Temporary files directory path")
    app_url: str = Field(
        default="http://localhost:8080",
        description="Base URL of the application (for OAuth redirects and CORS)",
    )
    # When set, enables the /managed/* endpoints for platform usage reporting.
    # Injected by the platform at provisioning time. Leave empty for self-hosted deployments.
    managed_api_key: Optional[str] = Field(
        default=None, description="Platform-managed API key; enables /managed/* endpoints when set"
    )

    model_config = SettingsConfigDict(env_prefix="")


class AppConfig(BaseSettings):
    """Main application configuration."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Dictionary containing configuration data
    """
    config_file = Path(config_path)

    if not config_file.exists():
        return {}

    with open(config_file, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}

    return config_data


def get_config(config_path: str = "config/config.yaml") -> AppConfig:
    """
    Get application configuration with precedence:
    Environment variables > .env file > config.yaml > defaults

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        AppConfig instance with merged configuration
    """
    # Load YAML configuration
    yaml_config = load_config(config_path)

    # Extract nested configurations
    general_config = yaml_config.get("general", {})
    database_config = yaml_config.get("database", {})
    security_config = yaml_config.get("security", {})

    # Create config objects with YAML values as defaults
    # Environment variables will override these
    general = GeneralConfig(
        log_level=os.getenv("LOG_LEVEL", general_config.get("log_level", "INFO")),
        environment=os.getenv("ENVIRONMENT", general_config.get("environment", "development")),
        data_dir=os.getenv("DATA_DIR", general_config.get("data_dir", "data")),
        tmp_dir=os.getenv("TMP_DIR", general_config.get("tmp_dir", "tmp")),
        app_url=os.getenv("APP_URL", general_config.get("app_url", "http://localhost:8080")),
        managed_api_key=os.getenv("MANAGED_API_KEY") or None,
    )

    database = DatabaseConfig(
        url=os.getenv("DATABASE_URL", database_config.get("url", "sqlite:///data/assistant.db"))
    )

    security = SecurityConfig(
        encryption_key=os.getenv("ENCRYPTION_KEY", security_config.get("encryption_key"))
    )

    return AppConfig(
        general=general,
        database=database,
        security=security,
    )


# Singleton instance
_config: Optional[AppConfig] = None


def init_config(config_path: str = "config/config.yaml") -> AppConfig:
    """
    Initialize global configuration (singleton pattern).

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        AppConfig instance
    """
    global _config
    if _config is None:
        _config = get_config(config_path)
    return _config


def get_app_config() -> AppConfig:
    """
    Get the global application configuration.

    Returns:
        AppConfig instance

    Raises:
        RuntimeError: If configuration hasn't been initialized
    """
    if _config is None:
        raise RuntimeError("Configuration not initialized. Call init_config() first.")
    return _config
