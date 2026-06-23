"""API endpoints for future task management."""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.dependencies import get_future_task_service
from src.models.cron_jobs import JobExecutionResponse
from src.models.future_tasks import (
    FutureTaskCreateAPI,
    FutureTaskDetailResponse,
    FutureTaskListResponse,
    FutureTaskResponse,
)
from src.services.future_task import FutureTaskService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/future-tasks", tags=["future-tasks"])


@router.get("", response_model=FutureTaskListResponse)
async def list_future_tasks(
    status: str = Query(
        None,
        description="Filter by status: 'pending', 'completed', 'failed', 'cancelled', or 'all'",
    ),
    service: FutureTaskService = Depends(get_future_task_service),
) -> FutureTaskListResponse:
    """List future tasks with optional status filter.

    Args:
        status: Filter by status (default: all tasks)
        service: Future task service (injected)

    Returns:
        List of future tasks
    """
    tasks = service.list_tasks(status=status)
    task_responses = [FutureTaskResponse(**task) for task in tasks]
    return FutureTaskListResponse(tasks=task_responses, total=len(task_responses))


@router.post("", response_model=FutureTaskResponse, status_code=201)
async def create_future_task(
    request: FutureTaskCreateAPI,
    service: FutureTaskService = Depends(get_future_task_service),
) -> FutureTaskResponse:
    """Create a new future task.

    Args:
        request: Task creation parameters
        service: Future task service (injected)

    Returns:
        Created future task
    """
    try:
        task = service.create_task(
            name=request.name,
            scheduled_time=request.scheduled_time,
            job_type=request.job_type,
            description=request.description,
            conversation_id=request.conversation_id,
            tool_name=request.tool_name,
            tool_parameters=request.tool_parameters,
            prompt=request.prompt,
            delivery_channel=request.delivery_channel,
            delivery_contact_identifier=request.delivery_contact_identifier,
        )
        return FutureTaskResponse(**task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{task_id}", response_model=FutureTaskDetailResponse)
async def get_future_task(
    task_id: str,
    service: FutureTaskService = Depends(get_future_task_service),
) -> FutureTaskDetailResponse:
    """Get a future task with execution history.

    Args:
        task_id: Task identifier
        service: Future task service (injected)

    Returns:
        Task details with recent executions
    """
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Extract executions from task dict (added by service.get_task)
    executions = task.pop("recent_executions", [])
    execution_responses = [JobExecutionResponse(**ex) for ex in executions]

    return FutureTaskDetailResponse(
        task=FutureTaskResponse(**task),
        recent_executions=execution_responses,
    )


@router.delete("/{task_id}")
async def cancel_future_task(
    task_id: str,
    service: FutureTaskService = Depends(get_future_task_service),
):
    """Cancel a pending future task.

    Args:
        task_id: Task identifier
        service: Future task service (injected)

    Returns:
        Success message
    """
    try:
        success = service.cancel_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return {
            "message": f"Task {task_id} cancelled successfully",
            "task_id": task_id,
            "status": "cancelled",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
