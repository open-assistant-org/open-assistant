"""FastAPI dependency injection for database and repositories."""

import os

from fastapi import Depends, Request

from src.core.database import DatabaseManager
from src.core.encryption import EncryptionService, get_encryption_service
from src.core.repositories.agent_task import AgentTaskRepository
from src.core.repositories.artifact import ArtifactRepository
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.cron_job import CronJobRepository
from src.core.repositories.future_task import FutureTaskRepository
from src.core.repositories.memory import MemoryRepository
from src.core.repositories.message import MessageRepository
from src.core.repositories.prompts import PromptsRepository
from src.core.repositories.settings import SettingsRepository
from src.core.repositories.skill import SkillRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_db_manager(request: Request) -> DatabaseManager:
    """
    Get database manager instance from app state.

    Args:
        request: FastAPI request object (injected)

    Returns:
        DatabaseManager singleton instance

    Raises:
        RuntimeError: If database is not initialized
    """
    if not hasattr(request.app.state, "db_manager"):
        raise RuntimeError("Database not initialized")

    return request.app.state.db_manager


def get_encryption() -> EncryptionService:
    """
    Get encryption service instance.

    Returns:
        EncryptionService instance
    """
    return get_encryption_service()


def get_conversation_repo(db: DatabaseManager = Depends(get_db_manager)) -> ConversationRepository:
    """
    Get conversation repository.

    Args:
        db: Database manager (injected)

    Returns:
        ConversationRepository instance
    """
    return ConversationRepository(db)


def get_artifact_repo(db: DatabaseManager = Depends(get_db_manager)) -> ArtifactRepository:
    """
    Get artifact repository.

    Args:
        db: Database manager (injected)

    Returns:
        ArtifactRepository instance
    """
    return ArtifactRepository(db)


def get_message_repo(db: DatabaseManager = Depends(get_db_manager)) -> MessageRepository:
    """
    Get message repository.

    Args:
        db: Database manager (injected)

    Returns:
        MessageRepository instance
    """
    return MessageRepository(db)


def get_memory_repo(db: DatabaseManager = Depends(get_db_manager)) -> MemoryRepository:
    """
    Get memory repository.

    Args:
        db: Database manager (injected)

    Returns:
        MemoryRepository instance
    """
    return MemoryRepository(db)


def get_prompts_repo(db: DatabaseManager = Depends(get_db_manager)) -> PromptsRepository:
    """
    Get prompts repository.

    Args:
        db: Database manager (injected)

    Returns:
        PromptsRepository instance
    """
    return PromptsRepository(db)


def get_settings_repo(db: DatabaseManager = Depends(get_db_manager)) -> SettingsRepository:
    """
    Get settings repository.

    Args:
        db: Database manager (injected)

    Returns:
        SettingsRepository instance
    """
    return SettingsRepository(db)


def get_skill_repo(db: DatabaseManager = Depends(get_db_manager)) -> SkillRepository:
    """
    Get skill repository.

    Args:
        db: Database manager (injected)

    Returns:
        SkillRepository instance
    """
    return SkillRepository(db)


def get_credentials_repo(
    db: DatabaseManager = Depends(get_db_manager),
    encryption: EncryptionService = Depends(get_encryption),
) -> CredentialsRepository:
    """
    Get credentials repository.

    Args:
        db: Database manager (injected)
        encryption: Encryption service (injected)

    Returns:
        CredentialsRepository instance
    """
    return CredentialsRepository(db, encryption)


def get_audit_repo(db: DatabaseManager = Depends(get_db_manager)) -> AuditLogRepository:
    """
    Get audit log repository.

    Args:
        db: Database manager (injected)

    Returns:
        AuditLogRepository instance
    """
    return AuditLogRepository(db)


def get_agent_task_repo(db: DatabaseManager = Depends(get_db_manager)) -> AgentTaskRepository:
    """
    Get agent task repository.

    Args:
        db: Database manager (injected)

    Returns:
        AgentTaskRepository instance
    """
    return AgentTaskRepository(db)


def get_settings_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get settings service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        SettingsService instance
    """
    from src.services.settings import SettingsService

    return SettingsService(settings_repo, credentials_repo, audit_repo)


def get_notion_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Notion service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        NotionService instance
    """
    from src.services.notion import NotionService

    return NotionService(settings_repo, credentials_repo, audit_repo)


