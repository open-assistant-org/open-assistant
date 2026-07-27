"""
Configuration setting definitions with metadata for validation and UI generation.

This module defines all application settings with their properties, validation rules,
default values, and display metadata. It serves as the single source of truth for
configuration management.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ConfigCategory(str, Enum):
    """Configuration categories for organizing settings in the UI."""

    BOOTSTRAP = "bootstrap"  # Must remain in ENV (DATABASE_URL, ENCRYPTION_KEY)
    APPLICATION = "application"  # General application settings
    LOGGING = "logging"  # Logging configuration
    MEMORY = "memory"  # Memory management settings
    WEB_UI = "web_ui"  # Web UI configuration
    LLM = "llm"  # LLM provider configuration
    GOOGLE = "google"  # Google integration (Gmail, Calendar, etc.)
    GOOGLE_NAVIGATOR = "google_navigator"  # Google Places, Directions & Geocoding
    OUTLOOK = "outlook"  # Outlook integration
    NOTION = "notion"  # Notion integration
    NEXTCLOUD = "nextcloud"  # Nextcloud integration
    WHATSAPP = "whatsapp"  # WhatsApp integration
    SLACK = "slack"  # Slack integration
    BRAVE = "brave"  # Brave Search integration
    BROWSER = "browser"  # Browser integration with Playwright
    WHISPER = "whisper"  # OpenAI Whisper audio transcription
    MISTRAL_OCR = "mistral_ocr"  # Mistral OCR for PDF text extraction
    GOOGLE_ADS = "google_ads"  # Google Ads API integration
    GOOGLE_NEWS = "google_news"  # Google News (no API key required)
    YAHOO_FINANCE = "yahoo_finance"  # Yahoo Finance market data (no API key required)
    USER = "user"  # User preferences (timezone, locale, etc.)


class SettingValueType(str, Enum):
    """Setting value types for storage and validation."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    JSON = "json"


@dataclass
class SettingDefinition:
    """
    Complete definition of a configuration setting.

    This includes the setting's key, type, validation rules, default value,
    and display metadata for UI generation.
    """

    # Core properties
    key: str  # Database key (e.g., "llm.provider")
    display_name: str  # Human-readable name for UI
    description: str  # Detailed description/help text
    value_type: SettingValueType  # Data type
    category: ConfigCategory  # Category for grouping

    # Security
    is_sensitive: bool = False  # Should be encrypted in service_credentials
    is_required: bool = False  # Must have a value

    # Default value
    default_value: Any = None

    # Validation
    validation_regex: Optional[str] = None  # Regex for string validation
    min_value: Optional[float] = None  # Min for int/float
    max_value: Optional[float] = None  # Max for int/float
    options: Optional[List[str]] = None  # Valid options for dropdown

    # Display
    display_order: int = 0  # Order within category
    placeholder: Optional[str] = None  # Placeholder text for input
    help_url: Optional[str] = None  # Link to documentation

    # Migration
    env_var_name: str = ""  # Original ENV variable name for migration

    # UI behavior
    ui_widget: str = "text"  # Widget type: text, number, select, toggle, slider, textarea, masked


# ============================================================================
# SETTING DEFINITIONS REGISTRY
# ============================================================================

