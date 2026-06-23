"""Pydantic models for monitoring operations."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FetchLogsRequest(BaseModel):
    """Request model for fetching application logs."""

    lines: int = Field(
        default=500, ge=1, le=2000, description="Number of log lines to fetch (max 2000)"
    )
    level: Optional[str] = Field(
        default=None,
        description="Filter by log level (ERROR, WARNING, INFO, DEBUG). If not specified, returns all levels.",
    )


class GetConversationTextRequest(BaseModel):
    """Request model for retrieving conversation text within a timespan."""

    since: Optional[str] = Field(
        default=None,
        description="ISO-8601 start timestamp (inclusive). Defaults to start of today (UTC).",
    )
    until: Optional[str] = Field(
        default=None,
        description="ISO-8601 end timestamp (inclusive). Defaults to now.",
    )
    channel: Optional[str] = Field(
        default=None,
        description="Optional channel filter, e.g. 'webui' or 'whatsapp'. Omit for all channels.",
    )
    limit: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Maximum number of messages to return (default 200, max 1000).",
    )


class GetPromptRequest(BaseModel):
    """Request model for reading a prompt by key."""

    key: str = Field(
        ...,
        description="Prompt key to read. One of: 'system_prompt_default', 'system_prompt_custom', 'memory', 'soul'.",
    )


class UpdateMemoryPromptRequest(BaseModel):
    """Request model for updating the memory prompt."""

    updated_memory: str = Field(
        ...,
        description="The full updated memory prompt text. Keep this lean: only IDs, account references, and operational facts the system needs on every request (e.g. user name, timezone, key contact IDs, critical preferences). General/contextual facts should go to system_index_memory_facts instead. Do NOT remove existing content unless it is outdated or incorrect.",
    )


class IndexMemoryFactsRequest(BaseModel):
    """Request model for indexing general memory facts into the search index."""

    date: str = Field(
        ...,
        description="ISO date string (YYYY-MM-DD) for when these facts were recorded. Used as part of the source_id and stored in metadata.",
    )
    facts: str = Field(
        ...,
        description="General/contextual facts to store. These are background facts that are useful for occasional recall but not needed on every request — e.g. interests, project context, relationship details, learnings.",
    )


class UpdateSoulPromptRequest(BaseModel):
    """Request model for updating the soul prompt."""

    updated_soul: str = Field(
        ...,
        description="The full updated soul prompt text. Should contain all existing personality/style information plus any new preferences. Do NOT remove existing content unless it is outdated or incorrect.",
    )


class RecallConversationMemoryRequest(BaseModel):
    """Request model for recalling information from past conversation messages."""

    query: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "One or more search keywords to match against past conversation messages. "
            "Prefer short, specific terms (e.g. 'vacation', 'deploy', 'John') rather "
            "than full sentences. Include synonyms and alternative spellings if relevant."
        ),
    )
    question: str = Field(
        ...,
        description=(
            "The specific question to answer from the retrieved context. The worker LLM "
            "will synthesise a focused answer to this question using the matched messages."
        ),
    )
    max_conversations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of past conversations to retrieve context from (default 3, max 10).",
    )
    context_window: int = Field(
        default=10,
        ge=2,
        le=50,
        description="Number of messages to include per matched conversation (default 10, max 50).",
    )


class CleanTmpDirRequest(BaseModel):
    """Request model for cleaning the temporary files directory."""

    max_age_hours: int = Field(
        default=24,
        ge=1,
        le=720,
        description="Delete files older than this many hours (default 24, max 720).",
    )


class HealthCheckResult(BaseModel):
    """Health check result model."""

    status: str = Field(..., description="Status (healthy, degraded, unhealthy)")
    latency_ms: Optional[float] = Field(None, description="Latency in milliseconds")
    message: str = Field(..., description="Status message")


class HealthResponse(BaseModel):
    """Health response model."""

    status: str = Field(..., description="Overall status (healthy, degraded, unhealthy)")
    timestamp: str = Field(..., description="Health check timestamp")
    checks: Dict[str, HealthCheckResult] = Field(..., description="Individual health checks")


class APIMetrics(BaseModel):
    """API metrics model."""

    total: int = Field(..., description="Total API calls")
    success: int = Field(..., description="Successful API calls")
    error: int = Field(..., description="Failed API calls")
    success_rate: float = Field(..., description="Success rate (0.0-1.0)")


class ConversationMetrics(BaseModel):
    """Conversation metrics model."""

    total: int = Field(..., description="Total conversations")
    active_since: str = Field(..., description="Active since timestamp")


class MetricsResponse(BaseModel):
    """Metrics response model."""

    api_calls: APIMetrics = Field(..., description="API call metrics")
    conversations: ConversationMetrics = Field(..., description="Conversation metrics")
    period: Dict[str, str] = Field(..., description="Period (since, until)")


class LogEntry(BaseModel):
    """Log entry model."""

    id: Optional[int] = Field(None, description="Log entry ID")
    timestamp: str = Field(..., description="Log timestamp")
    event_type: str = Field(..., description="Event type")
    service_name: Optional[str] = Field(None, description="Service name")
    agent_name: Optional[str] = Field(None, description="Agent name")
    action: str = Field(..., description="Action performed")
    success: bool = Field(..., description="Whether action succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class LogListResponse(BaseModel):
    """Log list response model."""

    logs: List[LogEntry] = Field(..., description="List of log entries")
    limit: int = Field(..., description="Page limit")
    total: Optional[int] = Field(None, description="Total log count")


class ConnectionStatus(BaseModel):
    """Connection status model."""

    service_name: str = Field(..., description="Service name")
    status: str = Field(..., description="Status (connected, disconnected, error, not_configured)")
    last_check: Optional[str] = Field(None, description="Last check timestamp")
    message: str = Field(..., description="Status message")


class ConnectionStatusListResponse(BaseModel):
    """Connection status list response model."""

    connections: List[ConnectionStatus] = Field(..., description="List of connection statuses")
    checked_at: str = Field(..., description="Check timestamp")


class ConversationStatsResponse(BaseModel):
    """Conversation statistics response model."""

    total_conversations: int = Field(..., description="Total conversations")
    by_channel: Dict[str, int] = Field(..., description="Conversations by channel")
    active_last_24h: int = Field(..., description="Active conversations in last 24 hours")


class SystemInfoResponse(BaseModel):
    """System information response model."""

    python_version: str = Field(..., description="Python version")
    platform: str = Field(..., description="Operating system platform")
    database_url: str = Field(..., description="Database URL")
    environment: str = Field(..., description="Environment (development, production)")
    log_level: str = Field(..., description="Log level")
