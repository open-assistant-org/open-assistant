"""Monitoring API for system health, metrics, and logs."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.core.dependencies import (
    get_audit_repo,
    get_conversation_repo,
    get_credentials_repo,
    get_message_repo,
)
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.message import MessageRepository
from src.models.monitoring import (
    ConnectionStatus,
    ConnectionStatusListResponse,
    ConversationStatsResponse,
    HealthCheckResult,
    HealthResponse,
    LogEntry,
    LogListResponse,
    MetricsResponse,
    SystemInfoResponse,
)
from src.services.monitoring import MonitoringService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/health", response_model=HealthResponse)
async def get_health(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> HealthResponse:
    """
    Get system health status.

    Args:
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        HealthResponse with health check results
    """
    monitoring_service = MonitoringService(
        conversation_repo, message_repo, credentials_repo, audit_repo
    )

    health = monitoring_service.get_system_health()

    # Convert checks to HealthCheckResult models
    checks = {name: HealthCheckResult(**check) for name, check in health["checks"].items()}

    return HealthResponse(
        status=health["status"],
        timestamp=health["timestamp"],
        checks=checks,
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    since: str = Query(None, description="Calculate metrics since this timestamp (ISO format)"),
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> MetricsResponse:
    """
    Get API usage metrics.

    Args:
        since: Optional timestamp to calculate metrics from
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        MetricsResponse with API metrics
    """
    monitoring_service = MonitoringService(
        conversation_repo, message_repo, credentials_repo, audit_repo
    )

    metrics = monitoring_service.get_api_metrics(since)

    return MetricsResponse(**metrics)


@router.get("/logs", response_model=LogListResponse)
async def get_logs(
    limit: int = Query(default=100, description="Maximum number of log entries"),
    level: str = Query(None, description="Filter by level (ERROR, WARNING, INFO)"),
    since: str = Query(None, description="Filter logs since this timestamp (ISO format)"),
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> LogListResponse:
    """
    Get recent log entries from application log file.

    Args:
        limit: Maximum number of entries
        level: Optional level filter
        since: Optional timestamp filter
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        LogListResponse with log entries
    """
    monitoring_service = MonitoringService(
        conversation_repo, message_repo, credentials_repo, audit_repo
    )

    logs = monitoring_service.get_recent_logs(limit=limit, level=level, since=since)

    log_entries = [LogEntry(**log) for log in logs]

    return LogListResponse(logs=log_entries, limit=limit, total=len(log_entries))


@router.get("/connections", response_model=ConnectionStatusListResponse)
async def get_connection_statuses(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> ConnectionStatusListResponse:
    """
    Get connection status for all integrations.

    Args:
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        ConnectionStatusListResponse with connection statuses
    """
    monitoring_service = MonitoringService(
        conversation_repo, message_repo, credentials_repo, audit_repo
    )

    statuses = monitoring_service.get_connection_statuses()
    connection_statuses = [ConnectionStatus(**status) for status in statuses]

    return ConnectionStatusListResponse(
        connections=connection_statuses,
        checked_at=datetime.utcnow().isoformat(),
    )


@router.get("/stats", response_model=ConversationStatsResponse)
async def get_stats(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> ConversationStatsResponse:
    """
    Get conversation and usage statistics.

    Args:
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        ConversationStatsResponse with statistics
    """
    monitoring_service = MonitoringService(
        conversation_repo, message_repo, credentials_repo, audit_repo
    )

    stats = monitoring_service.get_conversation_stats()

    return ConversationStatsResponse(**stats)


@router.get("/system", response_model=SystemInfoResponse)
async def get_system_info(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> SystemInfoResponse:
    """
    Get system information.

    Args:
        conversation_repo: Conversation repository (injected)
        message_repo: Message repository (injected)
        credentials_repo: Credentials repository (injected)
        audit_repo: Audit log repository (injected)

    Returns:
        SystemInfoResponse with system information
    """
    monitoring_service = MonitoringService(
        conversation_repo, message_repo, credentials_repo, audit_repo
    )

    info = monitoring_service.get_system_info()

    return SystemInfoResponse(**info)


@router.get("/audit-logs", response_model=LogListResponse)
async def get_audit_logs(
    limit: int = Query(default=100, description="Maximum number of log entries"),
    event_type: str = Query(None, description="Filter by event type"),
    service_name: str = Query(None, description="Filter by service name"),
    success: bool = Query(None, description="Filter by success status"),
    conversation_id: str = Query(None, description="Filter by conversation ID"),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> LogListResponse:
    """
    Get audit log entries (including tool executions).

    Args:
        limit: Maximum number of entries
        event_type: Optional event type filter
        service_name: Optional service name filter
        success: Optional success status filter
        conversation_id: Optional conversation ID filter
        audit_repo: Audit log repository (injected)

    Returns:
        LogListResponse with audit log entries
    """
    # Get logs with filters
    if conversation_id:
        # Use conversation-specific query
        logs = audit_repo.get_by_conversation(conversation_id, limit=limit)
        # Apply additional filters if needed
        if event_type:
            logs = [log for log in logs if log.get("event_type") == event_type]
        if service_name:
            logs = [log for log in logs if log.get("service_name") == service_name]
        if success is not None:
            logs = [log for log in logs if log.get("success") == success]
    else:
        logs = audit_repo.get_recent(
            limit=limit, event_type=event_type, service_name=service_name, success=success
        )

    # Convert to LogEntry objects
    log_entries = []
    for log in logs:
        log_entry = LogEntry(
            id=log.get("id"),
            timestamp=log.get("timestamp"),
            event_type=log.get("event_type"),
            service_name=log.get("service_name"),
            action=log.get("action"),
            success=log.get("success", True),
            error_message=log.get("error_message"),
            details=log.get("details"),
        )
        log_entries.append(log_entry)

    return LogListResponse(logs=log_entries, limit=limit, total=len(log_entries))


@router.get("/logs/stream")
async def stream_logs_sse() -> StreamingResponse:
    """Stream live application logs via Server-Sent Events."""
    log_dir = os.getenv("LOG_DIR", "logs")
    log_file = Path(log_dir) / "assistant.log"

    async def event_generator():
        # Send last 200 historical lines first
        if log_file.exists():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "tail",
                    "-n",
                    "200",
                    str(log_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await proc.communicate()
                for line in stdout.decode("utf-8", errors="replace").splitlines():
                    if line.strip():
                        yield f"data: {json.dumps({'line': line, 'historical': True})}\n\n"
            except Exception as e:
                logger.error(f"Failed to read historical logs: {e}")

        # Ensure log file exists so tail -f can follow it
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            if not log_file.exists():
                log_file.touch()
        except Exception as e:
            logger.error(f"Failed to create log file: {e}")
            yield f"data: {json.dumps({'error': 'Log file unavailable'})}\n\n"
            return

        # Follow the file for new lines
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "tail",
                "-f",
                "-n",
                "0",
                str(log_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            while True:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").rstrip("\n")
                    if line_str.strip():
                        yield f"data: {json.dumps({'line': line_str})}\n\n"
                except asyncio.TimeoutError:
                    # Send a comment line as keepalive (not dispatched as a message event)
                    yield ": keepalive\n\n"
        except Exception as e:
            logger.error(f"Log streaming error: {e}")
        finally:
            if proc:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
