"""Backup API for exporting and importing instance data."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from src.core.database import DatabaseManager
from src.core.dependencies import get_db_manager
from src.services.backup import BackupError, BackupService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])


def get_backup_service(
    db: DatabaseManager = Depends(get_db_manager),
) -> BackupService:
    return BackupService(db)


@router.post("/export")
async def export_data(
    payload: dict,
    service: BackupService = Depends(get_backup_service),
):
    """Export all instance data as a downloadable JSON bundle.

    Request body: ``{"secret": "<instance ENCRYPTION_KEY>"}``.
    The returned bundle can be imported on another instance via /api/backup/import.
    """
    secret = (payload or {}).get("secret")
    if not secret or not isinstance(secret, str):
        raise HTTPException(status_code=400, detail="Request body must include 'secret'")
    try:
        bundle = service.export_data(secret)
    except BackupError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    filename = "open-assistant-backup.json"
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_data(
    bundle: UploadFile = File(...),
    secret: str = Form(...),
    mode: str = Form("fail"),
    service: BackupService = Depends(get_backup_service),
):
    """Import a previously exported bundle into this instance.

    ``mode``: ``fail`` (default) aborts if any included table already contains
    rows; ``overwrite`` clears included tables first.
    """
    try:
        bundle_data = json.loads((await bundle.read()).decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid bundle file: not JSON") from e
    try:
        summary = service.import_data(bundle_data, secret, mode=mode)
    except BackupError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "imported", **summary}
