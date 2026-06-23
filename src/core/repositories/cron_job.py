"""Repository for cron job persistence."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class CronJobRepository(BaseRepository):
    """Repository for managing cron jobs and job executions."""

    def create_job(
        self,
        job_id: str,
        name: str,
        cron_expression: str,
        job_type: str,
        description: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_parameters: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        required_skills: Optional[List[str]] = None,
        delivery_channel: Optional[str] = None,
        delivery_contact_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new cron job.

        Args:
            job_id: Unique job identifier
            name: Human-readable job name
            cron_expression: Cron schedule expression
            job_type: 'tool' or 'prompt'
            description: Optional description
            tool_name: Tool to execute (if job_type='tool')
            tool_parameters: Tool parameters (if job_type='tool')
            prompt: Prompt for coordinator (if job_type='prompt')
            delivery_channel: 'whatsapp' or 'slack' to deliver output to user
            delivery_contact_identifier: Phone number or channel ID (optional, resolved
                from settings when omitted)

        Returns:
            Created job record
        """
        now = datetime.utcnow().isoformat()
        data = {
            "job_id": job_id,
            "name": name,
            "description": description,
            "cron_expression": cron_expression,
            "job_type": job_type,
            "tool_name": tool_name,
            "tool_parameters": json.dumps(tool_parameters) if tool_parameters else None,
            "prompt": prompt,
            "steps": json.dumps(steps) if steps is not None else None,
            "required_skills": json.dumps(required_skills) if required_skills else None,
            "enabled": 1,
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "next_run_at": None,
            "delivery_channel": delivery_channel,
            "delivery_contact_identifier": delivery_contact_identifier,
        }

        self.insert("cron_jobs", data)
        logger.info(f"Created cron job {job_id}: {name}")

        data["tool_parameters"] = tool_parameters
        data["steps"] = steps
        data["required_skills"] = required_skills
        data["enabled"] = True
        return data

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a cron job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job record or None
        """
        row = self.fetch_one(
            """
            SELECT job_id, name, description, cron_expression, job_type,
                   tool_name, tool_parameters, prompt, steps, required_skills,
                   enabled, created_at, updated_at, last_run_at, next_run_at,
                   delivery_channel, delivery_contact_identifier
            FROM cron_jobs WHERE job_id = ?
            """,
            (job_id,),
        )

        if not row:
            return None

        return self._parse_job_row(row)

    def list_jobs(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all cron jobs.

        Args:
            enabled_only: If True, only return enabled jobs

        Returns:
            List of job records
        """
        query = """
            SELECT job_id, name, description, cron_expression, job_type,
                   tool_name, tool_parameters, prompt, steps, required_skills,
                   enabled, created_at, updated_at, last_run_at, next_run_at,
                   delivery_channel, delivery_contact_identifier
            FROM cron_jobs
        """
        params = None

        if enabled_only:
            query += " WHERE enabled = 1"

        query += " ORDER BY created_at DESC"

        rows = self.fetch_all(query, params)
        return [self._parse_job_row(row) for row in rows]

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a cron job.

        Args:
            job_id: Job identifier
            updates: Dictionary of fields to update

        Returns:
            True if updated, False if not found
        """
        if "tool_parameters" in updates and updates["tool_parameters"] is not None:
            updates["tool_parameters"] = json.dumps(updates["tool_parameters"])
        if "steps" in updates and updates["steps"] is not None:
            updates["steps"] = json.dumps(updates["steps"])
        if "required_skills" in updates and updates["required_skills"] is not None:
            updates["required_skills"] = json.dumps(updates["required_skills"])

        updates["updated_at"] = datetime.utcnow().isoformat()

        affected = self.update("cron_jobs", updates, "job_id = ?", (job_id,))
        if affected > 0:
            logger.info(f"Updated cron job {job_id}")
            return True
        return False

    def delete_job(self, job_id: str) -> bool:
        """Delete a cron job.

        Args:
            job_id: Job identifier

        Returns:
            True if deleted, False if not found
        """
        affected = self.delete("cron_jobs", "job_id = ?", (job_id,))
        if affected > 0:
            logger.info(f"Deleted cron job {job_id}")
            return True
        return False

    def toggle_job(self, job_id: str, enabled: Optional[bool] = None) -> Optional[bool]:
        """Toggle or set the enabled state of a cron job.

        Args:
            job_id: Job identifier
            enabled: If provided, set to this value. If None, toggle current state.

        Returns:
            New enabled state, or None if job not found
        """
        if enabled is None:
            # Toggle: read current state first
            job = self.get_job(job_id)
            if not job:
                return None
            enabled = not job["enabled"]

        self.update(
            "cron_jobs",
            {"enabled": 1 if enabled else 0, "updated_at": datetime.utcnow().isoformat()},
            "job_id = ?",
            (job_id,),
        )
        logger.info(f"Toggled cron job {job_id} to enabled={enabled}")
        return enabled

    def update_last_run(self, job_id: str, last_run_at: str) -> None:
        """Update the last_run_at timestamp for a job.

        Args:
            job_id: Job identifier
            last_run_at: ISO timestamp of last run
        """
        self.update(
            "cron_jobs",
            {"last_run_at": last_run_at, "updated_at": datetime.utcnow().isoformat()},
            "job_id = ?",
            (job_id,),
        )

    def update_next_run(self, job_id: str, next_run_at: Optional[str]) -> None:
        """Update the next_run_at timestamp for a job.

        Args:
            job_id: Job identifier
            next_run_at: ISO timestamp of next run, or None
        """
        self.update(
            "cron_jobs",
            {"next_run_at": next_run_at},
            "job_id = ?",
            (job_id,),
        )

    # --- Job Executions ---

    def create_execution(
        self,
        job_id: str,
        job_type: str = "cron",
        container_id: Optional[str] = None,
    ) -> int:
        """Create a job execution record.

        Args:
            job_id: Job identifier
            job_type: 'cron' or 'future_task'
            container_id: Docker container ID

        Returns:
            Execution row ID
        """
        data = {
            "job_id": job_id,
            "job_type": job_type,
            "started_at": datetime.utcnow().isoformat(),
            "status": "running",
            "container_id": container_id,
        }

        row_id = self.insert("job_executions", data)
        logger.info(f"Created execution record {row_id} for job {job_id}")
        return row_id

    def complete_execution(
        self,
        execution_id: int,
        status: str,
        result: Optional[Any] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Complete a job execution.

        Args:
            execution_id: Execution row ID
            status: 'success' or 'failed'
            result: Execution result
            error_message: Error message if failed
        """
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
        """Get execution history for a job.

        Args:
            job_id: Job identifier
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

    def get_recent_executions(
        self, limit: int = 50, status: Optional[str] = None, job_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent executions across all jobs, with job names.

        Args:
            limit: Maximum number of records
            status: Optional status filter
            job_type: Optional job type filter ('cron' or 'future_task')

        Returns:
            List of execution records with job_name included
        """
        query = """
            SELECT e.id, e.job_id, e.job_type, e.started_at, e.completed_at,
                   e.status, e.result, e.error_message, e.container_id,
                   COALESCE(c.name, f.name, 'Unknown') AS job_name
            FROM job_executions e
            LEFT JOIN cron_jobs c ON e.job_id = c.job_id AND e.job_type = 'cron'
            LEFT JOIN future_tasks f ON e.job_id = f.task_id AND e.job_type = 'future_task'
        """
        conditions: list = []
        params: list = []

        if status:
            conditions.append("e.status = ?")
            params.append(status)

        if job_type:
            conditions.append("e.job_type = ?")
            params.append(job_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY e.started_at DESC LIMIT ?"
        params.append(limit)

        rows = self.fetch_all(query, tuple(params))
        return [self._parse_execution_row(row) for row in rows]

    # --- Execution Locking (for horizontal scaling) ---

    def try_acquire_execution_lock(self, job_id: str, instance_id: str) -> bool:
        """Try to acquire execution lock for a job.

        This enables horizontal scaling by preventing multiple instances
        from executing the same job simultaneously.

        Args:
            job_id: Job identifier
            instance_id: Instance identifier (typically HOSTNAME or INSTANCE_ID env var)

        Returns:
            True if lock acquired, False if another instance has it

        Note:
            Automatically releases locks older than 5 minutes (stale lock cleanup)
        """
        cursor = self.execute_query(
            """
            UPDATE cron_jobs
            SET
                execution_lock_instance = ?,
                execution_lock_acquired_at = ?
            WHERE
                job_id = ?
                AND (
                    execution_lock_instance IS NULL
                    OR execution_lock_acquired_at < datetime('now', '-5 minutes')
                )
            """,
            (instance_id, datetime.utcnow().isoformat(), job_id),
            commit=True,
        )

        affected = cursor.rowcount

        logger.debug(
            f"Lock acquisition for job {job_id} by {instance_id}: "
            f"{'SUCCESS' if affected > 0 else 'FAILED'}"
        )

        return affected > 0

    def release_execution_lock(self, job_id: str, instance_id: str) -> None:
        """Release execution lock for a job.

        Args:
            job_id: Job identifier
            instance_id: Instance identifier
        """
        self.execute_query(
            """
            UPDATE cron_jobs
            SET
                execution_lock_instance = NULL,
                execution_lock_acquired_at = NULL
            WHERE
                job_id = ?
                AND execution_lock_instance = ?
            """,
            (job_id, instance_id),
            commit=True,
        )
        logger.debug(f"Released lock for job {job_id} by {instance_id}")

    # --- Helpers ---

    def _parse_job_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a job row from database, deserializing JSON fields."""
        result = dict(row)
        if result.get("tool_parameters"):
            try:
                result["tool_parameters"] = json.loads(result["tool_parameters"])
            except (json.JSONDecodeError, TypeError):
                result["tool_parameters"] = None
        if result.get("steps"):
            try:
                parsed = json.loads(result["steps"])
                # Guard against double-encoding (parsed is still a string)
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)
                result["steps"] = parsed
            except (json.JSONDecodeError, TypeError):
                result["steps"] = None
        if result.get("required_skills"):
            try:
                result["required_skills"] = json.loads(result["required_skills"])
            except (json.JSONDecodeError, TypeError):
                result["required_skills"] = None
        result["enabled"] = bool(result.get("enabled", 0))
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
