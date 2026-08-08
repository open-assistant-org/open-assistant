"""File upload API endpoint — saves user-uploaded files to /tmp/uploads/."""

import os
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["uploads"])

# Directory where uploaded files are stored.  /tmp is always writable and is
# the natural scratch space for ephemeral user-uploaded content.
UPLOAD_DIR = Path("/tmp/uploads")
# 50 MB hard limit per file
MAX_FILE_SIZE = 50 * 1024 * 1024


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Accept a multipart file upload, persist it under /tmp/uploads/, and
    return the saved path so the chat UI can inject it into the message context.

    The assistant can then reference the path when using tools such as
    ``python_execute`` or ``analyze_content`` that can read local files.
    """
    _ensure_upload_dir()

    # Sanitise the original filename — strip directory components and keep only
    # the base name so path-traversal filenames like "../../etc/passwd" are safe.
    original_name = Path(file.filename or "upload").name or "upload"

    # Prefix with a short UUID so concurrent uploads of the same filename never
    # collide and the path is not guessable by third parties on the same host.
    unique_name = f"{uuid.uuid4().hex[:12]}-{original_name}"
    dest = UPLOAD_DIR / unique_name

    try:
        content = await file.read()
    except Exception as exc:
        logger.error(f"Failed to read uploaded file: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail="Could not read uploaded file.")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    try:
        dest.write_bytes(content)
    except Exception as exc:
        logger.error(f"Failed to write uploaded file to {dest}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    logger.info(
        f"File uploaded: original={original_name}, saved={dest}, "
        f"size={len(content)}, content_type={file.content_type}"
    )

    return {
        "filename": original_name,
        "saved_name": unique_name,
        "path": str(dest),
        "size": len(content),
        "content_type": file.content_type or "application/octet-stream",
    }
