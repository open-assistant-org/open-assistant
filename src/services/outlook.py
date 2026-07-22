"""Outlook service for email, calendar, and OneDrive operations."""

import re
import threading
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from dateutil import parser as dateutil_parser

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.outlook.auth import (
    AuthenticationRequiredException,
    complete_device_flow_background,
    get_outlook_token,
    refresh_outlook_token_proactively,
)
from src.integrations.outlook.client import OutlookClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)

_GRAPH_DATETIME_FMT = "%Y-%m-%dT%H:%M:%S"


def _apply_boundary(dt: datetime, boundary: str) -> datetime:
    """Apply a time-of-day to a bare date based on the filter boundary."""
    if boundary == "end":
        return dt.replace(hour=23, minute=59, second=59, microsecond=0)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _normalize_calendar_date(value: Optional[str], boundary: str = "start") -> Optional[str]:
    """Normalize a loose date term into a Graph-compatible ISO-8601 string.

    Microsoft Graph's OData ``$filter`` requires a strict ISO-8601 datetime
    (e.g. ``2026-07-15T00:00:00``). LLM tool calls frequently pass relative
    terms like ``"today"`` instead, which Graph rejects with a 400. This helper
    converts those terms into the exact format the calendar filter expects.

    Handles relative keywords (``now``, ``today``, ``tomorrow``, ``yesterday``,
    ``this week``) and any ``dateutil``-parsable date/datetime. Bare dates get a
    time-of-day from ``boundary``: ``"start"`` -> ``00:00:00``,
    ``"end"`` -> ``23:59:59``.

    Args:
        value: The date string to normalize. ``None`` is passed through.
        boundary: ``"start"`` or ``"end"`` — controls the time-of-day applied to
            bare dates and relative keywords.

    Returns:
        A ``"YYYY-MM-DDTHH:MM:SS"`` string (no timezone suffix, matching the
        existing filter format), or ``None`` if ``value`` is ``None``.

    Raises:
        ValueError: If the value cannot be parsed into a date.
    """
    if value is None:
        return None

    raw = value.strip()
    if not raw:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    keyword = raw.lower()

    # Relative keywords that dateutil cannot parse on its own.
    if keyword == "now":
        return now.strftime(_GRAPH_DATETIME_FMT)
    if keyword == "today":
        return _apply_boundary(now, boundary).strftime(_GRAPH_DATETIME_FMT)
    if keyword == "tomorrow":
        return _apply_boundary(now + timedelta(days=1), boundary).strftime(_GRAPH_DATETIME_FMT)
    if keyword == "yesterday":
        return _apply_boundary(now - timedelta(days=1), boundary).strftime(_GRAPH_DATETIME_FMT)
    if keyword in ("this week", "week"):
        target = now if boundary == "start" else now + timedelta(days=7)
        return _apply_boundary(target, boundary).strftime(_GRAPH_DATETIME_FMT)

    # Try strict ISO-8601 first (fast path, preserves explicit time-of-day).
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        # A bare date (e.g. "2026-07-15") parses to midnight — apply the
        # end-of-day boundary so end filters cover the whole day.
        if boundary == "end" and (dt.hour, dt.minute, dt.second) == (0, 0, 0) and "T" not in raw:
            dt = _apply_boundary(dt, boundary)
        return dt.strftime(_GRAPH_DATETIME_FMT)
    except (ValueError, AttributeError):
        pass

    # Fall back to fuzzy natural-language parsing.
    try:
        dt = dateutil_parser.parse(raw, fuzzy=True)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt.strftime(_GRAPH_DATETIME_FMT)
    except (ValueError, TypeError, OverflowError):
        pass

    raise ValueError(
        f"Could not parse date '{value}'. Use ISO-8601 like "
        f"'2026-07-15T00:00:00' or terms like 'today'/'tomorrow'."
    )


_BODY_TEXT_LIMIT = 1000


