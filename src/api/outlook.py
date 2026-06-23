"""Outlook API endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from src.core.dependencies import get_credentials_repo, get_settings_repo
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.outlook import *
from src.services.outlook import OutlookService
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/outlook", tags=["outlook"])


def get_outlook_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> OutlookService:
    return OutlookService(settings_repo, credentials_repo)


@router.post("/emails/read")
async def read_emails(
    request: ReadEmailsRequest, outlook_service: OutlookService = Depends(get_outlook_service)
) -> List[Dict[str, Any]]:
    try:
        return outlook_service.read_emails(
            folder=request.folder, limit=request.limit, query=request.query
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emails/send")
async def send_email(
    request: SendEmailRequest, outlook_service: OutlookService = Depends(get_outlook_service)
) -> Dict[str, str]:
    try:
        outlook_service.send_email(
            to=request.to,
            subject=request.subject,
            body=request.body,
            body_type=request.body_type,
            cc=request.cc,
            bcc=request.bcc,
        )
        return {"message": "Email sent successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calendar/events/list")
async def list_events(
    request: ListEventsRequest, outlook_service: OutlookService = Depends(get_outlook_service)
) -> List[Dict[str, Any]]:
    try:
        return outlook_service.list_calendar_events(
            start_date=request.start_date, end_date=request.end_date, limit=request.limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calendar/events/create")
async def create_event(
    request: CreateEventRequest, outlook_service: OutlookService = Depends(get_outlook_service)
) -> Dict[str, Any]:
    try:
        return outlook_service.create_calendar_event(
            subject=request.subject,
            start=request.start,
            end=request.end,
            timezone=request.timezone,
            location=request.location,
            body=request.body,
            attendees=request.attendees,
            is_online_meeting=request.is_online_meeting,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files/list")
async def list_files(
    request: ListFilesRequest, outlook_service: OutlookService = Depends(get_outlook_service)
) -> List[Dict[str, Any]]:
    try:
        return outlook_service.list_files(folder_path=request.folder_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files/search")
async def search_files(
    request: SearchFilesRequest, outlook_service: OutlookService = Depends(get_outlook_service)
) -> List[Dict[str, Any]]:
    try:
        return outlook_service.search_files(query=request.query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-connection", response_model=OutlookConnectionTestResponse)
async def test_connection(
    outlook_service: OutlookService = Depends(get_outlook_service),
) -> OutlookConnectionTestResponse:
    result = outlook_service.test_connection()
    return OutlookConnectionTestResponse(**result)