def get_nextcloud_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Nextcloud service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        NextcloudService instance
    """
    from src.services.nextcloud import NextcloudService

    return NextcloudService(settings_repo, credentials_repo, audit_repo)


def get_google_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Google service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        GoogleService instance
    """
    from src.services.google import GoogleService

    return GoogleService(settings_repo, credentials_repo, audit_repo)


def get_outlook_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Outlook service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        OutlookService instance
    """
    from src.services.outlook import OutlookService

    return OutlookService(settings_repo, credentials_repo, audit_repo)


def get_whatsapp_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get WhatsApp service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        WhatsAppService instance
    """
    from src.services.whatsapp import WhatsAppService

    return WhatsAppService(settings_repo, credentials_repo, audit_repo)


def get_slack_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Slack service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        SlackService instance
    """
    from src.services.slack import SlackService

    return SlackService(settings_repo, credentials_repo, audit_repo)


def get_google_news_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Google News service instance.

    Returns:
        GoogleNewsService instance
    """
    from src.services.google_news import GoogleNewsService

    return GoogleNewsService(settings_repo, credentials_repo, audit_repo)


def get_brave_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Brave Search service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        BraveService instance
    """
    from src.services.brave import BraveService

    return BraveService(settings_repo, credentials_repo, audit_repo)


def get_browser_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Browser service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        BrowserService instance
    """
    from src.services.browser import BrowserService

    return BrowserService(settings_repo, credentials_repo, audit_repo)


def get_embedding_service(
    settings_service=Depends(get_settings_service),
):
    """
    Get embedding service instance.

    Args:
        settings_service: Settings service (injected) for model configuration.

    Returns:
        EmbeddingService instance
    """
    from src.services.embedding import EmbeddingService

    embedding_model = settings_service.get_config_with_fallback(
        "search.embedding_model", "sentence-transformers/all-MiniLM-L6-v2"
    )
    return EmbeddingService(model=embedding_model)


def get_search_service(
    db: DatabaseManager = Depends(get_db_manager),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    google_service=Depends(get_google_service),
    outlook_service=Depends(get_outlook_service),
    notion_service=Depends(get_notion_service),
    nextcloud_service=Depends(get_nextcloud_service),
    embedding_service=Depends(get_embedding_service),
):
    """
    Get unified search service instance.

    Args:
        db: Database manager (injected)
        settings_repo: Settings repository (injected)
        google_service: Google service (injected)
        outlook_service: Outlook service (injected)
        notion_service: Notion service (injected)
        nextcloud_service: Nextcloud service (injected)
        embedding_service: Embedding service (injected)

    Returns:
        UnifiedSearchService instance
    """
    from src.services.search import UnifiedSearchService

    return UnifiedSearchService(
        settings_repo=settings_repo,
        db_manager=db,
        google_service=google_service,
        outlook_service=outlook_service,
        notion_service=notion_service,
        nextcloud_service=nextcloud_service,
        embedding_service=embedding_service,
    )


def get_whisper_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Whisper service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        WhisperService instance
    """
    from src.services.whisper import WhisperService

    return WhisperService(settings_repo, credentials_repo, audit_repo)


def get_google_ads_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Google Ads service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        GoogleAdsService instance
    """
    from src.services.google_ads import GoogleAdsService

    return GoogleAdsService(settings_repo, credentials_repo, audit_repo)


