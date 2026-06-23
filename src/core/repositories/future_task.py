"""Repository for future task persistence."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class FutureTaskRepository(BaseRepository):
    """Repository for managing one-time scheduled tasks."""

    def create_task(
        self,
        task_id: str,
        name: str,
        scheduled_time: str,
        job_type: str,
        description: Optional[str] = None,
        conversation_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_parameters: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        delivery_channel: Optional[str] = None,
        delivery_contact_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new future task.

        Args:
            task_id: Unique task identifier
            name: Human-readable task name
            scheduled_time: ISO 8601 timestamp when task should execute
            job_type: 'tool' or 'prompt'
            description: Optional description
            conversation_id: Conversation context ID
            tool_name: Tool to execute (if job_type='tool')
            tool_parameters: Tool parameters (if job_type='tool')
            prompt: Prompt for coordinator (if job_type='prompt')
            delivery_channel: 'whatsapp' or 'slack' to deliver output to user
            delivery_contact_identifier: Phone number or channel ID (optional, resolved
                from settings when omitted)

        Returns:
            Created task record
        """
        # Validate conversation_id exists if provided
        validated_conversation_id = None
        if conversation_id:
            # Check if conversation exists
            conv_row = self.fetch_one(
                "SELECT conversation_id FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            if conv_row:
                validated_conversation_id = conversation_id
            else:
                logger.warning(
                    f"Conversation {conversation_id} not found, creating task without conversation link"
                )

        now = datetime.utcnow().isoformat()
        data = {
            "task_id": task_id,
            "name": name,
            "description": description,
            "conversation_id": validated_conversation_id,
            "scheduled_time": scheduled_time,
            "job_type": job_type,
            "tool_name": tool_name,
            "tool_parameters": json.dumps(tool_parameters) if tool_parameters else None,
            "prompt": prompt,
            "status": "pending",
            "created_at": now,
            "delivery_channel": delivery_channel,
            "delivery_contact_identifier": delivery_contact_identifier,
        }

        self.insert("future_tasks", data)
        logger.info(f"Created future task {task_id}: {name} scheduled for {scheduled_time}")

        # Return with parsed tool_parameters
        data["tool_parameters"] = tool_parameters
        return data

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a future task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task record or None
        """
        row = self.fetch_one(
            """
            SELECT task_id, name, description, conversation_id, scheduled_time,
                   job_type, tool_name, tool_parameters, prompt,
                   status, result, error_message, created_at, completed_at,
                   delivery_channel, delivery_contact_identifier
            FROM future_tasks WHERE task_id = ?
            """,
            (task_id,),
        )

        if not row:
            return None

        return self._parse_task_row(row)

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List future tasks with optional status filter.

        Pending tasks are always returned in full. Completed/failed/cancelled
        tasks are limited to those finished within the past 24 hours so the
        list does not grow unbounded with historical noise.

        Args:
            status: Filter by status ('pending', 'completed', 'failed', 'cancelled', 'all')
                   If None or 'all', returns all pending tasks plus recently
                   finished ones.

        Returns:
            List of task records
        """
        from datetime import timedelta

        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

        query = """
            SELECT task_id, name, description, conversation_id, scheduled_time,
                   job_type, tool_name, tool_parameters, prompt,
                   status, result, error_message, created_at, completed_at,
                   delivery_channel, delivery_contact_identifier
            FROM future_tasks
        """
        params: tuple = ()

        if status and status != "all":
            if status == "pending":
                query += " WHERE status = ?"
                params = (status,)
            else:
                query += " WHERE status = ? AND completed_at >= ?"
                params = (status, cutoff)
        else:
            query += " WHERE status = 'pending' OR completed_at >= ?"
            params = (cutoff,)

        query += " ORDER BY scheduled_time DESC"

        rows = self.fetch_all(query, params if params else None)
        return [self._parse_task_row(row) for row in rows]

    def update_status(
        self,
        task_id: str,
        status: str,
        completed_at: Optional[str] = None,
        result: Optional[Any] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update task status and completion details.

        Args:
            task_id: Task identifier
            status: New status ('completed', 'failed', 'cancelled')
            completed_at: ISO timestamp of completion
            result: Task execution result
            error_message: Error message if failed

        Returns:
            True if updated, False if not found
        """
        updates = {"status": status}

        if completed_at:
            updates["completed_at"] = completed_at

        if result is not None:
            updates["result"] = json.dumps(result)

        if error_message is not None:
            updates["error_message"] = error_message

        affected = self.update("future_tasks", updates, "task_id = ?", (task_id,))
        if affected > 0:
            logger.info(f"Updated future task {task_id} status to {status}")
            return True
        return False

    def delete_task(self, task_id: str) -> bool:
        """Delete a future task.

        Args:
            task_id: Task identifier

        Returns:
            True if deleted, False if not found
        """
        affected = self.delete("future_tasks", "task_id = ?", (task_id,))
        if affected > 0:
            logger.info(f"Deleted future task {task_id}")
            return True
        return False

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks with status='pending' for scheduler loading.

        Returns:
            List of pending task records
        """
        rows = self.fetch_all(
            """
            SELECT task_id, name, description, conversation_id, scheduled_time,
                   job_type, tool_name, tool_parameters, prompt,
                   status, result, error_message, created_at, completed_at,
                   delivery_channel, delivery_contact_identifier
            FROM future_tasks
            WHERE status = 'pending'
            ORDER BY scheduled_time ASC
            """,
        )
        return [self._parse_task_row(row) for row in rows]

    def get_missed_tasks(self) -> List[Dict[str, Any]]:
        """Get tasks where scheduled_time < now() AND status='pending'.

        These are tasks that should have run but didn't (e.g., app was down).

        Returns:
            List of missed task records
        """
        now = datetime.utcnow().isoformat()
        rows = self.fetch_all(
            """
            SELECT task_id, name, description, conversation_id, scheduled_time,
                   job_type, tool_name, tool_parameters, prompt,
                   status, result, error_message, created_at, completed_at,
                   delivery_channel, delivery_contact_identifier
            FROM future_tasks
            WHERE status = 'pending' AND scheduled_time < ?
            ORDER BY scheduled_time ASC
            """,
            (now,),
        )
        return [self._parse_task_row(row) for row in rows]

    # --- Execution Tracking (shared job_executions table) ---

    def create_execution(
        self,
        job_id: str,
        job_type: str = "future_task",
        container_id: Optional[str] = None,
    ) -> int:
        """Create a job execution record in shared job_executions table.

        Args:
            job_id: Task identifier
            job_type: 'future_task' (always for this repository)
            container_id: Docker container ID (optional)

        Returns:
            Execution row ID
        """
        from datetime import datetime

        data = {
            "job_id": job_id,
            "job_type": job_type,
            "started_at": datetime.utcnow().isoformat(),
            "status": "running",
            "container_id": container_id,
        }

        row_id = self.insert("job_executions", data)
        logger.info(f"Created execution record {row_id} for task {job_id}")
        return row_id

    def complete_execution(
        self,
        execution_id: int,
        status: str,
        result: Optional[Any] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Complete a job execution record.

        Args:
            execution_id: Execution row ID
            status: 'success' or 'failed'
            result: Execution result
            error_message: Error message if failed
        """
        from datetime import datetime

        data = {
            "completed_at": datetime.utcnow().isoformat(),
            "status": status,
        }
        if result is not None:
            data["result"] = json.dumps(result)
        if error_message is not None:
            data["error_message"] = error_message

        self.update("job_executions", data, "id = ?", (execution_id,))
        logger.info(f"Completed execution {execution_id} with status {status}")

    def get_job_executions(self, job_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get execution history for a task from shared job_executions table.

        Args:
            job_id: Task identifier
            limit: Maximum number of records

        Returns:
            List of execution records
        """
        rows = self.fetch_all(
            """
            SELECT id, job_id, job_type, started_at, completed_at,
                   status, result, error_message, container_id
            FROM job_executions
            WHERE job_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (job_id, limit),
        )

        return [self._parse_execution_row(row) for row in rows]

    # --- Helpers ---

    def _parse_task_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a task row from database, deserializing JSON fields."""
        result = dict(row)
        if result.get("tool_parameters"):
            try:
                result["tool_parameters"] = json.loads(result["tool_parameters"])
            except (json.JSONDecodeError, TypeError):
                result["tool_parameters"] = None
        if result.get("result"):
            try:
                result["result"] = json.loads(result["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        return result

    def _parse_execution_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Parse an execution row from database, deserializing JSON fields."""
        result = dict(row)
        if result.get("result"):
            try:
                result["result"] = json.loads(result["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        return result
