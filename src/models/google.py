"""Google API request and response models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReadEmailsRequest(BaseModel):
    """Request model for reading emails."""

    filter: str = Field("is:unread", description="Gmail search filter")
    limit: int = Field(10, description="Maximum number of emails", ge=1, le=100)


class SearchEmailsRequest(BaseModel):
    """Request model for searching emails."""

    query: str = Field(..., description="Gmail search query")
    limit: int = Field(20, description="Maximum results", ge=1, le=100)


class GetEmailRequest(BaseModel):
    """Request model for getting a specific email."""

    message_id: str = Field(..., description="Gmail message ID")


class CreateDraftRequest(BaseModel):
    """Request model for creating a draft."""

    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body")
    cc: Optional[List[str]] = Field(None, description="CC recipients")
    bcc: Optional[List[str]] = Field(None, description="BCC recipients")
    html: bool = Field(False, description="Whether body is HTML")


class SendEmailRequest(BaseModel):
    """Request model for sending an email."""

    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body")
    cc: Optional[List[str]] = Field(None, description="CC recipients")
    bcc: Optional[List[str]] = Field(None, description="BCC recipients")
    html: bool = Field(False, description="Whether body is HTML")


class ListCalendarsRequest(BaseModel):
    """Request model for listing available calendars."""

    pass  # No parameters needed


class ListCalendarEventsRequest(BaseModel):
    """Request model for listing calendar events."""

    calendar_id: Optional[str] = Field(
        None,
        description="Calendar ID to list events from. Use google_list_calendars to see available calendars. If not specified, lists from primary calendar.",
    )
    time_min: Optional[str] = Field(
        None,
        description="Start time filter (RFC3339, e.g. 2026-01-01T00:00:00Z). If not specified, defaults to current time. For 'today' queries, use start of today (e.g. 2026-01-15T00:00:00Z).",
    )
    time_max: Optional[str] = Field(
        None,
        description="End time filter (RFC3339, e.g. 2026-01-01T23:59:59Z). Always set this to scope the query to the relevant period. For 'today' queries, use end of today (e.g. 2026-01-15T23:59:59Z).",
    )
    limit: int = Field(
        10,
        description="Maximum number of events. Use 25 for a single day, 50 for a week.",
        ge=1,
        le=100,
    )


class GetCalendarEventRequest(BaseModel):
    """Request model for getting a specific calendar event."""

    event_id: str = Field(..., description="Google Calendar event ID")


class CreateCalendarEventRequest(BaseModel):
    """Request model for creating a calendar event."""

    summary: str = Field(..., description="Event title")
    start: str = Field(
        ..., description="Start time (RFC3339 e.g. 2026-01-15T09:00:00Z, or YYYY-MM-DD for all-day)"
    )
    end: str = Field(..., description="End time (RFC3339 or YYYY-MM-DD for all-day)")
    timezone: str = Field("UTC", description="Timezone (e.g. America/New_York)")
    description: Optional[str] = Field(None, description="Event description")
    location: Optional[str] = Field(None, description="Event location")
    attendees: Optional[List[str]] = Field(None, description="Attendee email addresses")


class UpdateCalendarEventRequest(BaseModel):
    """Request model for updating a calendar event."""

    event_id: str = Field(..., description="Google Calendar event ID to update")
    summary: Optional[str] = Field(None, description="New event title")
    start: Optional[str] = Field(None, description="New start time (RFC3339 or YYYY-MM-DD)")
    end: Optional[str] = Field(None, description="New end time (RFC3339 or YYYY-MM-DD)")
    timezone: str = Field("UTC", description="Timezone (e.g. America/New_York)")
    description: Optional[str] = Field(None, description="New event description")
    location: Optional[str] = Field(None, description="New event location")
    attendees: Optional[List[str]] = Field(
        None, description="New attendee email list (replaces existing)"
    )


class DeleteCalendarEventRequest(BaseModel):
    """Request model for deleting a calendar event."""

    event_id: str = Field(..., description="Google Calendar event ID to delete")


class ReplyEmailRequest(BaseModel):
    """Request model for replying to an email."""

    message_id: str = Field(..., description="Original Gmail message ID to reply to")
    thread_id: str = Field(..., description="Thread ID of the email conversation")
    body: str = Field(..., description="Reply body text")
    to: Optional[str] = Field(
        None, description="Override recipient email (defaults to original sender)"
    )
    html: bool = Field(False, description="Whether body is HTML")


class TrashEmailRequest(BaseModel):
    """Request model for trashing an email."""

    message_id: str = Field(..., description="Gmail message ID to move to trash")


class ModifyLabelsRequest(BaseModel):
    """Request model for modifying email labels."""

    message_id: str = Field(..., description="Gmail message ID")
    add_labels: Optional[List[str]] = Field(
        None,
        description="Label IDs to add. Common labels: STARRED, IMPORTANT, CATEGORY_PERSONAL, CATEGORY_SOCIAL, CATEGORY_PROMOTIONS, CATEGORY_UPDATES, CATEGORY_FORUMS",
    )
    remove_labels: Optional[List[str]] = Field(
        None,
        description="Label IDs to remove. Common: UNREAD (marks as read), INBOX (archives), STARRED, IMPORTANT",
    )


class GetAttachmentRequest(BaseModel):
    """Request model for downloading an email attachment."""

    message_id: str = Field(..., description="Gmail message ID that contains the attachment")
    attachment_id: str = Field(
        ...,
        description="Attachment ID (found in the parts array of a message payload when mimeType is not text/*)",
    )
    filename: Optional[str] = Field(
        None, description="Original filename of the attachment (for context)"
    )


class GetLabelsRequest(BaseModel):
    """Request model for getting Gmail labels."""

    pass  # No parameters needed


class EmailResponse(BaseModel):
    """Response model for email message."""

    id: str = Field(..., description="Message ID")
    thread_id: str = Field(..., description="Thread ID")
    subject: Optional[str] = Field(None, description="Email subject")
    from_: Optional[str] = Field(None, alias="from", description="Sender email")
    to: Optional[str] = Field(None, description="Recipient email")
    date: Optional[str] = Field(None, description="Email date")
    snippet: Optional[str] = Field(None, description="Email snippet")
    body: Optional[str] = Field(None, description="Email body")
    label_ids: List[str] = Field(default_factory=list, description="Label IDs")

    class Config:
        populate_by_name = True


class DraftResponse(BaseModel):
    """Response model for draft."""

    id: str = Field(..., description="Draft ID")
    message: Dict[str, Any] = Field(..., description="Draft message")


class LabelResponse(BaseModel):
    """Response model for label."""

    id: str = Field(..., description="Label ID")
    name: str = Field(..., description="Label name")
    type: Optional[str] = Field(None, description="Label type")


class GoogleConnectionTestResponse(BaseModel):
    """Response model for connection test."""

    service_name: str = Field(..., description="Service name")
    status: str = Field(..., description="Connection status")
    message: str = Field(..., description="Status message")
    auth_url: Optional[str] = Field(
        None, description="OAuth authorization URL (if status is oauth_required)"
    )


# ========================================================================
# GOOGLE PLACES & ROUTES (API key-based)
# ========================================================================


class SearchPlacesRequest(BaseModel):
    """Request model for searching places via Google Places API."""

    query: str = Field(
        ...,
        description="Text query to search for places (e.g. 'restaurants near Central Park', 'gas stations in Amsterdam')",
    )
    location: Optional[str] = Field(
        None,
        description="Latitude,longitude to bias results around (e.g. '52.3676,4.9041')",
    )
    radius: Optional[int] = Field(
        None,
        description="Search radius in meters (max 50000). Only used when location is provided.",
        ge=1,
        le=50000,
    )
    max_results: int = Field(10, description="Maximum number of results to return", ge=1, le=20)
    language: Optional[str] = Field(
        None, description="Language code for results (e.g. 'en', 'nl', 'de')"
    )


class GetPlaceDetailsRequest(BaseModel):
    """Request model for getting details of a specific place."""

    place_id: str = Field(..., description="Google Maps Place ID (obtained from search results)")
    language: Optional[str] = Field(
        None, description="Language code for results (e.g. 'en', 'nl', 'de')"
    )


class NearbyPlacesRequest(BaseModel):
    """Request model for finding nearby places by type."""

    location: str = Field(
        ...,
        description="Latitude,longitude center point (e.g. '52.3676,4.9041')",
    )
    radius: int = Field(
        1000,
        description="Search radius in meters (max 50000)",
        ge=1,
        le=50000,
    )
    place_type: Optional[str] = Field(
        None,
        description="Place type filter (e.g. 'restaurant', 'gas_station', 'hospital', 'supermarket', 'hotel', 'pharmacy', 'parking', 'atm', 'ev_charging_station')",
    )
    max_results: int = Field(10, description="Maximum number of results to return", ge=1, le=20)
    language: Optional[str] = Field(
        None, description="Language code for results (e.g. 'en', 'nl', 'de')"
    )


class GetDirectionsRequest(BaseModel):
    """Request model for getting directions and travel time between locations."""

    origin: str = Field(
        ...,
        description="Starting point. Can be an address (e.g. 'Amsterdam Central Station'), a place name, or lat,lng coordinates (e.g. '52.3791,4.9003')",
    )
    destination: str = Field(
        ...,
        description="End point. Can be an address, place name, or lat,lng coordinates",
    )
    mode: str = Field(
        "driving",
        description="Travel mode: 'driving', 'walking', 'bicycling', or 'transit'",
    )
    departure_time: Optional[str] = Field(
        None,
        description="Departure time in RFC3339 format (e.g. '2026-02-10T08:00:00Z') for traffic-aware routing. Use 'now' for current time. Only for driving/transit.",
    )
    avoid: Optional[str] = Field(
        None,
        description="Comma-separated features to avoid: 'tolls', 'highways', 'ferries'",
    )
    waypoints: Optional[List[str]] = Field(
        None,
        description="Intermediate stops as addresses or lat,lng coordinates",
    )
    alternatives: bool = Field(False, description="Whether to return alternative routes")
    units: str = Field("metric", description="Unit system: 'metric' or 'imperial'")
    language: Optional[str] = Field(
        None, description="Language code for instructions (e.g. 'en', 'nl', 'de')"
    )


class GeocodePlaceRequest(BaseModel):
    """Request model for geocoding an address to coordinates."""

    address: str = Field(
        ...,
        description="Address or place name to geocode (e.g. 'Eiffel Tower, Paris' or '1600 Amphitheatre Parkway, Mountain View, CA')",
    )
    language: Optional[str] = Field(
        None, description="Language code for results (e.g. 'en', 'nl', 'de')"
    )


class ReverseGeocodeRequest(BaseModel):
    """Request model for reverse geocoding coordinates to an address."""

    latitude: float = Field(..., description="Latitude coordinate", ge=-90, le=90)
    longitude: float = Field(..., description="Longitude coordinate", ge=-180, le=180)
    language: Optional[str] = Field(
        None, description="Language code for results (e.g. 'en', 'nl', 'de')"
    )


# ========================================================================
# GOOGLE DRIVE / DOCS / SHEETS / SLIDES
# ========================================================================


class DriveListFilesRequest(BaseModel):
    """Request model for listing files in Google Drive."""

    folder_id: Optional[str] = Field(
        None,
        description="Parent folder ID to list files from. Leave empty to list from My Drive root. Use google_drive_search_files to find a folder ID.",
    )
    max_results: int = Field(
        50,
        description="Maximum number of files to return (1-200)",
        ge=1,
        le=200,
    )
    file_types: Optional[List[str]] = Field(
        None,
        description="Filter by MIME types. Common values: 'application/vnd.google-apps.document' (Docs), 'application/vnd.google-apps.spreadsheet' (Sheets), 'application/vnd.google-apps.presentation' (Slides), 'application/vnd.google-apps.folder' (Folders)",
    )


class DriveSearchFilesRequest(BaseModel):
    """Request model for searching files in Google Drive."""

    query: str = Field(
        ...,
        description="Search query to find files. Searches both file names and content. Example: 'project proposal', 'budget 2025', 'meeting notes'",
    )
    max_results: int = Field(
        30,
        description="Maximum number of results to return (1-100)",
        ge=1,
        le=100,
    )
    file_type: Optional[str] = Field(
        None,
        description="Filter by MIME type. Common values: 'application/vnd.google-apps.document' (Docs), 'application/vnd.google-apps.spreadsheet' (Sheets), 'application/vnd.google-apps.presentation' (Slides)",
    )


class DriveGetFileRequest(BaseModel):
    """Request model for getting file metadata from Google Drive."""

    file_id: str = Field(
        ...,
        description="Google Drive file ID (obtained from google_drive_list_files or google_drive_search_files)",
    )


class DriveReadFileRequest(BaseModel):
    """Request model for reading/exporting file content from Google Drive."""

    file_id: str = Field(
        ...,
        description="Google Drive file ID. For Google Docs/Sheets/Slides, exports as plain text/CSV. For regular files, downloads and extracts text content.",
    )


# Google Docs


class DocsCreateRequest(BaseModel):
    """Request model for creating a new Google Doc."""

    title: str = Field(..., description="Document title")
    content: Optional[str] = Field(
        None, description="Optional initial text content to insert into the document"
    )


class DocsGetRequest(BaseModel):
    """Request model for reading a Google Doc."""

    document_id: str = Field(
        ...,
        description="Google Docs document ID (from the URL: docs.google.com/document/d/<ID>/edit)",
    )


class DocsAppendRequest(BaseModel):
    """Request model for appending text to a Google Doc."""

    document_id: str = Field(..., description="Google Docs document ID")
    content: str = Field(..., description="Text content to append at the end of the document")


class DocsUpdateRequest(BaseModel):
    """Request model for replacing the full content of a Google Doc."""

    document_id: str = Field(..., description="Google Docs document ID")
    content: str = Field(
        ...,
        description="New text content that will replace all existing content in the document",
    )


# Google Sheets


class SheetsCreateRequest(BaseModel):
    """Request model for creating a new Google Sheets spreadsheet."""

    title: str = Field(..., description="Spreadsheet title")
    sheet_names: Optional[List[str]] = Field(
        None,
        description="Optional list of sheet tab names. If not specified, creates one sheet named 'Sheet1'",
    )


class SheetsGetRequest(BaseModel):
    """Request model for getting spreadsheet metadata."""

    spreadsheet_id: str = Field(
        ...,
        description="Google Sheets spreadsheet ID (from the URL: docs.google.com/spreadsheets/d/<ID>/edit)",
    )


class SheetsReadRequest(BaseModel):
    """Request model for reading values from a Google Sheet range."""

    spreadsheet_id: str = Field(..., description="Google Sheets spreadsheet ID")
    range_notation: str = Field(
        ...,
        description="A1 notation range to read. Examples: 'Sheet1!A1:D10', 'A1:Z100', 'Sheet1!A:A' (entire column A), 'Sheet1!1:1' (entire row 1)",
    )


class SheetsWriteRequest(BaseModel):
    """Request model for writing values to a Google Sheet range."""

    spreadsheet_id: str = Field(..., description="Google Sheets spreadsheet ID")
    range_notation: str = Field(
        ...,
        description="A1 notation range to write to. Examples: 'Sheet1!A1', 'A2:C5'",
    )
    values: List[List[Any]] = Field(
        ...,
        description="2D array of values. Each inner list is a row, each element is a cell value. Example: [['Name', 'Age', 'City'], ['Alice', 30, 'London']]",
    )


class SheetsAppendRequest(BaseModel):
    """Request model for appending rows to a Google Sheet."""

    spreadsheet_id: str = Field(..., description="Google Sheets spreadsheet ID")
    range_notation: str = Field(
        ...,
        description="A1 notation range identifying the table (e.g. 'Sheet1!A1'). Rows will be appended after the last row with data.",
    )
    values: List[List[Any]] = Field(
        ...,
        description="2D array of rows to append. Example: [['Alice', 30, 'London'], ['Bob', 25, 'Paris']]",
    )


# Google Slides


class SlidesCreateRequest(BaseModel):
    """Request model for creating a new Google Slides presentation."""

    title: str = Field(..., description="Presentation title")


class SlidesGetRequest(BaseModel):
    """Request model for reading a Google Slides presentation."""

    presentation_id: str = Field(
        ...,
        description="Google Slides presentation ID (from the URL: docs.google.com/presentation/d/<ID>/edit)",
    )
