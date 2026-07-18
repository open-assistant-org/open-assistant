"""Tool metadata for UI display."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ToolMetadata:
    """Metadata for displaying tool information in UI."""

    name: str
    display_name: str
    description: str
    category: str  # "email", "calendar", "files", "messaging", "notes", "database"


# Tool metadata registry
TOOL_METADATA: Dict[str, ToolMetadata] = {
    # Google Tools
    "google_send_email": ToolMetadata(
        name="google_send_email",
        display_name="Send Email",
        description="Send emails via Gmail",
        category="email",
    ),
    "google_read_emails": ToolMetadata(
        name="google_read_emails",
        display_name="Read Emails",
        description="Read emails from Gmail inbox",
        category="email",
    ),
    "google_search_emails": ToolMetadata(
        name="google_search_emails",
        display_name="Search Emails",
        description="Search Gmail messages by sender, subject, or date",
        category="email",
    ),
    "google_get_email": ToolMetadata(
        name="google_get_email",
        display_name="Get Email",
        description="Get full details of a specific Gmail message",
        category="email",
    ),
    "google_create_draft": ToolMetadata(
        name="google_create_draft",
        display_name="Create Draft",
        description="Create an email draft in Gmail without sending",
        category="email",
    ),
    "google_reply_email": ToolMetadata(
        name="google_reply_email",
        display_name="Reply Email",
        description="Reply to an existing Gmail email thread",
        category="email",
    ),
    "google_trash_email": ToolMetadata(
        name="google_trash_email",
        display_name="Trash Email",
        description="Move a Gmail message to the trash",
        category="email",
    ),
    "google_modify_labels": ToolMetadata(
        name="google_modify_labels",
        display_name="Modify Labels",
        description="Modify labels on a Gmail message (read/unread, star, archive)",
        category="email",
    ),
    "google_get_labels": ToolMetadata(
        name="google_get_labels",
        display_name="Get Labels",
        description="Get all Gmail labels and folders",
        category="email",
    ),
    "google_get_attachment": ToolMetadata(
        name="google_get_attachment",
        display_name="Get Attachment",
        description="Download and read an email attachment from Gmail",
        category="email",
    ),
    "google_list_events": ToolMetadata(
        name="google_list_events",
        display_name="List Events",
        description="List upcoming events from Google Calendar",
        category="calendar",
    ),
    "google_list_calendars": ToolMetadata(
        name="google_list_calendars",
        display_name="List Calendars",
        description="List all available Google calendars (primary, shared, subscribed)",
        category="calendar",
    ),
    "google_get_event": ToolMetadata(
        name="google_get_event",
        display_name="Get Event",
        description="Get full details of a specific calendar event",
        category="calendar",
    ),
    "google_create_event": ToolMetadata(
        name="google_create_event",
        display_name="Create Event",
        description="Create a new event in Google Calendar",
        category="calendar",
    ),
    "google_update_event": ToolMetadata(
        name="google_update_event",
        display_name="Update Event",
        description="Update an existing Google Calendar event",
        category="calendar",
    ),
    "google_delete_event": ToolMetadata(
        name="google_delete_event",
        display_name="Delete Event",
        description="Delete a Google Calendar event",
        category="calendar",
    ),
    # Google Drive Tools
    "google_drive_list_files": ToolMetadata(
        name="google_drive_list_files",
        display_name="List Drive Files",
        description="List files and folders in Google Drive (root or a specific folder)",
        category="files",
    ),
    "google_drive_search_files": ToolMetadata(
        name="google_drive_search_files",
        display_name="Search Drive Files",
        description="Search Google Drive for files by name or content",
        category="files",
    ),
    "google_drive_get_file": ToolMetadata(
        name="google_drive_get_file",
        display_name="Get Drive File",
        description="Get metadata of a specific Google Drive file (name, type, size, URL)",
        category="files",
    ),
    "google_drive_read_file": ToolMetadata(
        name="google_drive_read_file",
        display_name="Read Drive File",
        description="Read or export file content from Google Drive (Docs as text, Sheets as CSV, PDFs extracted)",
        category="files",
    ),
    # Google Docs Tools
    "google_docs_create": ToolMetadata(
        name="google_docs_create",
        display_name="Create Google Doc",
        description="Create a new Google Docs document with optional initial content",
        category="documents",
    ),
    "google_docs_get": ToolMetadata(
        name="google_docs_get",
        display_name="Read Google Doc",
        description="Read the full text content of a Google Docs document",
        category="documents",
    ),
    "google_docs_append": ToolMetadata(
        name="google_docs_append",
        display_name="Append to Google Doc",
        description="Append text to the end of an existing Google Docs document",
        category="documents",
    ),
    "google_docs_update": ToolMetadata(
        name="google_docs_update",
        display_name="Update Google Doc",
        description="Replace all content in a Google Docs document with new text",
        category="documents",
    ),
    # Google Sheets Tools
    "google_sheets_create": ToolMetadata(
        name="google_sheets_create",
        display_name="Create Google Sheet",
        description="Create a new Google Sheets spreadsheet",
        category="documents",
    ),
    "google_sheets_get": ToolMetadata(
        name="google_sheets_get",
        display_name="Get Sheet Info",
        description="Get sheet structure and tab names from a Google Sheets spreadsheet",
        category="documents",
    ),
    "google_sheets_read": ToolMetadata(
        name="google_sheets_read",
        display_name="Read Google Sheet",
        description="Read cell values from a Google Sheets range (A1 notation)",
        category="documents",
    ),
    "google_sheets_write": ToolMetadata(
        name="google_sheets_write",
        display_name="Write Google Sheet",
        description="Write values to a Google Sheets range, overwriting existing cells",
        category="documents",
    ),
    "google_sheets_append": ToolMetadata(
        name="google_sheets_append",
        display_name="Append to Google Sheet",
        description="Append rows to a Google Sheet after the last row with data",
        category="documents",
    ),
    # Google Slides Tools
    "google_slides_create": ToolMetadata(
        name="google_slides_create",
        display_name="Create Google Slides",
        description="Create a new Google Slides presentation",
        category="documents",
    ),
    "google_slides_get": ToolMetadata(
        name="google_slides_get",
        display_name="Read Google Slides",
        description="Read text content from each slide in a Google Slides presentation",
        category="documents",
    ),
    # Google Places & Routes Tools
    "google_search_places": ToolMetadata(
        name="google_search_places",
        display_name="Search Places",
        description="Search for places by name or type (restaurants, hotels, etc.)",
        category="places",
    ),
    "google_get_place_details": ToolMetadata(
        name="google_get_place_details",
        display_name="Get Place Details",
        description="Get detailed info about a place (reviews, hours, phone, website)",
        category="places",
    ),
    "google_nearby_places": ToolMetadata(
        name="google_nearby_places",
        display_name="Nearby Places",
        description="Find places near a location by type (restaurant, gas station, etc.)",
        category="places",
    ),
    "google_get_directions": ToolMetadata(
        name="google_get_directions",
        display_name="Get Directions",
        description="Get directions, travel time, and distance between locations",
        category="navigation",
    ),
    "google_geocode_place": ToolMetadata(
        name="google_geocode_place",
        display_name="Geocode Address",
        description="Convert an address or place name to coordinates",
        category="navigation",
    ),
    "google_reverse_geocode": ToolMetadata(
        name="google_reverse_geocode",
        display_name="Reverse Geocode",
        description="Convert coordinates to a human-readable address",
        category="navigation",
    ),
    # Outlook Tools
    "outlook_send_email": ToolMetadata(
        name="outlook_send_email",
        display_name="Send Email",
        description="Send emails via Outlook/Microsoft 365",
        category="email",
    ),
    "outlook_create_event": ToolMetadata(
        name="outlook_create_event",
        display_name="Create Event",
        description="Create a calendar event in Outlook Calendar",
        category="calendar",
    ),
    "outlook_read_emails": ToolMetadata(
        name="outlook_read_emails",
        display_name="Read Emails",
        description="Read emails from Outlook/Microsoft 365 mailbox",
        category="email",
    ),
    "outlook_list_events": ToolMetadata(
        name="outlook_list_events",
        display_name="List Events",
        description="List calendar events from Outlook Calendar",
        category="calendar",
    ),
    "outlook_list_calendars": ToolMetadata(
        name="outlook_list_calendars",
        display_name="List Calendars",
        description="List all available Outlook/Microsoft 365 calendars",
        category="calendar",
    ),
    "outlook_list_files": ToolMetadata(
        name="outlook_list_files",
        display_name="List Files",
        description="List files and folders in OneDrive",
        category="files",
    ),
    "outlook_search_files": ToolMetadata(
        name="outlook_search_files",
        display_name="Search Files",
        description="Search for files in OneDrive by name or content",
        category="files",
    ),
    "outlook_get_email": ToolMetadata(
        name="outlook_get_email",
        display_name="Get Email",
        description="Get full details of a specific Outlook email",
        category="email",
    ),
    "outlook_search_emails": ToolMetadata(
        name="outlook_search_emails",
        display_name="Search Emails",
        description="Search Outlook emails by query string",
        category="email",
    ),
    "outlook_create_draft": ToolMetadata(
        name="outlook_create_draft",
        display_name="Create Draft",
        description="Create an email draft in Outlook without sending",
        category="email",
    ),
    "outlook_get_attachment": ToolMetadata(
        name="outlook_get_attachment",
        display_name="Get Attachment",
        description="Download and read an email attachment from Outlook",
        category="email",
    ),
    "outlook_update_event": ToolMetadata(
        name="outlook_update_event",
        display_name="Update Event",
        description="Update an existing Outlook Calendar event",
        category="calendar",
    ),
    "outlook_delete_event": ToolMetadata(
        name="outlook_delete_event",
        display_name="Delete Event",
        description="Delete an Outlook Calendar event",
        category="calendar",
    ),
    "outlook_read_file": ToolMetadata(
        name="outlook_read_file",
        display_name="Read File",
        description="Read file content from OneDrive",
        category="files",
    ),
    "onedrive_upload_file": ToolMetadata(
        name="onedrive_upload_file",
        display_name="Upload File",
        description="Upload a file to OneDrive. Supports source_path for local files or content for text.",
        category="files",
    ),
    "outlook_refresh_credentials": ToolMetadata(
        name="outlook_refresh_credentials",
        display_name="Refresh Credentials",
        description="Refresh Outlook OAuth tokens",
        category="system",
    ),
    # OneNote Tools
    "onenote_list_notebooks": ToolMetadata(
        name="onenote_list_notebooks",
        display_name="List Notebooks",
        description="List all OneNote notebooks",
        category="notes",
    ),
    "onenote_get_notebook": ToolMetadata(
        name="onenote_get_notebook",
        display_name="Get Notebook",
        description="Get details of a specific OneNote notebook",
        category="notes",
    ),
    "onenote_list_sections": ToolMetadata(
        name="onenote_list_sections",
        display_name="List Sections",
        description="List OneNote sections",
        category="notes",
    ),
    "onenote_get_section": ToolMetadata(
        name="onenote_get_section",
        display_name="Get Section",
        description="Get details of a specific OneNote section",
        category="notes",
    ),
    "onenote_list_pages": ToolMetadata(
        name="onenote_list_pages",
        display_name="List Pages",
        description="List OneNote pages with filtering",
        category="notes",
    ),
    "onenote_get_page": ToolMetadata(
        name="onenote_get_page",
        display_name="Get Page",
        description="Get a specific OneNote page with content",
        category="notes",
    ),
    "onenote_create_page": ToolMetadata(
        name="onenote_create_page",
        display_name="Create Page",
        description="Create a new OneNote page",
        category="notes",
    ),
    "onenote_create_markdown_page": ToolMetadata(
        name="onenote_create_markdown_page",
        display_name="Create Markdown Page",
        description="Create a OneNote page from Markdown",
        category="notes",
    ),
    "onenote_create_from_template": ToolMetadata(
        name="onenote_create_from_template",
        display_name="Create from Template",
        description="Create a OneNote page from a template",
        category="notes",
    ),
    "onenote_update_page": ToolMetadata(
        name="onenote_update_page",
        display_name="Update Page",
        description="Append content to an existing OneNote page",
        category="notes",
    ),
    "onenote_delete_page": ToolMetadata(
        name="onenote_delete_page",
        display_name="Delete Page",
        description="Delete a OneNote page",
        category="notes",
    ),
    "onenote_copy_page": ToolMetadata(
        name="onenote_copy_page",
        display_name="Copy Page",
        description="Copy a OneNote page to another section",
        category="notes",
    ),
    "onenote_search": ToolMetadata(
        name="onenote_search",
        display_name="Search OneNote",
        description="Search OneNote pages by content",
        category="notes",
    ),
    "onenote_extract_text": ToolMetadata(
        name="onenote_extract_text",
        display_name="Extract Text",
        description="Extract plain text from a OneNote page",
        category="notes",
    ),
    # Microsoft To Do Tools
    "todo_list_task_lists": ToolMetadata(
        name="todo_list_task_lists",
        display_name="List Task Lists",
        description="List all Microsoft To Do task lists",
        category="tasks",
    ),
    "todo_get_task_list": ToolMetadata(
        name="todo_get_task_list",
        display_name="Get Task List",
        description="Get details of a specific To Do task list",
        category="tasks",
    ),
    "todo_create_task_list": ToolMetadata(
        name="todo_create_task_list",
        display_name="Create Task List",
        description="Create a new Microsoft To Do task list",
        category="tasks",
    ),
    "todo_delete_task_list": ToolMetadata(
        name="todo_delete_task_list",
        display_name="Delete Task List",
        description="Delete a Microsoft To Do task list",
        category="tasks",
    ),
    "todo_list_tasks": ToolMetadata(
        name="todo_list_tasks",
        display_name="List Tasks",
        description="List tasks in a Microsoft To Do task list",
        category="tasks",
    ),
    "todo_get_task": ToolMetadata(
        name="todo_get_task",
        display_name="Get Task",
        description="Get details of a specific To Do task",
        category="tasks",
    ),
    "todo_create_task": ToolMetadata(
        name="todo_create_task",
        display_name="Create Task",
        description="Create a new task in Microsoft To Do",
        category="tasks",
    ),
    "todo_update_task": ToolMetadata(
        name="todo_update_task",
        display_name="Update Task",
        description="Update an existing Microsoft To Do task",
        category="tasks",
    ),
    "todo_delete_task": ToolMetadata(
        name="todo_delete_task",
        display_name="Delete Task",
        description="Delete a Microsoft To Do task",
        category="tasks",
    ),
    # Notion Tools
    "notion_create_note": ToolMetadata(
        name="notion_create_note",
        display_name="Create Note",
        description="Create a new note/page in Notion",
        category="notes",
    ),
    "notion_search": ToolMetadata(
        name="notion_search",
        display_name="Search",
        description="Search for pages and content in Notion",
        category="notes",
    ),
    "notion_update_page": ToolMetadata(
        name="notion_update_page",
        display_name="Update Page",
        description="Update properties of an existing Notion page",
        category="notes",
    ),
    "notion_append_content": ToolMetadata(
        name="notion_append_content",
        display_name="Append Content",
        description="Append content blocks to an existing page",
        category="notes",
    ),
    "notion_list_databases": ToolMetadata(
        name="notion_list_databases",
        display_name="List Databases",
        description="List all accessible Notion databases with their IDs and schemas",
        category="database",
    ),
    "notion_query_database": ToolMetadata(
        name="notion_query_database",
        display_name="Query Database",
        description="Query entries from a Notion database with filters",
        category="database",
    ),
    "notion_get_page": ToolMetadata(
        name="notion_get_page",
        display_name="Get Page",
        description="Get properties and metadata of a Notion page",
        category="notes",
    ),
    "notion_get_page_content": ToolMetadata(
        name="notion_get_page_content",
        display_name="Get Page Content",
        description="Get the content blocks of a Notion page",
        category="notes",
    ),
    "notion_delete_page": ToolMetadata(
        name="notion_delete_page",
        display_name="Delete Page",
        description="Delete (archive) a Notion page",
        category="notes",
    ),
    # Nextcloud Tools
    "nextcloud_list_files": ToolMetadata(
        name="nextcloud_list_files",
        display_name="List Files",
        description="List files and folders in Nextcloud",
        category="files",
    ),
    "nextcloud_search_files": ToolMetadata(
        name="nextcloud_search_files",
        display_name="Search Files",
        description="Search for files in Nextcloud by name or pattern",
        category="files",
    ),
    "nextcloud_read_file": ToolMetadata(
        name="nextcloud_read_file",
        display_name="Read File",
        description="Read the content of a file stored in Nextcloud",
        category="files",
    ),
    "nextcloud_download_file": ToolMetadata(
        name="nextcloud_download_file",
        display_name="Download File",
        description="Download a file from Nextcloud to local storage",
        category="files",
    ),
    "nextcloud_get_file_info": ToolMetadata(
        name="nextcloud_get_file_info",
        display_name="Get File Info",
        description="Get metadata about a file (size, type, date)",
        category="files",
    ),
    "nextcloud_file_exists": ToolMetadata(
        name="nextcloud_file_exists",
        display_name="Check File Exists",
        description="Check whether a file exists at a given path",
        category="files",
    ),
    # Brave Search Tools
    "web_search": ToolMetadata(
        name="web_search",
        display_name="Web Search",
        description="Search the web for information using Brave Search",
        category="search",
    ),
    # WhatsApp Tools
    "whatsapp_send_message": ToolMetadata(
        name="whatsapp_send_message",
        display_name="Send Message",
        description="Send a WhatsApp message to a phone number",
        category="messaging",
    ),
    "notify_owner": ToolMetadata(
        name="notify_owner",
        display_name="Notify Owner",
        description="Send a notification to the owner via WhatsApp or Slack",
        category="messaging",
    ),
    "whatsapp_configure_webhook": ToolMetadata(
        name="whatsapp_configure_webhook",
        display_name="Configure Webhook",
        description="Configure webhook URL for incoming messages",
        category="messaging",
    ),
    # Nextcloud write tools
    "nextcloud_upload_file": ToolMetadata(
        name="nextcloud_upload_file",
        display_name="Upload File",
        description="Upload a file to Nextcloud. Supports source_path for local files or content for text.",
        category="files",
    ),
    "nextcloud_create_folder": ToolMetadata(
        name="nextcloud_create_folder",
        display_name="Create Folder",
        description="Create a folder in Nextcloud",
        category="files",
    ),
    "nextcloud_delete_file": ToolMetadata(
        name="nextcloud_delete_file",
        display_name="Delete File",
        description="Delete a file or folder from Nextcloud",
        category="files",
    ),
    "nextcloud_move_file": ToolMetadata(
        name="nextcloud_move_file",
        display_name="Move File",
        description="Move or rename a file in Nextcloud",
        category="files",
    ),
    "nextcloud_copy_file": ToolMetadata(
        name="nextcloud_copy_file",
        display_name="Copy File",
        description="Copy a file in Nextcloud",
        category="files",
    ),
    # Document tools
    "compose_document": ToolMetadata(
        name="compose_document",
        display_name="Compose Document",
        description="AI-powered long-form writing with planning, drafting, and review",
        category="documents",
    ),
    "create_docx": ToolMetadata(
        name="create_docx",
        display_name="Create DOCX",
        description="Create a Word document from markdown content",
        category="documents",
    ),
    "create_pdf": ToolMetadata(
        name="create_pdf",
        display_name="Create PDF",
        description="Create a PDF document from markdown content",
        category="documents",
    ),
    "create_html": ToolMetadata(
        name="create_html",
        display_name="Create HTML Page",
        description="Generate a complete, self-contained HTML page from a plain-English description",
        category="documents",
    ),
    "search_artifacts": ToolMetadata(
        name="search_artifacts",
        display_name="Search Artifacts",
        description="Search previously stored artifacts by filename or title using a regex or "
        "plain-text pattern",
        category="documents",
    ),
    "store_artifact": ToolMetadata(
        name="store_artifact",
        display_name="Store Artifact",
        description="Persist a generated file into the durable artifact store so the user can "
        "view, share, and manage it from the Artifacts tab",
        category="documents",
    ),
    "analyze_content": ToolMetadata(
        name="analyze_content",
        display_name="Analyze Content (LLM)",
        description="Analyze text content using an LLM for insights, summaries, or specific questions",
        category="llm",  # New category for LLM-based analysis
    ),
    # Calculator tools
    "calculate": ToolMetadata(
        name="calculate",
        display_name="Calculate",
        description="Evaluate mathematical expressions",
        category="utility",
    ),
    # Python execution tools
    "python_execute": ToolMetadata(
        name="python_execute",
        display_name="Run Python",
        description="Execute arbitrary Python code and return stdout/stderr output",
        category="utility",
    ),
    "python_agent": ToolMetadata(
        name="python_agent",
        display_name="Run Python (autonomous)",
        description=(
            "Delegate a multi-step Python task to a sub-agent that iterates write→run→refine "
            "and returns only the final summary and output filepaths"
        ),
        category="utility",
    ),
    # Browser tools
    "browse_url": ToolMetadata(
        name="browse_url",
        display_name="Navigate to URL",
        description="Navigate to URL and get accessibility tree structure",
        category="browser",
    ),
    "browse_get_tree": ToolMetadata(
        name="browse_get_tree",
        display_name="Get Page Structure",
        description="Get accessibility tree of current page",
        category="browser",
    ),
    "browse_action": ToolMetadata(
        name="browse_action",
        display_name="Execute Action",
        description="Click, type, or interact with page elements by reference",
        category="browser",
    ),
    "browse_scroll": ToolMetadata(
        name="browse_scroll",
        display_name="Scroll Page",
        description="Scroll up or down to see more content",
        category="browser",
    ),
    "browse_extract": ToolMetadata(
        name="browse_extract",
        display_name="Extract Text",
        description="Extract all visible text from page",
        category="browser",
    ),
    "browse_fetch": ToolMetadata(
        name="browse_fetch",
        display_name="Fetch Content",
        description="Fetch and extract content with anti-bot bypass via Scrapling",
        category="browser",
    ),
    # Unified Search Tools
    "unified_search": ToolMetadata(
        name="unified_search",
        display_name="Unified Search",
        description="Search across all connected sources with hybrid keyword + semantic matching",
        category="search",
    ),
    "reindex_search": ToolMetadata(
        name="reindex_search",
        display_name="Reindex Search",
        description="Rebuild the semantic search index from connected sources",
        category="search",
    ),
    # System Tools - Monitoring & Logging
    "system_fetch_logs": ToolMetadata(
        name="system_fetch_logs",
        display_name="Fetch Logs",
        description="Fetch recent application log lines to review system activity and diagnose issues",
        category="system",
    ),
    "system_get_conversation_text": ToolMetadata(
        name="system_get_conversation_text",
        display_name="Get Conversation Text",
        description="Retrieve conversation messages within a given timespan for review and analysis",
        category="system",
    ),
    "system_get_prompt": ToolMetadata(
        name="system_get_prompt",
        display_name="Get Prompt",
        description="Read the current value of a prompt (system_prompt, memory, or soul)",
        category="system",
    ),
    "system_update_memory_prompt": ToolMetadata(
        name="system_update_memory_prompt",
        display_name="Update Memory",
        description="Update the memory prompt with new information extracted from conversations",
        category="system",
    ),
    "memory_recall": ToolMetadata(
        name="memory_recall",
        display_name="Recall Memory",
        description="Search past conversation messages and indexed memory facts to recall information",
        category="system",
    ),
    "system_update_soul_prompt": ToolMetadata(
        name="system_update_soul_prompt",
        display_name="Update Soul",
        description="Update the soul/personality prompt based on communication preferences",
        category="system",
    ),
    # System Tools - Cron Job Scheduling
    "create_cron_job": ToolMetadata(
        name="create_cron_job",
        display_name="Create Cron Job",
        description="Create a recurring scheduled task (e.g., weekly report, hourly email check)",
        category="system",
    ),
    "list_cron_jobs": ToolMetadata(
        name="list_cron_jobs",
        display_name="List Cron Jobs",
        description="List all scheduled cron jobs and their status",
        category="system",
    ),
    "get_cron_job": ToolMetadata(
        name="get_cron_job",
        display_name="Get Cron Job",
        description="Get details of a specific cron job including execution history",
        category="system",
    ),
    "update_cron_job": ToolMetadata(
        name="update_cron_job",
        display_name="Update Cron Job",
        description="Update a cron job's schedule, name, or parameters",
        category="system",
    ),
    "delete_cron_job": ToolMetadata(
        name="delete_cron_job",
        display_name="Delete Cron Job",
        description="Delete a scheduled cron job permanently",
        category="system",
    ),
    "toggle_cron_job": ToolMetadata(
        name="toggle_cron_job",
        display_name="Toggle Cron Job",
        description="Enable or disable a cron job without deleting it",
        category="system",
    ),
    # System Tools - Future Task Scheduling
    "schedule_task": ToolMetadata(
        name="schedule_task",
        display_name="Schedule Task",
        description="Schedule a one-time task for a specific time (reminders, delayed actions)",
        category="system",
    ),
    "list_future_tasks": ToolMetadata(
        name="list_future_tasks",
        display_name="List Future Tasks",
        description="List scheduled future tasks and their status",
        category="system",
    ),
    "get_future_task": ToolMetadata(
        name="get_future_task",
        display_name="Get Future Task",
        description="Get details of a specific future task including execution history",
        category="system",
    ),
    "cancel_future_task": ToolMetadata(
        name="cancel_future_task",
        display_name="Cancel Future Task",
        description="Cancel a pending future task or reminder",
        category="system",
    ),
    # Google News Tools
    "google_news_top_headlines": ToolMetadata(
        name="google_news_top_headlines",
        display_name="Top Headlines",
        description="Fetch the current top headlines from Google News",
        category="news",
    ),
    "google_news_search": ToolMetadata(
        name="google_news_search",
        display_name="Search News",
        description="Search Google News for articles matching specific keywords",
        category="news",
    ),
    "google_news_by_topic": ToolMetadata(
        name="google_news_by_topic",
        display_name="News by Topic",
        description="Fetch news articles for a predefined topic category (WORLD, BUSINESS, TECHNOLOGY, etc.)",
        category="news",
    ),
    "google_news_by_location": ToolMetadata(
        name="google_news_by_location",
        display_name="News by Location",
        description="Fetch news articles related to a specific geographic location",
        category="news",
    ),
    "google_news_by_site": ToolMetadata(
        name="google_news_by_site",
        display_name="News by Publisher",
        description="Fetch the latest articles from a specific news publisher by domain",
        category="news",
    ),
    # Yahoo Finance Tools
    "yahoo_finance_get_quote": ToolMetadata(
        name="yahoo_finance_get_quote",
        display_name="Get Stock Quote",
        description="Get current price and key market metrics for a stock, ETF, index, or cryptocurrency",
        category="finance",
    ),
    "yahoo_finance_get_history": ToolMetadata(
        name="yahoo_finance_get_history",
        display_name="Get Price History",
        description="Get historical OHLCV price data for a ticker symbol",
        category="finance",
    ),
    "yahoo_finance_get_info": ToolMetadata(
        name="yahoo_finance_get_info",
        display_name="Get Company Info",
        description="Get detailed company or fund profile information including sector, industry, and financial ratios",
        category="finance",
    ),
    "yahoo_finance_get_financials": ToolMetadata(
        name="yahoo_finance_get_financials",
        display_name="Get Financial Statements",
        description="Get financial statements (income, balance sheet, cash flow) for a publicly traded company",
        category="finance",
    ),
    "yahoo_finance_get_news": ToolMetadata(
        name="yahoo_finance_get_news",
        display_name="Get Market News",
        description="Get recent news articles for a ticker symbol",
        category="finance",
    ),
    "yahoo_finance_search": ToolMetadata(
        name="yahoo_finance_search",
        display_name="Search Tickers",
        description="Search for ticker symbols by company name or keyword",
        category="finance",
    ),
    # Google Ads Tools
    "google_ads_get_account_info": ToolMetadata(
        name="google_ads_get_account_info",
        display_name="Get Account Info",
        description="Get basic information about a Google Ads account",
        category="advertising",
    ),
    "google_ads_list_campaigns": ToolMetadata(
        name="google_ads_list_campaigns",
        display_name="List Campaigns",
        description="List campaigns in a Google Ads account",
        category="advertising",
    ),
    "google_ads_get_campaign": ToolMetadata(
        name="google_ads_get_campaign",
        display_name="Get Campaign",
        description="Get details for a single campaign",
        category="advertising",
    ),
    "google_ads_create_campaign": ToolMetadata(
        name="google_ads_create_campaign",
        display_name="Create Campaign",
        description="Create a new Google Ads campaign",
        category="advertising",
    ),
    "google_ads_update_campaign_status": ToolMetadata(
        name="google_ads_update_campaign_status",
        display_name="Update Campaign Status",
        description="Enable, pause, or remove a campaign",
        category="advertising",
    ),
    "google_ads_update_campaign_budget": ToolMetadata(
        name="google_ads_update_campaign_budget",
        display_name="Update Campaign Budget",
        description="Change a campaign's daily budget",
        category="advertising",
    ),
    "google_ads_list_ad_groups": ToolMetadata(
        name="google_ads_list_ad_groups",
        display_name="List Ad Groups",
        description="List ad groups in a Google Ads account",
        category="advertising",
    ),
    "google_ads_create_ad_group": ToolMetadata(
        name="google_ads_create_ad_group",
        display_name="Create Ad Group",
        description="Create an ad group within a campaign",
        category="advertising",
    ),
    "google_ads_list_keywords": ToolMetadata(
        name="google_ads_list_keywords",
        display_name="List Keywords",
        description="List keywords in a Google Ads account",
        category="advertising",
    ),
    "google_ads_add_keyword": ToolMetadata(
        name="google_ads_add_keyword",
        display_name="Add Keyword",
        description="Add a keyword to an ad group",
        category="advertising",
    ),
    "google_ads_get_campaign_performance": ToolMetadata(
        name="google_ads_get_campaign_performance",
        display_name="Get Campaign Performance",
        description="Get performance metrics for campaigns",
        category="advertising",
    ),
    "google_ads_get_ad_group_performance": ToolMetadata(
        name="google_ads_get_ad_group_performance",
        display_name="Get Ad Group Performance",
        description="Get performance metrics for ad groups",
        category="advertising",
    ),
    # Plugin Builder Tools
    "install_plugin": ToolMetadata(
        name="install_plugin",
        display_name="Install Plugin",
        description="Install an Open Assistant plugin from a URL or pasted JSON definition",
        category="system",
    ),
    "inspect_api_source": ToolMetadata(
        name="inspect_api_source",
        display_name="Inspect API Source",
        description="Analyse a URL for plugin content (OpenAPI spec, plugin JSON, or docs page) without installing",
        category="system",
    ),
    "test_plugin_connection": ToolMetadata(
        name="test_plugin_connection",
        display_name="Test Plugin Connection",
        description="Test connectivity and auth for an installed plugin",
        category="system",
    ),
}


def get_tool_service(tool_name: str) -> str:
    """
    Get the service/integration name for a tool.

    Args:
        tool_name: Tool name (e.g., 'google_send_email')

    Returns:
        Service name (e.g., 'google', 'outlook', 'system')
    """
    # Google Navigator tools (places, directions, geocoding)
    navigator_tools = {
        "google_search_places",
        "google_get_place_details",
        "google_nearby_places",
        "google_get_directions",
        "google_geocode_place",
        "google_reverse_geocode",
    }
    if tool_name in navigator_tools:
        return "google_navigator"

    # WhatsApp/Slack unified tools
    if tool_name == "notify_owner":
        return "whatsapp"

    # System tools
    system_tools = {
        "system_fetch_logs",
        "system_get_conversation_text",
        "system_get_prompt",
        "system_update_memory_prompt",
        "system_update_soul_prompt",
        "create_cron_job",
        "list_cron_jobs",
        "get_cron_job",
        "update_cron_job",
        "delete_cron_job",
        "toggle_cron_job",
        "schedule_task",
        "list_future_tasks",
        "get_future_task",
        "cancel_future_task",
        "compose_document",
        "create_docx",
        "create_pdf",
        "create_html",
        "search_artifacts",
        "store_artifact",
        "calculate",
        "python_execute",
        "python_agent",
        "install_plugin",
        "inspect_api_source",
        "test_plugin_connection",
    }
    if tool_name in system_tools:
        return "system"

    # Prefix-based mapping
    prefix_map = {
        "google_ads_": "google_ads",
        "google_news_": "google_news",
        "google_": "google",
        "outlook_": "outlook",
        "onedrive_": "outlook",
        "onenote_": "outlook",
        "todo_": "outlook",
        "notion_": "notion",
        "nextcloud_": "nextcloud",
        "whatsapp_": "whatsapp",
        "web_search": "brave",
        "browse_": "browser",
        "yahoo_finance_": "yahoo_finance",
    }

    for prefix, service in prefix_map.items():
        if tool_name.startswith(prefix) or tool_name == prefix:
            return service

    return "system"


def get_all_tools_grouped() -> Dict[str, List[ToolMetadata]]:
    """
    Get all tools grouped by service/integration.

    Returns:
        Dictionary mapping service name to list of ToolMetadata
    """
    grouped: Dict[str, List[ToolMetadata]] = {}
    for tool in TOOL_METADATA.values():
        service = get_tool_service(tool.name)
        if service not in grouped:
            grouped[service] = []
        grouped[service].append(tool)
    return grouped


def get_tool_metadata(tool_name: str) -> ToolMetadata:
    """
    Get metadata for a specific tool.

    Args:
        tool_name: Tool name

    Returns:
        ToolMetadata for the tool or None if not found
    """
    return TOOL_METADATA.get(tool_name)
