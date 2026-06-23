"""Base service class with audit logging for external requests."""

from typing import Any, Dict, Optional
from datetime import datetime

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.settings import SettingsRepository
from src.core.repositories.credentials import CredentialsRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseService:
    """Base class for integration services with audit logging."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        """
        Initialize base service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository (optional)
        """
        self.settings_repo = settings_repo
        self.credentials_repo = credentials_repo
        self.audit_repo = audit_repo

    def _log_web_request(
        self,
        service_name: str,
        action: str,
        endpoint: str,
        method: str = "GET",
        success: bool = True,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        """
        Log an outgoing web request to external service.

        This method logs all HTTP requests made to external APIs for audit purposes.

        Args:
            service_name: Name of the external service (e.g., "google", "outlook")
            action: Description of the action (e.g., "read_emails", "send_email")
            endpoint: API endpoint URL or path
            method: HTTP method (GET, POST, etc.)
            success: Whether the request succeeded
            request_data: Request payload (sensitive data will be sanitized)
            response_data: Response data summary (not full response body)
            error_message: Error message if request failed
            conversation_id: Optional conversation ID for tracking
        """
        if not self.audit_repo:
            # If no audit repo provided, just log to application logs
            logger.info(
                f"Web request: {service_name}.{action} - {method} {endpoint} - "
                f"Success: {success}"
            )
            return

        # Sanitize sensitive data from request
        sanitized_request = self._sanitize_request_data(request_data) if request_data else None

        # Prepare details
        details = {
            "endpoint": endpoint,
            "method": method,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if sanitized_request:
            details["request"] = sanitized_request

        if response_data:
            details["response_summary"] = response_data

        # Log the event
        try:
            self.audit_repo.log_event(
                event_type="web_request",
                action=action,
                success=success,
                service_name=service_name,
                conversation_id=conversation_id,
                details=details,
                error_message=error_message,
            )
        except Exception as e:
            # Don't let audit logging failures break the service
            logger.error(f"Failed to log web request to audit: {e}")

    def _sanitize_request_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize request data to remove sensitive information.

        Args:
            data: Original request data

        Returns:
            Sanitized request data
        """
        if not data:
            return {}

        # Fields to exclude from audit logs
        sensitive_fields = {
            "password",
            "token",
            "secret",
            "api_key",
            "apikey",
            "authorization",
            "auth",
            "credentials",
            "credential",
            "private_key",
            "privatekey",
            "access_token",
            "refresh_token",
        }

        sanitized = {}
        for key, value in data.items():
            # Check if key contains sensitive terms
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_request_data(value)
            elif isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, list):
                # Sanitize list items
                sanitized[key] = [
                    self._sanitize_request_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                # For other types, just include type name
                sanitized[key] = f"<{type(value).__name__}>"

        return sanitized
