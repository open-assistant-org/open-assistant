"""File upload API endpoint — saves user-uploaded files to /tmp/uploads/.

For images the response includes the base64-encoded content so the frontend
can pass it straight through to the chat endpoint's vision path.

For PDFs the endpoint attempts OCR via MistralOCRService (if configured) and
returns the extracted text so the frontend can inject it as message context.
"""

import base64
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["uploads"])

# Directory where uploaded files are stored.  /tmp is always writable and is
# the natural scratch space for ephemeral user-uploaded content.
UPLOAD_DIR = Path("/tmp/uploads")
# 50 MB hard limit per file
MAX_FILE_SIZE = 50 * 1024 * 1024

# MIME types we treat as images and send to the media/vision model
IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
}


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_mistral_ocr_service(request: Request):
    """Lazily resolve the MistralOCRService from the app's dependency graph."""
    try:
        from src.core.dependencies import get_mistral_ocr_service

        # Manually construct the service the same way the DI would
        from src.core.database import DatabaseManager
        from src.core.encryption import get_encryption_service
        from src.core.repositories.audit import AuditLogRepository
        from src.core.repositories.credentials import CredentialsRepository
        from src.core.repositories.settings import SettingsRepository
        from src.services.mistral_ocr import MistralOCRService

        db: DatabaseManager = request.app.state.db_manager
        enc = get_encryption_service()
        settings_repo = SettingsRepository(db)
        credentials_repo = CredentialsRepository(db, enc)
        audit_repo = AuditLogRepository(db)
        return MistralOCRService(settings_repo, credentials_repo, audit_repo)
    except Exception as exc:
        logger.debug(f"Could not instantiate MistralOCRService: {exc}")
        return None


def _try_ocr(request: Request, content: bytes, filename: str) -> Optional[str]:
    """Run Mistral OCR on *content* and return the extracted text, or None."""
    service = _get_mistral_ocr_service(request)
    if service is None:
        return None
    try:
        pdf_b64 = base64.b64encode(content).decode("ascii")
        result = service.extract_text_from_pdf(pdf_b64, filename)
        text = result.get("text", "").strip()
        return text if text else None
    except Exception as exc:
        logger.warning(f"OCR failed for {filename} (non-fatal): {exc}")
        return None


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    """Accept a multipart file upload, persist it under /tmp/uploads/, and
    return metadata the chat UI uses to enrich the message sent to the LLM.

    * **Images** – the response includes ``image_base64`` and ``image_mimetype``
      so the frontend can pass them to the ``/api/chat/stream`` endpoint, which
      forwards them to ``handle_message`` for vision processing via the
      configured media model.

    * **PDFs** – the endpoint tries Mistral OCR and returns ``ocr_text`` when
      successful; the frontend injects the extracted text as message context so
      the LLM can reason over the document without needing file-reading tools.

    * **Everything else** – only the saved path is returned; the frontend
      injects a path reference so the LLM can use ``python_execute`` /
      ``analyze_content`` to read the file.
    """
    _ensure_upload_dir()

    # Sanitise the original filename — strip directory components to prevent
    # path-traversal filenames like "../../etc/passwd".
    original_name = Path(file.filename or "upload").name or "upload"
    content_type: str = file.content_type or "application/octet-stream"

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
        f"size={len(content)}, content_type={content_type}"
    )

    response: Dict[str, Any] = {
        "filename": original_name,
        "saved_name": unique_name,
        "path": str(dest),
        "size": len(content),
        "content_type": content_type,
    }

    # ── Images: return base64 so the frontend can send it to the vision path ──
    base_mime = content_type.split(";")[0].strip()
    if base_mime in IMAGE_MIME_TYPES:
        response["image_base64"] = base64.b64encode(content).decode("ascii")
        response["image_mimetype"] = base_mime
        logger.info(f"Returning base64 image content for {original_name} ({base_mime})")

    # ── PDFs: attempt OCR and return extracted text ───────────────────────────
    elif base_mime == "application/pdf" or original_name.lower().endswith(".pdf"):
        logger.info(f"Attempting OCR for PDF: {original_name}")
        ocr_text = _try_ocr(request, content, original_name)
        if ocr_text:
            response["ocr_text"] = ocr_text
            response["ocr_available"] = True
            logger.info(
                f"OCR succeeded for {original_name}: {len(ocr_text)} chars extracted"
            )
        else:
            response["ocr_available"] = False
            logger.info(f"OCR unavailable or returned no text for {original_name}")

    return response
