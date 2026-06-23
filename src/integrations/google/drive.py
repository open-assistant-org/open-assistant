"""Google Drive, Docs, Sheets, and Slides API client."""

import io
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.utils.logger import get_logger

logger = get_logger(__name__)

# MIME types for Google native formats
GOOGLE_DOCS_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEETS_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES_MIME = "application/vnd.google-apps.presentation"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"

# Export MIME types for native Google files
EXPORT_MIME_MAP = {
    GOOGLE_DOCS_MIME: "text/plain",
    GOOGLE_SHEETS_MIME: "text/csv",
    GOOGLE_SLIDES_MIME: "text/plain",
}


class GoogleDriveClient:
    """Client for Google Drive, Docs, Sheets, and Slides APIs."""

    def __init__(self, credentials: Credentials):
        """
        Initialize the Google Drive client.

        Args:
            credentials: Google OAuth credentials with Drive/Docs/Sheets/Slides scopes
        """
        self.credentials = credentials
        self.drive = build("drive", "v3", credentials=credentials)
        self.docs = build("docs", "v1", credentials=credentials)
        self.sheets = build("sheets", "v4", credentials=credentials)
        self.slides = build("slides", "v1", credentials=credentials)
        logger.info("GoogleDriveClient initialized (Drive + Docs + Sheets + Slides)")

    # ========================================================================
    # DRIVE FILE OPERATIONS
    # ========================================================================

    def list_files(
        self,
        folder_id: Optional[str] = None,
        max_results: int = 50,
        file_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List files and folders in Google Drive.

        Args:
            folder_id: Parent folder ID (None = root / My Drive)
            max_results: Maximum number of files to return
            file_types: Optional list of MIME types to filter by

        Returns:
            List of file metadata dicts
        """
        try:
            query_parts = ["trashed = false"]

            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            else:
                query_parts.append("'root' in parents")

            if file_types:
                type_conditions = " or ".join(f"mimeType = '{t}'" for t in file_types)
                query_parts.append(f"({type_conditions})")

            query = " and ".join(query_parts)

            results = (
                self.drive.files()
                .list(
                    q=query,
                    pageSize=max_results,
                    fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink)",
                )
                .execute()
            )

            files = results.get("files", [])
            logger.info(f"Listed {len(files)} files from Drive folder={folder_id or 'root'}")
            return self._format_files(files)

        except HttpError as e:
            logger.error(f"Failed to list Drive files: {e}")
            raise

    def search_files(
        self,
        query: str,
        max_results: int = 30,
        file_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for files in Google Drive by name or full-text content.

        Args:
            query: Search query (searches file name and content)
            max_results: Maximum number of results
            file_type: Optional MIME type filter (e.g. 'application/vnd.google-apps.document')

        Returns:
            List of matching file metadata dicts
        """
        try:
            query_parts = ["trashed = false"]

            # Build search query: name contains OR full-text
            safe_q = query.replace("'", "\\'")
            query_parts.append(f"(name contains '{safe_q}' or fullText contains '{safe_q}')")

            if file_type:
                query_parts.append(f"mimeType = '{file_type}'")

            q = " and ".join(query_parts)

            results = (
                self.drive.files()
                .list(
                    q=q,
                    pageSize=max_results,
                    fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink)",
                )
                .execute()
            )

            files = results.get("files", [])
            logger.info(f"Found {len(files)} files matching '{query}'")
            return self._format_files(files)

        except HttpError as e:
            logger.error(f"Failed to search Drive files: {e}")
            raise

    def get_file(self, file_id: str) -> Dict[str, Any]:
        """
        Get metadata for a specific file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dict
        """
        try:
            file = (
                self.drive.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink, description",
                )
                .execute()
            )
            logger.info(f"Retrieved Drive file metadata: {file_id}")
            return self._format_file(file)

        except HttpError as e:
            logger.error(f"Failed to get Drive file {file_id}: {e}")
            raise

    def read_file(self, file_id: str) -> Dict[str, Any]:
        """
        Read/export file content from Google Drive.

        For Google-native files (Docs, Sheets, Slides), exports as text/CSV.
        For binary files, returns a truncated text representation.

        Args:
            file_id: Google Drive file ID

        Returns:
            Dict with 'content' (str), 'mime_type', 'name', 'format'
        """
        try:
            # Get file metadata first
            meta = (
                self.drive.files().get(fileId=file_id, fields="id, name, mimeType, size").execute()
            )
            name = meta.get("name", "")
            mime_type = meta.get("mimeType", "")

            # Native Google formats: export as text
            export_mime = EXPORT_MIME_MAP.get(mime_type)
            if export_mime:
                response = self.drive.files().export(fileId=file_id, mimeType=export_mime).execute()
                if isinstance(response, bytes):
                    content = response.decode("utf-8", errors="replace")
                else:
                    content = str(response)

                logger.info(f"Exported native Google file {file_id} as {export_mime}")
                return {
                    "file_id": file_id,
                    "name": name,
                    "mime_type": mime_type,
                    "export_format": export_mime,
                    "content": content,
                }

            # Regular files: download and attempt text decode
            request = self.drive.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            from googleapiclient.http import MediaIoBaseDownload

            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            raw_bytes = buf.getvalue()

            # Attempt text decode
            try:
                content = raw_bytes.decode("utf-8")
                fmt = "text"
            except UnicodeDecodeError:
                # Binary file — try to extract text via document service
                from src.services.document import extract_text_from_bytes

                extracted = extract_text_from_bytes(raw_bytes, name)
                if extracted.get("success"):
                    content = extracted["text"]
                    fmt = extracted.get("format", "binary")
                else:
                    content = f"[Binary file: {name}, size={len(raw_bytes)} bytes. Cannot display as text.]"
                    fmt = "binary"

            logger.info(f"Read Drive file {file_id} ({name}): {len(content)} chars")
            return {
                "file_id": file_id,
                "name": name,
                "mime_type": mime_type,
                "export_format": fmt,
                "content": content,
            }

        except HttpError as e:
            logger.error(f"Failed to read Drive file {file_id}: {e}")
            raise

    # ========================================================================
    # GOOGLE DOCS OPERATIONS
    # ========================================================================

    def docs_create(self, title: str, content: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new Google Doc.

        Args:
            title: Document title
            content: Optional initial text content

        Returns:
            Created document metadata with document_id
        """
        try:
            doc = self.docs.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]
            logger.info(f"Created Google Doc: {doc_id} ({title})")

            if content:
                self._docs_insert_text(doc_id, content)

            return {
                "document_id": doc_id,
                "title": doc.get("title"),
                "url": f"https://docs.google.com/document/d/{doc_id}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to create Google Doc: {e}")
            raise

    def docs_get(self, document_id: str) -> Dict[str, Any]:
        """
        Get content of a Google Doc as plain text.

        Args:
            document_id: Google Doc document ID

        Returns:
            Dict with document title, content, and metadata
        """
        try:
            doc = self.docs.documents().get(documentId=document_id).execute()
            title = doc.get("title", "")
            content = self._extract_doc_text(doc)

            logger.info(f"Retrieved Google Doc: {document_id} ({len(content)} chars)")
            return {
                "document_id": document_id,
                "title": title,
                "content": content,
                "url": f"https://docs.google.com/document/d/{document_id}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to get Google Doc {document_id}: {e}")
            raise

    def docs_append(self, document_id: str, content: str) -> Dict[str, Any]:
        """
        Append text content to an existing Google Doc.

        Args:
            document_id: Google Doc document ID
            content: Text to append

        Returns:
            Updated document metadata
        """
        try:
            self._docs_insert_text(document_id, content, at_end=True)
            logger.info(f"Appended text to Google Doc: {document_id}")
            return {
                "document_id": document_id,
                "status": "appended",
                "chars_added": len(content),
                "url": f"https://docs.google.com/document/d/{document_id}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to append to Google Doc {document_id}: {e}")
            raise

    def docs_update(self, document_id: str, content: str) -> Dict[str, Any]:
        """
        Replace all content in a Google Doc with new text.

        Args:
            document_id: Google Doc document ID
            content: New text content (replaces everything)

        Returns:
            Updated document metadata
        """
        try:
            # Get current doc to find end index
            doc = self.docs.documents().get(documentId=document_id).execute()
            body = doc.get("body", {})
            end_index = body.get("content", [{}])[-1].get("endIndex", 1)

            requests = []

            # Delete all existing content (keep last newline, index 1 to end-1)
            if end_index > 2:
                requests.append(
                    {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}}
                )

            # Insert new content at beginning
            requests.append({"insertText": {"location": {"index": 1}, "text": content}})

            self.docs.documents().batchUpdate(
                documentId=document_id, body={"requests": requests}
            ).execute()

            logger.info(f"Updated content of Google Doc: {document_id}")
            return {
                "document_id": document_id,
                "status": "updated",
                "url": f"https://docs.google.com/document/d/{document_id}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to update Google Doc {document_id}: {e}")
            raise

    # ========================================================================
    # GOOGLE SHEETS OPERATIONS
    # ========================================================================

    def sheets_create(self, title: str, sheet_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Create a new Google Sheets spreadsheet.

        Args:
            title: Spreadsheet title
            sheet_names: Optional list of sheet tab names (default: Sheet1)

        Returns:
            Created spreadsheet metadata with spreadsheet_id
        """
        try:
            body: Dict[str, Any] = {"properties": {"title": title}}

            if sheet_names:
                body["sheets"] = [{"properties": {"title": name}} for name in sheet_names]

            spreadsheet = self.sheets.spreadsheets().create(body=body).execute()
            sid = spreadsheet["spreadsheetId"]
            logger.info(f"Created Google Sheet: {sid} ({title})")

            return {
                "spreadsheet_id": sid,
                "title": title,
                "sheets": [s["properties"]["title"] for s in spreadsheet.get("sheets", [])],
                "url": f"https://docs.google.com/spreadsheets/d/{sid}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to create Google Sheet: {e}")
            raise

    def sheets_get(self, spreadsheet_id: str) -> Dict[str, Any]:
        """
        Get metadata and sheet names for a spreadsheet.

        Args:
            spreadsheet_id: Spreadsheet ID

        Returns:
            Dict with spreadsheet title, sheet names, and URL
        """
        try:
            spreadsheet = (
                self.sheets.spreadsheets()
                .get(spreadsheetId=spreadsheet_id, includeGridData=False)
                .execute()
            )

            sheets = []
            for s in spreadsheet.get("sheets", []):
                props = s.get("properties", {})
                grid = props.get("gridProperties", {})
                sheets.append(
                    {
                        "title": props.get("title"),
                        "sheet_id": props.get("sheetId"),
                        "rows": grid.get("rowCount"),
                        "columns": grid.get("columnCount"),
                    }
                )

            logger.info(f"Retrieved Google Sheet metadata: {spreadsheet_id}")
            return {
                "spreadsheet_id": spreadsheet_id,
                "title": spreadsheet.get("properties", {}).get("title"),
                "sheets": sheets,
                "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to get Google Sheet {spreadsheet_id}: {e}")
            raise

    def sheets_read(
        self,
        spreadsheet_id: str,
        range_notation: str,
    ) -> Dict[str, Any]:
        """
        Read values from a Google Sheet range.

        Args:
            spreadsheet_id: Spreadsheet ID
            range_notation: A1 notation range (e.g. 'Sheet1!A1:D10' or 'A1:D10')

        Returns:
            Dict with values as list of rows (each row is a list of cell values)
        """
        try:
            result = (
                self.sheets.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_notation)
                .execute()
            )

            values = result.get("values", [])
            logger.info(
                f"Read {len(values)} rows from Sheet {spreadsheet_id} range {range_notation}"
            )
            return {
                "spreadsheet_id": spreadsheet_id,
                "range": result.get("range"),
                "rows": len(values),
                "values": values,
            }

        except HttpError as e:
            logger.error(f"Failed to read Google Sheet {spreadsheet_id}: {e}")
            raise

    def sheets_write(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
    ) -> Dict[str, Any]:
        """
        Write values to a Google Sheet range.

        Args:
            spreadsheet_id: Spreadsheet ID
            range_notation: A1 notation range (e.g. 'Sheet1!A1')
            values: List of rows, each row is a list of cell values

        Returns:
            Update result metadata
        """
        try:
            result = (
                self.sheets.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_notation,
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                )
                .execute()
            )

            logger.info(f"Wrote {result.get('updatedCells')} cells to Sheet {spreadsheet_id}")
            return {
                "spreadsheet_id": spreadsheet_id,
                "updated_range": result.get("updatedRange"),
                "updated_rows": result.get("updatedRows"),
                "updated_columns": result.get("updatedColumns"),
                "updated_cells": result.get("updatedCells"),
            }

        except HttpError as e:
            logger.error(f"Failed to write Google Sheet {spreadsheet_id}: {e}")
            raise

    def sheets_append(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
    ) -> Dict[str, Any]:
        """
        Append rows to a Google Sheet (after the last row with data).

        Args:
            spreadsheet_id: Spreadsheet ID
            range_notation: A1 notation range to find the table (e.g. 'Sheet1!A1')
            values: List of rows to append

        Returns:
            Append result metadata
        """
        try:
            result = (
                self.sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_notation,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": values},
                )
                .execute()
            )

            updates = result.get("updates", {})
            logger.info(f"Appended {len(values)} rows to Sheet {spreadsheet_id}")
            return {
                "spreadsheet_id": spreadsheet_id,
                "updated_range": updates.get("updatedRange"),
                "updated_rows": updates.get("updatedRows"),
                "updated_cells": updates.get("updatedCells"),
            }

        except HttpError as e:
            logger.error(f"Failed to append to Google Sheet {spreadsheet_id}: {e}")
            raise

    # ========================================================================
    # GOOGLE SLIDES OPERATIONS
    # ========================================================================

    def slides_create(self, title: str) -> Dict[str, Any]:
        """
        Create a new Google Slides presentation.

        Args:
            title: Presentation title

        Returns:
            Created presentation metadata with presentation_id
        """
        try:
            presentation = self.slides.presentations().create(body={"title": title}).execute()
            pid = presentation["presentationId"]
            logger.info(f"Created Google Slides presentation: {pid} ({title})")

            return {
                "presentation_id": pid,
                "title": presentation.get("title"),
                "slides_count": len(presentation.get("slides", [])),
                "url": f"https://docs.google.com/presentation/d/{pid}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to create Google Slides presentation: {e}")
            raise

    def slides_get(self, presentation_id: str) -> Dict[str, Any]:
        """
        Get content and structure of a Google Slides presentation.

        Extracts text from all slides (titles and body text).

        Args:
            presentation_id: Presentation ID

        Returns:
            Dict with presentation title, slide count, and text content of each slide
        """
        try:
            presentation = self.slides.presentations().get(presentationId=presentation_id).execute()

            title = presentation.get("title", "")
            slides_data = []

            for i, slide in enumerate(presentation.get("slides", []), 1):
                slide_texts = []
                for element in slide.get("pageElements", []):
                    shape = element.get("shape", {})
                    text_content = shape.get("text", {})
                    for text_element in text_content.get("textElements", []):
                        text_run = text_element.get("textRun", {})
                        text = text_run.get("content", "").strip()
                        if text:
                            slide_texts.append(text)

                slides_data.append(
                    {
                        "slide_number": i,
                        "slide_id": slide.get("objectId"),
                        "text": " | ".join(slide_texts) if slide_texts else "(empty slide)",
                    }
                )

            logger.info(
                f"Retrieved Slides presentation {presentation_id}: {len(slides_data)} slides"
            )
            return {
                "presentation_id": presentation_id,
                "title": title,
                "slides_count": len(slides_data),
                "slides": slides_data,
                "url": f"https://docs.google.com/presentation/d/{presentation_id}/edit",
            }

        except HttpError as e:
            logger.error(f"Failed to get Slides presentation {presentation_id}: {e}")
            raise

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    def _format_files(self, files: List[Dict]) -> List[Dict[str, Any]]:
        return [self._format_file(f) for f in files]

    def _format_file(self, f: Dict) -> Dict[str, Any]:
        """Normalize a Drive file metadata dict."""
        mime = f.get("mimeType", "")
        file_type = "folder"
        if mime == GOOGLE_DOCS_MIME:
            file_type = "google_doc"
        elif mime == GOOGLE_SHEETS_MIME:
            file_type = "google_sheet"
        elif mime == GOOGLE_SLIDES_MIME:
            file_type = "google_slides"
        elif mime != GOOGLE_FOLDER_MIME:
            file_type = "file"

        return {
            "id": f.get("id"),
            "name": f.get("name"),
            "type": file_type,
            "mime_type": mime,
            "size": f.get("size"),
            "created": f.get("createdTime"),
            "modified": f.get("modifiedTime"),
            "url": f.get("webViewLink"),
        }

    def _docs_insert_text(self, document_id: str, text: str, at_end: bool = False) -> None:
        """Insert text into a Google Doc."""
        if at_end:
            doc = self.docs.documents().get(documentId=document_id).execute()
            body = doc.get("body", {})
            content = body.get("content", [])
            end_index = content[-1].get("endIndex", 1) - 1 if content else 1
            index = max(1, end_index)
        else:
            index = 1

        requests = [{"insertText": {"location": {"index": index}, "text": text}}]
        self.docs.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()

    def _extract_doc_text(self, doc: Dict) -> str:
        """Extract plain text from a Google Docs document object."""
        texts = []
        content = doc.get("body", {}).get("content", [])
        for block in content:
            paragraph = block.get("paragraph", {})
            for element in paragraph.get("elements", []):
                text_run = element.get("textRun", {})
                text = text_run.get("content", "")
                if text:
                    texts.append(text)
        return "".join(texts).strip()
