"""Backup API for exporting and importing instance data."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from src.core.database import DatabaseManager
from src.core.dependencies import get_db_manager
from src.services.backup import BackupError, BackupService, parse_bundle, serialize_bundle
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
    """Export all instance data as a downloadable gzip-compressed JSON bundle.

    Request body: ``{"secret": "<instance ENCRYPTION_KEY>"}``.
    The downloaded file is ``open-assistant-backup.json.gz``; /api/backup/import
    accepts it as-is (plain JSON uploads are also accepted).
    """
    secret = (payload or {}).get("secret")
    if not secret or not isinstance(secret, str):
        raise HTTPException(status_code=400, detail="Request body must include 'secret'")
    try:
        bundle = service.export_data(secret)
    except BackupError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    return Response(
        content=serialize_bundle(bundle),
        media_type="application/gzip",
        headers={
            "Content-Disposition": 'attachment; filename="open-assistant-backup.json.gz"',
        },
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
        bundle_data = parse_bundle(await bundle.read())
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid bundle file: not JSON") from e
    try:
        summary = service.import_data(bundle_data, secret, mode=mode)
    except BackupError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "imported", **summary}
