"""Audio transcription and document text extraction service."""

import base64
import tempfile
import os
from typing import Optional

from openai import OpenAI

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Map audio MIME types to Whisper-supported file extensions
# Whisper supports: flac, m4a, mp3, mp4, mpeg, mpga, oga, ogg, wav, webm
AUDIO_MIME_TO_EXT = {
    # OGG/Opus (common for WhatsApp, Slack voice messages)
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/oga": ".oga",
    # MP3/MPEG
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mpeg3": ".mp3",
    "audio/x-mpeg": ".mp3",
    "audio/x-mp3": ".mp3",
    # MP4/M4A
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/x-mp4": ".m4a",
    # WAV
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    # WebM
    "audio/webm": ".webm",
    # FLAC
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
}

# Extensions supported by Whisper API
WHISPER_SUPPORTED_EXTENSIONS = {
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".oga",
    ".ogg",
    ".wav",
    ".webm",
}

# MIME types recognised as extractable documents (DOCX only - PDFs use Mistral OCR)
DOCUMENT_MIMETYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
}

# PDF MIME type (handled separately via Mistral OCR)
PDF_MIMETYPE = "application/pdf"


def is_audio_mimetype(mimetype: str) -> bool:
    """Check if a MIME type is an audio type."""
    if not mimetype:
        return False
    return mimetype.split(";")[0].strip().startswith("audio/")


def is_image_mimetype(mimetype: str) -> bool:
    """Check if a MIME type is an image type."""
    if not mimetype:
        return False
    return mimetype.split(";")[0].strip().startswith("image/")


def is_pdf_mimetype(mimetype: str) -> bool:
    """Check if a MIME type is a PDF document."""
    if not mimetype:
        return False
    return mimetype.split(";")[0].strip() == PDF_MIMETYPE


def is_document_mimetype(mimetype: str) -> bool:
    """Check if a MIME type is a supported document type (DOCX only - PDFs handled separately)."""
    if not mimetype:
        return False
    return mimetype.split(";")[0].strip() in DOCUMENT_MIMETYPES


def transcribe_audio(
    audio_base64: str,
    mimetype: str,
    api_key: str,
    base_url: Optional[str] = None,
    model: str = "whisper-1",
    language: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Transcribe audio using OpenAI Whisper API.

    Args:
        audio_base64: Base64-encoded audio data
        mimetype: Audio MIME type (e.g. audio/ogg)
        api_key: OpenAI API key
        base_url: Optional base URL override (for compatible APIs)
        model: Whisper model to use
        language: Optional language hint (ISO 639-1 code)
        filename: Optional original filename to extract extension from

    Returns:
        Transcribed text

    Raises:
        ValueError: If transcription fails
    """
    # Determine file extension: try MIME type first, then filename, then default
    base_mime = mimetype.split(";")[0].strip()
    ext = AUDIO_MIME_TO_EXT.get(base_mime) or AUDIO_MIME_TO_EXT.get(mimetype)

    # If MIME type didn't give us a valid extension, try the filename
    if not ext or ext not in WHISPER_SUPPORTED_EXTENSIONS:
        if filename:
            _, name_ext = os.path.splitext(filename)
            if name_ext and name_ext.lower() in WHISPER_SUPPORTED_EXTENSIONS:
                ext = name_ext.lower()

    # Final fallback: use .mp3 as a generic audio container (most APIs handle it)
    if not ext:
        logger.warning(f"Unknown audio MIME type '{mimetype}', defaulting to .mp3")
        ext = ".mp3"

    # Decode base64 audio to a temp file (Whisper API requires a file)
    audio_bytes = base64.b64decode(audio_base64)
    logger.info(f"Transcribing audio: {len(audio_bytes)} bytes, mimetype={mimetype}, ext={ext}")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Call Whisper API
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        with open(tmp_path, "rb") as audio_file:
            kwargs = {"model": model, "file": audio_file}
            if language:
                kwargs["language"] = language
            transcription = client.audio.transcriptions.create(**kwargs)

        text = transcription.text.strip()
        logger.info(f"Transcription result: {len(text)} chars")
        return text

    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}", exc_info=True)
        raise ValueError(f"Audio transcription failed: {e}") from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Document text extraction (PDF, DOCX)
# ---------------------------------------------------------------------------


def extract_document_text(
    doc_base64: str,
    mimetype: str,
    max_chars: int = 50_000,
) -> str:
    """
    Extract text from a DOCX document.

    Note: PDFs are now handled separately via Mistral OCR in the WhatsApp handler.

    Args:
        doc_base64: Base64-encoded document data
        mimetype: Document MIME type (DOCX only)
        max_chars: Maximum characters to return (truncates with notice)

    Returns:
        Extracted plain text

    Raises:
        ValueError: If extraction fails or unsupported document type
    """
    base_mime = mimetype.split(";")[0].strip()
    doc_bytes = base64.b64decode(doc_base64)
    logger.info(f"Extracting text from document: {len(doc_bytes)} bytes, mimetype={base_mime}")

    try:
        if base_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text = _extract_docx_text(doc_bytes)
        else:
            raise ValueError(
                f"Unsupported document type: {base_mime}. PDFs are handled via Mistral OCR."
            )

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[...truncated, {len(text)} total characters]"

        logger.info(f"Document text extracted: {len(text)} chars")
        return text

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Document text extraction failed: {e}", exc_info=True)
        raise ValueError(f"Document text extraction failed: {e}") from e


def _extract_docx_text(docx_bytes: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    import io
    from docx import Document

    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    if not paragraphs:
        raise ValueError("DOCX contains no extractable text")

    return "\n\n".join(paragraphs)
