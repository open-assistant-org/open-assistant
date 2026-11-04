"""Backup API for exporting and importing instance data."""

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from src.core.config import init_config
from src.core.database import DatabaseManager
from src.core.dependencies import get_db_manager
from src.services.backup import BackupError, BackupService, parse_bundle, serialize_bundle
from src.utils.logger import get_logger

logger = get_logger(__name__)



def _block_on_managed_instances() -> None:
    """Backup bundles contain every credential, which managed-instance users
    must never be able to read. Treat the endpoints as non-existent there."""
    if os.getenv("MANAGED_API_KEY"):
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(
    prefix="/api/backup",
    tags=["backup"],
    dependencies=[Depends(_block_on_managed_instances)],
)


def get_backup_service(
    db: DatabaseManager = Depends(get_db_manager),
) -> BackupService:
    return BackupService(db, data_dir=init_config().general.data_dir)


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
        # Key derivation, DB dump and compression are CPU/IO heavy: keep them
        # off the event loop so the rest of the app stays responsive.
        content = await run_in_threadpool(lambda: serialize_bundle(service.export_data(secret)))
    except BackupError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    return Response(
        content=content,
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

    ``mode``: ``fail`` (default) aborts if the target holds data that is not in
    the bundle; ``overwrite`` clears included tables first. Restart the
    instance afterwards so schedulers and plugin/MCP tools pick up the data.
    """
    if mode not in ("fail", "overwrite"):
        raise HTTPException(status_code=400, detail="mode must be 'fail' or 'overwrite'")
    raw = await bundle.read()
    try:
        bundle_data = await run_in_threadpool(parse_bundle, raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid bundle file: not JSON") from e
    try:
        summary = await run_in_threadpool(service.import_data, bundle_data, secret, mode)
    except BackupError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    for warning in summary["warnings"]:
        logger.warning(f"Backup import: {warning}")
    return {"status": "imported", **summary}
