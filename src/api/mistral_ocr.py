"""Mistral OCR API endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.core.dependencies import get_mistral_ocr_service
from src.services.mistral_ocr import MistralOCRService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/mistral-ocr", tags=["mistral_ocr"])


class OCRExtractRequest(BaseModel):
    """Request model for OCR extraction."""

    pdf_base64: str
    filename: str = "document.pdf"


@router.post("/test-connection")
async def test_connection(
    mistral_ocr_service: MistralOCRService = Depends(get_mistral_ocr_service),
) -> Dict[str, Any]:
    """
    Test Mistral OCR API connection.

    Args:
        mistral_ocr_service: Mistral OCR service (injected)

    Returns:
        Connection test result
    """
    return mistral_ocr_service.test_connection()


@router.post("/extract")
async def extract_text(
    request: OCRExtractRequest,
    mistral_ocr_service: MistralOCRService = Depends(get_mistral_ocr_service),
) -> Dict[str, Any]:
    """
    Extract text from a PDF using Mistral OCR.

    Args:
        request: OCR extraction request
        mistral_ocr_service: Mistral OCR service (injected)

    Returns:
        Extraction result with text and metadata
    """
    try:
        result = mistral_ocr_service.extract_text_from_pdf(
            pdf_base64=request.pdf_base64,
            filename=request.filename,
        )
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
        }
