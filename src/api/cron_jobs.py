"""API endpoints for cron job management."""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.dependencies import get_cron_job_service
from src.models.cron_jobs import (
    CronJobCreateAPI,
    CronJobDetailResponse,
    CronJobListResponse,
    CronJobResponse,
    CronJobUpdateAPI,
    JobExecutionListResponse,
    JobExecutionResponse,
    ToggleResponse,
)
from src.services.cron_job import CronJobService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/cron-jobs", tags=["cron-jobs"])


@router.get("/executions/recent", response_model=JobExecutionListResponse)
async def get_recent_executions(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of records"),
    status: str = Query(None, description="Filter by status"),
    job_type: str = Query(None, description="Filter by job type ('cron' or 'future_task')"),
    service: CronJobService = Depends(get_cron_job_service),
) -> JobExecutionListResponse:
    """Get recent job executions across all jobs.

    Args:
        limit: Maximum number of records
        status: Optional status filter
        job_type: Optional job type filter
        service: Cron job service (injected)

    Returns:
        List of recent executions
    """
    executions = service.get_recent_executions(limit=limit, status=status, job_type=job_type)
    execution_responses = [JobExecutionResponse(**ex) for ex in executions]
    return JobExecutionListResponse(executions=execution_responses, total=len(execution_responses))


@router.get("", response_model=CronJobListResponse)
async def list_cron_jobs(
    enabled_only: bool = Query(False, description="Only return enabled jobs"),
    service: CronJobService = Depends(get_cron_job_service),
) -> CronJobListResponse:
    """List all cron jobs.

    Args:
        enabled_only: Filter to enabled jobs only
        service: Cron job service (injected)

    Returns:
        List of cron jobs
    """
    jobs = service.list_jobs(enabled_only=enabled_only)
    job_responses = [CronJobResponse(**job) for job in jobs]
    return CronJobListResponse(jobs=job_responses, total=len(job_responses))


@router.post("", response_model=CronJobResponse, status_code=201)
async def create_cron_job(
    request: CronJobCreateAPI,
    service: CronJobService = Depends(get_cron_job_service),
) -> CronJobResponse:
    """Create a new cron job.

    Args:
        request: Job creation parameters
        service: Cron job service (injected)

    Returns:
        Created cron job
    """
    try:
        steps = [s.model_dump() for s in request.steps] if request.steps else None
        job = service.create_job(
            name=request.name,
            cron_expression=request.cron_expression,
            job_type=request.job_type,
            description=request.description,
            tool_name=request.tool_name,
            tool_parameters=request.tool_parameters,
            prompt=request.prompt,
            steps=steps,
            delivery_channel=request.delivery_channel,
            delivery_contact_identifier=request.delivery_contact_identifier,
        )
        return CronJobResponse(**job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{job_id}", response_model=CronJobDetailResponse)
async def get_cron_job(
    job_id: str,
    service: CronJobService = Depends(get_cron_job_service),
) -> CronJobDetailResponse:
    """Get a cron job with recent execution history.

    Args:
        job_id: Job identifier
        service: Cron job service (injected)

    Returns:
        Job details with recent executions
    """
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    executions = service.get_job_executions(job_id, limit=10)
    execution_responses = [JobExecutionResponse(**ex) for ex in executions]

    return CronJobDetailResponse(
        job=CronJobResponse(**job),
        recent_executions=execution_responses,
    )


@router.put("/{job_id}", response_model=CronJobResponse)
async def update_cron_job(
    job_id: str,
    request: CronJobUpdateAPI,
    service: CronJobService = Depends(get_cron_job_service),
) -> CronJobResponse:
    """Update a cron job.

    Args:
        job_id: Job identifier
        request: Fields to update
        service: Cron job service (injected)

    Returns:
        Updated cron job
    """
    updates = request.model_dump(exclude_none=True)
    # Serialise RecipeStep objects to plain dicts for the repository layer
    if "steps" in updates and updates["steps"]:
        updates["steps"] = [s if isinstance(s, dict) else s.model_dump() for s in updates["steps"]]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        job = service.update_job(job_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return CronJobResponse(**job)


@router.delete("/{job_id}")
async def delete_cron_job(
    job_id: str,
    service: CronJobService = Depends(get_cron_job_service),
):
    """Delete a cron job.

    Args:
        job_id: Job identifier
        service: Cron job service (injected)

    Returns:
        Deletion confirmation
    """
    deleted = service.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {"message": f"Job {job_id} deleted", "job_id": job_id}


@router.post("/{job_id}/toggle", response_model=ToggleResponse)
async def toggle_cron_job(
    job_id: str,
    enabled: bool = Query(None, description="Set enabled state. Omit to toggle."),
    service: CronJobService = Depends(get_cron_job_service),
) -> ToggleResponse:
    """Enable or disable a cron job.

    Args:
        job_id: Job identifier
        enabled: Explicit state, or omit to toggle
        service: Cron job service (injected)

    Returns:
        New enabled state
    """
    new_state = service.toggle_job(job_id, enabled)
    if new_state is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    state_str = "enabled" if new_state else "disabled"
    return ToggleResponse(
        job_id=job_id,
        enabled=new_state,
        message=f"Job {job_id} {state_str}",
    )


@router.post("/{job_id}/run-now")
async def run_cron_job_now(
    job_id: str,
    service: CronJobService = Depends(get_cron_job_service),
):
    """Trigger immediate execution of a cron job.

    Args:
        job_id: Job identifier
        service: Cron job service (injected)

    Returns:
        Execution result
    """
    try:
        result = await service.run_now(job_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
