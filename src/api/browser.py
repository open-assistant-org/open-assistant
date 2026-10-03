"""Browser API endpoints."""

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import get_audit_repo, get_browser_service, get_credentials_repo
from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.integrations.browser.sessions import (
    BrowserSessionStore,
    DuplicateSessionName,
    SessionParseError,
    parse_session_export,
)
from src.models.browser import (
    BrowserSessionCreate,
    BrowserSessionMetadata,
    BrowserSessionResponse,
    BrowserSessionTestRequest,
    BrowserSessionTestResponse,
    BrowserSessionUpdate,
)
from src.services.browser import BrowserService, BrowserSessionTestError
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/browser", tags=["browser"])


@router.post("/test-connection")
async def test_connection(
    browser_service: BrowserService = Depends(get_browser_service),
) -> Dict[str, Any]:
    """
    Test browser connection by launching Playwright and navigating to a test page.

    Args:
        browser_service: Browser service (injected)

    Returns:
        Connection test result
    """
    # Run sync Playwright code in a thread to avoid async loop conflict
    return await asyncio.to_thread(browser_service.test_connection)


# ============================================================================
# AUTHENTICATED SESSIONS (cookies)
#
# Write-only by design: no endpoint, response or error message ever contains a
# cookie name or value. These routes carry no auth of their own (like the rest
# of the settings API), so that property is what keeps the secrets safe.
# ============================================================================


def get_session_store(
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> BrowserSessionStore:
    """Get the encrypted browser session store."""
    return BrowserSessionStore(credentials_repo)


def _audit(
    audit_repo: Optional[AuditLogRepository],
    action: str,
    session: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Record a session change. Only non-secret metadata is written."""
    if audit_repo is None:
        return
    try:
        audit_repo.log_event(
            event_type="setting_change",
            action=action,
            success=success,
            service_name="browser",
            details={
                "name": (session or {}).get("name"),
                "domains": (session or {}).get("domains"),
                "cookie_count": (session or {}).get("cookie_count"),
                "values": "***MASKED***",
            },
            error_message=error,
        )
    except Exception as e:
        logger.error(f"Failed to audit browser session change: {type(e).__name__}")


def _parse(payload: str, fmt: str, domain: Optional[str]):
    try:
        return parse_session_export(payload, fmt=fmt, domain=domain)
    except SessionParseError as e:
        # The message is built to never contain cookie values.
        raise HTTPException(status_code=422, detail=f"Could not parse cookie export: {e}") from None


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Browser session not found")


@router.get("/sessions", response_model=List[BrowserSessionMetadata])
async def list_sessions(
    store: BrowserSessionStore = Depends(get_session_store),
) -> List[Dict[str, Any]]:
    """List saved logins (metadata only: domains, counts, expiry)."""
    return store.list_metadata()


@router.post("/sessions", response_model=BrowserSessionResponse, status_code=201)
async def create_session(
    request: BrowserSessionCreate,
    store: BrowserSessionStore = Depends(get_session_store),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> Dict[str, Any]:
    """Create a saved login from a pasted cookie export."""
    parsed = _parse(request.payload, request.format, request.domain)
    try:
        meta = store.create(
            request.name, parsed, persist_updates=request.persist_updates, enabled=True
        )
    except DuplicateSessionName as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    _audit(audit_repo, "create_browser_session", meta)
    return {"session": meta, "warnings": parsed.warnings}


@router.patch("/sessions/{session_id}", response_model=BrowserSessionResponse)
async def update_session(
    session_id: str,
    request: BrowserSessionUpdate,
    store: BrowserSessionStore = Depends(get_session_store),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> Dict[str, Any]:
    """Rename, enable/disable, toggle write-back, or replace the cookies of a saved login."""
    parsed = None
    if request.payload is not None:
        parsed = _parse(request.payload, request.format, request.domain)
    try:
        meta = store.update(
            session_id,
            name=request.name,
            enabled=request.enabled,
            persist_updates=request.persist_updates,
            parsed=parsed,
        )
    except DuplicateSessionName as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if meta is None:
        raise _not_found()
    _audit(audit_repo, "update_browser_session", meta)
    return {"session": meta, "warnings": parsed.warnings if parsed else []}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    store: BrowserSessionStore = Depends(get_session_store),
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
) -> Dict[str, str]:
    """Delete a saved login. (This does not log the session out on the website.)"""
    meta = store.get_metadata(session_id)
    if meta is None or not store.delete(session_id):
        raise _not_found()
    _audit(audit_repo, "delete_browser_session", meta)
    return {"status": "deleted"}


@router.post("/sessions/{session_id}/test", response_model=BrowserSessionTestResponse)
async def test_session(
    session_id: str,
    request: BrowserSessionTestRequest,
    browser_service: BrowserService = Depends(get_browser_service),
) -> Dict[str, Any]:
    """Open a page in a throwaway browser with only this login and report where it landed."""
    try:
        return await browser_service.test_session(session_id, request.url)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except BrowserSessionTestError as e:
        # Already scrubbed of cookie values by the service.
        raise HTTPException(status_code=502, detail=f"Could not load the page: {e}") from None
    except Exception as e:
        logger.error(f"Browser session test failed: {type(e).__name__}")
        raise HTTPException(
            status_code=502, detail=f"Could not load the page: {type(e).__name__}"
        ) from None
