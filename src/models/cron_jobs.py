"""Pydantic models for cron job scheduling."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --- Recipe Step ---


class RecipeStep(BaseModel):
    """One step in a multi-step recipe."""

    order: int = Field(..., description="Execution order (1-based)")
    description: str = Field(..., description="What this step accomplishes")
    tool_name: Optional[str] = Field(
        None,
        description="Pin a specific tool. When set the engine calls this tool directly — no LLM routing.",
    )
    tool_parameters: Optional[Dict[str, Any]] = Field(
        None, description="Static parameters for the pinned tool"
    )
    prompt_template: Optional[str] = Field(
        None,
        description="LLM prompt for this step when tool_name is not set. Must be fully self-contained.",
    )
    stores_as: Optional[str] = Field(
        None, description="Variable name to store this step's output under for later steps"
    )
    uses_variable: Optional[str] = Field(
        None, description="Variable name produced by a prior step to inject as context"
    )


# --- LLM Tool Parameter Models ---


class CreateCronJobRequest(BaseModel):
    """Parameters for creating a cron job."""

    name: str = Field(..., description="Human-readable job name")
    cron_expression: str = Field(
        ...,
        description="Cron schedule expression (e.g., '0 9 * * MON' for Monday 9am, '*/30 * * * *' for every 30 minutes)",
    )
    job_type: str = Field(
        ..., description="Job type: 'tool' for direct tool execution, 'prompt' for agent processing"
    )
    description: Optional[str] = Field(None, description="Optional job description")
    tool_name: Optional[str] = Field(
        None, description="Tool to execute (required if job_type='tool' and no steps provided)"
    )
    tool_parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="Parameters for the tool (required if job_type='tool' and no steps provided)",
    )
    prompt: Optional[str] = Field(
        None,
        description="Prompt to send to Coordinator agent (required if job_type='prompt' and no steps provided)",
    )
    steps: Optional[List[RecipeStep]] = Field(
        None,
        description="Ordered recipe steps. When provided, overrides job_type/tool_name/prompt. Each step can pin a tool or use a prompt template.",
    )
    delivery_channel: Optional[str] = Field(
        None,
        description="Messaging channel to deliver the LLM response to the user: 'whatsapp' or 'slack'. If omitted, the job runs silently (system execution only).",
    )
    delivery_contact_identifier: Optional[str] = Field(
        None,
        description="Optional override for the delivery address: phone number for whatsapp (e.g. '+1234567890') or Slack channel ID (e.g. 'C1234567'). When omitted, the configured default is used automatically.",
    )


class UpdateCronJobRequest(BaseModel):
    """Parameters for updating a cron job."""

    job_id: str = Field(..., description="The job ID to update")
    name: Optional[str] = Field(None, description="New job name")
    cron_expression: Optional[str] = Field(None, description="New cron schedule expression")
    description: Optional[str] = Field(None, description="New job description")
    tool_name: Optional[str] = Field(None, description="New tool name (for tool jobs)")
    tool_parameters: Optional[Dict[str, Any]] = Field(
        None, description="New tool parameters (for tool jobs)"
    )
    prompt: Optional[str] = Field(None, description="New prompt (for prompt jobs)")


class GetCronJobRequest(BaseModel):
    """Parameters for getting a specific cron job."""

    job_id: str = Field(..., description="The job ID to retrieve")


class DeleteCronJobRequest(BaseModel):
    """Parameters for deleting a cron job."""

    job_id: str = Field(..., description="The job ID to delete")


class ToggleCronJobRequest(BaseModel):
    """Parameters for enabling/disabling a cron job."""

    job_id: str = Field(..., description="The job ID to toggle")
    enabled: Optional[bool] = Field(
        None,
        description="Set to true to enable, false to disable. If omitted, toggles current state.",
    )


class ListCronJobsRequest(BaseModel):
    """Parameters for listing cron jobs."""

    enabled_only: Optional[bool] = Field(
        None, description="If true, only return enabled jobs. If omitted, returns all jobs."
    )


# --- API Request/Response Models ---


class CronJobCreateAPI(BaseModel):
    """API request body for creating a cron job."""

    name: str = Field(..., description="Human-readable job name")
    cron_expression: str = Field(..., description="Cron schedule expression")
    job_type: str = Field(..., description="'tool' or 'prompt'")
    description: Optional[str] = None
    tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    steps: Optional[List[RecipeStep]] = None
    delivery_channel: Optional[str] = None
    delivery_contact_identifier: Optional[str] = None


class CronJobUpdateAPI(BaseModel):
    """API request body for updating a cron job."""

    name: Optional[str] = None
    cron_expression: Optional[str] = None
    description: Optional[str] = None
    tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    steps: Optional[List[RecipeStep]] = None
    delivery_channel: Optional[str] = None
    delivery_contact_identifier: Optional[str] = None


class CronJobResponse(BaseModel):
    """Response model for a cron job."""

    job_id: str
    name: str
    description: Optional[str] = None
    cron_expression: str
    job_type: str
    tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None
    required_skills: Optional[List[str]] = None
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    delivery_channel: Optional[str] = None
    delivery_contact_identifier: Optional[str] = None


class CronJobListResponse(BaseModel):
    """Response model for listing cron jobs."""

    jobs: List[CronJobResponse]
    total: int


class JobExecutionResponse(BaseModel):
    """Response model for a job execution record."""

    id: int
    job_id: str
    job_type: str
    job_name: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    status: str
    result: Optional[Any] = None
    error_message: Optional[str] = None
    container_id: Optional[str] = None


class JobExecutionListResponse(BaseModel):
    """Response model for listing job executions."""

    executions: List[JobExecutionResponse]
    total: int


class CronJobDetailResponse(BaseModel):
    """Response model for cron job with recent executions."""

    job: CronJobResponse
    recent_executions: List[JobExecutionResponse] = []


class ToggleResponse(BaseModel):
    """Response for toggle operation."""

    job_id: str
    enabled: bool
    message: str
