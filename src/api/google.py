"""Google API endpoints for email operations."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import get_credentials_repo, get_settings_repo
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.google import (
    CreateDraftRequest,
    DraftResponse,
    EmailResponse,
    GoogleConnectionTestResponse,
    GetEmailRequest,
    LabelResponse,
    ReadEmailsRequest,
    SearchEmailsRequest,
    SendEmailRequest,
)
from src.services.google import GoogleService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/google", tags=["google"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


def get_google_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> GoogleService:
    """Get Google service with dependencies."""
    return GoogleService(settings_repo, credentials_repo)


# ============================================================================
# EMAIL READING
# ============================================================================


@router.post("/emails/read")
async def read_emails(
    request: ReadEmailsRequest, google_service: GoogleService = Depends(get_google_service)
) -> List[EmailResponse]:
    """
    Read emails matching filter.

    Args:
        request: Read emails request
        google_service: Google service (injected)

    Returns:
        List of emails

    Raises:
        HTTPException: If reading fails
    """
    try:
        emails = google_service.read_emails(filter=request.filter, limit=request.limit)

        return [EmailResponse(**email) for email in emails]

    except ValueError as e:
        logger.error(f"Invalid Google configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to read emails: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read emails: {str(e)}")


@router.post("/emails/search")
async def search_emails(
    request: SearchEmailsRequest, google_service: GoogleService = Depends(get_google_service)
) -> List[EmailResponse]:
    """
    Search emails with query.

    Args:
        request: Search request
        google_service: Google service (injected)

    Returns:
        List of matching emails

    Raises:
        HTTPException: If search fails
    """
    try:
        emails = google_service.search_emails(query=request.query, limit=request.limit)

        return [EmailResponse(**email) for email in emails]

    except ValueError as e:
        logger.error(f"Invalid Google configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to search emails: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/emails/{message_id}")
async def get_email(
    message_id: str, google_service: GoogleService = Depends(get_google_service)
) -> EmailResponse:
    """
    Get specific email by ID.

    Args:
        message_id: Gmail message ID
        google_service: Google service (injected)

    Returns:
        Email message

    Raises:
        HTTPException: If email not found
    """
    try:
        email = google_service.get_email(message_id=message_id)
        return EmailResponse(**email)

    except ValueError as e:
        logger.error(f"Invalid Google configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get email: {e}")
        raise HTTPException(status_code=404, detail=f"Email not found: {str(e)}")


# ============================================================================
# EMAIL COMPOSITION
# ============================================================================


@router.post("/drafts/create", response_model=DraftResponse)
async def create_draft(
    request: CreateDraftRequest, google_service: GoogleService = Depends(get_google_service)
) -> DraftResponse:
    """
    Create email draft.

    Args:
        request: Draft creation request
        google_service: Google service (injected)

    Returns:
        Created draft

    Raises:
        HTTPException: If creation fails
    """
    try:
        draft = google_service.create_draft(
            to=request.to,
            subject=request.subject,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
            html=request.html,
        )

        return DraftResponse(**draft)

    except ValueError as e:
        logger.error(f"Invalid Google configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create draft: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create draft: {str(e)}")


@router.post("/emails/send")
async def send_email(
    request: SendEmailRequest, google_service: GoogleService = Depends(get_google_service)
) -> EmailResponse:
    """
    Send email.

    Args:
        request: Send email request
        google_service: Google service (injected)

    Returns:
        Sent message

    Raises:
        HTTPException: If sending fails
    """
    try:
        message = google_service.send_email(
            to=request.to,
            subject=request.subject,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
            html=request.html,
        )

        return EmailResponse(**message)

    except ValueError as e:
        logger.error(f"Invalid Google configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


# ============================================================================
# LABELS
# ============================================================================


@router.get("/labels")
async def get_labels(
    google_service: GoogleService = Depends(get_google_service),
) -> List[LabelResponse]:
    """
    Get Gmail labels.

    Args:
        google_service: Google service (injected)

    Returns:
        List of labels

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        labels = google_service.get_labels()
        return [LabelResponse(**label) for label in labels]

    except ValueError as e:
        logger.error(f"Invalid Google configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get labels: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get labels: {str(e)}")


# ============================================================================
# CONNECTION TESTING
# ============================================================================


@router.post("/test-connection", response_model=GoogleConnectionTestResponse)
async def test_connection(
    google_service: GoogleService = Depends(get_google_service),
) -> GoogleConnectionTestResponse:
    """
    Test Google connection.

    Args:
        google_service: Google service (injected)

    Returns:
        Connection test result
    """
    result = google_service.test_connection()
    return GoogleConnectionTestResponse(**result)