SETTING_DEFINITIONS: Dict[str, SettingDefinition] = {
    # ========================================================================
    # BOOTSTRAP SETTINGS (Must remain in ENV - not migrated to DB)
    # ========================================================================
    "bootstrap.database_url": SettingDefinition(
        key="bootstrap.database_url",
        display_name="Database URL",
        description="Database connection URL. Required before DB initialization.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.BOOTSTRAP,
        is_required=True,
        default_value="sqlite:///data/assistant.db",
        env_var_name="DATABASE_URL",
        display_order=1,
        ui_widget="text",
        help_url="https://docs.sqlalchemy.org/en/20/core/engines.html",
    ),
    "bootstrap.encryption_key": SettingDefinition(
        key="bootstrap.encryption_key",
        display_name="Encryption Key",
        description="Fernet encryption key for sensitive data. Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.BOOTSTRAP,
        is_sensitive=True,
        is_required=True,
        env_var_name="ENCRYPTION_KEY",
        display_order=2,
        ui_widget="masked",
    ),
    # ========================================================================
    # APPLICATION SETTINGS
    # ========================================================================
    "application.environment": SettingDefinition(
        key="application.environment",
        display_name="Environment",
        description="Deployment environment (development or production)",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.APPLICATION,
        default_value="development",
        options=["development", "production"],
        env_var_name="ENVIRONMENT",
        display_order=1,
        ui_widget="select",
    ),
    "application.data_dir": SettingDefinition(
        key="application.data_dir",
        display_name="Data Directory",
        description="Directory for storing application data",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.APPLICATION,
        default_value="data",
        env_var_name="DATA_DIR",
        display_order=2,
        ui_widget="text",
        placeholder="/path/to/data",
    ),
    "application.message_retention_days": SettingDefinition(
        key="application.message_retention_days",
        display_name="Message Retention (days)",
        description=(
            "Age threshold for the nightly compaction job. Messages and LLM "
            "consumption rows older than this are collapsed into summary rows "
            "to bound database growth. Billing totals are preserved."
        ),
        value_type=SettingValueType.INT,
        category=ConfigCategory.APPLICATION,
        default_value=90,
        min_value=1,
        max_value=3650,
        display_order=3,
        ui_widget="number",
    ),
    # ========================================================================
    # LOGGING SETTINGS
    # ========================================================================
    "logging.log_level": SettingDefinition(
        key="logging.log_level",
        display_name="Log Level",
        description="Minimum log level to record",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LOGGING,
        default_value="INFO",
        options=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        env_var_name="LOG_LEVEL",
        display_order=1,
        ui_widget="select",
    ),
    "logging.rotation_days": SettingDefinition(
        key="logging.rotation_days",
        display_name="Log Rotation Days",
        description="Number of daily log files to keep",
        value_type=SettingValueType.INT,
        category=ConfigCategory.LOGGING,
        default_value=30,
        min_value=1,
        max_value=365,
        env_var_name="LOG_ROTATION_DAYS",
        display_order=2,
        ui_widget="number",
    ),
    "logging.rotation_when": SettingDefinition(
        key="logging.rotation_when",
        display_name="Log Rotation Timing",
        description="When to rotate logs (midnight, S=seconds, M=minutes, H=hours, D=days, W0-W6=weekday)",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LOGGING,
        default_value="midnight",
        options=["midnight", "S", "M", "H", "D", "W0", "W1", "W2", "W3", "W4", "W5", "W6"],
        env_var_name="LOG_ROTATION_WHEN",
        display_order=3,
        ui_widget="select",
    ),
    # ========================================================================
    # MEMORY MANAGEMENT SETTINGS
    # ========================================================================
    "memory.max_tokens": SettingDefinition(
        key="memory.max_tokens",
        display_name="Max Context Tokens",
        description=(
            "Maximum tokens of conversation history to keep in context each turn "
            "(separate from Max Tokens, which caps the response). The default is "
            "sized for 200K-context models, leaving headroom for the system prompt, "
            "tool definitions, in-turn tool results, and the response."
        ),
        value_type=SettingValueType.INT,
        category=ConfigCategory.MEMORY,
        default_value=100000,
        min_value=1000,
        max_value=1000000,
        env_var_name="MEMORY_MAX_TOKENS",
        display_order=10,
        ui_widget="number",
    ),
    "memory.summarization_threshold": SettingDefinition(
        key="memory.summarization_threshold",
        display_name="Summarization Threshold",
        description="Message count before summarization is recommended",
        value_type=SettingValueType.INT,
        category=ConfigCategory.MEMORY,
        default_value=50,
        min_value=10,
        max_value=1000,
        env_var_name="MEMORY_SUMMARIZATION_THRESHOLD",
        display_order=2,
        ui_widget="number",
    ),
    # ========================================================================
    # WEB UI SETTINGS
    # ========================================================================
    "web_ui.host": SettingDefinition(
        key="web_ui.host",
        display_name="Web UI Host",
        description="Host address for the web server",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.WEB_UI,
        default_value="0.0.0.0",
        env_var_name="WEB_UI_HOST",
        display_order=1,
        ui_widget="text",
        placeholder="0.0.0.0",
    ),
    "web_ui.port": SettingDefinition(
        key="web_ui.port",
        display_name="Web UI Port",
        description="Port number for the web server",
        value_type=SettingValueType.INT,
        category=ConfigCategory.WEB_UI,
        default_value=8080,
        min_value=1024,
        max_value=65535,
        env_var_name="WEB_UI_PORT",
        display_order=2,
        ui_widget="number",
    ),
    # ========================================================================
    # LLM CONFIGURATION
    # ========================================================================
    "llm.provider": SettingDefinition(
        key="llm.provider",
        display_name="LLM Provider",
        description="LLM provider to use (openrouter, groq, ollama, vllm, or custom)",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        default_value="openrouter",
        options=["openrouter", "groq", "ollama", "vllm", "custom"],
        env_var_name="LLM_PROVIDER",
        display_order=1,
        ui_widget="select",
    ),
    "llm.api_key": SettingDefinition(
        key="llm.api_key",
        display_name="API Key",
        description=(
            "API key for the LLM provider. Not required for local servers like "
            "Ollama or vLLM (leave blank unless vLLM was started with --api-key)."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        is_sensitive=True,
        is_required=False,
        env_var_name="LLM_API_KEY",
        display_order=2,
        ui_widget="masked",
        placeholder="sk-... (not required for Ollama / vLLM)",
    ),
    "llm.model": SettingDefinition(
        key="llm.model",
        display_name="Model",
        description="Model identifier to use",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        default_value="anthropic/claude-sonnet-4.6",
        env_var_name="LLM_MODEL",
        display_order=3,
        ui_widget="text",
        placeholder="anthropic/claude-sonnet-4.6",
    ),
    "llm.base_url": SettingDefinition(
        key="llm.base_url",
        display_name="Base URL",
        description=(
            "API endpoint URL for the LLM provider. "
            "Ollama default: http://localhost:11434/v1 — "
            "vLLM default: http://localhost:8000/v1"
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        default_value="https://openrouter.ai/api/v1",
        env_var_name="LLM_BASE_URL",
        display_order=7,
        ui_widget="text",
        placeholder="https://api.example.com/v1",
    ),
    "llm.temperature": SettingDefinition(
        key="llm.temperature",
        display_name="Temperature",
        description="Sampling temperature for response randomness (0=deterministic, 2=very random)",
        value_type=SettingValueType.FLOAT,
        category=ConfigCategory.LLM,
        default_value=0.7,
        min_value=0.0,
        max_value=2.0,
        env_var_name="LLM_TEMPERATURE",
        display_order=8,
        ui_widget="slider",
    ),
    "llm.max_tokens": SettingDefinition(
        key="llm.max_tokens",
        display_name="Max Tokens",
        description="Maximum tokens in the response",
        value_type=SettingValueType.INT,
        category=ConfigCategory.LLM,
        default_value=4096,
        min_value=1,
        max_value=128000,
        env_var_name="LLM_MAX_TOKENS",
        display_order=9,
        ui_widget="number",
    ),
    "llm.tool_output_max_chars": SettingDefinition(
        key="llm.tool_output_max_chars",
        display_name="Max Tool Output Chars",
        description=(
            "Tool results larger than this many characters are offloaded to a temp "
            "file and replaced in-context with a compact pointer (schema + sample) "
            "for python_agent to process, so a single large result never overflows "
            "the context window. ~4 chars ≈ 1 token; the default ~300K ≈ 75K tokens."
        ),
        value_type=SettingValueType.INT,
        category=ConfigCategory.LLM,
        default_value=300000,
        min_value=10000,
        max_value=2000000,
        env_var_name="TOOL_RESULT_OFFLOAD_THRESHOLD",
        display_order=11,
        ui_widget="number",
    ),
    "llm.context_strategy": SettingDefinition(
        key="llm.context_strategy",
        display_name="Context Strategy",
        description=(
            "How to manage conversation context on every turn: 'summarization' keeps long-term "
            "summaries of older messages; 'last_messages' keeps only the most recent N messages "
            "(configured below). Both strategies respect the token limit."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        default_value="summarization",
        options=["summarization", "last_messages"],
        env_var_name="LLM_CONTEXT_STRATEGY",
        display_order=12,
        ui_widget="select",
    ),
    "llm.context_max_messages": SettingDefinition(
        key="llm.context_max_messages",
        display_name="Context Max Messages",
        description=(
            "Maximum number of recent messages to include in context when using the "
            "'last_messages' strategy. Applied on every turn."
        ),
        value_type=SettingValueType.INT,
        category=ConfigCategory.LLM,
        default_value=20,
        min_value=1,
        max_value=500,
        env_var_name="LLM_CONTEXT_MAX_MESSAGES",
        display_order=13,
        ui_widget="number",
    ),
    "llm.auto_compact": SettingDefinition(
        key="llm.auto_compact",
        display_name="Auto-Compact Conversations",
        description=(
            "Automatically compress conversation history in the background after each turn "
            "using the worker model. Only active when Context Strategy is 'summarization'. "
            "Disable to suppress background LLM summarization calls."
        ),
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.LLM,
        default_value=True,
        env_var_name="LLM_AUTO_COMPACT",
        display_order=14,
        ui_widget="toggle",
    ),
    "llm.media_model": SettingDefinition(
        key="llm.media_model",
        display_name="Media Model",
        description=(
            "Model used to process non-textual data such as images sent via WhatsApp or Slack. "
            "Defaults to the main model if left empty. "
            "Ignored for Ollama and vLLM, which always use the main model."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        default_value="",
        env_var_name="LLM_MEDIA_MODEL",
        display_order=4,
        ui_widget="text",
        placeholder="anthropic/claude-sonnet-4.6",
    ),
    "llm.worker_model": SettingDefinition(
        key="llm.worker_model",
        display_name="Worker Model",
        description=(
            "Model used for background worker tasks. Defaults to the main model if left empty. "
            "Ignored for Ollama and vLLM, which always use the main model."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        default_value="",
        env_var_name="LLM_WORKER_MODEL",
        display_order=5,
        ui_widget="text",
        placeholder="anthropic/claude-sonnet-4.6",
    ),
    "llm.writer_model": SettingDefinition(
        key="llm.writer_model",
        display_name="Writer Model",
        description=(
            "Model used for the compose_document tool. Defaults to the main model if left empty. "
            "Ignored for Ollama and vLLM, which always use the main model."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.LLM,
        default_value="",
        env_var_name="LLM_WRITER_MODEL",
        display_order=6,
        ui_widget="text",
        placeholder="anthropic/claude-sonnet-4.6",
    ),
    "llm.paused": SettingDefinition(
        key="llm.paused",
        display_name="LLM Paused",
        description=(
            "When true, all LLM calls (chat, cron jobs, background tools) are blocked before "
            "they reach the provider. Set externally (e.g. via the managed settings API) to "
            "pause the instance — for example when a spending limit is reached — and cleared "
            "to resume. Not normally toggled manually in self-hosted deployments."
        ),
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.LLM,
        default_value=False,
        display_order=15,
        ui_widget="toggle",
    ),
    # ========================================================================
    # GOOGLE INTEGRATION (Gmail, Calendar, etc.)
    # ========================================================================
    "google.enabled": SettingDefinition(
        key="google.enabled",
        display_name="Enable Google Services",
        description="Enable Google integration (Gmail, Calendar, etc.)",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.GOOGLE,
        default_value=False,
        env_var_name="GOOGLE_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "google.client_id": SettingDefinition(
        key="google.client_id",
        display_name="Client ID",
        description="Google OAuth 2.0 Client ID from Google Cloud Console",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE,
        is_sensitive=True,
        default_value="",
        env_var_name="GOOGLE_CLIENT_ID",
        display_order=2,
        ui_widget="text",
        placeholder="123456789-abc123.apps.googleusercontent.com",
        help_url="https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google.md",
    ),
    "google.client_secret": SettingDefinition(
        key="google.client_secret",
        display_name="Client Secret",
        description="Google OAuth 2.0 Client Secret from Google Cloud Console",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE,
        is_sensitive=True,
        default_value="",
        env_var_name="GOOGLE_CLIENT_SECRET",
        display_order=3,
        ui_widget="masked",
        placeholder="Enter your client secret",
        help_url="https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google.md",
    ),
    "google.project_id": SettingDefinition(
        key="google.project_id",
        display_name="Project ID",
        description="Google Cloud Project ID (optional)",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE,
        is_sensitive=False,
        default_value="",
        env_var_name="GOOGLE_PROJECT_ID",
        display_order=4,
        ui_widget="text",
        placeholder="my-project-12345",
    ),
    # Note: OAuth tokens are now stored encrypted in the database (credentials table)
    # No token_path setting needed - tokens persist across deployments automatically
    # ========================================================================
    # OUTLOOK INTEGRATION
    # ========================================================================
    "outlook.enabled": SettingDefinition(
        key="outlook.enabled",
        display_name="Enable Outlook",
        description="Enable Outlook integration",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.OUTLOOK,
        default_value=False,
        env_var_name="OUTLOOK_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "outlook.client_id": SettingDefinition(
        key="outlook.client_id",
        display_name="Client ID",
        description="Outlook/Azure app client ID",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.OUTLOOK,
        default_value="",
        env_var_name="OUTLOOK_CLIENT_ID",
        display_order=2,
        ui_widget="text",
        placeholder="00000000-0000-0000-0000-000000000000",
    ),
    "outlook.client_secret": SettingDefinition(
        key="outlook.client_secret",
        display_name="Client Secret",
        description="Outlook/Azure app client secret",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.OUTLOOK,
        is_sensitive=True,
        default_value="",
        env_var_name="OUTLOOK_CLIENT_SECRET",
        display_order=3,
        ui_widget="masked",
        placeholder="Your client secret",
    ),
    "outlook.tenant_id": SettingDefinition(
        key="outlook.tenant_id",
        display_name="Tenant ID",
        description="Azure tenant ID",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.OUTLOOK,
        default_value="",
        env_var_name="OUTLOOK_TENANT_ID",
        display_order=4,
        ui_widget="text",
        placeholder="00000000-0000-0000-0000-000000000000",
    ),
    # ========================================================================
    # NOTION INTEGRATION
    # ========================================================================
    "notion.enabled": SettingDefinition(
        key="notion.enabled",
        display_name="Enable Notion",
        description="Enable Notion integration",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.NOTION,
        default_value=False,
        env_var_name="NOTION_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "notion.api_key": SettingDefinition(
        key="notion.api_key",
        display_name="API Key",
        description="Notion integration API key",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.NOTION,
        is_sensitive=True,
        default_value="",
        env_var_name="NOTION_API_KEY",
        display_order=2,
        ui_widget="masked",
        placeholder="secret_...",
    ),
    "notion.database_id": SettingDefinition(
        key="notion.database_id",
        display_name="Database ID",
        description="Notion database ID for storing data",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.NOTION,
        default_value="",
        env_var_name="NOTION_DATABASE_ID",
        display_order=3,
        ui_widget="text",
        placeholder="00000000000000000000000000000000",
    ),
    # ========================================================================
    # NEXTCLOUD INTEGRATION
    # ========================================================================
    "nextcloud.enabled": SettingDefinition(
        key="nextcloud.enabled",
        display_name="Enable Nextcloud",
        description="Enable Nextcloud integration",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.NEXTCLOUD,
        default_value=False,
        env_var_name="NEXTCLOUD_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "nextcloud.url": SettingDefinition(
        key="nextcloud.url",
        display_name="Server URL",
        description="Nextcloud server URL",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.NEXTCLOUD,
        default_value="",
        env_var_name="NEXTCLOUD_URL",
        display_order=2,
        ui_widget="text",
        placeholder="https://cloud.example.com",
    ),
    "nextcloud.username": SettingDefinition(
        key="nextcloud.username",
        display_name="Username",
        description="Nextcloud username",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.NEXTCLOUD,
        default_value="",
        env_var_name="NEXTCLOUD_USERNAME",
        display_order=3,
        ui_widget="text",
        placeholder="user@example.com",
    ),
    "nextcloud.password": SettingDefinition(
        key="nextcloud.password",
        display_name="Password",
        description="Nextcloud app password or password",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.NEXTCLOUD,
        is_sensitive=True,
        default_value="",
        env_var_name="NEXTCLOUD_PASSWORD",
        display_order=4,
        ui_widget="masked",
        placeholder="Your app password",
    ),
    # ========================================================================
    # WHATSAPP INTEGRATION
    # ========================================================================
    "whatsapp.enabled": SettingDefinition(
        key="whatsapp.enabled",
        display_name="Enable WhatsApp",
        description="Enable WhatsApp integration",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.WHATSAPP,
        default_value=False,
        env_var_name="WHATSAPP_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "whatsapp.phone_number": SettingDefinition(
        key="whatsapp.phone_number",
        display_name="Phone Number / WhatsApp ID",
        description="WhatsApp phone number with country code or full WhatsApp ID (e.g., +1234567890 or 1234567890@lid)",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.WHATSAPP,
        default_value="",
        validation_regex=r"^(\+?[1-9]\d{1,14}|\d+@(c\.us|lid))$",
        env_var_name="WHATSAPP_PHONE_NUMBER",
        display_order=2,
        ui_widget="text",
        placeholder="+1234567890 or 1234567890@lid",
    ),
    "whatsapp.session_dir": SettingDefinition(
        key="whatsapp.session_dir",
        display_name="Session Directory",
        description="Directory for storing WhatsApp session data",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.WHATSAPP,
        default_value="data/whatsapp_session",
        env_var_name="WHATSAPP_SESSION_DIR",
        display_order=3,
        ui_widget="text",
        placeholder="data/whatsapp_session",
    ),
    # ========================================================================
    # SLACK INTEGRATION
    # ========================================================================
    "slack.enabled": SettingDefinition(
        key="slack.enabled",
        display_name="Enable Slack",
        description="Enable Slack integration for sending and receiving messages",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.SLACK,
        default_value=False,
        env_var_name="SLACK_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "slack.bot_token": SettingDefinition(
        key="slack.bot_token",
        display_name="Bot Token",
        description="Slack Bot User OAuth Token (xoxb-...). Found under OAuth & Permissions in your Slack app.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.SLACK,
        is_sensitive=True,
        default_value="",
        env_var_name="SLACK_BOT_TOKEN",
        display_order=2,
        ui_widget="password",
        placeholder="xoxb-...",
    ),
    "slack.signing_secret": SettingDefinition(
        key="slack.signing_secret",
        display_name="Signing Secret",
        description="Slack app signing secret for verifying incoming webhook requests. Found under Basic Information.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.SLACK,
        is_sensitive=True,
        default_value="",
        env_var_name="SLACK_SIGNING_SECRET",
        display_order=3,
        ui_widget="password",
        placeholder="Your signing secret",
    ),
    "slack.app_token": SettingDefinition(
        key="slack.app_token",
        display_name="App-Level Token (Socket Mode)",
        description="Slack App-Level Token (xapp-...) for Socket Mode. Optional — only needed if you use Socket Mode instead of HTTP webhooks.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.SLACK,
        is_sensitive=True,
        default_value="",
        env_var_name="SLACK_APP_TOKEN",
        display_order=4,
        ui_widget="password",
        placeholder="xapp-...",
    ),
    "slack.default_channel": SettingDefinition(
        key="slack.default_channel",
        display_name="Default Channel",
        description="Default Slack channel ID for sending messages (e.g., C01ABCDEF12). You can find this in the channel details.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.SLACK,
        default_value="",
        env_var_name="SLACK_DEFAULT_CHANNEL",
        display_order=5,
        ui_widget="text",
        placeholder="C01ABCDEF12",
    ),
    "slack.allowed_user_ids": SettingDefinition(
        key="slack.allowed_user_ids",
        display_name="Allowed User IDs",
        description="Comma-separated list of Slack user IDs allowed to interact with the bot. Leave empty to allow all users.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.SLACK,
        default_value="",
        env_var_name="SLACK_ALLOWED_USER_IDS",
        display_order=6,
        ui_widget="text",
        placeholder="U01ABCDEF,U02GHIJKL",
    ),
    # ========================================================================
    # BRAVE SEARCH INTEGRATION
    # ========================================================================
    "brave.enabled": SettingDefinition(
        key="brave.enabled",
        display_name="Enable Brave Search",
        description="Enable web search via Brave Search API. Falls back to DuckDuckGo when disabled or on failure.",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.BRAVE,
        default_value=True,
        env_var_name="BRAVE_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "brave.api_key": SettingDefinition(
        key="brave.api_key",
        display_name="API Key",
        description="Brave Search API key. Get one free at https://brave.com/search/api/",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.BRAVE,
        is_sensitive=True,
        default_value="",
        env_var_name="BRAVE_API_KEY",
        display_order=2,
        ui_widget="masked",
        placeholder="BSA...",
        help_url="https://brave.com/search/api/",
    ),
    "brave.results_limit": SettingDefinition(
        key="brave.results_limit",
        display_name="Results Limit",
        description="Maximum number of search results to return per query",
        value_type=SettingValueType.INT,
        category=ConfigCategory.BRAVE,
        default_value=10,
        min_value=1,
        max_value=20,
        env_var_name="BRAVE_RESULTS_LIMIT",
        display_order=3,
        ui_widget="number",
    ),
    "brave.safe_search": SettingDefinition(
        key="brave.safe_search",
        display_name="Safe Search",
        description="Safe search filtering level",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.BRAVE,
        default_value="moderate",
        options=["off", "moderate", "strict"],
        env_var_name="BRAVE_SAFE_SEARCH",
        display_order=4,
        ui_widget="select",
    ),
    # ========================================================================
    # BROWSER INTEGRATION (Playwright)
    # ========================================================================
    "browser.enabled": SettingDefinition(
        key="browser.enabled",
        display_name="Enable Browser",
        description="Enable web browsing with Playwright and vision-based screenshots",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.BROWSER,
        default_value=True,
        env_var_name="BROWSER_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "browser.headless": SettingDefinition(
        key="browser.headless",
        display_name="Headless Mode",
        description="Run browser in headless mode (no visible window)",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.BROWSER,
        default_value=True,
        env_var_name="BROWSER_HEADLESS",
        display_order=2,
        ui_widget="toggle",
    ),
    "browser.viewport_width": SettingDefinition(
        key="browser.viewport_width",
        display_name="Viewport Width",
        description="Browser viewport width in pixels",
        value_type=SettingValueType.INT,
        category=ConfigCategory.BROWSER,
        default_value=1280,
        min_value=800,
        max_value=1920,
        env_var_name="BROWSER_VIEWPORT_WIDTH",
        display_order=3,
        ui_widget="number",
    ),
    "browser.viewport_height": SettingDefinition(
        key="browser.viewport_height",
        display_name="Viewport Height",
        description="Browser viewport height in pixels",
        value_type=SettingValueType.INT,
        category=ConfigCategory.BROWSER,
        default_value=720,
        min_value=600,
        max_value=1080,
        env_var_name="BROWSER_VIEWPORT_HEIGHT",
        display_order=4,
        ui_widget="number",
    ),
    "browser.screenshot_quality": SettingDefinition(
        key="browser.screenshot_quality",
        display_name="Screenshot Quality",
        description="JPEG screenshot quality (0-100, higher is better but larger)",
        value_type=SettingValueType.INT,
        category=ConfigCategory.BROWSER,
        default_value=85,
        min_value=50,
        max_value=100,
        env_var_name="BROWSER_SCREENSHOT_QUALITY",
        display_order=5,
        ui_widget="number",
    ),
    # ========================================================================
    # GOOGLE NAVIGATOR INTEGRATION (Places, Directions, Geocoding)
    # ========================================================================
    "google_navigator.enabled": SettingDefinition(
        key="google_navigator.enabled",
        display_name="Enable Google Navigator",
        description="Enable Google Places, Directions, and Geocoding APIs",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.GOOGLE_NAVIGATOR,
        default_value=True,
        env_var_name="GOOGLE_NAVIGATOR_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "google_navigator.places_api_key": SettingDefinition(
        key="google_navigator.places_api_key",
        display_name="Places / Maps API Key",
        description="Google API key for Places, Directions, and Geocoding APIs. Create one in Google Cloud Console with Places API (New), Directions API, and Geocoding API enabled.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_NAVIGATOR,
        is_sensitive=True,
        default_value="",
        env_var_name="GOOGLE_PLACES_API_KEY",
        display_order=2,
        ui_widget="masked",
        placeholder="AIzaSy...",
        help_url="https://developers.google.com/maps/documentation/places/web-service/get-api-key",
    ),
    # ========================================================================
    # WHISPER (OpenAI Audio Transcription)
    # ========================================================================
    "whisper.enabled": SettingDefinition(
        key="whisper.enabled",
        display_name="Enable Whisper",
        description="Enable OpenAI Whisper for automatic voice message transcription via WhatsApp",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.WHISPER,
        default_value=True,
        env_var_name="WHISPER_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "whisper.api_key": SettingDefinition(
        key="whisper.api_key",
        display_name="API Key",
        description="OpenAI API key for Whisper transcription. If empty, falls back to the main LLM API key.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.WHISPER,
        is_sensitive=True,
        default_value="",
        env_var_name="WHISPER_API_KEY",
        display_order=2,
        ui_widget="masked",
        placeholder="sk-...",
        help_url="https://platform.openai.com/api-keys",
    ),
    "whisper.base_url": SettingDefinition(
        key="whisper.base_url",
        display_name="Base URL",
        description="API base URL for Whisper. Leave empty for default OpenAI endpoint (https://api.openai.com/v1).",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.WHISPER,
        default_value="",
        env_var_name="WHISPER_BASE_URL",
        display_order=3,
        ui_widget="text",
        placeholder="https://api.openai.com/v1",
    ),
    "whisper.model": SettingDefinition(
        key="whisper.model",
        display_name="Model",
        description="Whisper model to use for transcription",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.WHISPER,
        default_value="whisper-1",
        env_var_name="WHISPER_MODEL",
        display_order=4,
        ui_widget="text",
        placeholder="whisper-1",
    ),
    # ========================================================================
    # MISTRAL OCR (PDF Text Extraction)
    # ========================================================================
    "mistral_ocr.enabled": SettingDefinition(
        key="mistral_ocr.enabled",
        display_name="Enable Mistral OCR",
        description="Enable Mistral AI OCR for PDF document text extraction",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.MISTRAL_OCR,
        default_value=True,
        env_var_name="MISTRAL_OCR_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "mistral_ocr.api_key": SettingDefinition(
        key="mistral_ocr.api_key",
        display_name="API Key",
        description="Mistral AI API key. If empty, falls back to main LLM API key.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.MISTRAL_OCR,
        is_sensitive=True,
        default_value="",
        env_var_name="MISTRAL_OCR_API_KEY",
        display_order=2,
        ui_widget="masked",
        placeholder="your-api-key",
    ),
    "mistral_ocr.base_url": SettingDefinition(
        key="mistral_ocr.base_url",
        display_name="Base URL",
        description="API base URL for Mistral. Leave empty for default (https://api.mistral.ai).",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.MISTRAL_OCR,
        default_value="",
        env_var_name="MISTRAL_OCR_BASE_URL",
        display_order=3,
        ui_widget="text",
        placeholder="https://api.mistral.ai",
    ),
    "mistral_ocr.model": SettingDefinition(
        key="mistral_ocr.model",
        display_name="Model",
        description="Mistral OCR model to use",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.MISTRAL_OCR,
        default_value="mistral-ocr-latest",
        env_var_name="MISTRAL_OCR_MODEL",
        display_order=4,
        ui_widget="text",
        placeholder="mistral-ocr-latest",
    ),
    "mistral_ocr.notion_database_id": SettingDefinition(
        key="mistral_ocr.notion_database_id",
        display_name="Notion Database ID",
        description="Notion database ID where PDF notes should be saved. Get this from your Notion database URL.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.MISTRAL_OCR,
        default_value="",
        env_var_name="MISTRAL_OCR_NOTION_DB",
        display_order=5,
        ui_widget="text",
        placeholder="abc123def456...",
    ),
    # ========================================================================
    # GOOGLE ADS (Advertising)
    # ========================================================================
    "google_ads.enabled": SettingDefinition(
        key="google_ads.enabled",
        display_name="Enable Google Ads",
        description="Enable Google Ads integration for managing campaigns, ad groups, and keywords.",
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.GOOGLE_ADS,
        default_value=False,
        env_var_name="GOOGLE_ADS_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "google_ads.client_id": SettingDefinition(
        key="google_ads.client_id",
        display_name="Client ID",
        description="Google OAuth 2.0 Client ID for Google Ads (separate from regular Google integration).",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_ADS,
        is_sensitive=True,
        default_value="",
        env_var_name="GOOGLE_ADS_CLIENT_ID",
        display_order=2,
        ui_widget="text",
        placeholder="123456789-abc123.apps.googleusercontent.com",
        help_url="https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google_ads.md",
    ),
    "google_ads.client_secret": SettingDefinition(
        key="google_ads.client_secret",
        display_name="Client Secret",
        description="Google OAuth 2.0 Client Secret for Google Ads.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_ADS,
        is_sensitive=True,
        default_value="",
        env_var_name="GOOGLE_ADS_CLIENT_SECRET",
        display_order=3,
        ui_widget="masked",
        placeholder="Enter your client secret",
        help_url="https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google_ads.md",
    ),
    "google_ads.developer_token": SettingDefinition(
        key="google_ads.developer_token",
        display_name="Developer Token",
        description="Google Ads Developer Token from your Manager Account's API Center.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_ADS,
        is_sensitive=True,
        default_value="",
        env_var_name="GOOGLE_ADS_DEVELOPER_TOKEN",
        display_order=4,
        ui_widget="masked",
        placeholder="abc123def456...",
        help_url="https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google_ads.md",
    ),
    "google_ads.customer_id": SettingDefinition(
        key="google_ads.customer_id",
        display_name="Customer ID",
        description="Your Google Ads advertising account ID (10-digit number, dashes optional).",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_ADS,
        default_value="",
        env_var_name="GOOGLE_ADS_CUSTOMER_ID",
        display_order=5,
        ui_widget="text",
        placeholder="123-456-7890",
        help_url="https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google_ads.md",
    ),
    "google_ads.login_customer_id": SettingDefinition(
        key="google_ads.login_customer_id",
        display_name="Login Customer ID",
        description="Manager Account (MCC) ID if authenticating via a manager account. Optional.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_ADS,
        default_value="",
        env_var_name="GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        display_order=6,
        ui_widget="text",
        placeholder="123-456-7890",
        help_url="https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google_ads.md",
    ),
    "google_ads.project_id": SettingDefinition(
        key="google_ads.project_id",
        display_name="Project ID",
        description="Google Cloud Project ID for the Google Ads API. Optional.",
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_ADS,
        default_value="",
        env_var_name="GOOGLE_ADS_PROJECT_ID",
        display_order=7,
        ui_widget="text",
        placeholder="my-project-12345",
    ),
    # ========================================================================
    # GOOGLE NEWS (no API key required)
    # ========================================================================
    "google_news.enabled": SettingDefinition(
        key="google_news.enabled",
        display_name="Enable Google News",
        description=(
            "Enable Google News integration for fetching headlines, searching news, "
            "and browsing news by topic or location. No API key required."
        ),
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.GOOGLE_NEWS,
        default_value=False,
        env_var_name="GOOGLE_NEWS_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "google_news.language": SettingDefinition(
        key="google_news.language",
        display_name="Language",
        description=(
            "ISO 639-1 language code for news results. "
            "Examples: en (English), de (German), fr (French), es (Spanish), nl (Dutch)."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_NEWS,
        default_value="en",
        env_var_name="GOOGLE_NEWS_LANGUAGE",
        display_order=2,
        ui_widget="text",
        placeholder="en",
    ),
    "google_news.country": SettingDefinition(
        key="google_news.country",
        display_name="Country",
        description=(
            "ISO 3166-1 alpha-2 country code to localise news results. "
            "Examples: US, GB, DE, FR, NL, AU."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.GOOGLE_NEWS,
        default_value="US",
        env_var_name="GOOGLE_NEWS_COUNTRY",
        display_order=3,
        ui_widget="text",
        placeholder="US",
    ),
    "google_news.max_results": SettingDefinition(
        key="google_news.max_results",
        display_name="Max Results",
        description="Maximum number of articles to return per request (1–50). Default is 10.",
        value_type=SettingValueType.INT,
        category=ConfigCategory.GOOGLE_NEWS,
        default_value=10,
        min_value=1,
        max_value=50,
        env_var_name="GOOGLE_NEWS_MAX_RESULTS",
        display_order=4,
        ui_widget="number",
        placeholder="10",
    ),
    # ========================================================================
    # YAHOO FINANCE (Market Data — no API key required)
    # ========================================================================
    "yahoo_finance.enabled": SettingDefinition(
        key="yahoo_finance.enabled",
        display_name="Enable Yahoo Finance",
        description=(
            "Enable Yahoo Finance integration for real-time stock quotes, historical price data, "
            "company profiles, financial statements, and market news. "
            "No API key required — data is fetched directly from Yahoo Finance."
        ),
        value_type=SettingValueType.BOOL,
        category=ConfigCategory.YAHOO_FINANCE,
        default_value=True,
        env_var_name="YAHOO_FINANCE_ENABLED",
        display_order=1,
        ui_widget="toggle",
    ),
    "yahoo_finance.request_timeout": SettingDefinition(
        key="yahoo_finance.request_timeout",
        display_name="Request Timeout",
        description="Timeout in seconds for Yahoo Finance API requests.",
        value_type=SettingValueType.INT,
        category=ConfigCategory.YAHOO_FINANCE,
        default_value=10,
        min_value=1,
        max_value=60,
        env_var_name="YAHOO_FINANCE_REQUEST_TIMEOUT",
        display_order=2,
        ui_widget="number",
    ),
    # ========================================================================
    # USER PREFERENCES
    # ========================================================================
    "user.timezone": SettingDefinition(
        key="user.timezone",
        display_name="Timezone",
        description=(
            "Your local timezone. Used so the assistant understands dates, times, and cron "
            "schedules in your local time. Uses IANA timezone names (e.g. Europe/Brussels)."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.USER,
        default_value="UTC",
        options=[
            "UTC",
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Phoenix",
            "America/Los_Angeles",
            "America/Anchorage",
            "America/Honolulu",
            "America/Toronto",
            "America/Vancouver",
            "America/Mexico_City",
            "America/Bogota",
            "America/Lima",
            "America/Santiago",
            "America/Sao_Paulo",
            "America/Argentina/Buenos_Aires",
            "Europe/London",
            "Europe/Dublin",
            "Europe/Lisbon",
            "Europe/Paris",
            "Europe/Brussels",
            "Europe/Amsterdam",
            "Europe/Berlin",
            "Europe/Vienna",
            "Europe/Zurich",
            "Europe/Madrid",
            "Europe/Rome",
            "Europe/Stockholm",
            "Europe/Oslo",
            "Europe/Copenhagen",
            "Europe/Helsinki",
            "Europe/Warsaw",
            "Europe/Prague",
            "Europe/Budapest",
            "Europe/Bucharest",
            "Europe/Athens",
            "Europe/Istanbul",
            "Europe/Kiev",
            "Europe/Moscow",
            "Africa/Cairo",
            "Africa/Johannesburg",
            "Africa/Lagos",
            "Africa/Nairobi",
            "Asia/Dubai",
            "Asia/Karachi",
            "Asia/Kolkata",
            "Asia/Dhaka",
            "Asia/Bangkok",
            "Asia/Singapore",
            "Asia/Kuala_Lumpur",
            "Asia/Jakarta",
            "Asia/Hong_Kong",
            "Asia/Shanghai",
            "Asia/Taipei",
            "Asia/Seoul",
            "Asia/Tokyo",
            "Australia/Perth",
            "Australia/Adelaide",
            "Australia/Sydney",
            "Australia/Melbourne",
            "Australia/Brisbane",
            "Pacific/Auckland",
            "Pacific/Fiji",
            "Pacific/Honolulu",
        ],
        env_var_name="USER_TIMEZONE",
        display_order=1,
        ui_widget="select",
    ),
    "user.first_day_of_week": SettingDefinition(
        key="user.first_day_of_week",
        display_name="First Day of Week",
        description=(
            "The day your week starts on. Used by the assistant to interpret "
            "relative date expressions like 'this week' or 'next week'."
        ),
        value_type=SettingValueType.STRING,
        category=ConfigCategory.USER,
        default_value="Monday",
        options=["Monday", "Sunday", "Saturday"],
        env_var_name="USER_FIRST_DAY_OF_WEEK",
        display_order=2,
        ui_widget="select",
    ),
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_setting_definition(key: str) -> Optional[SettingDefinition]:
    """Get a setting definition by key."""
    return SETTING_DEFINITIONS.get(key)


def get_settings_by_category(category: ConfigCategory) -> Dict[str, SettingDefinition]:
    """Get all setting definitions for a specific category."""
    return {
        key: definition
        for key, definition in SETTING_DEFINITIONS.items()
        if definition.category == category
    }


def get_all_categories() -> List[ConfigCategory]:
    """Get all unique categories from setting definitions."""
    return list(set(definition.category for definition in SETTING_DEFINITIONS.values()))


def get_env_to_db_key_mapping() -> Dict[str, str]:
    """
    Get mapping of environment variable names to database keys.

    Returns:
        Dict mapping ENV names (e.g., "LLM_API_KEY") to DB keys (e.g., "llm.api_key")
    """
    return {
        definition.env_var_name: key
        for key, definition in SETTING_DEFINITIONS.items()
        if definition.env_var_name
    }


def get_sensitive_settings() -> List[SettingDefinition]:
    """Get all settings marked as sensitive."""
    return [definition for definition in SETTING_DEFINITIONS.values() if definition.is_sensitive]


def get_required_settings() -> List[SettingDefinition]:
    """Get all settings marked as required."""
    return [definition for definition in SETTING_DEFINITIONS.values() if definition.is_required]


def get_bootstrap_settings() -> List[SettingDefinition]:
    """Get all bootstrap settings that must remain in ENV."""
    return [
        definition
        for definition in SETTING_DEFINITIONS.values()
        if definition.category == ConfigCategory.BOOTSTRAP
    ]
