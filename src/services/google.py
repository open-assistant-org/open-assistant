"""Google service for email and calendar operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.google.auth import (
    OAuthFlowRequired,
    complete_google_oauth_flow,
    get_google_credentials,
    validate_credentials_file,
)
from src.integrations.google.client import GoogleClient
from src.integrations.google.drive import GoogleDriveClient
from src.integrations.google.places import GooglePlacesClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleService(BaseService):
    """Service for Google integration operations (Gmail, Calendar, etc.)."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        """
        Initialize Google service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository (optional)
        """
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_client(self, use_console_flow: bool = True) -> GoogleClient:
        """
        Get configured Google client.

        Args:
            use_console_flow: If True, raise OAuthFlowRequired for chat-based auth

        Returns:
            GoogleClient instance

        Raises:
            ValueError: If Google is not configured properly
            OAuthFlowRequired: If OAuth authorization is needed (when use_console_flow=True)
        """
        # Check if Google integration is enabled
        enabled = self.settings_repo.get("google.enabled")
        if not enabled:
            raise ValueError("Google integration is not enabled")

        # Get OAuth credentials from settings
        # client_id and client_secret are sensitive and stored in credentials repo when set via UI
        client_id = self.settings_repo.get("google.client_id")
        client_secret = self.settings_repo.get("google.client_secret")

        # Fall back to credentials repo for sensitive values
        if not client_id or not client_secret:
            cred = self.credentials_repo.get("google")
            if cred:
                cred_data = cred.get("credential_data", {})
                if not client_id:
                    client_id = cred_data.get("client_id")
                if not client_secret:
                    client_secret = cred_data.get("client_secret")

        project_id = self.settings_repo.get("google.project_id")

        if not client_id:
            raise ValueError("Google Client ID not configured. Please add it in Settings.")
        if not client_secret:
            raise ValueError("Google Client Secret not configured. Please add it in Settings.")

        # Get OAuth credentials (handles token refresh automatically)
        try:
            creds = get_google_credentials(
                client_id=client_id,
                client_secret=client_secret,
                credentials_repo=self.credentials_repo,
                project_id=project_id,
                use_console_flow=use_console_flow,
            )
        except OAuthFlowRequired:
            # Re-raise to be caught by tool executor
            raise
        except Exception as e:
            logger.error(f"Failed to get Google credentials: {e}")
            raise ValueError(f"Failed to authenticate with Google: {str(e)}")

        return GoogleClient(credentials=creds)

    def _get_drive_client(self) -> GoogleDriveClient:
        """
        Get configured Google Drive client (uses same OAuth credentials).

        Returns:
            GoogleDriveClient instance

        Raises:
            ValueError: If Google is not configured properly
            OAuthFlowRequired: If OAuth authorization is needed
        """
        # Reuse the same OAuth credential retrieval — Drive scopes are included
        # in DEFAULT_SCOPES so the same token covers Drive, Docs, Sheets, Slides.
        enabled = self.settings_repo.get("google.enabled")
        if not enabled:
            raise ValueError("Google integration is not enabled")

        client_id = self.settings_repo.get("google.client_id")
        client_secret = self.settings_repo.get("google.client_secret")

        if not client_id or not client_secret:
            cred = self.credentials_repo.get("google")
            if cred:
                cred_data = cred.get("credential_data", {})
                if not client_id:
                    client_id = cred_data.get("client_id")
                if not client_secret:
                    client_secret = cred_data.get("client_secret")

        project_id = self.settings_repo.get("google.project_id")

        if not client_id:
            raise ValueError("Google Client ID not configured. Please add it in Settings.")
        if not client_secret:
            raise ValueError("Google Client Secret not configured. Please add it in Settings.")

        try:
            creds = get_google_credentials(
                client_id=client_id,
                client_secret=client_secret,
                credentials_repo=self.credentials_repo,
                project_id=project_id,
                use_console_flow=True,
            )
        except OAuthFlowRequired:
            raise
        except Exception as e:
            logger.error(f"Failed to get Google credentials for Drive: {e}")
            raise ValueError(f"Failed to authenticate with Google: {str(e)}")

        return GoogleDriveClient(credentials=creds)

    def read_emails(self, filter: str = "is:unread", limit: int = 10) -> List[Dict[str, Any]]:
        """
        Read emails matching filter.

        Args:
            filter: Gmail search filter (default: unread emails)
            limit: Maximum number of emails to return

        Returns:
            List of email messages

        Raises:
            ValueError: If Google is not configured
        """
        client = self._get_client()

        try:
            result = client.list_messages(query=filter, max_results=limit)

            # Log successful request
            self._log_web_request(
                service_name="google",
                action="read_emails",
                endpoint="gmail.users.messages.list",
                method="GET",
                success=True,
                request_data={"filter": filter, "limit": limit},
                response_data={"count": len(result)},
            )

            return result
        except Exception as e:
            # Log failed request
            self._log_web_request(
                service_name="google",
                action="read_emails",
                endpoint="gmail.users.messages.list",
                method="GET",
                success=False,
                request_data={"filter": filter, "limit": limit},
                error_message=str(e),
            )
            raise

    def search_emails(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search emails with query.

        Args:
            query: Gmail search query
            limit: Maximum results

        Returns:
            List of matching emails

        Raises:
            ValueError: If Google is not configured
        """
        client = self._get_client()
        return client.search_messages(query=query, max_results=limit)

    def get_email(self, message_id: str) -> Dict[str, Any]:
        """
        Get specific email by ID.

        Args:
            message_id: Gmail message ID

        Returns:
            Email message

        Raises:
            ValueError: If Google is not configured
        """
        client = self._get_client()
        return client.get_message(message_id=message_id)

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
            to: Recipient email
            subject: Email subject
            body: Email body
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            html: Whether body is HTML

        Returns:
            Created draft

        Raises:
            ValueError: If Google is not configured
        """
        client = self._get_client()
        return client.create_draft(to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html)

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        html: bool = False,
    ) -> Dict[str, Any]:
        """
        Send email.

        Args:
            to: Recipient email
            subject: Email subject
            body: Email body
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            html: Whether body is HTML

        Returns:
            Sent message

        Raises:
            ValueError: If Google is not configured
        """
        client = self._get_client()

        try:
            result = client.send_message(
                to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html
            )

            # Log successful request
            self._log_web_request(
                service_name="google",
                action="send_email",
                endpoint="gmail.users.messages.send",
                method="POST",
                success=True,
                request_data={
                    "to": to,
                    "subject": subject,
                    "cc": cc,
                    "bcc": bcc,
                    "html": html,
                    # Don't log email body for privacy
                    "body_length": len(body),
                },
                response_data={"message_id": result.get("id")},
            )

            return result
        except Exception as e:
            # Log failed request
            self._log_web_request(
                service_name="google",
                action="send_email",
                endpoint="gmail.users.messages.send",
                method="POST",
                success=False,
                request_data={"to": to, "subject": subject, "body_length": len(body)},
                error_message=str(e),
            )
            raise

    def list_calendars(self) -> List[Dict[str, Any]]:
        """
        List all Google calendars accessible to the user.

        Returns:
            List of calendar objects with id, summary, primary status, etc.
        """
        client = self._get_client()
        return client.list_calendars()

    def list_calendar_events(
        self,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        limit: int = 10,
        calendar_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List Google Calendar events.

        Args:
            time_min: Start time filter (RFC3339). Defaults to now if not specified.
            time_max: End time filter (RFC3339)
            limit: Maximum number of events
            calendar_id: Calendar ID to list events from (default: primary)

        Returns:
            List of calendar events
        """
        client = self._get_client()

        # Default to current time if time_min not specified (show only future events)
        if time_min is None:
            time_min = datetime.now(timezone.utc).isoformat()

        # Use primary calendar if not specified
        cal_id = calendar_id if calendar_id else "primary"

        return client.list_events(
            time_min=time_min, time_max=time_max, max_results=limit, calendar_id=cal_id
        )

    def get_calendar_event(self, event_id: str) -> Dict[str, Any]:
        """
        Get a specific Google Calendar event.

        Args:
            event_id: Calendar event ID

        Returns:
            Event object
        """
        client = self._get_client()
        return client.get_event(event_id=event_id)

    def create_calendar_event(
        self,
        summary: str,
        start: str,
        end: str,
        timezone: str = "UTC",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a Google Calendar event.

        Args:
            summary: Event title
            start: Start time (RFC3339 or YYYY-MM-DD for all-day)
            end: End time (RFC3339 or YYYY-MM-DD for all-day)
            timezone: Timezone
            description: Event description
            location: Event location
            attendees: Attendee email addresses

        Returns:
            Created event
        """
        client = self._get_client()
        return client.create_event(
            summary=summary,
            start=start,
            end=end,
            timezone=timezone,
            description=description,
            location=location,
            attendees=attendees,
        )

    def update_calendar_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timezone: str = "UTC",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update a Google Calendar event.

        Args:
            event_id: Event ID to update
            summary: New event title
            start: New start time
            end: New end time
            timezone: Timezone
            description: New description
            location: New location
            attendees: New attendee list

        Returns:
            Updated event
        """
        client = self._get_client()
        return client.update_event(
            event_id=event_id,
            summary=summary,
            start=start,
            end=end,
            timezone=timezone,
            description=description,
            location=location,
            attendees=attendees,
        )

    def delete_calendar_event(self, event_id: str) -> bool:
        """
        Delete a Google Calendar event.

        Args:
            event_id: Event ID to delete

        Returns:
            True if deleted
        """
        client = self._get_client()
        return client.delete_event(event_id=event_id)

    def reply_email(
        self,
        message_id: str,
        thread_id: str,
        body: str,
        to: Optional[str] = None,
        html: bool = False,
    ) -> Dict[str, Any]:
        """
        Reply to an email.

        Args:
            message_id: Original message ID
            thread_id: Thread ID
            body: Reply body
            to: Override recipient
            html: Whether body is HTML

        Returns:
            Sent reply
        """
        client = self._get_client()
        return client.reply_to_message(
            message_id=message_id,
            thread_id=thread_id,
            body=body,
            to=to,
            html=html,
        )

    def trash_email(self, message_id: str) -> bool:
        """
        Move an email to trash.

        Args:
            message_id: Message ID to trash

        Returns:
            True if trashed
        """
        client = self._get_client()
        return client.trash_message(message_id=message_id)

    def modify_labels(
        self,
        message_id: str,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Modify labels on a Gmail message.

        Args:
            message_id: Message ID
            add_labels: Labels to add
            remove_labels: Labels to remove

        Returns:
            Updated message
        """
        client = self._get_client()
        return client.modify_labels(
            message_id=message_id,
            add_labels=add_labels,
            remove_labels=remove_labels,
        )

    def get_attachment(
        self,
        message_id: str,
        attachment_id: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get an email attachment and extract its text content where possible.

        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID
            filename: Original filename (for format detection)

        Returns:
            Dictionary with extracted text or metadata
        """
        from src.services.document import extract_text_from_bytes

        client = self._get_client()
        result = client.get_attachment(message_id=message_id, attachment_id=attachment_id)
        file_data = result["data"]

        extracted = extract_text_from_bytes(file_data, filename or "")

        return {
            "filename": filename,
            "size": result["size"],
            "extracted_text": extracted["text"] if extracted["success"] else None,
            "format": extracted["format"],
            "message": extracted.get("message", ""),
        }

    def get_labels(self) -> List[Dict[str, Any]]:
        """
        Get Gmail labels.

        Returns:
            List of labels

        Raises:
            ValueError: If Google is not configured
        """
        client = self._get_client()
        return client.get_labels()

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Google connection.

        Returns:
            Dictionary with test results
        """
        try:
            client = self._get_client()

            # Try to get labels as a simple test
            client.get_labels()

            return {
                "service_name": "google",
                "status": "success",
                "message": "Google connection successful (Gmail API)",
            }

        except OAuthFlowRequired as e:
            # OAuth needs to be completed by the user first
            return {
                "service_name": "google",
                "status": "oauth_required",
                "message": "Google OAuth not configured. Please complete the OAuth flow first.",
                "auth_url": e.auth_url,
            }
        except ValueError as e:
            return {"service_name": "google", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Google connection test failed: {e}")
            return {
                "service_name": "google",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }

    # ========================================================================
    # PLACES & ROUTES (API key-based)
    # ========================================================================

    def _get_places_client(self) -> GooglePlacesClient:
        """
        Get configured Google Places client.

        Returns:
            GooglePlacesClient instance

        Raises:
            ValueError: If Google Places API key is not configured
        """
        enabled = self.settings_repo.get("google_navigator.enabled")
        if not enabled:
            raise ValueError("Google Navigator integration is not enabled")

        # Check credentials table first (API key stored as service_name='google_navigator', credential_type='api_key')
        api_key = None
        credentials = self.credentials_repo.get("google_navigator")
        if credentials and credentials.get("credential_type") == "api_key":
            credential_data = credentials.get("credential_data", {})
            api_key = credential_data.get("places_api_key")

        # Fall back to settings table for backward compatibility
        if not api_key:
            api_key = self.settings_repo.get("google_navigator.places_api_key")
            # Legacy key support
            if not api_key:
                api_key = self.settings_repo.get("google.places_api_key")

        if not api_key:
            raise ValueError(
                "Google Places API key not configured. "
                "Please add it in Settings under Google Navigator integration."
            )

        return GooglePlacesClient(api_key=api_key)

    def search_places(
        self,
        query: str,
        location: Optional[str] = None,
        radius: Optional[int] = None,
        max_results: int = 10,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for places using text query.

        Args:
            query: Text search query
            location: Lat,lng to bias results
            radius: Search radius in meters
            max_results: Maximum results
            language: Language code

        Returns:
            List of place results
        """
        client = self._get_places_client()
        try:
            result = client.search_places(
                query=query,
                location=location,
                radius=radius,
                max_results=max_results,
                language=language,
            )
            self._log_web_request(
                service_name="google",
                action="search_places",
                endpoint="places.searchText",
                method="POST",
                success=True,
                request_data={"query": query, "location": location, "max_results": max_results},
                response_data={"count": len(result)},
            )
            return result
        except Exception as e:
            self._log_web_request(
                service_name="google",
                action="search_places",
                endpoint="places.searchText",
                method="POST",
                success=False,
                request_data={"query": query},
                error_message=str(e),
            )
            raise

    def get_place_details(
        self,
        place_id: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific place.

        Args:
            place_id: Google Maps Place ID
            language: Language code

        Returns:
            Place details
        """
        client = self._get_places_client()
        return client.get_place_details(place_id=place_id, language=language)

    def nearby_places(
        self,
        location: str,
        radius: int = 1000,
        place_type: Optional[str] = None,
        max_results: int = 10,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for places near a location by type.

        Args:
            location: Lat,lng center point
            radius: Search radius in meters
            place_type: Place type filter
            max_results: Maximum results
            language: Language code

        Returns:
            List of nearby places
        """
        client = self._get_places_client()
        try:
            result = client.nearby_places(
                location=location,
                radius=radius,
                place_type=place_type,
                max_results=max_results,
                language=language,
            )
            self._log_web_request(
                service_name="google",
                action="nearby_places",
                endpoint="places.searchNearby",
                method="POST",
                success=True,
                request_data={
                    "location": location,
                    "radius": radius,
                    "place_type": place_type,
                },
                response_data={"count": len(result)},
            )
            return result
        except Exception as e:
            self._log_web_request(
                service_name="google",
                action="nearby_places",
                endpoint="places.searchNearby",
                method="POST",
                success=False,
                request_data={"location": location, "place_type": place_type},
                error_message=str(e),
            )
            raise

    def get_directions(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
        departure_time: Optional[str] = None,
        avoid: Optional[str] = None,
        waypoints: Optional[List[str]] = None,
        alternatives: bool = False,
        units: str = "metric",
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get directions and travel time between locations.

        Args:
            origin: Starting point
            destination: End point
            mode: Travel mode
            departure_time: Departure time
            avoid: Features to avoid
            waypoints: Intermediate stops
            alternatives: Return alternative routes
            units: Unit system
            language: Language code

        Returns:
            Directions with routes, duration, distance
        """
        client = self._get_places_client()
        try:
            result = client.get_directions(
                origin=origin,
                destination=destination,
                mode=mode,
                departure_time=departure_time,
                avoid=avoid,
                waypoints=waypoints,
                alternatives=alternatives,
                units=units,
                language=language,
            )
            self._log_web_request(
                service_name="google",
                action="get_directions",
                endpoint="directions",
                method="GET",
                success=True,
                request_data={
                    "origin": origin,
                    "destination": destination,
                    "mode": mode,
                },
                response_data={
                    "routes_count": len(result.get("routes", [])),
                },
            )
            return result
        except Exception as e:
            self._log_web_request(
                service_name="google",
                action="get_directions",
                endpoint="directions",
                method="GET",
                success=False,
                request_data={
                    "origin": origin,
                    "destination": destination,
                    "mode": mode,
                },
                error_message=str(e),
            )
            raise

    def geocode_place(
        self,
        address: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Geocode an address to coordinates.

        Args:
            address: Address or place name
            language: Language code

        Returns:
            Geocoding result with coordinates
        """
        client = self._get_places_client()
        return client.geocode(address=address, language=language)

    def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reverse geocode coordinates to an address.

        Args:
            latitude: Latitude
            longitude: Longitude
            language: Language code

        Returns:
            Address information
        """
        client = self._get_places_client()
        return client.reverse_geocode(latitude=latitude, longitude=longitude, language=language)

    # ========================================================================
    # GOOGLE DRIVE OPERATIONS
    # ========================================================================

    def drive_list_files(
        self,
        folder_id: Optional[str] = None,
        max_results: int = 50,
        file_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List files and folders in Google Drive."""
        client = self._get_drive_client()
        result = client.list_files(
            folder_id=folder_id,
            max_results=max_results,
            file_types=file_types,
        )
        self._log_web_request(
            service_name="google",
            action="drive_list_files",
            endpoint="drive.files.list",
            method="GET",
            success=True,
            request_data={"folder_id": folder_id, "max_results": max_results},
            response_data={"count": len(result)},
        )
        return result

    def drive_search_files(
        self,
        query: str,
        max_results: int = 30,
        file_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for files in Google Drive."""
        client = self._get_drive_client()
        result = client.search_files(
            query=query,
            max_results=max_results,
            file_type=file_type,
        )
        self._log_web_request(
            service_name="google",
            action="drive_search_files",
            endpoint="drive.files.list",
            method="GET",
            success=True,
            request_data={"query": query, "max_results": max_results},
            response_data={"count": len(result)},
        )
        return result

    def drive_get_file(self, file_id: str) -> Dict[str, Any]:
        """Get metadata for a Google Drive file."""
        client = self._get_drive_client()
        return client.get_file(file_id=file_id)

    def drive_read_file(self, file_id: str) -> Dict[str, Any]:
        """Read/export content of a Google Drive file."""
        client = self._get_drive_client()
        result = client.read_file(file_id=file_id)
        self._log_web_request(
            service_name="google",
            action="drive_read_file",
            endpoint="drive.files.export",
            method="GET",
            success=True,
            request_data={"file_id": file_id},
            response_data={"name": result.get("name"), "format": result.get("export_format")},
        )
        return result

    # ========================================================================
    # GOOGLE DOCS OPERATIONS
    # ========================================================================

    def docs_create(self, title: str, content: Optional[str] = None) -> Dict[str, Any]:
        """Create a new Google Doc."""
        client = self._get_drive_client()
        result = client.docs_create(title=title, content=content)
        self._log_web_request(
            service_name="google",
            action="docs_create",
            endpoint="docs.documents.create",
            method="POST",
            success=True,
            request_data={"title": title},
            response_data={"document_id": result.get("document_id")},
        )
        return result

    def docs_get(self, document_id: str) -> Dict[str, Any]:
        """Get the text content of a Google Doc."""
        client = self._get_drive_client()
        return client.docs_get(document_id=document_id)

    def docs_append(self, document_id: str, content: str) -> Dict[str, Any]:
        """Append text to an existing Google Doc."""
        client = self._get_drive_client()
        return client.docs_append(document_id=document_id, content=content)

    def docs_update(self, document_id: str, content: str) -> Dict[str, Any]:
        """Replace the full content of a Google Doc."""
        client = self._get_drive_client()
        return client.docs_update(document_id=document_id, content=content)

    # ========================================================================
    # GOOGLE SHEETS OPERATIONS
    # ========================================================================

    def sheets_create(
        self,
        title: str,
        sheet_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new Google Sheets spreadsheet."""
        client = self._get_drive_client()
        result = client.sheets_create(title=title, sheet_names=sheet_names)
        self._log_web_request(
            service_name="google",
            action="sheets_create",
            endpoint="sheets.spreadsheets.create",
            method="POST",
            success=True,
            request_data={"title": title},
            response_data={"spreadsheet_id": result.get("spreadsheet_id")},
        )
        return result

    def sheets_get(self, spreadsheet_id: str) -> Dict[str, Any]:
        """Get metadata and sheet structure of a Google Sheet."""
        client = self._get_drive_client()
        return client.sheets_get(spreadsheet_id=spreadsheet_id)

    def sheets_read(self, spreadsheet_id: str, range_notation: str) -> Dict[str, Any]:
        """Read values from a Google Sheet range."""
        client = self._get_drive_client()
        return client.sheets_read(
            spreadsheet_id=spreadsheet_id,
            range_notation=range_notation,
        )

    def sheets_write(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
    ) -> Dict[str, Any]:
        """Write values to a Google Sheet range."""
        client = self._get_drive_client()
        return client.sheets_write(
            spreadsheet_id=spreadsheet_id,
            range_notation=range_notation,
            values=values,
        )

    def sheets_append(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
    ) -> Dict[str, Any]:
        """Append rows to a Google Sheet."""
        client = self._get_drive_client()
        return client.sheets_append(
            spreadsheet_id=spreadsheet_id,
            range_notation=range_notation,
            values=values,
        )

    # ========================================================================
    # GOOGLE SLIDES OPERATIONS
    # ========================================================================

    def slides_create(self, title: str) -> Dict[str, Any]:
        """Create a new Google Slides presentation."""
        client = self._get_drive_client()
        result = client.slides_create(title=title)
        self._log_web_request(
            service_name="google",
            action="slides_create",
            endpoint="slides.presentations.create",
            method="POST",
            success=True,
            request_data={"title": title},
            response_data={"presentation_id": result.get("presentation_id")},
        )
        return result

    def slides_get(self, presentation_id: str) -> Dict[str, Any]:
        """Get the content of a Google Slides presentation."""
        client = self._get_drive_client()
        return client.slides_get(presentation_id=presentation_id)

    def complete_oauth(self, authorization_code: str) -> Dict[str, Any]:
        """
        Complete Google OAuth flow with authorization code from user.

        Args:
            authorization_code: Authorization code from Google OAuth consent page

        Returns:
            Dictionary with completion status
        """
        try:
            raise NotImplementedError(
                "OAuth completion via service not yet implemented. "
                "Please use the complete_google_oauth endpoint with the flow state."
            )

        except Exception as e:
            logger.error(f"Failed to complete OAuth: {e}")
            return {
                "service_name": "google",
                "status": "error",
                "message": f"OAuth completion failed: {str(e)}",
            }
