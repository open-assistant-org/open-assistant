"""Repository for agent task persistence."""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from src.core.database import DatabaseManager

logger = logging.getLogger(__name__)


class AgentTaskRepository:
    """Repository for managing agent task records."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize repository with database manager.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager

    def create_task(
        self,
        task_id: str,
        conversation_id: str,
        agent_name: str,
        action: str,
        parameters: Dict[str, Any],
        status: str = "pending",
    ) -> Dict[str, Any]:
        """Create a new agent task record.

        Args:
            task_id: Unique task identifier
            conversation_id: Associated conversation ID
            agent_name: Name of agent handling the task
            action: Action to be performed
            parameters: Task parameters as dict
            status: Initial status (default: 'pending')

        Returns:
            Created task record
        """
        now = datetime.utcnow()

        task = {
            "task_id": task_id,
            "conversation_id": conversation_id,
            "agent_name": agent_name,
            "action": action,
            "parameters": json.dumps(parameters),
            "status": status,
            "result": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "started_at": None,
            "completed_at": None,
        }

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_tasks (
                    task_id, conversation_id, agent_name, action, parameters,
                    status, result, error_message, created_at, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task["task_id"],
                    task["conversation_id"],
                    task["agent_name"],
                    task["action"],
                    task["parameters"],
                    task["status"],
                    task["result"],
                    task["error_message"],
                    task["created_at"],
                    task["started_at"],
                    task["completed_at"],
                ),
            )
            conn.commit()

        logger.info(f"Created task {task_id} with status {status}")
        return task

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task record dict or None if not found
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT task_id, conversation_id, agent_name, action, parameters,
                       status, result, error_message, created_at, started_at, completed_at
                FROM agent_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            return {
                "task_id": row[0],
                "conversation_id": row[1],
                "agent_name": row[2],
                "action": row[3],
                "parameters": json.loads(row[4]) if row[4] else {},
                "status": row[5],
                "result": json.loads(row[6]) if row[6] else None,
                "error_message": row[7],
                "created_at": row[8],
                "started_at": row[9],
                "completed_at": row[10],
            }

    def update_task_status(
        self,
        task_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update task status and optional fields.

        Args:
            task_id: Task identifier
            status: New status ('pending', 'running', 'completed', 'failed')
            started_at: Task start timestamp (optional)
            completed_at: Task completion timestamp (optional)
            result: Task result as dict (optional)
            error_message: Error message if failed (optional)

        Returns:
            True if task was updated, False if not found
        """
        update_fields = ["status = ?"]
        params = [status]

        if started_at:
            update_fields.append("started_at = ?")
            params.append(started_at.isoformat())

        if completed_at:
            update_fields.append("completed_at = ?")
            params.append(completed_at.isoformat())

        if result is not None:
            update_fields.append("result = ?")
            params.append(json.dumps(result))

        if error_message is not None:
            update_fields.append("error_message = ?")
            params.append(error_message)

        params.append(task_id)

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = f"UPDATE agent_tasks SET {', '.join(update_fields)} WHERE task_id = ?"
            cursor.execute(query, params)
            conn.commit()
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Updated task {task_id} to status {status}")
        else:
            logger.warning(f"Task {task_id} not found for update")

        return updated

    def get_conversation_tasks(
        self, conversation_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get all tasks for a conversation.

        Args:
            conversation_id: Conversation identifier
            limit: Maximum number of tasks to return (optional)

        Returns:
            List of task records, ordered by creation time (newest first)
        """
        query = """
            SELECT task_id, conversation_id, agent_name, action, parameters,
                   status, result, error_message, created_at, started_at, completed_at
            FROM agent_tasks
            WHERE conversation_id = ?
            ORDER BY created_at DESC
        """

        params = [conversation_id]
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            tasks = []
            for row in rows:
                tasks.append(
                    {
                        "task_id": row[0],
                        "conversation_id": row[1],
                        "agent_name": row[2],
                        "action": row[3],
                        "parameters": json.loads(row[4]) if row[4] else {},
                        "status": row[5],
                        "result": json.loads(row[6]) if row[6] else None,
                        "error_message": row[7],
                        "created_at": row[8],
                        "started_at": row[9],
                        "completed_at": row[10],
                    }
                )

            return tasks
