"""Media processing service for messaging channels (WhatsApp, Slack, etc.).

Handles processing of various media types:
- Audio files (Whisper transcription)
- Images (Vision LLM description)
- PDF documents (Mistral OCR + storage)
- DOCX documents (text extraction)
"""

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from src.services.mistral_ocr import MistralOCRService
from src.services.nextcloud import NextcloudService
from src.services.notion import NotionService
from src.services.settings import SettingsService
from src.services.transcription import extract_document_text, transcribe_audio
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MediaProcessingResult:
    """Result of media processing."""

    effective_message: str  # Text representation for LLM
    note_url: Optional[str] = None  # URL to saved note/file (if applicable)
    image_base64: Optional[str] = None  # Image data for vision LLM
    image_mimetype: Optional[str] = None  # Image MIME type


class MediaHandler:
    """Handles processing of media attachments from messaging channels."""

    def __init__(
        self,
        settings_service: SettingsService,
        mistral_ocr_service: MistralOCRService,
        nextcloud_service: NextcloudService,
        notion_service: NotionService,
        channel: str = "WhatsApp",
    ):
        """
        Initialize media handler.

        Args:
            settings_service: Settings service for configuration
            mistral_ocr_service: Mistral OCR service for PDF processing
            nextcloud_service: Nextcloud service for file storage
            notion_service: Notion service for note creation
            channel: Channel name for logging and storage paths (e.g. "WhatsApp", "Slack")
        """
        self.settings = settings_service
        self.mistral_ocr = mistral_ocr_service
        self.nextcloud = nextcloud_service
        self.notion = notion_service
        self.channel = channel

    def process_media(
        self,
        media_data: str,
        mimetype: str,
        filename: Optional[str],
        caption: Optional[str],
        contact_id: str,
    ) -> MediaProcessingResult:
        """
        Process media based on type.

        Args:
            media_data: Base64-encoded media data
            mimetype: Media MIME type
            filename: Original filename
            caption: Optional caption/message with media
            contact_id: Contact identifier for the messaging channel

        Returns:
            MediaProcessingResult with processed content
        """
        if self._is_audio(mimetype):
            return self._process_audio(media_data, mimetype, filename, caption, contact_id)
        elif self._is_image(mimetype):
            return self._process_image(media_data, mimetype, caption)
        elif self._is_pdf(mimetype):
            return self._process_pdf(media_data, filename or "document.pdf", caption)
        elif self._is_docx(mimetype):
            return self._process_docx(media_data, filename or "document.docx", caption)
        else:
            # Unknown media type
            logger.warning(f"Unknown media type: {mimetype}")
            return MediaProcessingResult(effective_message=caption or "[Unsupported media type]")

    def _is_audio(self, mimetype: str) -> bool:
        """Check if MIME type is audio."""
        return mimetype.split(";")[0].strip().startswith("audio/")

    def _is_image(self, mimetype: str) -> bool:
        """Check if MIME type is image."""
        return mimetype.split(";")[0].strip().startswith("image/")

    def _is_pdf(self, mimetype: str) -> bool:
        """Check if MIME type is PDF."""
        return mimetype.split(";")[0].strip() == "application/pdf"

    def _is_docx(self, mimetype: str) -> bool:
        """Check if MIME type is DOCX."""
        return (
            mimetype.split(";")[0].strip()
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def _process_audio(
        self,
        audio_base64: str,
        mimetype: str,
        filename: Optional[str],
        caption: Optional[str],
        contact_id: str,
    ) -> MediaProcessingResult:
        """
        Process audio file with Whisper transcription.

        Args:
            audio_base64: Base64-encoded audio
            mimetype: Audio MIME type
            filename: Original filename (for extension detection)
            caption: Optional caption
            contact_id: Contact identifier for the messaging channel

        Returns:
            MediaProcessingResult with transcription
        """
        whisper_enabled = self.settings.get_config_with_fallback("whisper.enabled", False)
        if not whisper_enabled:
            logger.info("Whisper not enabled, skipping audio transcription")
            return MediaProcessingResult(effective_message=caption or "[Audio message received]")

        logger.info(f"[{self.channel}] Processing audio message with Whisper")

        try:
            # Get Whisper configuration
            api_key = self.settings.get_config_with_fallback(
                "whisper.api_key", ""
            ) or self.settings.get_config_with_fallback("llm.api_key")
            base_url = self.settings.get_config_with_fallback("whisper.base_url", "") or None
            model = self.settings.get_config_with_fallback("whisper.model", "whisper-1")

            # Transcribe
            transcription = transcribe_audio(
                audio_base64=audio_base64,
                mimetype=mimetype,
                api_key=api_key,
                base_url=base_url,
                model=model,
                filename=filename,
            )
            logger.info(f"[{self.channel}] Audio transcribed: {len(transcription)} chars")

            # Build effective message
            if caption:
                effective_message = (
                    f"[Voice message transcription]: {transcription}\n\n[Caption]: {caption}"
                )
            else:
                effective_message = f"[Voice message transcription]: {transcription}"

            # Save transcription to Notion/Nextcloud
            note_url = self._save_transcription_note(transcription, caption, contact_id)

            return MediaProcessingResult(
                effective_message=effective_message,
                note_url=note_url,
            )

        except Exception as e:
            logger.error(f"[{self.channel}] Audio transcription failed: {e}", exc_info=True)
            return MediaProcessingResult(
                effective_message=caption or "[Audio message received but transcription failed]"
            )

    def _process_image(
        self,
        image_base64: str,
        mimetype: str,
        caption: Optional[str],
    ) -> MediaProcessingResult:
        """
        Process image with vision LLM.

        Args:
            image_base64: Base64-encoded image
            mimetype: Image MIME type
            caption: Optional caption

        Returns:
            MediaProcessingResult with image data for LLM
        """
        logger.info(f"[{self.channel}] Processing image message for vision")

        # Return image data for vision LLM processing
        # The actual vision processing happens later in the LLM call
        effective_message = caption or "[Image attached]"

        return MediaProcessingResult(
            effective_message=effective_message,
            image_base64=image_base64,
            image_mimetype=mimetype,
        )

    def _process_pdf(
        self,
        pdf_base64: str,
        filename: str,
        caption: Optional[str],
    ) -> MediaProcessingResult:
        """
        Process PDF with Mistral OCR and save to Nextcloud/Notion.

        Args:
            pdf_base64: Base64-encoded PDF
            filename: PDF filename
            caption: Optional caption/question

        Returns:
            MediaProcessingResult with extracted text and note URL
        """
        logger.info(f"[{self.channel}] Processing PDF document with Mistral OCR")

        try:
            # 1. Extract text via Mistral OCR
            ocr_result = self.mistral_ocr.extract_text_from_pdf(
                pdf_base64=pdf_base64,
                filename=filename,
            )
            pdf_text = ocr_result["text"]
            logger.info(f"[{self.channel}] OCR extracted: {len(pdf_text)} chars")

            # 2. Save PDF file to Nextcloud
            pdf_bytes = base64.b64decode(pdf_base64)
            safe_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            docs_folder = f"/{self.channel}_Documents"
            nextcloud_path = f"{docs_folder}/{safe_ts}_{filename}"

            file_url = self._upload_to_nextcloud(
                path=nextcloud_path,
                content=pdf_bytes,
                folder=docs_folder,
            )

            # 3. Create Notion note with extracted text + file link
            note_url = self._create_pdf_note(
                filename=filename,
                pdf_text=pdf_text,
                file_url=file_url,
                safe_ts=safe_ts,
            )

            # 4. Build effective message
            if caption:
                effective_message = f"{caption}\n\n[PDF Document: {filename}]\n{pdf_text}"
            else:
                effective_message = f"[PDF Document: {filename}]\n\n{pdf_text}"

            return MediaProcessingResult(
                effective_message=effective_message,
                note_url=note_url,
            )

        except Exception as e:
            logger.error(f"[{self.channel}] PDF OCR processing failed: {e}", exc_info=True)
            return MediaProcessingResult(
                effective_message=caption or "[A PDF was sent but could not be processed]"
            )

    def _process_docx(
        self,
        docx_base64: str,
        filename: str,
        caption: Optional[str],
    ) -> MediaProcessingResult:
        """
        Process DOCX document with python-docx.

        Args:
            docx_base64: Base64-encoded DOCX
            filename: DOCX filename
            caption: Optional caption

        Returns:
            MediaProcessingResult with extracted text
        """
        logger.info(f"[{self.channel}] Processing DOCX document")

        try:
            doc_text = extract_document_text(
                doc_base64=docx_base64,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            logger.info(f"[{self.channel}] DOCX text extracted: {len(doc_text)} chars")

            if caption:
                effective_message = f"{caption}\n\n[Document: {filename}]\n{doc_text}"
            else:
                effective_message = f"[Document: {filename}]\n{doc_text}"

            return MediaProcessingResult(effective_message=effective_message)

        except Exception as e:
            logger.error(f"[{self.channel}] DOCX extraction failed: {e}", exc_info=True)
            return MediaProcessingResult(
                effective_message=caption or "[A DOCX document was sent but could not be read]"
            )

    def _upload_to_nextcloud(
        self,
        path: str,
        content: bytes,
        folder: str,
    ) -> Optional[str]:
        """
        Upload file to Nextcloud.

        Args:
            path: Remote file path
            content: File content (bytes)
            folder: Folder path to ensure exists

        Returns:
            Public URL to file, or None if upload failed
        """
        try:
            # Ensure folder exists
            try:
                self.nextcloud.create_folder(folder)
            except Exception:
                pass  # Folder may already exist

            self.nextcloud.upload_file(remote_path=path, content=content)

            # Build URL
            nc_url = self.settings.get_config_with_fallback("nextcloud.url", "")
            if nc_url:
                filename = path.split("/")[-1]
                folder_name = folder.split("/")[-1]
                return f"{nc_url.rstrip('/')}/apps/files/" f"?dir=/{folder_name}&file={filename}"
            else:
                return f"Nextcloud: {path}"

        except Exception as e:
            logger.warning(f"[{self.channel}] Nextcloud upload failed: {e}")
            return None

    def _create_pdf_note(
        self,
        filename: str,
        pdf_text: str,
        file_url: Optional[str],
        safe_ts: str,
    ) -> Optional[str]:
        """
        Create Notion note with PDF content.

        Args:
            filename: PDF filename
            pdf_text: Extracted text
            file_url: URL to PDF file in Nextcloud
            safe_ts: Timestamp string

        Returns:
            Note URL, or None if creation failed
        """
        try:
            from src.core.repositories.settings import SettingsRepository

            # Get database ID from settings (need direct access to settings repo)
            # This is a bit awkward - might need to pass settings_repo to constructor
            database_id = self.settings.settings_repo.get("mistral_ocr.notion_database_id")
            if not database_id:
                database_id = self.settings.settings_repo.get("notion.database_id")

            if not database_id:
                raise ValueError("No Notion database ID configured")

            timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            note_content = f"**Source:** {self.channel}\n**Date:** {timestamp_str}\n"
            if file_url:
                note_content += f"**File:** {file_url}\n"
            note_content += f"\n---\n\n## Extracted Text\n\n"

            # Limit total note size (Notion will auto-chunk paragraphs)
            if len(pdf_text) > 20000:
                note_content += pdf_text[:20000]
                note_content += f"\n\n*[...truncated, {len(pdf_text)} total chars. See attached PDF for full content]*"
            else:
                note_content += pdf_text

            notion_page = self.notion.create_note(
                title=f"{self.channel}: {filename}",
                content=note_content,
                database_id=database_id,
            )
            note_url = notion_page.get("url")
            logger.info(f"[{self.channel}] Notion note created: {note_url}")
            return note_url

        except Exception as notion_err:
            logger.warning(
                f"[{self.channel}] Notion creation failed, falling back to Nextcloud: {notion_err}"
            )

            # Fallback: Save text file to Nextcloud
            try:
                text_filename = filename.replace(".pdf", ".txt")
                docs_folder = f"/{self.channel}_Documents"
                nextcloud_text_path = f"{docs_folder}/{safe_ts}_{text_filename}"
                self.nextcloud.upload_file(
                    remote_path=nextcloud_text_path,
                    content=pdf_text,
                )

                nc_url = self.settings.get_config_with_fallback("nextcloud.url", "")
                if nc_url:
                    return (
                        f"{nc_url.rstrip('/')}/apps/files/"
                        f"?dir={docs_folder}&file={safe_ts}_{text_filename}"
                    )
                else:
                    return f"Nextcloud: {nextcloud_text_path}"

            except Exception as nc_text_err:
                logger.error(
                    f"[{self.channel}] Nextcloud text fallback failed: {nc_text_err}",
                    exc_info=True,
                )
                logger.warning(
                    f"[{self.channel}] Both Notion and Nextcloud storage failed. "
                    "PDF text extracted but not saved to external storage."
                )
                return None

    def _save_transcription_note(
        self,
        transcription: str,
        caption: Optional[str],
        contact_id: str,
    ) -> Optional[str]:
        """
        Save audio transcription to Notion/Nextcloud.

        Args:
            transcription: Transcribed text
            caption: Optional caption
            contact_id: Contact identifier for the messaging channel

        Returns:
            Note URL, or None if saving failed
        """
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        note_title = f"Voice Note - {timestamp_str}"
        note_content = f"**Transcription:**\n\n{transcription}"
        if caption:
            note_content += f"\n\n**Caption:** {caption}"

        # Try Notion first
        try:
            notion_page = self.notion.create_note(
                title=note_title,
                content=note_content,
            )
            saved_url = notion_page.get("url")
            logger.info(f"[{self.channel}] Transcription saved to Notion: {saved_url}")
            return saved_url

        except Exception as notion_err:
            logger.warning(f"[{self.channel}] Notion save failed, trying Nextcloud: {notion_err}")

            # Fallback: save as markdown file on Nextcloud
            try:
                safe_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                nc_path = f"/Voice Notes/voice_note_{safe_ts}.md"
                md_content = f"# {note_title}\n\n{note_content}"

                return self._upload_to_nextcloud(
                    path=nc_path,
                    content=md_content.encode("utf-8"),
                    folder="/Voice Notes",
                )

            except Exception as nc_err:
                logger.error(
                    f"[{self.channel}] Nextcloud fallback also failed: {nc_err}",
                    exc_info=True,
                )
                return None


# Backward-compatible alias
WhatsAppMediaHandler = MediaHandler
