"""Mistral OCR service for PDF text extraction."""

import base64
from typing import Any, Dict

from mistralai import Mistral

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MistralOCRService:
    """Service for Mistral OCR text extraction from PDFs."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: AuditLogRepository,
    ):
        """
        Initialize Mistral OCR service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository
        """
        self.settings_repo = settings_repo
        self.credentials_repo = credentials_repo
        self.audit_repo = audit_repo

    def _get_config(self) -> Dict[str, Any]:
        """
        Get Mistral OCR configuration from settings.

        Returns:
            Dictionary with API key, base URL, and model
        """
        # Get Mistral-specific API key, fallback to main LLM API key
        mistral_api_key = None

        # Try credentials repository first
        creds = self.credentials_repo.get("mistral_ocr")
        if creds:
            mistral_api_key = creds.get("credential_data", {}).get("api_key")

        # Fallback to settings
        if not mistral_api_key:
            mistral_api_key = self.settings_repo.get("mistral_ocr.api_key")

        # If still no Mistral key, try main LLM API key from credentials
        if not mistral_api_key:
            llm_creds = self.credentials_repo.get("llm")
            if llm_creds:
                mistral_api_key = llm_creds.get("credential_data", {}).get("api_key")

        # Final fallback to LLM settings
        if not mistral_api_key:
            mistral_api_key = self.settings_repo.get("llm.api_key")

        base_url = self.settings_repo.get("mistral_ocr.base_url") or "https://api.mistral.ai"
        model = self.settings_repo.get("mistral_ocr.model") or "mistral-ocr-latest"

        return {
            "api_key": mistral_api_key,
            "base_url": base_url,
            "model": model,
        }

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Mistral OCR API connection by verifying credentials.

        Returns:
            Dictionary with test results
        """
        try:
            config = self._get_config()

            if not config["api_key"]:
                return {
                    "service_name": "mistral_ocr",
                    "status": "error",
                    "message": "No API key configured. Set mistral_ocr.api_key or llm.api_key.",
                }

            # Initialize Mistral client
            client = Mistral(
                api_key=config["api_key"],
                server_url=config["base_url"],
            )

            # Test by listing models (lightweight API call)
            try:
                models = client.models.list()
                # Check if OCR model exists in the response
                model_ids = [m.id for m in models.data]
                has_ocr = config["model"] in model_ids or any("ocr" in m.lower() for m in model_ids)

                if has_ocr or config["model"] in model_ids:
                    return {
                        "service_name": "mistral_ocr",
                        "status": "success",
                        "message": f"Connection successful. Model '{config['model']}' available.",
                    }
                else:
                    return {
                        "service_name": "mistral_ocr",
                        "status": "warning",
                        "message": f"API key valid, but model '{config['model']}' not found. Check model name.",
                    }
            except Exception as api_error:
                # If models.list() fails, it might be a custom endpoint
                # Return success with a warning
                logger.warning(f"Could not list models, but API key appears valid: {api_error}")
                return {
                    "service_name": "mistral_ocr",
                    "status": "warning",
                    "message": "API key appears valid. Model availability could not be verified.",
                }

        except Exception as e:
            logger.error(f"Mistral OCR connection test failed: {e}", exc_info=True)
            return {
                "service_name": "mistral_ocr",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }

    def extract_text_from_pdf(self, pdf_base64: str, filename: str) -> Dict[str, Any]:
        """
        Extract text from a PDF using Mistral OCR.

        Args:
            pdf_base64: Base64-encoded PDF content
            filename: Original filename

        Returns:
            Dictionary with extracted text and metadata
        """
        try:
            config = self._get_config()

            if not config["api_key"]:
                raise ValueError("No API key configured for Mistral OCR")

            # Initialize Mistral client
            client = Mistral(
                api_key=config["api_key"],
                server_url=config["base_url"],
            )

            logger.info(f"[MistralOCR] Starting OCR extraction for {filename}")

            # Upload the file first to get a file_id
            import base64

            pdf_bytes = base64.b64decode(pdf_base64)

            # Upload the file to Mistral with proper structure
            logger.info(f"[MistralOCR] Uploading file to Mistral: {filename}")
            upload_result = client.files.upload(
                file={
                    "file_name": filename,
                    "content": pdf_bytes,
                    "content_type": "application/pdf",
                },
                purpose="ocr",
            )
            file_id = upload_result.id
            logger.info(f"[MistralOCR] File uploaded, ID: {file_id}")

            try:
                # Process the PDF with OCR using the file_id
                result = client.ocr.process(
                    model=config["model"],
                    document={
                        "type": "file",
                        "file_id": file_id,
                    },
                )

                # Extract text from the result
                # The response structure may vary, so we'll handle multiple formats
                extracted_text = ""

                if hasattr(result, "text"):
                    extracted_text = result.text
                elif hasattr(result, "content"):
                    extracted_text = result.content
                elif isinstance(result, dict):
                    extracted_text = result.get("text", "") or result.get("content", "")
                elif hasattr(result, "pages"):
                    # If paginated response, concatenate all pages
                    pages = result.pages if isinstance(result.pages, list) else [result.pages]
                    extracted_text = "\n\n".join(
                        page.text if hasattr(page, "text") else str(page) for page in pages
                    )

                # Log audit entry
                self.audit_repo.log_event(
                    event_type="api_call",
                    action="mistral_ocr_extract",
                    success=True,
                    service_name="mistral_ocr",
                    details={
                        "filename": filename,
                        "model": config["model"],
                        "text_length": len(extracted_text),
                    },
                )

                logger.info(
                    f"[MistralOCR] Extracted {len(extracted_text)} characters from {filename}"
                )

                return {
                    "text": extracted_text,
                    "filename": filename,
                    "model": config["model"],
                    "char_count": len(extracted_text),
                }
            finally:
                # Clean up: delete the uploaded file from Mistral
                try:
                    client.files.delete(file_id=file_id)
                    logger.info(f"[MistralOCR] Cleaned up file {file_id}")
                except Exception as cleanup_err:
                    logger.warning(f"[MistralOCR] Failed to delete file {file_id}: {cleanup_err}")

        except Exception as e:
            logger.error(f"[MistralOCR] Extraction failed for {filename}: {e}", exc_info=True)
            raise
