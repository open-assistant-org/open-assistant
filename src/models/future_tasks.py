"""Pydantic models for future task scheduling."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --- LLM Tool Parameter Models ---


class ScheduleTaskRequest(BaseModel):
    """Parameters for scheduling a future task."""

    name: str = Field(..., description="Human-readable task name")
    scheduled_time: str = Field(
        ...,
        description="When to execute the task. Supports ISO 8601 (e.g., '2024-01-16T15:00:00'), natural language (e.g., 'tomorrow at 3pm'), or relative time (e.g., 'in 2 hours')",
    )
    job_type: str = Field(
        ...,
        description="Task type: 'tool' for direct tool execution, 'prompt' for agent processing",
    )
    description: Optional[str] = Field(None, description="Optional task description")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID to link task to conversation context"
    )
    tool_name: Optional[str] = Field(
        None, description="Tool to execute (required if job_type='tool')"
    )
    tool_parameters: Optional[Dict[str, Any]] = Field(
        None, description="Parameters for the tool (required if job_type='tool')"
    )
    prompt: Optional[str] = Field(
        None, description="Prompt to send to Coordinator agent (required if job_type='prompt')"
    )
    delivery_channel: Optional[str] = Field(
        None,
        description="Messaging channel to deliver the result to the user: 'whatsapp' or 'slack'. If omitted, the task runs silently.",
    )
    delivery_contact_identifier: Optional[str] = Field(
        None,
        description="Optional override for the delivery address. When omitted, the configured default is used automatically.",
    )


class ListFutureTasksRequest(BaseModel):
    """Parameters for listing future tasks."""

    status: Optional[str] = Field(
        None,
        description="Filter by status: 'pending', 'completed', 'failed', 'cancelled', or 'all'. If omitted, returns all tasks.",
    )


class CancelFutureTaskRequest(BaseModel):
    """Parameters for cancelling a future task."""

    task_id: str = Field(..., description="The task ID to cancel")


class GetFutureTaskRequest(BaseModel):
    """Parameters for getting a specific future task."""

    task_id: str = Field(..., description="The task ID to retrieve")


# --- API Request/Response Models ---


class FutureTaskCreateAPI(BaseModel):
    """API request body for creating a future task."""

    name: str = Field(..., description="Human-readable task name")
    scheduled_time: str = Field(
        ..., description="When to execute (ISO 8601, natural language, or relative)"
    )
    job_type: str = Field(..., description="'tool' or 'prompt'")
    description: Optional[str] = None
    conversation_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    delivery_channel: Optional[str] = None
    delivery_contact_identifier: Optional[str] = None


class FutureTaskResponse(BaseModel):
    """Response model for a future task."""

    task_id: str
    name: str
    description: Optional[str] = None
    conversation_id: Optional[str] = None
    scheduled_time: str
    job_type: str
    tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    status: str
    result: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    delivery_channel: Optional[str] = None
    delivery_contact_identifier: Optional[str] = None


class FutureTaskListResponse(BaseModel):
    """Response model for listing future tasks."""

    tasks: List[FutureTaskResponse]
    total: int


class FutureTaskDetailResponse(BaseModel):
    """Response model for future task with execution history."""

    task: FutureTaskResponse
    recent_executions: List[Any] = []  # Reuse JobExecutionResponse from cron_jobs