class _HTMLTextExtractor(HTMLParser):
    """Extracts plain text from HTML, skipping style/script blocks."""

    _SKIP_TAGS = frozenset({"style", "script", "head"})
    _BLOCK_TAGS = frozenset(
        {"p", "div", "br", "tr", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}
    )

    def __init__(self):
        super().__init__()
        self._parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag_lower in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _html_to_text(html_content: str) -> str:
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html_content)
    except Exception:
        # HTMLParser.feed may raise on severely malformed HTML; return partial extraction
        pass
    return extractor.get_text()


def _summarize_email(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact, LLM-friendly representation of a Graph API message object."""
    body = msg.get("body", {})
    content = body.get("content", "")
    content_type = body.get("contentType", "text").lower()

    body_text = _html_to_text(content) if content_type == "html" else content.strip()
    if len(body_text) > _BODY_TEXT_LIMIT:
        body_text = body_text[:_BODY_TEXT_LIMIT] + "..."

    def _addrs(recipients):
        return [
            r["emailAddress"]["address"]
            for r in (recipients or [])
            if r.get("emailAddress", {}).get("address")
        ]

    from_field = msg.get("from") or msg.get("sender") or {}
    from_addr = from_field.get("emailAddress", {})

    return {
        "id": msg.get("id", ""),
        "subject": msg.get("subject", ""),
        "receivedDateTime": msg.get("receivedDateTime", ""),
        "from": {
            "name": from_addr.get("name", ""),
            "address": from_addr.get("address", ""),
        },
        "bodyPreview": msg.get("bodyPreview", ""),
        "body_text": body_text,
        "hasAttachments": msg.get("hasAttachments", False),
        "toRecipients": _addrs(msg.get("toRecipients")),
        "ccRecipients": _addrs(msg.get("ccRecipients")),
    }


class OutlookService(BaseService):
    """Service for Outlook/Microsoft Graph integration."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_client(self) -> OutlookClient:
        """Get configured Outlook client."""
        enabled = self.settings_repo.get("outlook.enabled")
        if not enabled:
            raise ValueError("Outlook integration is not enabled")

        client_id = self.settings_repo.get("outlook.client_id")
        tenant_id = self.settings_repo.get("outlook.tenant_id") or "common"

        if not client_id:
            raise ValueError(
                "Outlook client ID not configured. Please set 'outlook.client_id' in Settings.\n"
                "Get this from Azure Portal -> App registrations -> Your app -> Overview -> Application (client) ID"
            )

        # Get client secret from settings (optional for public clients)
        # client_secret is sensitive and stored in credentials repo when set via UI
        client_secret = self.settings_repo.get("outlook.client_secret")
        if not client_secret:
            cred = self.credentials_repo.get("outlook")
            if cred:
                client_secret = cred.get("credential_data", {}).get("client_secret")
        # Treat empty string as None
        if client_secret == "":
            client_secret = None

        logger.info(f"Using {'Confidential' if client_secret else 'Public'} client for Outlook")

        # Get access token with persistent cache
        token_cache_path = "data/outlook_token_cache.json"

        try:
            token_result = get_outlook_token(
                client_id=client_id,
                client_secret=client_secret,
                tenant_id=tenant_id,
                token_cache_path=token_cache_path,
            )
            access_token = token_result["access_token"]
        except AuthenticationRequiredException as auth_ex:
            # Start background thread to complete device flow
            thread = threading.Thread(
                target=complete_device_flow_background,
                args=(client_id, client_secret, tenant_id, auth_ex.flow, token_cache_path),
                daemon=True,
            )
            thread.start()
            logger.info("Started background thread to complete device flow authentication")

            # Re-raise so user sees auth instructions in chat
            raise
        except Exception as e:
            logger.error(f"Failed to get Outlook token: {e}")
            raise ValueError(f"Failed to authenticate: {str(e)}")

        return OutlookClient(access_token=access_token)

    # Mail operations
    def read_emails(
        self,
        folder: str = "inbox",
        limit: int = 10,
        query: Optional[str] = None,
        summary_mode: bool = True,
    ) -> List[Dict[str, Any]]:
        client = self._get_client()
        if query:
            messages = client.search_emails(query=query, folder=folder, limit=limit)
        else:
            messages = client.list_messages(folder=folder, limit=limit)
        if summary_mode:
            return [_summarize_email(m) for m in messages]
        return messages

    def send_email(self, to: List[str], subject: str, body: str, **kwargs) -> bool:
        client = self._get_client()
        return client.send_email(to=to, subject=subject, body=body, **kwargs)

    # Calendar operations
    def list_calendars(self) -> List[Dict[str, Any]]:
        """
        List all Outlook calendars accessible to the user.

        Returns:
            List of calendar objects with id, name, and other metadata.
        """
        client = self._get_client()
        return client.list_calendars()

    def list_calendar_events(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        calendar_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List Outlook Calendar events.

        Args:
            start_date: Start date filter (ISO format). Defaults to now if not specified.
            end_date: End date filter (ISO format).
            limit: Maximum number of events.
            calendar_id: Calendar ID to list events from (default: user's default calendar).

        Returns:
            List of calendar events.
        """
        client = self._get_client()

        # Default to current time if start_date not specified (show only future events).
        # Otherwise normalize loose/relative terms (e.g. "today") into strict ISO-8601
        # so Microsoft Graph's OData $filter accepts them instead of returning a 400.
        if start_date is None:
            start_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        else:
            start_date = _normalize_calendar_date(start_date, boundary="start")
        end_date = _normalize_calendar_date(end_date, boundary="end")

        return client.list_events(
            start_date=start_date, end_date=end_date, limit=limit, calendar_id=calendar_id
        )

    def create_calendar_event(self, subject: str, start: str, end: str, **kwargs) -> Dict[str, Any]:
        client = self._get_client()
        return client.create_event(subject=subject, start=start, end=end, **kwargs)

    def update_calendar_event(self, event_id: str, **kwargs) -> Dict[str, Any]:
        """
        Update an Outlook calendar event.

        Args:
            event_id: Event ID to update
            **kwargs: Fields to update (subject, start, end, location, body, attendees, etc.)

        Returns:
            Updated event
        """
        client = self._get_client()
        return client.update_event(event_id=event_id, **kwargs)

    def delete_calendar_event(self, event_id: str) -> bool:
        """
        Delete an Outlook calendar event.

        Args:
            event_id: Event ID to delete

        Returns:
            True if deleted
        """
        client = self._get_client()
        return client.delete_event(event_id=event_id)

    # Additional mail operations
    def get_email(self, message_id: str) -> Dict[str, Any]:
        """
        Get a specific email by ID.

        Args:
            message_id: Outlook message ID

        Returns:
            Message object
        """
        client = self._get_client()
        return client.get_message(message_id=message_id)

    def search_emails(
        self, query: str, folder: str = "inbox", limit: int = 20, summary_mode: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search emails by query string.

        Args:
            query: Search query
            folder: Mail folder to search in
            limit: Maximum results
            summary_mode: When True, returns compact plain-text summaries instead of raw Graph payloads

        Returns:
            List of matching messages
        """
        client = self._get_client()
        messages = client.search_emails(query=query, folder=folder, limit=limit)
        if summary_mode:
            return [_summarize_email(m) for m in messages]
        return messages

    def create_draft(
        self,
        to: List[str],
        subject: str,
        body: str,
        body_type: str = "text",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create an email draft in Outlook.

        Args:
            to: Recipients
            subject: Email subject
            body: Email body
            body_type: Body type (text or html)
            cc: CC recipients
            bcc: BCC recipients

        Returns:
            Created draft
        """
        client = self._get_client()
        return client.create_draft(
            to=to, subject=subject, body=body, body_type=body_type, cc=cc, bcc=bcc
        )

    def get_attachment(
        self,
        message_id: str,
        attachment_id: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get an Outlook email attachment and extract text content where possible.

        Args:
            message_id: Outlook message ID
            attachment_id: Attachment ID
            filename: Original filename

        Returns:
            Dictionary with extracted text or metadata
        """
        import base64

        from src.services.document import extract_text_from_bytes

        client = self._get_client()
        result = client.get_attachment(message_id=message_id, attachment_id=attachment_id)

        content_bytes_b64 = result.get("contentBytes", "")
        file_data = base64.b64decode(content_bytes_b64) if content_bytes_b64 else b""

        att_name = filename or result.get("name", "")
        extracted = extract_text_from_bytes(file_data, att_name)

        return {
            "filename": att_name,
            "size": result.get("size", len(file_data)),
            "extracted_text": extracted["text"] if extracted["success"] else None,
            "format": extracted["format"],
            "message": extracted.get("message", ""),
        }

    def upload_file(
        self,
        folder_path: str,
        filename: str,
        content: Optional[str] = None,
        is_base64: bool = False,
        source_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to OneDrive.

        Args:
            folder_path: OneDrive folder path
            filename: File name
            content: File content (plain text or base64)
            is_base64: Whether content is base64-encoded
            source_path: Local file path to read and upload. Takes precedence over content.

        Returns:
            Created file metadata
        """
        import base64 as b64

        client = self._get_client()

        if source_path:
            with open(source_path, "rb") as f:
                file_bytes = f.read()
        elif is_base64:
            file_bytes = b64.b64decode(content or "")
        else:
            file_bytes = (content or "").encode("utf-8")

        return client.upload_file(folder_path=folder_path, filename=filename, content=file_bytes)

    # OneDrive operations
    def list_files(self, folder_path: str = "/") -> List[Dict[str, Any]]:
        client = self._get_client()
        return client.list_files(folder_path=folder_path)

    def search_files(self, query: str) -> List[Dict[str, Any]]:
        client = self._get_client()
        return client.search_files(query=query)

    def read_file(
        self,
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Read file content from OneDrive by ID or path, with text extraction.

        Accepts either file_id or file_path (at least one required).
        Downloads the file bytes, then extracts text for supported formats
        (.md, .txt, .json, .csv, .docx, .xlsx, .pdf, etc.).

        For PDF files, uses Mistral OCR for text extraction.
        For XLSX files, extracts cell data from all sheets.

        Args:
            file_id: OneDrive file ID
            file_path: OneDrive file path (e.g. '/Obsidian/vault/Note.md')

        Returns:
            Dict with filename, size, extracted_text, format, and message
        """
        import base64

        from src.services.document import extract_text_from_bytes

        if not file_id and not file_path:
            return {
                "success": False,
                "error": "Either file_id or file_path is required",
            }

        client = self._get_client()

        # Resolve filename from metadata
        if file_id:
            metadata = client.get_file_metadata(file_id)
            file_bytes = client.read_file(file_id=file_id)
        else:
            metadata = client.get_file_metadata_by_path(file_path)
            file_bytes = client.read_file_by_path(file_path=file_path)

        filename = metadata.get("name", file_path or file_id or "unknown")
        size = metadata.get("size", len(file_bytes))

        # Extract text content
        extracted = extract_text_from_bytes(file_bytes, filename)

        # If extraction failed for PDF, try Mistral OCR
        if not extracted["success"] and extracted["format"] == "pdf":
            try:
                from src.services.mistral_ocr import MistralOCRService

                ocr_service = MistralOCRService(
                    self.settings_repo, self.credentials_repo, self.audit_repo
                )
                pdf_base64 = base64.b64encode(file_bytes).decode("utf-8")
                ocr_result = ocr_service.extract_text_from_pdf(
                    pdf_base64=pdf_base64, filename=filename
                )
                logger.info(
                    f"PDF OCR extraction successful for {filename}: "
                    f"{ocr_result['char_count']} chars"
                )
                return {
                    "filename": filename,
                    "size": size,
                    "extracted_text": ocr_result["text"],
                    "format": "pdf",
                    "message": f"Extracted via Mistral OCR ({ocr_result['char_count']} chars)",
                }
            except Exception as ocr_err:
                logger.error(f"Mistral OCR failed for {filename}: {ocr_err}")
                return {
                    "filename": filename,
                    "size": size,
                    "extracted_text": None,
                    "format": "pdf",
                    "message": f"PDF extraction failed: {str(ocr_err)}. "
                    "Ensure Mistral OCR is configured (mistral_ocr.api_key or llm.api_key).",
                }

        return {
            "filename": filename,
            "size": size,
            "extracted_text": extracted["text"] if extracted["success"] else None,
            "format": extracted["format"],
            "message": extracted.get("message", ""),
        }

    def download_file(self, file_id: str, destination: str) -> None:
        """
        Download file from OneDrive to local storage.

        Args:
            file_id: OneDrive file ID
            destination: Local path to save file
        """
        client = self._get_client()
        client.download_file(file_id=file_id, destination=destination)

    def refresh_credentials(self) -> Dict[str, Any]:
        """
        Proactively refresh Outlook tokens to prevent expiry during idle periods.

        This method should be called periodically (e.g., via a scheduled job) to keep
        the MSAL token cache alive. It performs a silent token acquisition which
        refreshes the access token and extends the refresh token's lifetime.

        Returns:
            Dictionary with refresh status and message
        """
        enabled = self.settings_repo.get("outlook.enabled")
        if not enabled:
            return {
                "service_name": "outlook",
                "status": "skipped",
                "message": "Outlook integration is not enabled",
            }

        client_id = self.settings_repo.get("outlook.client_id")
        if not client_id:
            return {
                "service_name": "outlook",
                "status": "skipped",
                "message": "Outlook client ID not configured",
            }

        tenant_id = self.settings_repo.get("outlook.tenant_id") or "common"

        # Get client secret from settings (optional for public clients)
        # client_secret is sensitive and stored in credentials repo when set via UI
        client_secret = self.settings_repo.get("outlook.client_secret")
        if not client_secret:
            cred = self.credentials_repo.get("outlook")
            if cred:
                client_secret = cred.get("credential_data", {}).get("client_secret")
        if client_secret == "":
            client_secret = None

        token_cache_path = "data/outlook_token_cache.json"

        try:
            success = refresh_outlook_token_proactively(
                client_id=client_id,
                client_secret=client_secret,
                tenant_id=tenant_id,
                token_cache_path=token_cache_path,
            )

            if success:
                return {
                    "service_name": "outlook",
                    "status": "success",
                    "message": "Token refreshed successfully",
                }
            else:
                return {
                    "service_name": "outlook",
                    "status": "warning",
                    "message": "Token refresh failed — no cached account or refresh token expired. "
                    "Re-authentication may be required.",
                }
        except Exception as e:
            logger.error(f"Outlook token refresh failed: {e}")
            return {
                "service_name": "outlook",
                "status": "error",
                "message": f"Token refresh error: {str(e)}",
            }

    def test_connection(self) -> Dict[str, Any]:
        try:
            client = self._get_client()
            client.list_messages(limit=1)
            return {
                "service_name": "outlook",
                "status": "success",
                "message": "Connection successful",
            }
        except ValueError as e:
            return {"service_name": "outlook", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Outlook connection test failed: {e}")
            return {
                "service_name": "outlook",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }

    # ========================================================================
    # ONENOTE OPERATIONS
    # ========================================================================

    def list_notebooks(self, include_sections: bool = False) -> List[Dict[str, Any]]:
        """List all OneNote notebooks with optional sections."""
        client = self._get_client()
        return client.list_notebooks(include_sections=include_sections)

    def get_notebook(self, notebook_id: str) -> Dict[str, Any]:
        """Get a specific notebook."""
        client = self._get_client()
        return client.get_notebook(notebook_id)

    def list_sections(self, notebook_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List sections, optionally filtered by notebook."""
        client = self._get_client()
        return client.list_sections(notebook_id=notebook_id)

    def get_section(self, section_id: str) -> Dict[str, Any]:
        """Get a specific section."""
        client = self._get_client()
        return client.get_section(section_id)

    def list_pages(
        self,
        section_id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        limit: int = 20,
        include_content: bool = False,
    ) -> List[Dict[str, Any]]:
        """List pages with optional filtering."""
        client = self._get_client()
        return client.list_pages(
            section_id=section_id,
            notebook_id=notebook_id,
            limit=limit,
            include_content=include_content,
        )

    def get_page(self, page_id: str, include_content: bool = True) -> Dict[str, Any]:
        """Get page with optional content."""
        client = self._get_client()
        return client.get_page(page_id, include_content=include_content)

    def create_page(self, section_id: str, title: str, content: str) -> Dict[str, Any]:
        """Create a new OneNote page."""
        client = self._get_client()
        return client.create_page(section_id=section_id, title=title, content=content)

    def update_page(self, page_id: str, content: str) -> Dict[str, Any]:
        """Update page content."""
        client = self._get_client()
        return client.update_page(page_id=page_id, content=content)

    def delete_page(self, page_id: str) -> bool:
        """Delete a page."""
        client = self._get_client()
        return client.delete_page(page_id)

    def search_onenote(
        self,
        query: str,
        section_id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search OneNote pages by title, optionally within a section or notebook."""
        client = self._get_client()
        return client.search_pages(
            query=query,
            section_id=section_id,
            notebook_id=notebook_id,
            limit=limit,
        )

    def copy_page(self, page_id: str, target_section_id: str) -> Dict[str, Any]:
        """Copy a page to another section."""
        client = self._get_client()
        return client.copy_page(page_id=page_id, target_section_id=target_section_id)

    def extract_page_text(self, page_id: str) -> Dict[str, Any]:
        """Extract plain text from a page."""
        client = self._get_client()
        return client.extract_page_text(page_id=page_id)

    def create_page_from_markdown(
        self, section_id: str, title: str, markdown_content: str
    ) -> Dict[str, Any]:
        """Create a page from Markdown."""
        client = self._get_client()
        return client.create_page_from_markdown(
            section_id=section_id,
            title=title,
            markdown_content=markdown_content,
        )

    # ========================================================================
    # MICROSOFT TO DO OPERATIONS
    # ========================================================================

    def list_todo_lists(self) -> List[Dict[str, Any]]:
        """List all Microsoft To Do task lists."""
        client = self._get_client()
        return client.list_todo_lists()

    def get_todo_list(self, list_id: str) -> Dict[str, Any]:
        """Get a specific To Do task list."""
        client = self._get_client()
        return client.get_todo_list(list_id)

    def create_todo_list(self, display_name: str) -> Dict[str, Any]:
        """Create a new To Do task list."""
        client = self._get_client()
        return client.create_todo_list(display_name=display_name)

    def delete_todo_list(self, list_id: str) -> bool:
        """Delete a To Do task list."""
        client = self._get_client()
        return client.delete_todo_list(list_id)

    def list_todo_tasks(
        self,
        list_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List tasks in a To Do task list."""
        client = self._get_client()
        return client.list_todo_tasks(list_id=list_id, status=status, limit=limit)

    def get_todo_task(self, list_id: str, task_id: str) -> Dict[str, Any]:
        """Get a specific To Do task."""
        client = self._get_client()
        return client.get_todo_task(list_id=list_id, task_id=task_id)

    def create_todo_task(
        self,
        list_id: str,
        title: str,
        body: Optional[str] = None,
        due_date: Optional[str] = None,
        importance: str = "normal",
        reminder_date_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new task in a To Do task list."""
        client = self._get_client()
        return client.create_todo_task(
            list_id=list_id,
            title=title,
            body=body,
            due_date=due_date,
            importance=importance,
            reminder_date_time=reminder_date_time,
        )

    def update_todo_task(
        self,
        list_id: str,
        task_id: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        due_date: Optional[str] = None,
        importance: Optional[str] = None,
        status: Optional[str] = None,
        reminder_date_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing To Do task."""
        client = self._get_client()
        return client.update_todo_task(
            list_id=list_id,
            task_id=task_id,
            title=title,
            body=body,
            due_date=due_date,
            importance=importance,
            status=status,
            reminder_date_time=reminder_date_time,
        )

    def delete_todo_task(self, list_id: str, task_id: str) -> bool:
        """Delete a To Do task."""
        client = self._get_client()
        return client.delete_todo_task(list_id=list_id, task_id=task_id)

    def create_page_from_template(
        self,
        section_id: str,
        template: str,
        title: str,
        variables: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a page from a predefined template."""
        client = self._get_client()

        # Define templates
        templates = {
            "meeting_notes": """<h1>{title}</h1>
<h2>Meeting Details</h2>
<ul>
<li><b>Date:</b> {date}</li>
<li><b>Attendees:</b> {attendees}</li>
</ul>
<h2>Agenda</h2>
<ol>
<li>Agenda item 1</li>
<li>Agenda item 2</li>
</ol>
<h2>Notes</h2>
<p>Meeting notes go here...</p>
<h2>Action Items</h2>
<ul>
<li>[ ] Action item 1 - @owner</li>
<li>[ ] Action item 2 - @owner</li>
</ul>""",
            "daily_journal": """<h1>{title}</h1>
<h2>Date: {date}</h2>
<h3>Goals for Today</h3>
<ul>
<li>Goal 1</li>
<li>Goal 2</li>
</ul>
<h3>Notes</h3>
<p>Today's notes...</p>
<h3>Reflections</h3>
<p>What went well? What could improve?</p>""",
            "todo": """<h1>{title}</h1>
<h2>To-Do List</h2>
<h3>High Priority</h3>
<ul>
<li>[ ] Urgent task 1</li>
<li>[ ] Urgent task 2</li>
</ul>
<h3>Medium Priority</h3>
<ul>
<li>[ ] Task 1</li>
<li>[ ] Task 2</li>
</ul>
<h3>Low Priority</h3>
<ul>
<li>[ ] Task 1</li>
</ul>""",
            "project": """<h1>{title}</h1>
<h2>Project Overview</h2>
<p>Brief description of the project...</p>
<h2>Objectives</h2>
<ul>
<li>Objective 1</li>
<li>Objective 2</li>
</ul>
<h2>Timeline</h2>
<ul>
<li><b>Phase 1:</b> Description - Due date</li>
<li><b>Phase 2:</b> Description - Due date</li>
</ul>
<h2>Resources</h2>
<ul>
<li>Resource 1</li>
</ul>
<h2>Notes</h2>
<p>Project notes...</p>""",
        }

        if template not in templates:
            raise ValueError(f"Unknown template: {template}. Available: {list(templates.keys())}")

        # Build content with variables
        content = templates[template]
        default_vars = {"title": title, "date": "{{date}}"}

        if variables:
            default_vars.update(variables)

        # Replace variables
        for key, value in default_vars.items():
            content = content.replace("{" + key + "}", value)

        # Replace {{date}} with current date
        from datetime import datetime

        content = content.replace("{{date}}", datetime.now().strftime("%Y-%m-%d"))

        return client.create_page(section_id=section_id, title=title, content=content)
