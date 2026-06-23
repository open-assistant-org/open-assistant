"""Outlook/Microsoft Graph API client for mail, calendar, and OneDrive."""

from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)


class OutlookClient:
    """Client for interacting with Microsoft Graph API."""

    def __init__(self, access_token: str):
        """
        Initialize Outlook client.

        Args:
            access_token: Microsoft Graph access token
        """
        self.access_token = access_token
        self.graph_url = "https://graph.microsoft.com/v1.0"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        logger.info("Outlook client initialized")

    def _encode_id(self, id_value: str) -> str:
        """
        URL-encode an ID for use in API paths.

        Microsoft Graph API IDs are mostly URL-safe but may contain
        characters like '=' (base64 padding) that need encoding.

        Args:
            id_value: The ID to encode

        Returns:
            URL-encoded ID safe for use in API paths
        """
        # Keep alphanumeric, hyphen, underscore, and tilde as-is
        # Only encode special characters like =, +, / etc.
        return quote(id_value, safe="-_.~")

    def _resolve_todo_list_id(self, list_id_or_name: str) -> str:
        """
        Resolve a To Do list ID or display name to the actual ID.

        Microsoft Graph API accepts display names for some endpoints,
        but for consistency and reliability, we resolve names to IDs.

        Args:
            list_id_or_name: Either a list ID or display name

        Returns:
            The actual list ID

        Raises:
            ValueError: If the list cannot be found
        """
        # If it looks like an ID (contains typical ID characters), return as-is
        # Microsoft To Do IDs typically start with 'AAMk' or 'AQMk' and are long
        if len(list_id_or_name) > 50 and (
            list_id_or_name.startswith("AAMk") or list_id_or_name.startswith("AQMk")
        ):
            return list_id_or_name

        # Otherwise, treat it as a display name and look up the ID
        logger.info(f"Looking up To Do list ID for name: '{list_id_or_name}'")
        lists = self.list_todo_lists()

        # Try exact match first
        for lst in lists:
            if lst.get("displayName", "").lower() == list_id_or_name.lower():
                logger.info(f"Found list '{list_id_or_name}' with ID: {lst['id']}")
                return lst["id"]

        # Try partial match
        for lst in lists:
            if list_id_or_name.lower() in lst.get("displayName", "").lower():
                logger.info(
                    f"Found list matching '{list_id_or_name}': "
                    f"'{lst.get('displayName')}' with ID: {lst['id']}"
                )
                return lst["id"]

        raise ValueError(f"To Do list '{list_id_or_name}' not found")

    def _log_error(self, operation: str, error: requests.RequestException) -> None:
        """
        Log an error with response body details for debugging.

        Args:
            operation: Name of the operation that failed
            error: The RequestException that was raised
        """
        if error.response is not None:
            try:
                error_body = error.response.json()
                logger.error(f"Failed to {operation}: {error} - Response: {error_body}")
            except Exception:
                response_text = error.response.text
                logger.error(f"Failed to {operation}: {error} - Response text: {response_text}")
        else:
            logger.error(f"Failed to {operation}: {error}")

    # ========================================================================
    # MAIL OPERATIONS
    # ========================================================================

    def list_messages(
        self, folder: str = "inbox", filter: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        List messages from a folder.

        Args:
            folder: Folder name (inbox, sentitems, drafts, etc.)
            filter: OData filter query
            limit: Maximum messages to return

        Returns:
            List of message objects
        """
        try:
            url = f"{self.graph_url}/me/mailFolders/{folder}/messages"
            params = {"$top": limit, "$orderby": "receivedDateTime desc"}

            if filter:
                params["$filter"] = filter

            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            data = response.json()
            messages = data.get("value", [])

            logger.info(f"Retrieved {len(messages)} messages from {folder}")
            return messages

        except requests.RequestException as e:
            logger.error(f"Failed to list messages: {e}")
            raise

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get message by ID."""
        try:
            url = f"{self.graph_url}/me/messages/{self._encode_id(message_id)}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Failed to get message: {e}")
            raise

    def create_draft(
        self,
        to: List[str],
        subject: str,
        body: str,
        body_type: str = "text",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create email draft."""
        try:
            message_data = {
                "subject": subject,
                "body": {"contentType": "HTML" if body_type == "html" else "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
            }

            if cc:
                message_data["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
            if bcc:
                message_data["bccRecipients"] = [
                    {"emailAddress": {"address": addr}} for addr in bcc
                ]

            url = f"{self.graph_url}/me/messages"
            response = requests.post(url, headers=self.headers, json=message_data)
            response.raise_for_status()

            draft = response.json()
            logger.info(f"Created draft: {draft['id']}")
            return draft

        except requests.RequestException as e:
            logger.error(f"Failed to create draft: {e}")
            raise

    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        body_type: str = "text",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> bool:
        """Send email."""
        try:
            message_data = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML" if body_type == "html" else "Text",
                        "content": body,
                    },
                    "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
                }
            }

            if cc:
                message_data["message"]["ccRecipients"] = [
                    {"emailAddress": {"address": addr}} for addr in cc
                ]
            if bcc:
                message_data["message"]["bccRecipients"] = [
                    {"emailAddress": {"address": addr}} for addr in bcc
                ]

            url = f"{self.graph_url}/me/sendMail"
            response = requests.post(url, headers=self.headers, json=message_data)
            response.raise_for_status()

            logger.info("Email sent successfully")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to send email: {e}")
            raise

    # ========================================================================
    # CALENDAR OPERATIONS
    # ========================================================================

    def list_calendars(self) -> List[Dict[str, Any]]:
        """
        List all calendars accessible to the user.

        Returns:
            List of calendar objects with id, name, and other metadata.
        """
        try:
            url = f"{self.graph_url}/me/calendars"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            calendars = data.get("value", [])

            # Parse calendars to extract useful info
            parsed_calendars = []
            for cal in calendars:
                parsed_calendars.append(
                    {
                        "id": cal.get("id"),
                        "name": cal.get("name"),
                        "color": cal.get("color"),
                        "is_default": cal.get("isDefaultCalendar", False),
                        "can_edit": cal.get("canEdit", False),
                        "can_share": cal.get("canShare", False),
                        "can_view_private_items": cal.get("canViewPrivateItems", False),
                        "owner": cal.get("owner", {}).get("name"),
                        "owner_email": cal.get("owner", {}).get("address"),
                    }
                )

            logger.info(f"Retrieved {len(parsed_calendars)} calendars")
            return parsed_calendars

        except requests.RequestException as e:
            logger.error(f"Failed to list calendars: {e}")
            raise

    def list_events(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        calendar_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List calendar events.

        Args:
            start_date: Start date filter (ISO format). If provided without end_date, filters from this date onwards.
            end_date: End date filter (ISO format).
            limit: Maximum number of events to return.
            calendar_id: Calendar ID to list events from. If not specified, uses default calendar.

        Returns:
            List of event objects.
        """
        try:
            # Build URL based on whether a specific calendar is requested
            if calendar_id:
                url = f"{self.graph_url}/me/calendars/{self._encode_id(calendar_id)}/events"
            else:
                url = f"{self.graph_url}/me/calendar/events"

            params = {"$top": limit, "$orderby": "start/dateTime"}

            # Build filter based on provided dates
            if start_date and end_date:
                params["$filter"] = (
                    f"start/dateTime ge '{start_date}' and start/dateTime le '{end_date}'"
                )
            elif start_date:
                # If only start_date provided, filter from that date onwards
                params["$filter"] = f"start/dateTime ge '{start_date}'"

            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            data = response.json()
            events = data.get("value", [])

            logger.info(f"Retrieved {len(events)} calendar events")
            return events

        except requests.RequestException as e:
            logger.error(f"Failed to list events: {e}")
            raise

    def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        timezone: str = "UTC",
        location: Optional[str] = None,
        body: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        is_online_meeting: bool = False,
    ) -> Dict[str, Any]:
        """Create calendar event."""
        try:
            event_data = {
                "subject": subject,
                "start": {"dateTime": start, "timeZone": timezone},
                "end": {"dateTime": end, "timeZone": timezone},
                "isOnlineMeeting": is_online_meeting,
            }

            if location:
                event_data["location"] = {"displayName": location}

            if body:
                event_data["body"] = {"contentType": "Text", "content": body}

            if attendees:
                event_data["attendees"] = [
                    {"emailAddress": {"address": addr}, "type": "required"} for addr in attendees
                ]

            url = f"{self.graph_url}/me/calendar/events"
            response = requests.post(url, headers=self.headers, json=event_data)
            response.raise_for_status()

            event = response.json()
            logger.info(f"Created event: {event['id']}")
            return event

        except requests.RequestException as e:
            logger.error(f"Failed to create event: {e}")
            raise

    def update_event(self, event_id: str, **kwargs) -> Dict[str, Any]:
        """Update calendar event."""
        try:
            url = f"{self.graph_url}/me/calendar/events/{self._encode_id(event_id)}"
            response = requests.patch(url, headers=self.headers, json=kwargs)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Failed to update event: {e}")
            raise

    def delete_event(self, event_id: str) -> bool:
        """Delete calendar event."""
        try:
            url = f"{self.graph_url}/me/calendar/events/{self._encode_id(event_id)}"
            response = requests.delete(url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Deleted event: {event_id}")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to delete event: {e}")
            raise

    # ========================================================================
    # ONEDRIVE OPERATIONS
    # ========================================================================

    def list_files(self, folder_path: str = "/") -> List[Dict[str, Any]]:
        """List files in OneDrive folder."""
        try:
            if folder_path == "/":
                url = f"{self.graph_url}/me/drive/root/children"
            else:
                url = f"{self.graph_url}/me/drive/root:{folder_path}:/children"

            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            files = data.get("value", [])

            logger.info(f"Retrieved {len(files)} files from {folder_path}")
            return files

        except requests.RequestException as e:
            logger.error(f"Failed to list files: {e}")
            raise

    def read_file(self, file_id: str) -> bytes:
        """Read file content by ID."""
        try:
            url = f"{self.graph_url}/me/drive/items/{self._encode_id(file_id)}/content"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Read file: {file_id}")
            return response.content

        except requests.RequestException as e:
            logger.error(f"Failed to read file: {e}")
            raise

    def read_file_by_path(self, file_path: str) -> bytes:
        """Read file content by OneDrive path.

        Args:
            file_path: Full path from drive root, e.g. '/Documents/notes.md'

        Returns:
            File content as bytes
        """
        try:
            url = f"{self.graph_url}/me/drive/root:{file_path}:/content"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Read file by path: {file_path}")
            return response.content

        except requests.RequestException as e:
            logger.error(f"Failed to read file by path: {e}")
            raise

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata (name, size, mime type) by ID.

        Args:
            file_id: OneDrive file ID

        Returns:
            File metadata dict from Graph API
        """
        try:
            url = f"{self.graph_url}/me/drive/items/{self._encode_id(file_id)}"
            params = {"$select": "id,name,size,file"}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Failed to get file metadata: {e}")
            raise

    def get_file_metadata_by_path(self, file_path: str) -> Dict[str, Any]:
        """Get file metadata (name, size, mime type) by path.

        Args:
            file_path: Full path from drive root

        Returns:
            File metadata dict from Graph API
        """
        try:
            url = f"{self.graph_url}/me/drive/root:{file_path}:"
            params = {"$select": "id,name,size,file"}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Failed to get file metadata by path: {e}")
            raise

    def download_file(self, file_id: str, destination: str) -> None:
        """Download file to local storage."""
        try:
            content = self.read_file(file_id)

            with open(destination, "wb") as f:
                f.write(content)

            logger.info(f"Downloaded file to {destination}")

        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            raise

    def search_files(self, query: str) -> List[Dict[str, Any]]:
        """Search files in OneDrive."""
        try:
            url = f"{self.graph_url}/me/drive/root/search(q='{query}')"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            files = data.get("value", [])

            logger.info(f"Found {len(files)} files matching '{query}'")
            return files

        except requests.RequestException as e:
            logger.error(f"Failed to search files: {e}")
            raise

    def upload_file(
        self,
        folder_path: str,
        filename: str,
        content: bytes = None,
        source_path: str = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to OneDrive.

        Args:
            folder_path: Folder path (e.g. '/Documents/Reports')
            filename: Filename
            content: File content as bytes
            source_path: Local file path to read and upload. Takes precedence over content.

        Returns:
            Created file metadata
        """
        try:
            if source_path:
                with open(source_path, "rb") as f:
                    content = f.read()
            # Build path
            if folder_path == "/":
                url = f"{self.graph_url}/me/drive/root:/{filename}:/content"
            else:
                path = folder_path.rstrip("/")
                url = f"{self.graph_url}/me/drive/root:{path}/{filename}:/content"

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }

            response = requests.put(url, headers=headers, data=content)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Uploaded file: {filename} to {folder_path}")
            return result

        except requests.RequestException as e:
            logger.error(f"Failed to upload file: {e}")
            raise

    def get_attachment(self, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """
        Get an email attachment.

        Args:
            message_id: Message ID
            attachment_id: Attachment ID

        Returns:
            Attachment object with contentBytes, name, contentType
        """
        try:
            encoded_msg_id = self._encode_id(message_id)
            encoded_att_id = self._encode_id(attachment_id)
            url = f"{self.graph_url}/me/messages/{encoded_msg_id}/attachments/{encoded_att_id}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Failed to get attachment: {e}")
            raise

    def list_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """
        List attachments on a message.

        Args:
            message_id: Message ID

        Returns:
            List of attachment metadata
        """
        try:
            url = f"{self.graph_url}/me/messages/{self._encode_id(message_id)}/attachments"
            params = {"$select": "id,name,contentType,size"}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            data = response.json()
            return data.get("value", [])

        except requests.RequestException as e:
            logger.error(f"Failed to list attachments: {e}")
            raise

    # ========================================================================
    # ADDITIONAL MAIL OPERATIONS
    # ========================================================================

    def search_emails(
        self, query: str, folder: str = "inbox", limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search emails using OData filter or $search.

        Args:
            query: Search query string
            folder: Mail folder to search in
            limit: Maximum results

        Returns:
            List of matching messages
        """
        try:
            url = f"{self.graph_url}/me/mailFolders/{folder}/messages"
            # Note: $search and $orderby cannot be combined in Microsoft Graph API.
            # When $search is used, results are ranked by relevance automatically.
            params = {
                "$top": limit,
                "$search": f'"{query}"',
            }

            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            data = response.json()
            messages = data.get("value", [])

            logger.info(f"Found {len(messages)} messages matching '{query}'")
            return messages

        except requests.RequestException as e:
            logger.error(f"Failed to search emails: {e}")
            raise

    # ========================================================================
    # ONENOTE OPERATIONS
    # ========================================================================

    def list_notebooks(self, include_sections: bool = False) -> List[Dict[str, Any]]:
        """
        List all OneNote notebooks.

        Args:
            include_sections: Include sections in each notebook

        Returns:
            List of notebook objects
        """
        try:
            url = f"{self.graph_url}/me/onenote/notebooks"
            params = {"$orderby": "lastModifiedDateTime desc"}

            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            notebooks = response.json().get("value", [])

            if include_sections:
                for nb in notebooks:
                    nb["sections"] = self.list_sections(notebook_id=nb["id"])

            logger.info(f"Retrieved {len(notebooks)} OneNote notebooks")
            return notebooks

        except requests.RequestException as e:
            logger.error(f"Failed to list notebooks: {e}")
            raise

    def get_notebook(self, notebook_id: str) -> Dict[str, Any]:
        """Get a specific notebook with metadata."""
        try:
            url = f"{self.graph_url}/me/onenote/notebooks/{self._encode_id(notebook_id)}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get notebook: {e}")
            raise

    def list_sections(self, notebook_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List sections, optionally filtered by notebook.

        Args:
            notebook_id: Filter by notebook ID

        Returns:
            List of section objects
        """
        try:
            if notebook_id:
                url = (
                    f"{self.graph_url}/me/onenote/notebooks/{self._encode_id(notebook_id)}/sections"
                )
            else:
                url = f"{self.graph_url}/me/onenote/sections"

            params = {"$orderby": "lastModifiedDateTime desc"}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            sections = response.json().get("value", [])
            logger.info(f"Retrieved {len(sections)} OneNote sections")
            return sections

        except requests.RequestException as e:
            logger.error(f"Failed to list sections: {e}")
            raise

    def get_section(self, section_id: str) -> Dict[str, Any]:
        """Get a specific section with metadata."""
        try:
            url = f"{self.graph_url}/me/onenote/sections/{self._encode_id(section_id)}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get section: {e}")
            raise

    def list_pages(
        self,
        section_id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        limit: int = 20,
        include_content: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List pages with optional filtering.

        Args:
            section_id: Filter by section ID
            notebook_id: Filter by notebook ID
            limit: Maximum pages to return
            include_content: Include full page HTML content

        Returns:
            List of page objects
        """
        try:
            if section_id:
                url = f"{self.graph_url}/me/onenote/sections/{self._encode_id(section_id)}/pages"
            elif notebook_id:
                url = f"{self.graph_url}/me/onenote/notebooks/{self._encode_id(notebook_id)}/pages"
            else:
                url = f"{self.graph_url}/me/onenote/pages"

            params = {"$top": limit, "$orderby": "lastModifiedDateTime desc"}
            params["$select"] = (
                "id,title,createdDateTime,lastModifiedDateTime,parentSection,parentNotebook"
            )

            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            pages = response.json().get("value", [])

            if include_content:
                for page in pages:
                    page["content"] = self.get_page_content(page["id"])

            logger.info(f"Retrieved {len(pages)} OneNote pages")
            return pages

        except requests.RequestException as e:
            logger.error(f"Failed to list pages: {e}")
            raise

    def get_page(self, page_id: str, include_content: bool = True) -> Dict[str, Any]:
        """Get page metadata and optionally content."""
        try:
            url = f"{self.graph_url}/me/onenote/pages/{self._encode_id(page_id)}"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 404:
                logger.warning(f"OneNote page not found: {page_id}")
                return {
                    "success": False,
                    "error": "OneNote page not found. The page ID may be stale or deleted.",
                    "page_id": page_id,
                }
            response.raise_for_status()

            page = response.json()

            if include_content:
                page["content"] = self.get_page_content(page_id)

            return page
        except requests.RequestException as e:
            logger.error(f"Failed to get page: {e}")
            raise

    def get_page_content(self, page_id: str):
        """Get page HTML content."""
        try:
            url = f"{self.graph_url}/me/onenote/pages/{self._encode_id(page_id)}/content"

            response = requests.get(url, headers=self.headers)
            if response.status_code == 404:
                logger.warning(f"OneNote page content not found: {page_id}")
                return {
                    "success": False,
                    "error": "OneNote page not found. The page ID may be stale or deleted.",
                    "page_id": page_id,
                }
            response.raise_for_status()

            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to get page content: {e}")
            raise

    def create_page(self, section_id: str, title: str, content: str) -> Dict[str, Any]:
        """
        Create a new page with HTML content.

        Args:
            section_id: Section to create page in
            title: Page title
            content: HTML content

        Returns:
            Created page object
        """
        try:
            url = f"{self.graph_url}/me/onenote/sections/{self._encode_id(section_id)}/pages"

            # Build HTML document for OneNote
            html_content = f"""<!DOCTYPE html>
<html>
  <head>
    <title>{title}</title>
  </head>
  <body>
    {content}
  </body>
</html>"""

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "text/html",
            }

            response = requests.post(url, headers=headers, data=html_content.encode("utf-8"))
            response.raise_for_status()

            page = response.json()
            logger.info(f"Created OneNote page: {page['id']}")
            return page

        except requests.RequestException as e:
            logger.error(f"Failed to create page: {e}")
            raise

    def update_page(self, page_id: str, content: str) -> Dict[str, Any]:
        """Update page content using PATCH (appends content)."""
        try:
            url = f"{self.graph_url}/me/onenote/pages/{self._encode_id(page_id)}/content"

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # OneNote PATCH uses special commands
            patch_data = [
                {
                    "target": "body",
                    "action": "append",
                    "content": content,
                }
            ]

            response = requests.patch(url, headers=headers, json=patch_data)
            response.raise_for_status()

            logger.info(f"Updated OneNote page: {page_id}")
            return {"success": True}

        except requests.RequestException as e:
            logger.error(f"Failed to update page: {e}")
            raise

    def delete_page(self, page_id: str) -> bool:
        """Delete a page."""
        try:
            url = f"{self.graph_url}/me/onenote/pages/{self._encode_id(page_id)}"
            response = requests.delete(url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Deleted OneNote page: {page_id}")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to delete page: {e}")
            raise

    def _search_via_microsoft_search_api(
        self,
        query: str,
        limit: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Search OneNote pages using the Microsoft Search API.

        Supports full-text search across page title and content.
        Returns None if the API is unavailable (e.g. insufficient scope).
        """
        url = f"{self.graph_url}/search/query"
        # Search API max page size is 25; request in batches if needed
        size = min(limit, 25)
        body = {
            "requests": [
                {
                    "entityTypes": ["onenotePage"],
                    "query": {"queryString": query},
                    "from": 0,
                    "size": size,
                    "fields": [
                        "id",
                        "name",
                        "webUrl",
                        "createdDateTime",
                        "lastModifiedDateTime",
                        "parentSection",
                        "parentNotebook",
                    ],
                }
            ]
        }

        response = requests.post(url, headers=self.headers, json=body)
        # 403/401 means the token lacks the required scope — signal caller to fall back
        if response.status_code in (401, 403):
            logger.debug(
                "Microsoft Search API returned %s, falling back to paginated search",
                response.status_code,
            )
            return None
        response.raise_for_status()

        hits_containers = response.json().get("value", [{}])[0].get("hitsContainers", [])
        if not hits_containers:
            return []

        results = []
        for hit in hits_containers[0].get("hits", []):
            resource = hit.get("resource", {})
            results.append(
                {
                    "id": resource.get("id", ""),
                    "title": resource.get("name", ""),
                    "webUrl": resource.get("webUrl", ""),
                    "createdDateTime": resource.get("createdDateTime", ""),
                    "lastModifiedDateTime": resource.get("lastModifiedDateTime", ""),
                    "parentSection": resource.get("parentSection"),
                    "parentNotebook": resource.get("parentNotebook"),
                }
            )
        return results

    def _search_pages_by_title(
        self,
        query: str,
        section_id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        limit: int = 20,
        max_fetch: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Paginate through all pages and filter client-side by title.

        Splits the query into tokens so that "Konings kick off" matches a title
        containing both words regardless of order.  Follows @odata.nextLink until
        enough results are collected or all pages are exhausted.
        """
        if section_id:
            url = f"{self.graph_url}/me/onenote/sections/{self._encode_id(section_id)}/pages"
        elif notebook_id:
            url = f"{self.graph_url}/me/onenote/notebooks/{self._encode_id(notebook_id)}/pages"
        else:
            url = f"{self.graph_url}/me/onenote/pages"

        params: Dict[str, Any] = {
            "$top": 100,
            "$orderby": "lastModifiedDateTime desc",
            "$select": "id,title,createdDateTime,lastModifiedDateTime,parentSection,parentNotebook",
        }

        query_tokens = query.lower().split()
        matching_pages: List[Dict[str, Any]] = []
        total_fetched = 0

        while url and total_fetched < max_fetch:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            pages = data.get("value", [])
            total_fetched += len(pages)

            for page in pages:
                title_lower = page.get("title", "").lower()
                if all(token in title_lower for token in query_tokens):
                    matching_pages.append(page)
                    if len(matching_pages) >= limit:
                        break

            if len(matching_pages) >= limit:
                break

            # Follow pagination link; clear params because they are baked into nextLink
            url = data.get("@odata.nextLink")
            params = {}

        scope_info = (
            f" in section {section_id}"
            if section_id
            else (f" in notebook {notebook_id}" if notebook_id else "")
        )
        logger.info(
            f"Found {len(matching_pages)} pages matching '{query}'{scope_info} "
            f"(searched {total_fetched} pages)"
        )
        return matching_pages

    def search_pages(
        self,
        query: str,
        section_id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search OneNote pages by title and content.

        Strategy:
        1. Try the Microsoft Search API — full-text search across title and page
           content, fast and scope-aware.
        2. Fall back to paginating through ALL pages and filtering by title tokens
           client-side, so no page is missed regardless of how many you have.
        """
        try:
            # Prefer Microsoft Search API when no explicit scope is requested,
            # because it searches content too and is not limited by page count.
            if not section_id and not notebook_id:
                results = self._search_via_microsoft_search_api(query, limit)
                if results is not None:
                    logger.info(
                        f"Found {len(results)} pages matching '{query}' via Microsoft Search API"
                    )
                    return results
        except requests.RequestException as e:
            logger.warning(
                f"Microsoft Search API failed ({e}), falling back to paginated title search"
            )

        try:
            return self._search_pages_by_title(query, section_id, notebook_id, limit)
        except requests.RequestException as e:
            logger.error(f"Failed to search pages: {e}")
            raise

    def copy_page(self, page_id: str, target_section_id: str) -> Dict[str, Any]:
        """Copy a page to another section."""
        try:
            url = f"{self.graph_url}/me/onenote/pages/{self._encode_id(page_id)}/copyToSection"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            body = {"id": target_section_id, "groupId": None}

            response = requests.post(url, headers=headers, json=body)
            response.raise_for_status()

            logger.info(f"Copied page {page_id} to section {target_section_id}")
            return {"success": True, "page_id": page_id, "target_section_id": target_section_id}

        except requests.RequestException as e:
            logger.error(f"Failed to copy page: {e}")
            raise

    def extract_page_text(self, page_id: str) -> Dict[str, Any]:
        """Extract plain text from a OneNote page HTML."""
        try:
            html_content = self.get_page_content(page_id)

            # Simple HTML to text extraction
            import re
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text_parts = []
                    self.skip_tags = {"script", "style", "head", "meta", "title"}
                    self.current_skip = False

                def handle_starttag(self, tag, attrs):
                    if tag in self.skip_tags:
                        self.current_skip = True
                    elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
                        self.text_parts.append("\n")

                def handle_endtag(self, tag):
                    if tag in self.skip_tags:
                        self.current_skip = False
                    elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
                        self.text_parts.append("\n")

                def handle_data(self, data):
                    if not self.current_skip:
                        self.text_parts.append(data)

            extractor = TextExtractor()
            extractor.feed(html_content)
            text = "".join(extractor.text_parts)
            # Clean up whitespace
            text = re.sub(r"\n\s*\n", "\n\n", text).strip()

            return {"page_id": page_id, "text": text, "char_count": len(text)}

        except Exception as e:
            logger.error(f"Failed to extract text: {e}")
            raise

    # ========================================================================
    # MICROSOFT TO DO OPERATIONS
    # ========================================================================

    def list_todo_lists(self) -> List[Dict[str, Any]]:
        """
        List all Microsoft To Do task lists.

        Returns:
            List of task list objects with id, displayName, and other metadata.
        """
        try:
            url = f"{self.graph_url}/me/todo/lists"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            lists = data.get("value", [])

            # Log each list's ID and name for debugging
            for lst in lists:
                list_id = lst.get("id", "")
                name = lst.get("displayName")
                logger.info(f"To Do list: '{name}' id={list_id} (len={len(list_id)})")

            logger.info(f"Retrieved {len(lists)} To Do lists")
            return lists

        except requests.RequestException as e:
            self._log_error("list To Do lists", e)
            raise

    def get_todo_list(self, list_id: str) -> Dict[str, Any]:
        """Get a specific To Do task list by ID or display name."""
        try:
            resolved_id = self._resolve_todo_list_id(list_id)
            url = f"{self.graph_url}/me/todo/lists/{self._encode_id(resolved_id)}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            self._log_error("get To Do list", e)
            raise

    def create_todo_list(self, display_name: str) -> Dict[str, Any]:
        """
        Create a new To Do task list.

        Args:
            display_name: Name of the task list

        Returns:
            Created task list object
        """
        try:
            url = f"{self.graph_url}/me/todo/lists"
            body = {"displayName": display_name}
            response = requests.post(url, headers=self.headers, json=body)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Created To Do list: {result['id']}")
            return result

        except requests.RequestException as e:
            logger.error(f"Failed to create To Do list: {e}")
            raise

    def delete_todo_list(self, list_id: str) -> bool:
        """Delete a To Do task list."""
        try:
            resolved_id = self._resolve_todo_list_id(list_id)
            url = f"{self.graph_url}/me/todo/lists/{self._encode_id(resolved_id)}"
            response = requests.delete(url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Deleted To Do list: {list_id}")
            return True

        except requests.RequestException as e:
            self._log_error("delete To Do list", e)
            raise

    def list_todo_tasks(
        self,
        list_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List tasks in a To Do task list.

        Args:
            list_id: Task list ID or display name
            status: Filter by status ('notStarted', 'inProgress', 'completed')
            limit: Maximum tasks to return

        Returns:
            List of task objects
        """
        try:
            resolved_id = self._resolve_todo_list_id(list_id)
            logger.info(f"Listing tasks for list_id={resolved_id} (original: {list_id})")
            url = f"{self.graph_url}/me/todo/lists/{self._encode_id(resolved_id)}/tasks"
            params: Dict[str, Any] = {"$top": limit}

            if status:
                params["$filter"] = f"status eq '{status}'"

            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            data = response.json()
            tasks = data.get("value", [])

            logger.info(f"Retrieved {len(tasks)} tasks from list {list_id}")
            return tasks

        except requests.RequestException as e:
            self._log_error("list To Do tasks", e)
            raise

    def get_todo_task(self, list_id: str, task_id: str) -> Dict[str, Any]:
        """Get a specific task by ID."""
        try:
            resolved_id = self._resolve_todo_list_id(list_id)
            encoded_list_id = self._encode_id(resolved_id)
            encoded_task_id = self._encode_id(task_id)
            url = f"{self.graph_url}/me/todo/lists/{encoded_list_id}/tasks/{encoded_task_id}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            self._log_error("get To Do task", e)
            raise

    def create_todo_task(
        self,
        list_id: str,
        title: str,
        body: Optional[str] = None,
        due_date: Optional[str] = None,
        importance: str = "normal",
        reminder_date_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new task in a To Do task list.

        Args:
            list_id: Task list ID or display name
            title: Task title
            body: Task body/notes (plain text)
            due_date: Due date in YYYY-MM-DD format
            importance: 'low', 'normal', or 'high'
            reminder_date_time: Reminder datetime in ISO format (e.g. 2026-03-05T09:00:00)

        Returns:
            Created task object
        """
        try:
            resolved_id = self._resolve_todo_list_id(list_id)
            task_data: Dict[str, Any] = {
                "title": title,
                "importance": importance,
            }

            if body:
                task_data["body"] = {"content": body, "contentType": "text"}

            if due_date:
                task_data["dueDateTime"] = {
                    "dateTime": f"{due_date}T00:00:00",
                    "timeZone": "UTC",
                }

            if reminder_date_time:
                task_data["isReminderOn"] = True
                task_data["reminderDateTime"] = {
                    "dateTime": reminder_date_time,
                    "timeZone": "UTC",
                }

            url = f"{self.graph_url}/me/todo/lists/{self._encode_id(resolved_id)}/tasks"
            response = requests.post(url, headers=self.headers, json=task_data)
            response.raise_for_status()

            task = response.json()
            logger.info(f"Created To Do task: {task['id']}")
            return task

        except requests.RequestException as e:
            self._log_error("create To Do task", e)
            raise

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
        """
        Update an existing To Do task.

        Args:
            list_id: Task list ID or display name
            task_id: Task ID
            title: New title
            body: New body/notes
            due_date: New due date (YYYY-MM-DD)
            importance: 'low', 'normal', or 'high'
            status: 'notStarted', 'inProgress', or 'completed'
            reminder_date_time: Reminder datetime in ISO format

        Returns:
            Updated task object
        """
        try:
            resolved_id = self._resolve_todo_list_id(list_id)
            task_data: Dict[str, Any] = {}

            if title is not None:
                task_data["title"] = title
            if body is not None:
                task_data["body"] = {"content": body, "contentType": "text"}
            if due_date is not None:
                task_data["dueDateTime"] = {
                    "dateTime": f"{due_date}T00:00:00",
                    "timeZone": "UTC",
                }
            if importance is not None:
                task_data["importance"] = importance
            if status is not None:
                task_data["status"] = status
            if reminder_date_time is not None:
                task_data["isReminderOn"] = True
                task_data["reminderDateTime"] = {
                    "dateTime": reminder_date_time,
                    "timeZone": "UTC",
                }

            encoded_list_id = self._encode_id(resolved_id)
            encoded_task_id = self._encode_id(task_id)
            url = f"{self.graph_url}/me/todo/lists/{encoded_list_id}/tasks/{encoded_task_id}"
            response = requests.patch(url, headers=self.headers, json=task_data)
            response.raise_for_status()

            task = response.json()
            logger.info(f"Updated To Do task: {task_id}")
            return task

        except requests.RequestException as e:
            self._log_error("update To Do task", e)
            raise

    def delete_todo_task(self, list_id: str, task_id: str) -> bool:
        """Delete a To Do task."""
        try:
            resolved_id = self._resolve_todo_list_id(list_id)
            encoded_list_id = self._encode_id(resolved_id)
            encoded_task_id = self._encode_id(task_id)
            url = f"{self.graph_url}/me/todo/lists/{encoded_list_id}/tasks/{encoded_task_id}"
            response = requests.delete(url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Deleted To Do task: {task_id}")
            return True

        except requests.RequestException as e:
            self._log_error("delete To Do task", e)
            raise

    def create_page_from_markdown(
        self, section_id: str, title: str, markdown_content: str
    ) -> Dict[str, Any]:
        """Create a page from Markdown content (converts to HTML)."""
        try:
            # Simple markdown to HTML conversion
            import re

            html_content = markdown_content

            # Headers
            html_content = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html_content, flags=re.MULTILINE)
            html_content = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html_content, flags=re.MULTILINE)
            html_content = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html_content, flags=re.MULTILINE)

            # Bold and italic
            html_content = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html_content)
            html_content = re.sub(r"\*(.+?)\*", r"<i>\1</i>", html_content)

            # Code blocks
            html_content = re.sub(
                r"```(\w*)\n(.+?)```", r"<pre><code>\2</code></pre>", html_content, flags=re.DOTALL
            )
            html_content = re.sub(r"`(.+?)`", r"<code>\1</code>", html_content)

            # Lists
            html_content = re.sub(r"^- (.+)$", r"<li>\1</li>", html_content, flags=re.MULTILINE)
            html_content = re.sub(r"(<li>.*</li>\n?)+", r"<ul>\g<0></ul>", html_content)

            # Paragraphs (wrap remaining lines)
            lines = html_content.split("\n")
            processed_lines = []
            for line in lines:
                if line.strip() and not line.strip().startswith("<"):
                    processed_lines.append(f"<p>{line}</p>")
                else:
                    processed_lines.append(line)
            html_content = "\n".join(processed_lines)

            return self.create_page(section_id, title, html_content)

        except Exception as e:
            logger.error(f"Failed to create page from markdown: {e}")
            raise
