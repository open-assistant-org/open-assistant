"""Async task dispatcher for parallel sub-task execution.

The ``AsyncTaskDispatcher`` lets the main conversation handler spawn
independent sub-tasks that run concurrently.  Each dispatched task
receives its own ``handle_message`` call, giving it full access to
skill selection, planning, and tool execution.

Typical flow
------------
1. Main handler calls ``dispatch(description, context, skill)`` → returns *task_id*.
2. A background asyncio.Task runs ``handle_message`` for the description.
   If *skill* is provided, the sub-task is pinned to that specialist's
   context-prompt and tool set, bypassing keyword-based skill selection.
3. The caller uses ``wait_for_tasks`` (LLM tool) to block until all
   dispatched tasks finish, then retrieves their results.
4. The main loop refuses to return a final response while any sub-tasks
   are still running, guaranteeing no tasks are left unmonitored.
5. Each sub-task is persisted to the ``agent_tasks`` table via the
   optional ``AgentTaskRepository`` so state survives restarts and is
   visible in the admin UI.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AsyncTask:
    """Represents a single dispatched background task."""

    task_id: str
    description: str
    skill: Optional[str] = None  # pinned specialist skill name, if any
    status: str = "running"  # running | completed | failed
    result: str = ""
    error: str = ""
    tools_executed: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    # The underlying asyncio.Task — used by wait_for(); excluded from dict output.
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task state for returning to the LLM."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status,
            **({"skill": self.skill} if self.skill else {}),
            # Only include result / error when relevant to reduce token waste
            **({"result": self.result} if self.status == "completed" else {}),
            **({"error": self.error} if self.status == "failed" else {}),
            "tools_executed": self.tools_executed,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AsyncTaskDispatcher:
    """
    Dispatches sub-tasks that execute asynchronously in the background.

    Each sub-task is a full ``handle_message`` invocation — it gets its own
    skill selection, planning loop, and stuck detection, identical to a
    top-level user request.  When *skill* is provided, the sub-task is
    pinned to that specialist's context-prompt and tool set instead of
    re-running keyword-based skill selection.

    Sub-tasks can themselves dispatch further sub-tasks, enabling arbitrary
    depth of parallel work.

    The ``wait_for`` coroutine is used by the ``wait_for_tasks`` inline tool
    handler to properly block until a set of tasks has finished (with an
    optional timeout), after which the main loop can collect results and
    respond to the user.

    Task state is persisted to the ``agent_tasks`` table when a
    ``task_repo`` is provided, making sub-task progress visible after
    restarts.
    """

    def __init__(self, handle_message_fn: Callable, task_repo=None) -> None:
        """
        Args:
            handle_message_fn: Async callable with the signature::

                handle_message(
                    message: str,
                    channel: str = "subtask",
                    pinned_skill: Optional[str] = None,
                ) -> dict

            Typically ``MessageHandler.handle_message`` bound to an instance.

            task_repo: Optional ``AgentTaskRepository`` instance.  When
                provided, each dispatched task is persisted to the
                ``agent_tasks`` database table.
        """
        self._handle_message = handle_message_fn
        self._task_repo = task_repo
        self._tasks: Dict[str, AsyncTask] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dispatch(
        self,
        description: str,
        context: str = "",
        skill: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        Dispatch *description* as an async sub-task.

        Args:
            description: Self-contained instruction for the sub-task.
            context: Optional context from the parent conversation (e.g.
                earlier results, user preferences).
            skill: Optional specialist skill name to pin for this sub-task.
                When set, the sub-task uses only that skill's context-prompt
                and tools rather than running keyword-based skill selection.
            conversation_id: Parent conversation ID, used when persisting the
                task record to the ``agent_tasks`` table.

        Returns:
            A short *task_id* string (8 hex chars).  Pass this to
            ``wait_for_tasks`` or ``get_task_result`` to monitor progress.
        """
        task_id = uuid.uuid4().hex[:8]
        message = description
        if context:
            message = f"Context from parent task:\n{context}\n\nTask: {description}"

        task = AsyncTask(task_id=task_id, description=description, skill=skill)
        self._tasks[task_id] = task

        # Persist the task record so state survives restarts and is visible
        # in the admin UI.
        if self._task_repo:
            try:
                self._task_repo.create_task(
                    task_id=task_id,
                    conversation_id=conversation_id or "",
                    agent_name=skill or "auto",
                    action="dispatch_task",
                    parameters={
                        "description": description,
                        "context": context,
                        "skill": skill,
                    },
                    status="running",
                )
            except Exception as exc:
                logger.warning(f"Failed to persist sub-task {task_id} to DB: {exc}")

        asyncio_task = asyncio.create_task(
            self._run(task, message, task_id), name=f"subtask-{task_id}"
        )
        task._asyncio_task = asyncio_task

        logger.info(
            f"Dispatched sub-task {task_id}"
            + (f" [skill={skill}]" if skill else "")
            + f": {description[:100]}"
        )
        return task_id

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Return current status and (when done) result for *task_id*.

        Returns ``None`` if the task ID is unknown.
        """
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def get_running_tasks(self) -> List[Dict[str, Any]]:
        """Return status dicts for all tasks that are still running."""
        return [t.to_dict() for t in self._tasks.values() if t.status == "running"]

    def list_tasks(self) -> List[Dict[str, Any]]:
        """Return status dicts for every tracked task (useful for debugging)."""
        return [t.to_dict() for t in self._tasks.values()]

    async def wait_for(
        self,
        task_ids: List[str],
        timeout: float = 300,
    ) -> Dict[str, Any]:
        """
        Await a set of tasks and return their final status dicts.

        Args:
            task_ids: List of task IDs to wait for.  Pass an empty list to
                wait for *all* currently-running tasks.
            timeout: Maximum seconds to wait before returning (tasks still
                running at timeout will have ``status="running"`` in the
                result dict).

        Returns:
            Mapping of task_id → status dict for every requested task.
        """
        if not task_ids:
            task_ids = [t.task_id for t in self._tasks.values() if t.status == "running"]

        if not task_ids:
            return {}

        # Gather live asyncio.Task handles for tasks that haven't finished yet
        pending_handles = [
            task._asyncio_task
            for tid in task_ids
            if (task := self._tasks.get(tid))
            and task._asyncio_task is not None
            and not task._asyncio_task.done()
        ]

        if pending_handles:
            try:
                await asyncio.wait(pending_handles, timeout=timeout)
            except Exception as exc:
                logger.warning(f"wait_for encountered an error while waiting: {exc}")

        return {tid: self._tasks[tid].to_dict() for tid in task_ids if tid in self._tasks}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run(self, task: AsyncTask, message: str, task_id: str) -> None:
        """Execute the task and record the outcome."""
        started_at = datetime.now(timezone.utc)

        # Mark as running in DB (already created as 'running', but update
        # started_at so the timestamp is accurate after any queue delay).
        if self._task_repo:
            try:
                self._task_repo.update_task_status(
                    task_id=task_id, status="running", started_at=started_at
                )
            except Exception as exc:
                logger.debug(f"Sub-task {task_id}: failed to update started_at in DB: {exc}")

        # Initialise DB-write locals before the try/except so `finally`
        # always has valid values even if an unexpected error escapes both branches.
        db_result: Optional[Dict[str, Any]] = None
        db_status: str = "failed"
        db_error: Optional[str] = None

        try:
            result = await self._handle_message(
                message=message,
                channel="subtask",
                pinned_skill=task.skill,
            )
            task.status = "completed"
            task.result = result.get("response", "")
            task.tools_executed = result.get("tools_executed", [])
            db_result = {"response": task.result, "tools_executed": task.tools_executed}
            db_status = "completed"
            db_error = None
        except Exception as exc:
            logger.error(
                f"Sub-task {task.task_id} failed: {exc}",
                exc_info=True,
            )
            task.status = "failed"
            task.error = str(exc)
            db_result = None
            db_status = "failed"
            db_error = str(exc)
        finally:
            task.completed_at = datetime.now(timezone.utc)
            tool_count = len(task.tools_executed)
            logger.info(
                f"Sub-task {task.task_id} {task.status}"
                + (f" ({tool_count} tools executed)" if tool_count else "")
            )

            # Persist final state to DB.
            if self._task_repo:
                try:
                    self._task_repo.update_task_status(
                        task_id=task_id,
                        status=db_status,
                        completed_at=task.completed_at,
                        result=db_result,
                        error_message=db_error,
                    )
                except Exception as exc:
                    logger.debug(f"Sub-task {task_id}: failed to persist final state to DB: {exc}")
