"""Google API client for email and calendar operations."""

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleClient:
    """Client for interacting with Gmail and Google Calendar APIs."""

    def __init__(self, credentials: Credentials):
        """
        Initialize Google client.

        Args:
            credentials: Google OAuth credentials
        """
        self.credentials = credentials
        self.gmail_service = build("gmail", "v1", credentials=credentials)
        self.calendar_service = build("calendar", "v3", credentials=credentials)
        logger.info("Google client initialized (Gmail + Calendar)")

    def list_messages(
        self, query: str = "", max_results: int = 10, label_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        List messages matching query.

        Args:
            query: Gmail search query (e.g., "is:unread", "from:example@gmail.com")
            max_results: Maximum number of messages to return
            label_ids: Optional list of label IDs to filter by

        Returns:
            List of message objects

        Raises:
            HttpError: If API request fails
        """
        try:
            logger.info(f"Listing Gmail messages: query='{query}', max={max_results}")

            # List message IDs
            request_params = {"userId": "me", "q": query, "maxResults": max_results}

            if label_ids:
                request_params["labelIds"] = label_ids

            results = self.gmail_service.users().messages().list(**request_params).execute()
            messages = results.get("messages", [])

            # Get full message details
            full_messages = []
            for msg in messages:
                message = self.get_message(msg["id"])
                full_messages.append(message)

            logger.info(f"Retrieved {len(full_messages)} messages")
            return full_messages

        except HttpError as e:
            logger.error(f"Failed to list Gmail messages: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing messages: {e}")
            raise

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """
        Get full message details.

        Args:
            message_id: Message ID

        Returns:
            Message object with full details

        Raises:
            HttpError: If API request fails
        """
        try:
            message = (
                self.gmail_service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            # Parse message for easier access
            parsed = self._parse_message(message)
            return parsed

        except HttpError as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            raise

    def search_messages(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Search messages with query.

        Args:
            query: Gmail search query
            max_results: Maximum results

        Returns:
            List of matching messages
        """
        return self.list_messages(query=query, max_results=max_results)

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        html: bool = False,
    ) -> Dict[str, Any]:
        """
        Create email draft.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            html: Whether body is HTML (default: plain text)

        Returns:
            Created draft object

        Raises:
            HttpError: If API request fails
        """
        try:
            logger.info(f"Creating Gmail draft to {to}")

            # Create MIME message
            message = MIMEMultipart()
            message["To"] = to
            message["Subject"] = subject

            if cc:
                message["Cc"] = ", ".join(cc)

            if bcc:
                message["Bcc"] = ", ".join(bcc)

            # Add body
            body_type = "html" if html else "plain"
            message.attach(MIMEText(body, body_type))

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            # Create draft
            draft = (
                self.gmail_service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw_message}})
                .execute()
            )

            logger.info(f"Created draft: {draft['id']}")
            return draft

        except HttpError as e:
            logger.error(f"Failed to create draft: {e}")
            raise

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        html: bool = False,
    ) -> Dict[str, Any]:
        """
        Send email message.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            html: Whether body is HTML

        Returns:
            Sent message object

        Raises:
            HttpError: If API request fails
        """
        try:
            logger.info(f"Sending Gmail message to {to}")

            # Create MIME message
            message = MIMEMultipart()
            message["To"] = to
            message["Subject"] = subject

            if cc:
                message["Cc"] = ", ".join(cc)

            if bcc:
                message["Bcc"] = ", ".join(bcc)

            # Add body
            body_type = "html" if html else "plain"
            message.attach(MIMEText(body, body_type))

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            # Send message
            sent = (
                self.gmail_service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )

            logger.info(f"Sent message: {sent['id']}")
            return sent

        except HttpError as e:
            logger.error(f"Failed to send message: {e}")
            raise

    def get_labels(self) -> List[Dict[str, Any]]:
        """
        Get all Gmail labels.

        Returns:
            List of label objects

        Raises:
            HttpError: If API request fails
        """
        try:
            results = self.gmail_service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])

            logger.info(f"Retrieved {len(labels)} labels")
            return labels

        except HttpError as e:
            logger.error(f"Failed to get labels: {e}")
            raise

    def _parse_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Gmail message for easier access.

        Args:
            message: Raw Gmail message object

        Returns:
            Parsed message with common fields extracted
        """
        headers = message.get("payload", {}).get("headers", [])

        # Extract common headers
        parsed = {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "label_ids": message.get("labelIds", []),
            "snippet": message.get("snippet"),
            "internal_date": message.get("internalDate"),
        }

        # Parse headers
        for header in headers:
            name = header.get("name", "").lower()
            value = header.get("value")

            if name == "from":
                parsed["from"] = value
            elif name == "to":
                parsed["to"] = value
            elif name == "subject":
                parsed["subject"] = value
            elif name == "date":
                parsed["date"] = value
            elif name == "cc":
                parsed["cc"] = value
            elif name == "bcc":
                parsed["bcc"] = value

        # Try to extract body
        body = self._get_body(message.get("payload", {}))
        parsed["body"] = body

        # Extract attachment info
        attachments = []
        parts = message.get("payload", {}).get("parts", [])
        for part in parts:
            filename = part.get("filename")
            if filename:
                att_body = part.get("body", {})
                attachments.append(
                    {
                        "filename": filename,
                        "mimeType": part.get("mimeType", ""),
                        "attachmentId": att_body.get("attachmentId", ""),
                        "size": att_body.get("size", 0),
                    }
                )
        if attachments:
            parsed["attachments"] = attachments

        return parsed

    def _get_body(self, payload: Dict[str, Any]) -> str:
        """
        Extract email body from payload.

        Args:
            payload: Message payload

        Returns:
            Email body text
        """
        body = ""

        if "body" in payload and "data" in payload["body"]:
            # Simple message body
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        elif "parts" in payload:
            # Multipart message
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    if "data" in part.get("body", {}):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        break
                elif part.get("mimeType") == "text/html":
                    # Fallback to HTML if no plain text
                    if not body and "data" in part.get("body", {}):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

        return body.strip()

    # ========================================================================
    # CALENDAR OPERATIONS
    # ========================================================================

    def list_calendars(self) -> List[Dict[str, Any]]:
        """
        List all calendars accessible to the user.

        Returns:
            List of calendar objects with id, summary, primary status, etc.

        Raises:
            HttpError: If API request fails
        """
        try:
            logger.info("Listing Google calendars")

            results = self.calendar_service.calendarList().list().execute()
            calendars = results.get("items", [])

            # Parse calendars to extract useful info
            parsed_calendars = []
            for cal in calendars:
                parsed_calendars.append(
                    {
                        "id": cal.get("id"),
                        "summary": cal.get("summary"),
                        "description": cal.get("description"),
                        "primary": cal.get("primary", False),
                        "access_role": cal.get("accessRole"),
                        "background_color": cal.get("backgroundColor"),
                        "foreground_color": cal.get("foregroundColor"),
                        "selected": cal.get("selected", False),
                        "time_zone": cal.get("timeZone"),
                    }
                )

            logger.info(f"Retrieved {len(parsed_calendars)} calendars")
            return parsed_calendars

        except HttpError as e:
            logger.error(f"Failed to list calendars: {e}")
            raise

    def list_events(
        self,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 10,
        calendar_id: str = "primary",
    ) -> List[Dict[str, Any]]:
        """
        List calendar events.

        Args:
            time_min: Start time filter (RFC3339, e.g. 2026-01-01T00:00:00Z)
            time_max: End time filter (RFC3339)
            max_results: Maximum number of events to return
            calendar_id: Calendar ID (default: primary)

        Returns:
            List of event objects

        Raises:
            HttpError: If API request fails
        """
        try:
            logger.info(f"Listing calendar events: calendar={calendar_id}, max={max_results}")

            params = {
                "calendarId": calendar_id,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }

            if time_min:
                params["timeMin"] = time_min
            if time_max:
                params["timeMax"] = time_max

            results = self.calendar_service.events().list(**params).execute()
            events = results.get("items", [])

            logger.info(f"Retrieved {len(events)} calendar events")
            return events

        except HttpError as e:
            logger.error(f"Failed to list calendar events: {e}")
            raise

    def get_event(self, event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Get a specific calendar event.

        Args:
            event_id: Event ID
            calendar_id: Calendar ID (default: primary)

        Returns:
            Event object

        Raises:
            HttpError: If API request fails
        """
        try:
            event = (
                self.calendar_service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )

            logger.info(f"Retrieved event: {event_id}")
            return event

        except HttpError as e:
            logger.error(f"Failed to get event {event_id}: {e}")
            raise

    def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        timezone: str = "UTC",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Create a calendar event.

        Args:
            summary: Event title
            start: Start time (RFC3339 or date string YYYY-MM-DD for all-day)
            end: End time (RFC3339 or date string YYYY-MM-DD for all-day)
            timezone: Timezone (default: UTC)
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
            calendar_id: Calendar ID (default: primary)

        Returns:
            Created event object

        Raises:
            HttpError: If API request fails
        """
        try:
            logger.info(f"Creating calendar event: {summary}")

            # Detect all-day events (date-only strings like YYYY-MM-DD)
            is_all_day = len(start) == 10 and len(end) == 10

            if is_all_day:
                event_data = {
                    "summary": summary,
                    "start": {"date": start},
                    "end": {"date": end},
                }
            else:
                event_data = {
                    "summary": summary,
                    "start": {"dateTime": start, "timeZone": timezone},
                    "end": {"dateTime": end, "timeZone": timezone},
                }

            if description:
                event_data["description"] = description
            if location:
                event_data["location"] = location
            if attendees:
                event_data["attendees"] = [{"email": addr} for addr in attendees]

            event = (
                self.calendar_service.events()
                .insert(calendarId=calendar_id, body=event_data)
                .execute()
            )

            logger.info(f"Created event: {event['id']}")
            return event

        except HttpError as e:
            logger.error(f"Failed to create event: {e}")
            raise

    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timezone: str = "UTC",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Update an existing calendar event.

        Args:
            event_id: Event ID to update
            summary: New event title (optional)
            start: New start time (optional)
            end: New end time (optional)
            timezone: Timezone
            description: New description (optional)
            location: New location (optional)
            attendees: New attendee list (optional)
            calendar_id: Calendar ID (default: primary)

        Returns:
            Updated event object
        """
        try:
            logger.info(f"Updating calendar event: {event_id}")

            # Get existing event first
            existing = self.get_event(event_id=event_id, calendar_id=calendar_id)

            # Build update data from existing + changes
            event_data = {}

            if summary is not None:
                event_data["summary"] = summary
            if description is not None:
                event_data["description"] = description
            if location is not None:
                event_data["location"] = location
            if attendees is not None:
                event_data["attendees"] = [{"email": addr} for addr in attendees]

            if start is not None and end is not None:
                is_all_day = len(start) == 10 and len(end) == 10
                if is_all_day:
                    event_data["start"] = {"date": start}
                    event_data["end"] = {"date": end}
                else:
                    event_data["start"] = {"dateTime": start, "timeZone": timezone}
                    event_data["end"] = {"dateTime": end, "timeZone": timezone}
            elif start is not None:
                is_all_day = len(start) == 10
                if is_all_day:
                    event_data["start"] = {"date": start}
                else:
                    event_data["start"] = {"dateTime": start, "timeZone": timezone}
            elif end is not None:
                is_all_day = len(end) == 10
                if is_all_day:
                    event_data["end"] = {"date": end}
                else:
                    event_data["end"] = {"dateTime": end, "timeZone": timezone}

            event = (
                self.calendar_service.events()
                .patch(calendarId=calendar_id, eventId=event_id, body=event_data)
                .execute()
            )

            logger.info(f"Updated event: {event_id}")
            return event

        except HttpError as e:
            logger.error(f"Failed to update event {event_id}: {e}")
            raise

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """
        Delete a calendar event.

        Args:
            event_id: Event ID to delete
            calendar_id: Calendar ID (default: primary)

        Returns:
            True if deleted successfully
        """
        try:
            logger.info(f"Deleting calendar event: {event_id}")

            self.calendar_service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            logger.info(f"Deleted event: {event_id}")
            return True

        except HttpError as e:
            logger.error(f"Failed to delete event {event_id}: {e}")
            raise

    # ========================================================================
    # EMAIL MANAGEMENT OPERATIONS
    # ========================================================================

    def reply_to_message(
        self,
        message_id: str,
        thread_id: str,
        body: str,
        to: Optional[str] = None,
        html: bool = False,
    ) -> Dict[str, Any]:
        """
        Reply to an email message.

        Args:
            message_id: Original message ID to reply to
            thread_id: Thread ID of the conversation
            body: Reply body text
            to: Override recipient (defaults to original sender)
            html: Whether body is HTML

        Returns:
            Sent reply message object
        """
        try:
            logger.info(f"Replying to message {message_id} in thread {thread_id}")

            # Get original message to extract headers
            original = self.get_message(message_id)

            # Determine recipient
            reply_to = to or original.get("from", "")

            # Build subject with Re: prefix
            subject = original.get("subject", "")
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"

            # Create MIME message
            message = MIMEMultipart()
            message["To"] = reply_to
            message["Subject"] = subject
            message["In-Reply-To"] = message_id
            message["References"] = message_id

            body_type = "html" if html else "plain"
            message.attach(MIMEText(body, body_type))

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            sent = (
                self.gmail_service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message, "threadId": thread_id})
                .execute()
            )

            logger.info(f"Sent reply: {sent['id']}")
            return sent

        except HttpError as e:
            logger.error(f"Failed to reply to message: {e}")
            raise

    def trash_message(self, message_id: str) -> bool:
        """
        Move a message to trash.

        Args:
            message_id: Message ID to trash

        Returns:
            True if trashed successfully
        """
        try:
            logger.info(f"Trashing message: {message_id}")

            self.gmail_service.users().messages().trash(userId="me", id=message_id).execute()

            logger.info(f"Trashed message: {message_id}")
            return True

        except HttpError as e:
            logger.error(f"Failed to trash message {message_id}: {e}")
            raise

    def get_attachment(self, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """
        Get an email attachment by ID.

        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID from message parts

        Returns:
            Dictionary with 'data' (base64 decoded bytes) and 'size'
        """
        try:
            logger.info(f"Getting attachment {attachment_id} from message {message_id}")

            attachment = (
                self.gmail_service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )

            data = attachment.get("data", "")
            # Gmail returns URL-safe base64
            file_data = base64.urlsafe_b64decode(data)

            logger.info(f"Retrieved attachment: {len(file_data)} bytes")
            return {"data": file_data, "size": len(file_data)}

        except HttpError as e:
            logger.error(f"Failed to get attachment: {e}")
            raise

    def list_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """
        List attachments on a message.

        Args:
            message_id: Gmail message ID

        Returns:
            List of attachment info dicts with filename, mimeType, attachmentId, size
        """
        try:
            message = (
                self.gmail_service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            attachments = []
            parts = message.get("payload", {}).get("parts", [])
            for part in parts:
                filename = part.get("filename")
                if filename:
                    body = part.get("body", {})
                    attachments.append(
                        {
                            "filename": filename,
                            "mimeType": part.get("mimeType", ""),
                            "attachmentId": body.get("attachmentId", ""),
                            "size": body.get("size", 0),
                        }
                    )

            return attachments

        except HttpError as e:
            logger.error(f"Failed to list attachments: {e}")
            raise

    def modify_labels(
        self,
        message_id: str,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Modify labels on a message (mark read/unread, star, archive, etc.).

        Args:
            message_id: Message ID
            add_labels: Label IDs to add (e.g., ["STARRED", "IMPORTANT"])
            remove_labels: Label IDs to remove (e.g., ["UNREAD", "INBOX"])

        Returns:
            Updated message object
        """
        try:
            logger.info(f"Modifying labels on message: {message_id}")

            body = {}
            if add_labels:
                body["addLabelIds"] = add_labels
            if remove_labels:
                body["removeLabelIds"] = remove_labels

            result = (
                self.gmail_service.users()
                .messages()
                .modify(userId="me", id=message_id, body=body)
                .execute()
            )

            logger.info(f"Modified labels on message: {message_id}")
            return result

        except HttpError as e:
            logger.error(f"Failed to modify labels on message {message_id}: {e}")
            raise
