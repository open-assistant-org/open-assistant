"""Outlook API request and response models."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ReadEmailsRequest(BaseModel):
    folder: str = Field("inbox", description="Folder name")
    limit: int = Field(10, description="Maximum emails", ge=1, le=100)
    query: Optional[str] = Field(
        None,
        description="OData filter query to narrow results (e.g. \"from/emailAddress/address eq 'user@example.com'\")",
    )


class SendEmailRequest(BaseModel):
    to: List[str] = Field(..., description="Recipients")
    subject: str = Field(..., description="Subject")
    body: str = Field(..., description="Body")
    body_type: str = Field("text", description="Body type (text or html)")
    cc: Optional[List[str]] = Field(None, description="CC recipients")
    bcc: Optional[List[str]] = Field(None, description="BCC recipients")


class ListCalendarsRequest(BaseModel):
    """Request model for listing available calendars."""

    pass  # No parameters needed


class ListEventsRequest(BaseModel):
    calendar_id: Optional[str] = Field(
        None,
        description="Calendar ID to list events from. Use outlook_list_calendars to see available calendars. If not specified, uses default calendar.",
    )
    start_date: Optional[str] = Field(
        None,
        description="Start date filter. Accepts ISO-8601 (e.g. 2026-01-01T00:00:00) or relative terms like 'today', 'tomorrow', 'yesterday', 'now', 'this week'. If not specified, defaults to the current time.",
    )
    end_date: Optional[str] = Field(
        None,
        description="End date filter. Accepts ISO-8601 (e.g. 2026-01-01T23:59:59) or relative terms like 'today', 'tomorrow', 'this week'. Always set this to scope the query to the relevant period; relative terms and bare dates resolve to end-of-day.",
    )
    limit: int = Field(
        10, description="Maximum events. Use 25 for a single day, 50 for a week.", ge=1, le=100
    )


class CreateEventRequest(BaseModel):
    subject: str = Field(..., description="Event subject")
    start: str = Field(..., description="Start time (ISO format)")
    end: str = Field(..., description="End time (ISO format)")
    timezone: str = Field("UTC", description="Timezone")
    location: Optional[str] = Field(None, description="Location")
    body: Optional[str] = Field(None, description="Event body")
    attendees: Optional[List[str]] = Field(None, description="Attendees")
    is_online_meeting: bool = Field(False, description="Create Teams meeting")


class ListFilesRequest(BaseModel):
    folder_path: str = Field("/", description="Folder path")


class SearchFilesRequest(BaseModel):
    query: str = Field(..., description="Search query")


class GetEmailRequest(BaseModel):
    """Request model for getting a specific email."""

    message_id: str = Field(..., description="Outlook message ID")


class SearchEmailsRequest(BaseModel):
    """Request model for searching emails."""

    query: str = Field(..., description="Search query string")
    folder: str = Field(
        "inbox", description="Mail folder to search in (inbox, sentitems, drafts, etc.)"
    )
    limit: int = Field(20, description="Maximum results", ge=1, le=100)


class CreateDraftRequest(BaseModel):
    """Request model for creating an email draft."""

    to: List[str] = Field(..., description="Recipient email addresses")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body")
    body_type: str = Field("text", description="Body type: 'text' or 'html'")
    cc: Optional[List[str]] = Field(None, description="CC recipients")
    bcc: Optional[List[str]] = Field(None, description="BCC recipients")


class UpdateEventRequest(BaseModel):
    """Request model for updating a calendar event."""

    event_id: str = Field(..., description="Outlook event ID to update")
    subject: Optional[str] = Field(None, description="New event subject")
    start: Optional[str] = Field(None, description="New start time (ISO format)")
    end: Optional[str] = Field(None, description="New end time (ISO format)")
    timezone: Optional[str] = Field(None, description="Timezone")
    location: Optional[str] = Field(None, description="New location")
    body: Optional[str] = Field(None, description="New event body/description")


class DeleteEventRequest(BaseModel):
    """Request model for deleting a calendar event."""

    event_id: str = Field(..., description="Outlook event ID to delete")


class ReadFileRequest(BaseModel):
    """Request model for reading a OneDrive file by ID or path."""

    file_id: Optional[str] = Field(
        None,
        description="OneDrive file ID (from outlook_list_files or outlook_search_files). Provide either file_id or file_path.",
    )
    file_path: Optional[str] = Field(
        None,
        description="Full OneDrive file path from root, e.g. '/Documents/notes.md' or '/Obsidian/vault/Schema A.md'. Provide either file_id or file_path.",
    )


class GetAttachmentRequest(BaseModel):
    """Request model for downloading an Outlook email attachment."""

    message_id: str = Field(..., description="Outlook message ID that contains the attachment")
    attachment_id: str = Field(..., description="Attachment ID")
    filename: Optional[str] = Field(
        None, description="Original filename of the attachment (for context)"
    )


class UploadFileRequest(BaseModel):
    """Request model for uploading a file to OneDrive."""

    folder_path: str = Field(
        "/", description="OneDrive folder path to upload to (e.g. '/Documents/Reports')"
    )
    filename: str = Field(..., description="Name of the file to create (e.g. 'report.docx')")
    content: Optional[str] = Field(
        default=None,
        description="File content as a string. Use this for text, or provide source_path for local files.",
    )
    is_base64: bool = Field(False, description="Whether the content is base64-encoded binary data")
    source_path: Optional[str] = Field(
        default=None,
        description="Local file path to upload. If provided, content is ignored and "
        "the file at source_path is read and uploaded to folder_path/filename.",
    )


class RefreshCredentialsRequest(BaseModel):
    """Request model for proactively refreshing Outlook credentials."""

    pass  # No parameters needed


# ========================================================================
# ONENOTE REQUEST MODELS
# ========================================================================


class OnenoteListNotebooksRequest(BaseModel):
    """Request model for listing OneNote notebooks."""

    include_sections: bool = Field(False, description="Include sections in each notebook")


class OnenoteGetNotebookRequest(BaseModel):
    """Request model for getting a specific OneNote notebook."""

    notebook_id: str = Field(..., description="OneNote notebook ID")


class OnenoteListSectionsRequest(BaseModel):
    """Request model for listing OneNote sections."""

    notebook_id: Optional[str] = Field(None, description="Filter by notebook ID")


class OnenoteGetSectionRequest(BaseModel):
    """Request model for getting a specific OneNote section."""

    section_id: str = Field(..., description="OneNote section ID")


class OnenoteListPagesRequest(BaseModel):
    """Request model for listing OneNote pages."""

    section_id: Optional[str] = Field(None, description="Filter by section ID")
    notebook_id: Optional[str] = Field(None, description="Filter by notebook ID")
    limit: int = Field(20, description="Maximum pages to return", ge=1, le=100)
    include_content: bool = Field(False, description="Include full page HTML content")


class OnenoteGetPageRequest(BaseModel):
    """Request model for getting a specific OneNote page."""

    page_id: str = Field(..., description="OneNote page ID")
    include_content: bool = Field(True, description="Include full page HTML content")


class OnenoteCreatePageRequest(BaseModel):
    """Request model for creating a OneNote page."""

    section_id: str = Field(..., description="Section ID to create page in")
    title: str = Field(..., description="Page title")
    content: str = Field(..., description="Page content (HTML format)")
    content_type: str = Field("html", description="Content type: 'html' or 'text'")


class OnenoteUpdatePageRequest(BaseModel):
    """Request model for updating (appending to) a OneNote page."""

    page_id: str = Field(..., description="OneNote page ID")
    content: str = Field(..., description="Content to append (HTML format)")


class OnenoteDeletePageRequest(BaseModel):
    """Request model for deleting a OneNote page."""

    page_id: str = Field(..., description="OneNote page ID to delete")


class OnenoteSearchRequest(BaseModel):
    """Request model for searching OneNote pages."""

    query: str = Field(..., description="Search query (matches against page title)")
    section_id: Optional[str] = Field(
        None, description="Optional section ID to narrow search scope"
    )
    notebook_id: Optional[str] = Field(
        None, description="Optional notebook ID to narrow search scope"
    )
    limit: int = Field(20, description="Maximum results", ge=1, le=100)


class OnenoteCopyPageRequest(BaseModel):
    """Request model for copying a page to another section."""

    page_id: str = Field(..., description="Page ID to copy")
    target_section_id: str = Field(..., description="Target section ID")


class OnenoteCreateFromTemplateRequest(BaseModel):
    """Request model for creating a page from a predefined template."""

    section_id: str = Field(..., description="Section ID to create page in")
    template: str = Field(
        ...,
        description="Template name: 'meeting_notes', 'daily_journal', 'todo', or 'project'",
    )
    title: str = Field(..., description="Page title")
    variables: Optional[Dict[str, str]] = Field(
        None,
        description="Template variables (e.g., {'attendees': 'John, Jane', 'date': '2024-01-15'})",
    )


class OnenoteExtractTextRequest(BaseModel):
    """Request model for extracting plain text from a page."""

    page_id: str = Field(..., description="OneNote page ID")


class OnenoteCreateMarkdownPageRequest(BaseModel):
    """Request model for creating a page from Markdown content."""

    section_id: str = Field(..., description="Section ID to create page in")
    title: str = Field(..., description="Page title")
    markdown_content: str = Field(..., description="Page content in Markdown format")


# ========================================================================
# MICROSOFT TO DO REQUEST MODELS
# ========================================================================


class TodoListTaskListsRequest(BaseModel):
    """Request model for listing Microsoft To Do task lists."""

    pass  # No parameters needed


class TodoGetTaskListRequest(BaseModel):
    """Request model for getting a specific To Do task list."""

    list_id: str = Field(..., description="To Do task list ID or display name")


class TodoCreateTaskListRequest(BaseModel):
    """Request model for creating a new To Do task list."""

    display_name: str = Field(..., description="Name of the task list")


class TodoDeleteTaskListRequest(BaseModel):
    """Request model for deleting a To Do task list."""

    list_id: str = Field(..., description="To Do task list ID or display name to delete")


class TodoListTasksRequest(BaseModel):
    """Request model for listing tasks in a To Do task list."""

    list_id: str = Field(
        ...,
        description="To Do task list ID or display name (e.g., 'Tasks', 'Groceries')",
    )
    status: Optional[str] = Field(
        None,
        description="Filter by status: 'notStarted', 'inProgress', or 'completed'",
    )
    limit: int = Field(50, description="Maximum tasks to return", ge=1, le=100)


class TodoGetTaskRequest(BaseModel):
    """Request model for getting a specific To Do task."""

    list_id: str = Field(..., description="To Do task list ID or display name")
    task_id: str = Field(..., description="To Do task ID")


class TodoCreateTaskRequest(BaseModel):
    """Request model for creating a new To Do task."""

    list_id: str = Field(
        ...,
        description="To Do task list ID or display name (e.g., 'Tasks', 'Groceries')",
    )
    title: str = Field(..., description="Task title")
    body: Optional[str] = Field(None, description="Task body/notes (plain text)")
    due_date: Optional[str] = Field(
        None, description="Due date in YYYY-MM-DD format (e.g. '2026-03-15')"
    )
    importance: str = Field("normal", description="Task importance: 'low', 'normal', or 'high'")
    reminder_date_time: Optional[str] = Field(
        None,
        description="Reminder datetime in ISO format (e.g. '2026-03-05T09:00:00')",
    )


class TodoUpdateTaskRequest(BaseModel):
    """Request model for updating an existing To Do task."""

    list_id: str = Field(..., description="To Do task list ID or display name")
    task_id: str = Field(..., description="To Do task ID to update")
    title: Optional[str] = Field(None, description="New task title")
    body: Optional[str] = Field(None, description="New task body/notes")
    due_date: Optional[str] = Field(None, description="New due date in YYYY-MM-DD format")
    importance: Optional[str] = Field(
        None, description="New importance: 'low', 'normal', or 'high'"
    )
    status: Optional[str] = Field(
        None,
        description="New status: 'notStarted', 'inProgress', or 'completed'",
    )
    reminder_date_time: Optional[str] = Field(
        None,
        description="Reminder datetime in ISO format (e.g. '2026-03-05T09:00:00')",
    )


class TodoDeleteTaskRequest(BaseModel):
    """Request model for deleting a To Do task."""

    list_id: str = Field(..., description="To Do task list ID or display name")
    task_id: str = Field(..., description="To Do task ID to delete")


class OutlookConnectionTestResponse(BaseModel):
    service_name: str = Field(..., description="Service name")
    status: str = Field(..., description="Status")
    message: str = Field(..., description="Message")