def get_yahoo_finance_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Yahoo Finance service instance.

    Returns:
        YahooFinanceService instance (no API key required)
    """
    from src.services.yahoo_finance import YahooFinanceService

    return YahooFinanceService(settings_repo, credentials_repo, audit_repo)


def get_mistral_ocr_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
):
    """
    Get Mistral OCR service instance.

    Args:
        settings_repo: Settings repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        MistralOCRService instance
    """
    from src.services.mistral_ocr import MistralOCRService

    return MistralOCRService(settings_repo, credentials_repo, audit_repo)


def get_whatsapp_media_handler(
    settings_service=Depends(get_settings_service),
    mistral_ocr_service=Depends(get_mistral_ocr_service),
    nextcloud_service=Depends(get_nextcloud_service),
    notion_service=Depends(get_notion_service),
):
    """
    Get WhatsApp media handler instance.

    Args:
        settings_service: Settings service (injected)
        mistral_ocr_service: Mistral OCR service (injected)
        nextcloud_service: Nextcloud service (injected)
        notion_service: Notion service (injected)

    Returns:
        MediaHandler instance configured for WhatsApp
    """
    from src.services.whatsapp_media import MediaHandler

    return MediaHandler(
        settings_service=settings_service,
        mistral_ocr_service=mistral_ocr_service,
        nextcloud_service=nextcloud_service,
        notion_service=notion_service,
        channel="WhatsApp",
    )


def get_slack_media_handler(
    settings_service=Depends(get_settings_service),
    mistral_ocr_service=Depends(get_mistral_ocr_service),
    nextcloud_service=Depends(get_nextcloud_service),
    notion_service=Depends(get_notion_service),
):
    """
    Get Slack media handler instance.

    Args:
        settings_service: Settings service (injected)
        mistral_ocr_service: Mistral OCR service (injected)
        nextcloud_service: Nextcloud service (injected)
        notion_service: Notion service (injected)

    Returns:
        MediaHandler instance configured for Slack
    """
    from src.services.whatsapp_media import MediaHandler

    return MediaHandler(
        settings_service=settings_service,
        mistral_ocr_service=mistral_ocr_service,
        nextcloud_service=nextcloud_service,
        notion_service=notion_service,
        channel="Slack",
    )


def get_agent_registry(db: DatabaseManager = Depends(get_db_manager)):
    """
    Get agent registry instance.

    Args:
        db: Database manager (injected)

    Returns:
        AgentRegistry instance
    """
    from src.agents.registry import AgentRegistry

    return AgentRegistry(db)


# Note: get_crew() removed - replaced by get_message_handler() for skills-based system


def get_cron_job_repo(db: DatabaseManager = Depends(get_db_manager)) -> CronJobRepository:
    """
    Get cron job repository.

    Args:
        db: Database manager (injected)

    Returns:
        CronJobRepository instance
    """
    return CronJobRepository(db)


def get_cron_job_service(
    request: Request,
    cron_job_repo: CronJobRepository = Depends(get_cron_job_repo),
):
    """
    Get cron job service instance.

    Uses the shared service from app state if available (has scheduler),
    otherwise creates a new instance for repository-only operations.

    Args:
        request: FastAPI request (injected)
        cron_job_repo: Cron job repository (injected)

    Returns:
        CronJobService instance
    """
    # Prefer the app-state service which has the running scheduler
    if hasattr(request.app.state, "cron_job_service"):
        return request.app.state.cron_job_service

    from src.services.cron_job import CronJobService

    return CronJobService(cron_job_repo)


def get_future_task_repo(db: DatabaseManager = Depends(get_db_manager)) -> FutureTaskRepository:
    """
    Get future task repository.

    Args:
        db: Database manager (injected)

    Returns:
        FutureTaskRepository instance
    """
    return FutureTaskRepository(db)


def get_future_task_service(
    request: Request,
    future_task_repo: FutureTaskRepository = Depends(get_future_task_repo),
):
    """
    Get future task service instance.

    Uses the shared service from app state if available (has scheduler),
    otherwise creates a new instance for repository-only operations.

    Args:
        request: FastAPI request (injected)
        future_task_repo: Future task repository (injected)

    Returns:
        FutureTaskService instance
    """
    # Prefer the app-state service which has the running scheduler
    if hasattr(request.app.state, "future_task_service"):
        return request.app.state.future_task_service

    from src.services.future_task import FutureTaskService

    return FutureTaskService(future_task_repo)


def get_classifier(settings_service=Depends(get_settings_service)):
    """
    Get request classifier instance.

    Args:
        settings_service: Settings service (injected)

    Returns:
        RequestClassifier instance
    """
    from src.core.classifier import RequestClassifier
    from src.core.llm_client import LLMClient, LLMConfig

    llm_config = LLMConfig.from_settings(settings_service, temperature=0.0, max_tokens=100)

    llm_client = LLMClient(llm_config)

    return RequestClassifier(llm_client)


def get_memory_service(
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repo),
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    db: DatabaseManager = Depends(get_db_manager),
):
    """
    Get memory service instance.

    Args:
        message_repo: Message repository (injected)
        memory_repo: Memory repository (injected)
        conversation_repo: Conversation repository (injected)
        prompts_repo: Prompts repository (injected)
        settings_repo: Settings repository (injected)
        db: Database manager (injected)

    Returns:
        MemoryService instance
    """
    from src.services.memory import MemoryService

    # llm_client=None: MemoryService builds it lazily from settings_repo on first use,
    # which lets it pick up the correct worker_model setting at runtime.
    return MemoryService(
        message_repo=message_repo,
        memory_repo=memory_repo,
        conversation_repo=conversation_repo,
        prompts_repo=prompts_repo,
        settings_repo=settings_repo,
        db_manager=db,
        llm_client=None,
    )


def get_conversation_service(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    memory_service=Depends(get_memory_service),
):
    """
    Get conversation service instance.

    Args:
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        memory_service: Memory service (injected)

    Returns:
        ConversationService instance
    """
    from src.services.conversation import ConversationService

    return ConversationService(conversation_repo, message_repo, memory_service)


def get_tool_executor(
    request: Request,
    db: DatabaseManager = Depends(get_db_manager),
    google_service=Depends(get_google_service),
    google_ads_service=Depends(get_google_ads_service),
    outlook_service=Depends(get_outlook_service),
    notion_service=Depends(get_notion_service),
    nextcloud_service=Depends(get_nextcloud_service),
    whatsapp_service=Depends(get_whatsapp_service),
    slack_service=Depends(get_slack_service),
    google_news_service=Depends(get_google_news_service),
    yahoo_finance_service=Depends(get_yahoo_finance_service),
    brave_service=Depends(get_brave_service),
    browser_service=Depends(get_browser_service),
    cron_job_service=Depends(get_cron_job_service),
    future_task_service=Depends(get_future_task_service),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
    settings_service=Depends(get_settings_service),
    search_service=Depends(get_search_service),
    embedding_service=Depends(get_embedding_service),
):
    """
    Get tool executor instance.

    Args:
        google_service: Google service (injected)
        outlook_service: Outlook service (injected)
        notion_service: Notion service (injected)
        nextcloud_service: Nextcloud service (injected)
        whatsapp_service: WhatsApp service (injected)
        slack_service: Slack service (injected)
        brave_service: Brave service (injected)
        browser_service: Browser service (injected)
        cron_job_service: Cron job service (injected)
        future_task_service: Future task service (injected)
        audit_repo: Audit log repository (injected)
        settings_service: Settings service (injected)
        search_service: Unified search service (injected)
        embedding_service: Embedding service (injected)

    Returns:
        ToolExecutor instance
    """
    from src.core.tools.executor import ToolExecutor
    from src.services.system import SystemService

    # Create system service with database access for conversation/prompt tools
    system_service = SystemService(
        db_manager=db, embedding_service=embedding_service, settings_service=settings_service
    )

    return ToolExecutor(
        google_service=google_service,
        google_ads_service=google_ads_service,
        outlook_service=outlook_service,
        notion_service=notion_service,
        nextcloud_service=nextcloud_service,
        whatsapp_service=whatsapp_service,
        slack_service=slack_service,
        google_news_service=google_news_service,
        yahoo_finance_service=yahoo_finance_service,
        brave_service=brave_service,
        browser_service=browser_service,
        system_service=system_service,
        cron_job_service=cron_job_service,
        future_task_service=future_task_service,
        audit_repo=audit_repo,
        conversation_id=None,  # Will be set per request
        settings_service=settings_service,
        search_service=search_service,
        plugin_service=getattr(request.app.state, "plugin_service", None),
    )


def get_message_handler(
    skill_repo: SkillRepository = Depends(get_skill_repo),
    conversation_service=Depends(get_conversation_service),
    memory_service=Depends(get_memory_service),
    settings_service=Depends(get_settings_service),
    tool_executor=Depends(get_tool_executor),
):
    """
    Get message handler instance.

    Args:
        skill_repo: Skill repository (injected)
        conversation_service: Conversation service (injected)
        memory_service: Memory service (injected)
        settings_service: Settings service (injected)
        tool_executor: Tool executor (injected)

    Returns:
        MessageHandler instance
    """
    from src.services.message_handler import MessageHandler

    return MessageHandler(
        skill_repo=skill_repo,
        conversation_service=conversation_service,
        memory_service=memory_service,
        settings_service=settings_service,
        tool_executor=tool_executor,
        max_iterations=15,
        max_skills_per_request=5,
    )
