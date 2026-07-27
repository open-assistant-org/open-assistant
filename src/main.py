"""FastAPI application entry point with health checks and database initialization."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.api.agents import router as agents_router
from src.api.artifacts import router as artifacts_router
from src.api.artifacts import visitor_router as artifact_visitor_router
from src.api.auth import router as auth_router
from src.api.brave import router as brave_router
from src.api.browser import router as browser_router
from src.api.chat import router as chat_router
from src.api.conversations import router as conversations_router
from src.api.cron_jobs import router as cron_jobs_router
from src.api.future_tasks import router as future_tasks_router
from src.api.google import router as google_router
from src.api.google_ads import router as google_ads_router
from src.api.google_navigator import router as google_navigator_router
from src.api.integrations import router as integrations_router
from src.api.monitoring import router as monitoring_router
from src.api.nextcloud import router as nextcloud_router
from src.api.notion import router as notion_router
from src.api.outlook import router as outlook_router
from src.api.prompts import router as prompts_router
from src.api.pwa import router as pwa_router
from src.api.settings import router as settings_router
from src.api.skills import router as skills_router
from src.api.slack import router as slack_router
from src.api.plugins import router as plugins_router
from src.api.mcp import router as mcp_router
from src.api.google_news import router as google_news_router
from src.api.yahoo_finance import router as yahoo_finance_router
from src.api.whatsapp import router as whatsapp_router
from src.api.whisper import router as whisper_router
from src.api.mistral_ocr import router as mistral_ocr_router
from src.core.config import init_config

# Managed mode (Open Assistant Platform)
_MANAGED_API_KEY = os.getenv("MANAGED_API_KEY", "")
from src.core.database import DatabaseManager
from src.core.encryption import get_encryption_service
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.cron_job import CronJobRepository
from src.core.repositories.future_task import FutureTaskRepository
from src.core.repositories.settings import SettingsRepository
from src.services.cron_job import CronJobService
from src.services.future_task import FutureTaskService
from src.utils.logger import get_logger, setup_logging

# Load environment variables from .env file
load_dotenv()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown tasks."""
    # Startup
    logger.info("Starting Open Assistant application...")

    try:
        # Initialize database
        config = init_config()

        # Extract database path from URL (handle sqlite:/// prefix)
        db_url = config.database.url
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
        else:
            # For other database types, we'd need SQLAlchemy
            # For now, just use the URL as-is and hope it's a path
            db_path = db_url

        db_manager = DatabaseManager(db_path)

        # Run migrations if needed
        logger.info("Initializing database...")
        db_manager.init_database()
        logger.info("Database initialized successfully")

        # Store database manager in app state
        app.state.db_manager = db_manager

        # Initialize APScheduler for cron jobs with service dependencies
        logger.info("Initializing cron job scheduler...")

        # Create repositories needed for services
        encryption_service = get_encryption_service()
        settings_repo = SettingsRepository(db_manager)
        credentials_repo = CredentialsRepository(db_manager, encryption_service)
        audit_repo = AuditLogRepository(db_manager)

        # Create SettingsService for LLM configuration
        from src.services.settings import SettingsService

        settings_service = SettingsService(settings_repo, credentials_repo, audit_repo)

        # Apply the user's configured timezone to log timestamps now that the
        # settings DB is available (setup_logging ran before this with system local).
        from src.utils.logger import set_log_timezone

        set_log_timezone(settings_service.get_config_with_fallback("user.timezone", "UTC"))

        # Create integration services for cron jobs
        from src.services.google import GoogleService
        from src.services.google_ads import GoogleAdsService
        from src.services.outlook import OutlookService
        from src.services.notion import NotionService
        from src.services.nextcloud import NextcloudService
        from src.services.whatsapp import WhatsAppService
        from src.services.slack import SlackService
        from src.services.brave import BraveService
        from src.services.browser import BrowserService
        from src.services.google_news import GoogleNewsService
        from src.services.system import SystemService
        from src.services.yahoo_finance import YahooFinanceService
        from src.services.plugin_service import PluginService

        google_service = GoogleService(settings_repo, credentials_repo, audit_repo)
        google_ads_service = GoogleAdsService(settings_repo, credentials_repo, audit_repo)
        outlook_service = OutlookService(settings_repo, credentials_repo, audit_repo)
        notion_service = NotionService(settings_repo, credentials_repo, audit_repo)
        nextcloud_service = NextcloudService(settings_repo, credentials_repo, audit_repo)
        whatsapp_service = WhatsAppService(settings_repo, credentials_repo, audit_repo)
        slack_service = SlackService(settings_repo, credentials_repo, audit_repo)
        brave_service = BraveService(settings_repo, credentials_repo, audit_repo)
        browser_service = BrowserService(settings_repo, credentials_repo, audit_repo)
        google_news_service = GoogleNewsService(settings_repo, credentials_repo, audit_repo)
        yahoo_finance_service = YahooFinanceService(settings_repo, credentials_repo, audit_repo)

        # Initialize plugin service and register all plugin tools
        plugin_service = PluginService(
            settings_repo, credentials_repo, audit_repo, data_dir=config.general.data_dir
        )
        plugin_service.register_plugin_tools()
        app.state.plugin_service = plugin_service

        # Initialize MCP service and register cached MCP server tools
        from src.agents.registry import AgentRegistry
        from src.services.mcp_service import McpService

        mcp_service = McpService(
            settings_repo,
            credentials_repo,
            audit_repo,
            data_dir=config.general.data_dir,
            agent_registry=AgentRegistry(db_manager),
        )
        mcp_service.register_mcp_tools()
        app.state.mcp_service = mcp_service

        # Create embedding service (shared by search and system services)
        from src.services.embedding import EmbeddingService
        from src.services.search import UnifiedSearchService

        embedding_model = settings_service.get_config_with_fallback(
            "search.embedding_model", "sentence-transformers/all-MiniLM-L6-v2"
        )
        embedding_service = EmbeddingService(model=embedding_model)

        # Create unified search service (must come before SystemService so it can be injected)
        search_service = UnifiedSearchService(
            settings_repo=settings_repo,
            db_manager=db_manager,
            google_service=google_service,
            outlook_service=outlook_service,
            notion_service=notion_service,
            nextcloud_service=nextcloud_service,
            embedding_service=embedding_service,
        )

        system_service = SystemService(
            db_manager=db_manager,
            embedding_service=embedding_service,
            search_service=search_service,
            settings_service=settings_service,
        )

        # Create ToolExecutor for cron jobs and MessageHandler
        from src.core.tools.executor import ToolExecutor

        cron_tool_executor = ToolExecutor(
            google_service=google_service,
            google_ads_service=google_ads_service,
            outlook_service=outlook_service,
            notion_service=notion_service,
            nextcloud_service=nextcloud_service,
            whatsapp_service=whatsapp_service,
            slack_service=slack_service,
            brave_service=brave_service,
            browser_service=browser_service,
            google_news_service=google_news_service,
            yahoo_finance_service=yahoo_finance_service,
            system_service=system_service,
            search_service=search_service,
            cron_job_service=None,  # Will be set after CronJobService creation
            future_task_service=None,  # Will be set after FutureTaskService creation
            audit_repo=audit_repo,
            conversation_id=None,  # No conversation context for cron jobs
            settings_service=settings_service,
            plugin_service=plugin_service,
            mcp_service=mcp_service,
        )

        # Create MessageHandler for new skills-based execution
        from src.core.repositories.skill import SkillRepository
        from src.core.repositories.conversation import ConversationRepository
        from src.core.repositories.message import MessageRepository
        from src.core.repositories.memory import MemoryRepository
        from src.core.repositories.prompts import PromptsRepository
        from src.services.conversation import ConversationService
        from src.services.memory import MemoryService
        from src.services.message_handler import MessageHandler

        skill_repo = SkillRepository(db_manager)
        conversation_repo = ConversationRepository(db_manager)
        message_repo = MessageRepository(db_manager)
        memory_repo = MemoryRepository(db_manager)
        prompts_repo = PromptsRepository(db_manager)

        memory_service = MemoryService(
            message_repo=message_repo,
            memory_repo=memory_repo,
            conversation_repo=conversation_repo,
            prompts_repo=prompts_repo,
            settings_repo=settings_repo,
            db_manager=db_manager,
            llm_client=None,  # Will create on demand
        )

        conversation_service = ConversationService(conversation_repo, message_repo, memory_service)

        message_handler = MessageHandler(
            skill_repo=skill_repo,
            conversation_service=conversation_service,
            memory_service=memory_service,
            settings_service=settings_service,
            tool_executor=cron_tool_executor,
            max_iterations=15,
            max_skills_per_request=5,
        )

        # Create CronJobService with dependencies
        # Note: crew=None for now (legacy CrewAI support removed)
        cron_job_repo = CronJobRepository(db_manager)
        cron_job_service = CronJobService(
            cron_job_repo,
            tool_executor=cron_tool_executor,
            crew=None,  # Legacy CrewAI removed
            message_handler=message_handler,
            whatsapp_service=whatsapp_service,
            slack_service=slack_service,
            settings_service=settings_service,
        )

        # Complete circular reference
        cron_tool_executor.cron_job_service = cron_job_service

        # Ensure the system Outlook token refresh job exists in the database
        # before starting the scheduler, so it gets loaded with all other jobs.
        # This keeps the MSAL refresh token active during idle periods so cron
        # jobs that use Outlook don't fail due to expired credentials.
        _OUTLOOK_REFRESH_JOB_ID = "__system_outlook_token_refresh"
        refresh_hours = int(os.getenv("OUTLOOK_TOKEN_REFRESH_HOURS", "6"))
        refresh_cron = f"0 */{refresh_hours} * * *"

        existing_refresh_job = cron_job_repo.get_job(_OUTLOOK_REFRESH_JOB_ID)
        if not existing_refresh_job:
            cron_job_repo.create_job(
                job_id=_OUTLOOK_REFRESH_JOB_ID,
                name="Outlook Token Refresh",
                cron_expression=refresh_cron,
                job_type="tool",
                description="System job: proactively refreshes Outlook OAuth tokens to prevent "
                "credential expiry during idle periods.",
                tool_name="outlook_refresh_credentials",
                steps=[
                    {
                        "order": 1,
                        "description": "Refresh Outlook OAuth credentials",
                        "tool_name": "outlook_refresh_credentials",
                    }
                ],
            )
            logger.info(
                f"Created system Outlook token refresh job (every {refresh_hours}h): "
                f"{_OUTLOOK_REFRESH_JOB_ID}"
            )
        else:
            logger.info(
                f"System Outlook token refresh job already exists: {_OUTLOOK_REFRESH_JOB_ID}"
            )

        # Ensure the system tmp directory cleanup job exists in the database.
        # Runs nightly at 3:00 AM to remove files older than 24 hours from TMP_DIR.
        _TMP_CLEANUP_JOB_ID = "__system_tmp_cleanup"
        existing_tmp_job = cron_job_repo.get_job(_TMP_CLEANUP_JOB_ID)
        if not existing_tmp_job:
            cron_job_repo.create_job(
                job_id=_TMP_CLEANUP_JOB_ID,
                name="Tmp Directory Cleanup",
                cron_expression="0 3 * * *",
                job_type="tool",
                description="System job: nightly cleanup of temporary files older than 24 hours.",
                tool_name="system_clean_tmp_dir",
                tool_parameters={"max_age_hours": 24},
                steps=[
                    {
                        "order": 1,
                        "description": "Remove temporary files older than 24 hours",
                        "tool_name": "system_clean_tmp_dir",
                        "tool_parameters": {"max_age_hours": 24},
                    }
                ],
            )
            logger.info(f"Created system tmp cleanup job (daily at 03:00): {_TMP_CLEANUP_JOB_ID}")
        else:
            logger.info(f"System tmp cleanup job already exists: {_TMP_CLEANUP_JOB_ID}")

        # Start scheduler (loads all persisted jobs, including the system refresh job)
        cron_job_service.start_scheduler()
        app.state.cron_job_service = cron_job_service
        logger.info("Cron job scheduler initialized with tool executor and MessageHandler")

        # Create FutureTaskService with shared scheduler
        logger.info("Initializing future task service...")
        future_task_repo = FutureTaskRepository(db_manager)
        future_task_service = FutureTaskService(
            future_task_repo,
            scheduler=cron_job_service.scheduler,  # Share scheduler!
            tool_executor=cron_tool_executor,  # Share tool executor
            crew=None,  # Legacy CrewAI removed
            message_handler=message_handler,  # Use MessageHandler instead
            whatsapp_service=whatsapp_service,
            slack_service=slack_service,
        )

        # Complete circular reference for future task service
        cron_tool_executor.future_task_service = future_task_service

        # Load pending tasks into scheduler
        future_task_service.load_pending_tasks()

        # Store in app state for dependency injection
        app.state.future_task_service = future_task_service
        logger.info("Future task service initialized with shared scheduler")

        # Store browser service for cleanup
        app.state.browser_service = browser_service

        # Initialize Slack Socket Mode if app_token is configured
        # Socket Mode allows receiving Slack events without a public HTTP endpoint
        # Use settings_service for sensitive settings (checks both settings and credentials tables)
        slack_app_token = settings_service.get_config_with_fallback("slack.app_token")
        slack_enabled = settings_repo.get("slack.enabled")
        slack_bot_token = settings_service.get_config_with_fallback("slack.bot_token")
        slack_allowed_users = settings_repo.get("slack.allowed_user_ids") or ""

        logger.info(
            f"[Slack] Configuration: enabled={slack_enabled}, "
            f"app_token={'configured' if slack_app_token else 'not set'}, "
            f"bot_token={'configured' if slack_bot_token else 'not set'}, "
            f"allowed_user_ids={'configured' if slack_allowed_users else 'all users allowed'}"
        )

        if slack_enabled and slack_app_token:
            try:
                from src.integrations.slack.socket_mode import SlackSocketModeHandler
                from src.services.mistral_ocr import MistralOCRService
                from src.services.whatsapp_media import MediaHandler

                # Get the event loop to pass to the socket mode handler
                # Use get_event_loop() which works even if the loop isn't currently running
                # in the current context (the socket mode client runs in a background thread)
                event_loop = asyncio.get_event_loop()
                logger.info(f"[Slack] Got event loop: {event_loop}")

                # Create media handler for Slack file processing
                mistral_ocr_service = MistralOCRService(settings_repo, credentials_repo, audit_repo)
                slack_media_handler = MediaHandler(
                    settings_service=settings_service,
                    mistral_ocr_service=mistral_ocr_service,
                    nextcloud_service=nextcloud_service,
                    notion_service=notion_service,
                    channel="Slack",
                )

                socket_handler = SlackSocketModeHandler(
                    app_token=slack_app_token,
                    bot_token=slack_bot_token or "",
                    message_handler=message_handler,
                    slack_service=slack_service,
                    settings_service=settings_service,
                    event_loop=event_loop,
                    media_handler=slack_media_handler,
                )
                socket_handler.start()
                app.state.slack_socket_handler = socket_handler
                logger.info("[Slack] Socket Mode client started successfully")
            except Exception as e:
                logger.error(f"[Slack] Failed to start Socket Mode: {e}", exc_info=True)
                # Don't fail startup if Socket Mode fails
        else:
            logger.info(
                f"[Slack] Socket Mode not started (enabled={slack_enabled}, app_token={'configured' if slack_app_token else 'not configured'})"
            )

        yield

    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise
    finally:
        # Close Slack Socket Mode connection
        if hasattr(app.state, "slack_socket_handler"):
            app.state.slack_socket_handler.close()
        # Close browser session
        if hasattr(app.state, "browser_service"):
            app.state.browser_service.close()
        # Shutdown scheduler
        if hasattr(app.state, "cron_job_service"):
            app.state.cron_job_service.shutdown_scheduler()
        logger.info("Shutting down Open Assistant application...")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Open Assistant API",
        description="AI-powered personal assistant for task automation and integration",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS
    # Get allowed origins from environment variable
    # For production, set CORS_ORIGINS to specific domains, e.g.:
    # CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    app_url = os.getenv("APP_URL", "http://localhost:8080")

    if cors_origins_env:
        # Production: Use specific origins from environment
        allowed_origins = [
            origin.strip() for origin in cors_origins_env.split(",") if origin.strip()
        ]
    else:
        # Development/Default: Allow localhost and APP_URL
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8080",
        ]
        # Add APP_URL if it's different from defaults
        if app_url not in allowed_origins:
            allowed_origins.append(app_url)

    logger.info(f"CORS allowed origins: {allowed_origins}")
    logger.info(f"Application URL: {app_url}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
    )

    # Mount static files
    static_dir = Path(__file__).parent / "ui" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Include API routers
    app.include_router(agents_router)
    app.include_router(artifacts_router)
    app.include_router(artifact_visitor_router)
    app.include_router(auth_router)
    app.include_router(brave_router)
    app.include_router(browser_router)
    app.include_router(chat_router)
    app.include_router(conversations_router)
    app.include_router(cron_jobs_router)
    app.include_router(future_tasks_router)
    app.include_router(google_router)
    app.include_router(google_ads_router)
    app.include_router(google_navigator_router)
    app.include_router(integrations_router)
    app.include_router(monitoring_router)
    app.include_router(nextcloud_router)
    app.include_router(notion_router)
    app.include_router(outlook_router)
    app.include_router(prompts_router)
    app.include_router(pwa_router)
    app.include_router(settings_router)
    app.include_router(skills_router)
    app.include_router(slack_router)
    app.include_router(plugins_router)
    app.include_router(mcp_router)
    app.include_router(google_news_router)
    app.include_router(yahoo_finance_router)
    app.include_router(whatsapp_router)
    app.include_router(whisper_router)
    app.include_router(mistral_ocr_router)

    # Managed mode endpoints (only when MANAGED_API_KEY is configured)
    if _MANAGED_API_KEY:
        from src.api.managed import router as managed_router

        app.include_router(managed_router)
        logger.info("Managed mode enabled: /managed/* endpoints registered")

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        """Health check endpoint for monitoring and Docker health checks."""
        return {
            "status": "healthy",
            "version": __version__,
            "service": "personal-assistant",
        }

    # UI Routes
    @app.get("/")
    async def root():
        """Serve the chat UI."""
        return FileResponse(static_dir / "index.html")

    @app.get("/settings")
    async def settings_page():
        """Serve the settings UI."""
        return FileResponse(static_dir / "settings.html")

    @app.get("/artifacts")
    async def artifacts_page():
        """Serve the artifacts management UI."""
        return FileResponse(static_dir / "artifacts.html")

    @app.get("/monitoring")
    async def monitoring_page():
        """Serve the monitoring UI."""
        return FileResponse(static_dir / "monitoring.html")

    @app.get("/service-worker.js")
    async def service_worker():
        """Serve the service worker from root for PWA."""
        return FileResponse(
            static_dir / "service-worker.js",
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    return app


def main() -> None:
    """Main entry point for running the application."""
    # Initialize configuration
    config = init_config()

    # Get logging configuration from environment
    log_rotation_days = int(os.getenv("LOG_ROTATION_DAYS", "30"))
    log_rotation_when = os.getenv("LOG_ROTATION_WHEN", "midnight")

    # Setup logging with daily rotation
    setup_logging(
        log_level=config.general.log_level,
        log_dir="logs",
        log_file="assistant.log",
        when=log_rotation_when,
        backup_count=log_rotation_days,
    )

    logger.info(f"Starting Open Assistant v{__version__}")
    logger.info(f"Environment: {config.general.environment}")
    logger.info(f"Log level: {config.general.log_level}")
    logger.info(f"Log rotation: daily at {log_rotation_when}, keeping {log_rotation_days} days")

    # Create and run application
    app = create_app()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_config=None,  # Use our custom logging
    )


if __name__ == "__main__":
    main()
