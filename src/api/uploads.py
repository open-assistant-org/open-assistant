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

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.core.dependencies import get_audit_repo, get_credentials_repo, get_settings_repo
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


def get_optional_ocr_service(
    settings_repo=Depends(get_settings_repo),
    credentials_repo=Depends(get_credentials_repo),
    audit_repo=Depends(get_audit_repo),
):
    """FastAPI dependency that returns MistralOCRService when the package and
    credentials are available, or None when they are not.

    The caller just checks ``if ocr_service is None`` — no exception handling
    needed at the call site.
    """
    try:
        from src.services.mistral_ocr import MistralOCRService

        return MistralOCRService(settings_repo, credentials_repo, audit_repo)
    except Exception as exc:
        logger.debug(f"MistralOCRService unavailable (non-fatal): {exc}")
        return None


def _try_ocr(ocr_service, content: bytes, filename: str) -> Optional[str]:
    """Run OCR on PDF bytes. Returns extracted text or None on any failure."""
    if ocr_service is None:
        return None
    try:
        pdf_b64 = base64.b64encode(content).decode("ascii")
        result = ocr_service.extract_text_from_pdf(pdf_b64, filename)
        text = result.get("text", "").strip()
        return text if text else None
    except Exception as exc:
        logger.warning(f"OCR failed for {filename} (non-fatal): {exc}")
        return None


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    ocr_service=Depends(get_optional_ocr_service),
) -> Dict[str, Any]:
    """Accept a multipart file upload, persist it under /tmp/uploads/, and
    return metadata the chat UI uses to enrich the message sent to the LLM.

    * **Images** – response includes ``image_base64`` + ``image_mimetype``
      for the frontend to pass to the vision path.
    * **PDFs** – attempts Mistral OCR; returns ``ocr_text`` on success.
    * **Everything else** – returns the saved path for tool-based access.
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

    # ── Images: return base64 so the frontend can pass it to the vision path ─
    base_mime = content_type.split(";")[0].strip()
    if base_mime in IMAGE_MIME_TYPES:
        response["image_base64"] = base64.b64encode(content).decode("ascii")
        response["image_mimetype"] = base_mime
        logger.info(f"Returning base64 image content for {original_name} ({base_mime})")

    # ── PDFs: attempt OCR and return extracted text ───────────────────────────
    elif base_mime == "application/pdf" or original_name.lower().endswith(".pdf"):
        logger.info(f"Attempting OCR for PDF: {original_name}")
        ocr_text = _try_ocr(ocr_service, content, original_name)
        if ocr_text:
            response["ocr_text"] = ocr_text
            response["ocr_available"] = True
            logger.info(f"OCR succeeded for {original_name}: {len(ocr_text)} chars extracted")
        else:
            response["ocr_available"] = False
            logger.info(f"OCR unavailable or returned no text for {original_name}")

    return response
