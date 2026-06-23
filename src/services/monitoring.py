"""Monitoring service for system health, metrics, and logs."""

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.message import MessageRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MonitoringService:
    """Service for system monitoring, health checks, and metrics."""

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: AuditLogRepository,
    ):
        """
        Initialize monitoring service.

        Args:
            conversation_repo: Conversation repository
            message_repo: Message repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository
        """
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.credentials_repo = credentials_repo
        self.audit_repo = audit_repo

    def get_system_health(self) -> Dict[str, Any]:
        """
        Get overall system health status.

        Returns:
            Dictionary with health status for each component
        """
        health_checks = {
            "database": self._check_database_health(),
            "llm_api": self._check_llm_health(),
            "disk_space": self._check_disk_space(),
        }

        # Determine overall status
        statuses = [check["status"] for check in health_checks.values()]

        if all(s == "healthy" for s in statuses):
            overall_status = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            overall_status = "unhealthy"
        else:
            overall_status = "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": health_checks,
        }

    def _check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and performance."""
        try:
            # Try a simple query
            start = datetime.utcnow()
            count = self.conversation_repo.count_conversations()
            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000

            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "message": f"Database operational ({count} conversations)",
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "latency_ms": None,
                "message": f"Database error: {str(e)}",
            }

    def _check_llm_health(self) -> Dict[str, Any]:
        """Check LLM API availability."""
        # Check if API key is configured - check credentials repo first
        try:
            # Check if LLM credentials exist in database
            llm_creds_metadata = self.credentials_repo.get_metadata("llm")

            if llm_creds_metadata:
                # Credentials exist in database
                return {"status": "healthy", "message": "LLM API configured (database)"}

            # Fallback to environment variable
            api_key = os.getenv("LLM_API_KEY")
            if api_key:
                return {"status": "healthy", "message": "LLM API configured (environment)"}

            return {"status": "unhealthy", "message": "LLM API key not configured"}
        except Exception as e:
            logger.error(f"LLM health check failed: {e}")
            return {"status": "unhealthy", "message": f"Error checking LLM config: {str(e)}"}

    def _check_disk_space(self) -> Dict[str, Any]:
        """Check available disk space."""
        try:
            # Get data directory
            data_dir = os.getenv("DATA_DIR", "data")
            path = Path(data_dir)

            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)

            # Get disk usage
            stat = os.statvfs(path)
            free_bytes = stat.f_bavail * stat.f_frsize
            free_gb = free_bytes / (1024**3)

            status = "healthy" if free_gb > 1 else "degraded" if free_gb > 0.1 else "unhealthy"

            return {
                "status": status,
                "free_gb": round(free_gb, 2),
                "message": f"{free_gb:.2f} GB free",
            }
        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return {
                "status": "unknown",
                "free_gb": None,
                "message": f"Error checking disk space: {str(e)}",
            }

    def get_api_metrics(self, since: Optional[str] = None) -> Dict[str, Any]:
        """
        Get API usage metrics.

        Args:
            since: Optional timestamp to calculate metrics from

        Returns:
            Dictionary with API metrics
        """
        if since is None:
            # Default to last 24 hours
            since = (datetime.utcnow() - timedelta(hours=24)).isoformat()

        # Get API call counts
        total_calls = self.audit_repo.count_events("api_call", since)
        error_calls = self.audit_repo.count_events("api_call", since, success=False)

        # Get conversation stats
        # Note: This is a simplification - ideally we'd track these in audit logs
        total_conversations = self.conversation_repo.count_conversations()

        return {
            "api_calls": {
                "total": total_calls,
                "success": total_calls - error_calls,  # Approximate
                "error": error_calls,
                "success_rate": (
                    round((total_calls - error_calls) / total_calls, 2) if total_calls > 0 else 1.0
                ),
            },
            "conversations": {"total": total_conversations, "active_since": since},
            "period": {"since": since, "until": datetime.utcnow().isoformat()},
        }

    def get_recent_logs(
        self, limit: int = 100, level: Optional[str] = None, since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent log entries from application log file.

        Args:
            limit: Maximum number of entries
            level: Filter by level (ERROR, WARNING, INFO)
            since: Optional timestamp to filter from

        Returns:
            List of log entries
        """
        logs = []

        try:
            # Get log file path
            log_dir = os.getenv("LOG_DIR", "logs")
            log_file = Path(log_dir) / "assistant.log"

            if not log_file.exists():
                logger.warning(f"Log file not found: {log_file}")
                return []

            # Read last N lines from log file
            # This is more efficient than reading the entire file
            result = subprocess.run(
                ["tail", "-n", str(limit * 2), str(log_file)],
                capture_output=True,
                text=True,
                check=True,
            )

            lines = result.stdout.strip().split("\n")

            # Parse log lines (format: timestamp - level - logger - message)
            for line in reversed(lines):  # Reverse to get newest first
                if not line.strip():
                    continue

                try:
                    # Parse log format: "2024-01-01 12:00:00,123 - INFO - module - message"
                    parts = line.split(" - ", 3)
                    if len(parts) >= 4:
                        timestamp_str, log_level, module, message = parts

                        # Filter by level if specified
                        if level and log_level != level:
                            continue

                        # Determine success based on log level
                        success = log_level not in ["ERROR", "CRITICAL"]

                        logs.append(
                            {
                                "timestamp": timestamp_str.replace(",", "."),
                                "event_type": log_level,
                                "action": f"[{module}] {message}",
                                "success": success,
                                "service_name": module.split(".")[0] if "." in module else None,
                            }
                        )

                        if len(logs) >= limit:
                            break
                except Exception as e:
                    # Skip malformed lines
                    logger.debug(f"Failed to parse log line: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return []

        return logs

    def get_connection_statuses(self) -> List[Dict[str, Any]]:
        """
        Get connection status for all integrations.

        Returns:
            List of connection status dictionaries
        """
        from src.services.settings import SettingsService
        from src.core.database import DatabaseManager
        from src.core.repositories.settings import SettingsRepository

        services = ["google", "outlook", "notion", "nextcloud", "whatsapp", "llm"]

        statuses = []

        # Initialize settings service for connection tests
        db_manager = DatabaseManager()
        settings_repo = SettingsRepository(db_manager)
        settings_service = SettingsService(settings_repo, self.credentials_repo)

        for service in services:
            # Check if credentials exist
            creds_metadata = self.credentials_repo.get_metadata(service)

            if not creds_metadata:
                status = {
                    "service_name": service,
                    "status": "not_configured",
                    "last_check": datetime.utcnow().isoformat(),
                    "message": "No credentials configured",
                }
            else:
                # Check if expired
                is_expired = self.credentials_repo.is_expired(service)

                if is_expired:
                    status = {
                        "service_name": service,
                        "status": "expired",
                        "last_check": datetime.utcnow().isoformat(),
                        "message": "Credentials expired",
                    }
                else:
                    # Perform actual connection test using service-specific implementations
                    test_result = self._test_service_connection(service, settings_repo)
                    status = {
                        "service_name": service,
                        "status": test_result.get("status", "unknown"),
                        "last_check": datetime.utcnow().isoformat(),
                        "message": test_result.get("message", "Connection test completed"),
                    }

            statuses.append(status)

        return statuses

    def _test_service_connection(self, service: str, settings_repo) -> Dict[str, Any]:
        """
        Test connection using service-specific implementation.

        Args:
            service: Service name
            settings_repo: Settings repository

        Returns:
            Test result dictionary
        """
        try:
            # Import service-specific classes and test
            if service == "google":
                from src.services.google import GoogleService

                google_service = GoogleService(settings_repo, self.credentials_repo)
                return google_service.test_connection()

            elif service == "outlook":
                from src.services.outlook import OutlookService

                outlook_service = OutlookService(settings_repo, self.credentials_repo)
                return outlook_service.test_connection()

            elif service == "notion":
                from src.services.notion import NotionService

                notion_service = NotionService(settings_repo, self.credentials_repo)
                return notion_service.test_connection()

            elif service == "nextcloud":
                from src.services.nextcloud import NextcloudService

                nextcloud_service = NextcloudService(settings_repo, self.credentials_repo)
                return nextcloud_service.test_connection()

            elif service == "whatsapp":
                from src.services.whatsapp import WhatsAppService

                whatsapp_service = WhatsAppService(settings_repo, self.credentials_repo)
                return whatsapp_service.test_connection()

            elif service == "llm":
                from src.services.settings import SettingsService

                settings_service = SettingsService(settings_repo, self.credentials_repo)
                return settings_service.test_connection(service)

            else:
                return {
                    "service_name": service,
                    "status": "error",
                    "message": f"Unknown service: {service}",
                }

        except Exception as e:
            logger.error(f"Failed to test {service} connection: {e}")
            return {"service_name": service, "status": "error", "message": f"Test failed: {str(e)}"}

    def get_conversation_stats(self) -> Dict[str, Any]:
        """
        Get conversation and message statistics.

        Returns:
            Dictionary with statistics
        """
        # Count conversations
        total_conversations = self.conversation_repo.count_conversations()

        # Count by channel
        webui_conversations = self.conversation_repo.count_conversations("webui")
        whatsapp_conversations = self.conversation_repo.count_conversations("whatsapp")

        # Get recent conversations (last 24 hours)
        since = (datetime.utcnow() - timedelta(hours=24)).isoformat()

        # Note: This is a simplification - ideally we'd have efficient queries for this
        all_conversations = self.conversation_repo.list_conversations(limit=1000)
        recent_conversations = [c for c in all_conversations if c["updated_at"] >= since]

        return {
            "total_conversations": total_conversations,
            "by_channel": {"webui": webui_conversations, "whatsapp": whatsapp_conversations},
            "active_last_24h": len(recent_conversations),
        }

    def get_system_info(self) -> Dict[str, Any]:
        """
        Get system information.

        Returns:
            Dictionary with system info
        """
        return {
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "platform": os.sys.platform,
            "database_url": os.getenv("DATABASE_URL", "sqlite:///data/assistant.db"),
            "environment": os.getenv("ENVIRONMENT", "development"),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        }
