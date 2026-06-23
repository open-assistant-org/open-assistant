"""Repository for audit log operations."""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AuditLogRepository(BaseRepository):
    """Repository for managing audit logs."""

    def log_event(
        self,
        event_type: str,
        action: str,
        success: bool = True,
        service_name: Optional[str] = None,
        agent_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> int:
        """
        Log an audit event.

        Args:
            event_type: Event type (api_call, credential_access, etc.)
            action: Action performed
            success: Whether the action succeeded
            service_name: Service name (optional)
            agent_name: Agent name (optional)
            conversation_id: Conversation ID (optional)
            details: Additional details (optional)
            error_message: Error message if failed (optional)

        Returns:
            Inserted row ID
        """
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "service_name": service_name,
            "agent_name": agent_name,
            "action": action,
            "conversation_id": conversation_id,
            "details": json.dumps(details) if details else None,
            "success": success,
            "error_message": error_message,
        }

        return self.insert("audit_log", data)

    def get_recent(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        service_name: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent audit log entries.

        Args:
            limit: Maximum number of entries
            event_type: Filter by event type (optional)
            service_name: Filter by service name (optional)
            success: Filter by success status (optional)

        Returns:
            List of audit log entries
        """
        conditions = []
        params = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        if service_name:
            conditions.append("service_name = ?")
            params.append(service_name)

        if success is not None:
            conditions.append("success = ?")
            params.append(success)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT * FROM audit_log
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        results = self.fetch_all(query, tuple(params))

        for result in results:
            if result.get("details"):
                result["details"] = json.loads(result["details"])

        return results

    def get_by_conversation(self, conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get audit logs for a specific conversation.

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of entries

        Returns:
            List of audit log entries
        """
        query = """
            SELECT * FROM audit_log
            WHERE conversation_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """

        results = self.fetch_all(query, (conversation_id, limit))

        for result in results:
            if result.get("details"):
                result["details"] = json.loads(result["details"])

        return results

    def get_error_logs(self, since: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get error logs.

        Args:
            since: Optional timestamp to filter from (ISO format)
            limit: Maximum number of entries

        Returns:
            List of error log entries
        """
        if since:
            query = """
                SELECT * FROM audit_log
                WHERE success = 0 AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (since, limit)
        else:
            query = """
                SELECT * FROM audit_log
                WHERE success = 0
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (limit,)

        results = self.fetch_all(query, params)

        for result in results:
            if result.get("details"):
                result["details"] = json.loads(result["details"])

        return results

    def count_events(
        self,
        event_type: Optional[str] = None,
        since: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> int:
        """
        Count audit log events.

        Args:
            event_type: Filter by event type (optional)
            since: Count events since timestamp (ISO format, optional)
            success: Filter by success status (optional)

        Returns:
            Event count
        """
        conditions = []
        params = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        if since:
            conditions.append("timestamp >= ?")
            params.append(since)

        if success is not None:
            conditions.append("success = ?")
            params.append(success)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT COUNT(*) FROM audit_log WHERE {where_clause}"

        return self.fetch_scalar(query, tuple(params) if params else None) or 0

    def cleanup_old(self, days: int = 30) -> int:
        """
        Delete audit logs older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of deleted entries
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        affected = self.delete("audit_log", "timestamp < ?", (cutoff_date,))

        if affected > 0:
            logger.info(f"Cleaned up {affected} old audit log entries")

        return affected
