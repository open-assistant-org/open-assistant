"""Tool definitions for all integrations."""

from src.core.tools.registry import Tool, get_tool_registry
from src.core.tools.schema import create_tool_schema
from src.models.cron_jobs import (
    CreateCronJobRequest,
    DeleteCronJobRequest,
    GetCronJobRequest,
    ListCronJobsRequest,
    ToggleCronJobRequest,
    UpdateCronJobRequest,
)
from src.models.future_tasks import (
    CancelFutureTaskRequest,
    GetFutureTaskRequest,
    ListFutureTasksRequest,
    ScheduleTaskRequest,
)
from src.models.batch import BatchToolRequest
from src.models.loop import LoopToolRequest
from src.models.plan_tools import (
    AskUserRequest,
    DispatchTaskRequest,
    GetTaskResultRequest,
    RevisePlanRequest,
    WaitForTasksRequest,
)
from src.models.calculator import CalculateRequest
from src.models.python_exec import PythonAgentRequest, PythonExecuteRequest
from src.models.document import (
    ComposeDocumentRequest,
    CreateDocxRequest,
    CreateHtmlRequest,
    CreatePdfRequest,
)
from src.models.analysis import AnalyzeContentRequest
from src.models.google import (
    CreateCalendarEventRequest,
    CreateDraftRequest,
    DeleteCalendarEventRequest,
    DocsAppendRequest,
    DocsCreateRequest,
    DocsGetRequest,
    DocsUpdateRequest,
    DriveGetFileRequest,
    DriveListFilesRequest,
    DriveReadFileRequest,
    DriveSearchFilesRequest,
    GeocodePlaceRequest,
    GetAttachmentRequest,
    GetCalendarEventRequest,
    GetDirectionsRequest,
    GetEmailRequest,
    GetLabelsRequest,
    GetPlaceDetailsRequest,
    ListCalendarEventsRequest,
    ListCalendarsRequest,
    ModifyLabelsRequest,
    NearbyPlacesRequest,
    ReadEmailsRequest,
    ReplyEmailRequest,
    ReverseGeocodeRequest,
    SearchEmailsRequest,
    SearchPlacesRequest,
    SendEmailRequest,
    SheetsAppendRequest,
    SheetsCreateRequest,
    SheetsGetRequest,
    SheetsReadRequest,
    SheetsWriteRequest,
    SlidesCreateRequest,
    SlidesGetRequest,
    TrashEmailRequest,
    UpdateCalendarEventRequest,
)
from src.models.monitoring import (
    CleanTmpDirRequest,
    FetchLogsRequest,
    GetConversationTextRequest,
    GetPromptRequest,
    IndexMemoryFactsRequest,
    RecallConversationMemoryRequest,
    UpdateMemoryPromptRequest,
    UpdateSoulPromptRequest,
)
from src.models.nextcloud import (
    CopyFileRequest,
    CreateFolderRequest,
    DeleteFileRequest,
    DownloadFileRequest,
    FileExistsRequest,
    FileInfoRequest,
    ListFilesRequest,
    MoveFileRequest,
    ReadFileRequest,
    ReadPdfRequest,
    SearchFilesRequest,
    UploadFileRequest,
)
from src.models.notion import (
    AppendContentRequest,
    CreateNoteRequest,
    CreatePageRequest,
    DeletePageRequest,
    GetPageContentRequest,
    GetPageRequest,
    ListDatabasesRequest,
    ListDataSourcesRequest,
    QueryDatabaseRequest,
    SearchRequest,
    UpdatePageRequest,
)
from src.models.outlook import CreateEventRequest, ListEventsRequest
from src.models.outlook import CreateDraftRequest as OutlookCreateDraftRequest
from src.models.outlook import DeleteEventRequest as OutlookDeleteEventRequest
from src.models.outlook import GetAttachmentRequest as OutlookGetAttachmentRequest
from src.models.outlook import GetEmailRequest as OutlookGetEmailRequest
from src.models.outlook import ListCalendarsRequest as OutlookListCalendarsRequest
from src.models.outlook import ListFilesRequest as OutlookListFilesRequest
from src.models.outlook import ReadEmailsRequest as OutlookReadEmailsRequest
from src.models.outlook import ReadFileRequest as OutlookReadFileRequest
from src.models.outlook import SearchEmailsRequest as OutlookSearchEmailsRequest
from src.models.outlook import SearchFilesRequest as OutlookSearchFilesRequest
from src.models.outlook import SendEmailRequest as OutlookSendEmailRequest
from src.models.outlook import RefreshCredentialsRequest as OutlookRefreshCredentialsRequest
from src.models.outlook import UpdateEventRequest as OutlookUpdateEventRequest
from src.models.outlook import UploadFileRequest as OutlookUploadFileRequest

# OneNote models
from src.models.outlook import (
    OnenoteCopyPageRequest,
    OnenoteCreateFromTemplateRequest,
    OnenoteCreateMarkdownPageRequest,
    OnenoteCreatePageRequest,
    OnenoteDeletePageRequest,
    OnenoteExtractTextRequest,
    OnenoteGetNotebookRequest,
    OnenoteGetPageRequest,
    OnenoteGetSectionRequest,
    OnenoteListNotebooksRequest,
    OnenoteListPagesRequest,
    OnenoteListSectionsRequest,
    OnenoteSearchRequest,
    OnenoteUpdatePageRequest,
)

# Microsoft To Do models
from src.models.outlook import (
    TodoCreateTaskListRequest,
    TodoCreateTaskRequest,
    TodoDeleteTaskListRequest,
    TodoDeleteTaskRequest,
    TodoGetTaskListRequest,
    TodoGetTaskRequest,
    TodoListTaskListsRequest,
    TodoListTasksRequest,
    TodoUpdateTaskRequest,
)
from src.models.google_ads import (
    AddKeywordRequest as GoogleAdsAddKeywordRequest,
    CreateAdGroupRequest as GoogleAdsCreateAdGroupRequest,
    CreateCampaignRequest as GoogleAdsCreateCampaignRequest,
    GetAccountInfoRequest as GoogleAdsGetAccountInfoRequest,
    GetAdGroupPerformanceRequest as GoogleAdsGetAdGroupPerformanceRequest,
    GetCampaignPerformanceRequest as GoogleAdsGetCampaignPerformanceRequest,
    GetCampaignRequest as GoogleAdsGetCampaignRequest,
    ListAdGroupsRequest as GoogleAdsListAdGroupsRequest,
    ListCampaignsRequest as GoogleAdsListCampaignsRequest,
    ListKeywordsRequest as GoogleAdsListKeywordsRequest,
    UpdateCampaignBudgetRequest as GoogleAdsUpdateCampaignBudgetRequest,
    UpdateCampaignStatusRequest as GoogleAdsUpdateCampaignStatusRequest,
)
from src.models.brave import WebSearchRequest
from src.models.browser import (
    BrowseActionRequest,
    BrowseExtractRequest,
    BrowseFetchRequest,
    BrowseGetTreeRequest,
    BrowseScrollRequest,
    BrowseUrlRequest,
)
from src.models.search import ReindexSearchRequest, UnifiedSearchRequest
from src.models.whatsapp import (
    GetStatusRequest,
    NotifyOwnerRequest,
    SendMessageRequest,
    WebhookConfigRequest,
)
from src.models.slack import (
    SlackSendMessageRequest,
    SlackSendMessageToDefaultChannelRequest,
)
from src.models.google_news import (
    GoogleNewsByLocationRequest,
    GoogleNewsBySiteRequest,
    GoogleNewsByTopicRequest,
    GoogleNewsSearchRequest,
    GoogleNewsTopHeadlinesRequest,
)
from src.models.yahoo_finance import (
    YahooFinanceGetFinancialsRequest,
    YahooFinanceGetHistoryRequest,
    YahooFinanceGetInfoRequest,
    YahooFinanceGetNewsRequest,
    YahooFinanceGetQuoteRequest,
    YahooFinanceSearchRequest,
)


def define_google_tools():
    """Define Google integration tools."""
    registry = get_tool_registry()

    # Google: Send Email
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_send_email",
                description="Send an email via Google (Gmail). Use this when the user asks to send an email through Google/Gmail. If authentication is required, the tool will return an auth URL for the user to visit.",
                parameters_model=SendEmailRequest,
            ),
            executor=None,  # Set by tool executor
            service_name="google",
        )
    )

    # Google: Read Emails
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_read_emails",
                description="Read emails from Google (Gmail) inbox. Use to check recent emails or search for specific emails. Returns email details including sender, subject, and body. If authentication is required, the tool will return an auth URL for the user to visit.",
                parameters_model=ReadEmailsRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Search Emails
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_search_emails",
                description="Search Gmail messages using a query. Use when the user wants to find specific emails by sender, subject, date, or other criteria.",
                parameters_model=SearchEmailsRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Get Email
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_get_email",
                description="Get full details of a specific Gmail message by its ID. Use when the user wants to read the complete content of a particular email.",
                parameters_model=GetEmailRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Create Draft
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_create_draft",
                description="Create an email draft in Gmail without sending it. Use when the user wants to compose an email to review or send later.",
                parameters_model=CreateDraftRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Reply Email
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_reply_email",
                description="Reply to an existing Gmail email thread. Requires the original message_id and thread_id (obtained from google_get_email or google_search_emails). The reply is sent within the same thread.",
                parameters_model=ReplyEmailRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Trash Email
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_trash_email",
                description="Move a Gmail message to the trash. Use when the user wants to delete an email. The message can be recovered from trash for 30 days.",
                parameters_model=TrashEmailRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Modify Labels
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_modify_labels",
                description="Modify labels on a Gmail message. Use to mark as read (remove UNREAD), mark as unread (add UNREAD), star (add STARRED), unstar (remove STARRED), archive (remove INBOX), or apply any other Gmail label. Get available labels with google_get_labels first.",
                parameters_model=ModifyLabelsRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Get Labels
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_get_labels",
                description="Get all Gmail labels/folders available to the user. Returns label IDs and names. Use this to discover available labels before modifying labels on messages. Common system labels: INBOX, SENT, DRAFT, SPAM, TRASH, UNREAD, STARRED, IMPORTANT.",
                parameters_model=GetLabelsRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Get Attachment
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_get_attachment",
                description="Download and read an email attachment from Gmail. Automatically extracts text from PDF, DOCX, and text files. First get the message details with google_get_email to find attachment IDs in the 'attachments' array, then use this tool with the message_id and attachment_id.",
                parameters_model=GetAttachmentRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: List Calendars
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_list_calendars",
                description="List all Google calendars accessible to the user. Use this to discover available calendars before listing events from a specific calendar. Returns calendar IDs, names, and whether they are the primary calendar.",
                parameters_model=ListCalendarsRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: List Calendar Events
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_list_events",
                description="List events from Google Calendar. By default returns only future events from the primary calendar. IMPORTANT: Always set both time_min AND time_max to the narrowest relevant window for the user's query (e.g. for 'today' use start/end of today, for 'this week' use start/end of the week). Only omit time_max for open-ended 'all upcoming' queries. Use calendar_id to list from a different calendar (discover IDs with google_list_calendars). Increase limit for multi-day ranges (e.g. limit=25 for a day, limit=50 for a week).",
                parameters_model=ListCalendarEventsRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Get Calendar Event
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_get_event",
                description="Get full details of a specific Google Calendar event by its ID.",
                parameters_model=GetCalendarEventRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Create Calendar Event
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_create_event",
                description="Create a new event in Google Calendar. Use when the user wants to schedule a meeting, appointment, or event. Supports timed and all-day events, attendees, and location.",
                parameters_model=CreateCalendarEventRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Update Calendar Event
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_update_event",
                description="Update an existing Google Calendar event. Use when the user wants to change the time, title, location, description, or attendees of an event. Only provide the fields that need to change.",
                parameters_model=UpdateCalendarEventRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # Google: Delete Calendar Event
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_delete_event",
                description="Delete a Google Calendar event. Use when the user wants to cancel or remove an event from their calendar.",
                parameters_model=DeleteCalendarEventRequest,
            ),
            executor=None,
            service_name="google",
        )
    )


def define_google_drive_tools():
    """Define Google Drive, Docs, Sheets, and Slides tools."""
    registry = get_tool_registry()

    # ------------------------------------------------------------------ Drive

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_drive_list_files",
                description="List files and folders in Google Drive. Use to browse the contents of a folder or the root of My Drive. Returns file IDs, names, types (google_doc, google_sheet, google_slides, folder, file), and links. Use folder_id to list a specific folder (obtain folder IDs from this tool or google_drive_search_files).",
                parameters_model=DriveListFilesRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_drive_search_files",
                description="Search for files in Google Drive by name or content. Searches both file names and full-text content. Use to find documents, spreadsheets, presentations, or any file by keyword. Returns file IDs needed for reading or editing. Optionally filter by file type.",
                parameters_model=DriveSearchFilesRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_drive_get_file",
                description="Get metadata for a specific Google Drive file — name, type, size, creation/modification dates, and URL. Use when you have a file ID and need its details without downloading the content.",
                parameters_model=DriveGetFileRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_drive_read_file",
                description="Read or export the content of a Google Drive file as text. Google Docs are exported as plain text, Google Sheets as CSV, Google Slides as plain text. Regular files (PDF, DOCX, TXT) are downloaded and text-extracted automatically. Use this to read any file stored in Drive.",
                parameters_model=DriveReadFileRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # ------------------------------------------------------------------ Docs

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_docs_create",
                description="Create a new Google Docs document with an optional initial text content. Returns the document ID and URL. Use for creating reports, notes, letters, meeting agendas, or any long-form text content in Google Drive.",
                parameters_model=DocsCreateRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_docs_get",
                description="Read the full text content of a Google Docs document. Use to retrieve the current content of a Doc before editing, or to summarize/analyse its content. Requires the document ID (from the URL or from google_drive_search_files).",
                parameters_model=DocsGetRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_docs_append",
                description="Append text to the end of an existing Google Docs document. Use to add new sections, paragraphs, or updates to an existing document without overwriting existing content.",
                parameters_model=DocsAppendRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_docs_update",
                description="Replace the entire content of a Google Docs document with new text. Use when you need to completely rewrite a document. WARNING: This replaces ALL existing content. Use google_docs_append to add content instead of replacing.",
                parameters_model=DocsUpdateRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # ----------------------------------------------------------------- Sheets

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_sheets_create",
                description="Create a new Google Sheets spreadsheet with a given title and optional sheet tab names. Returns the spreadsheet ID and URL.",
                parameters_model=SheetsCreateRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_sheets_get",
                description="Get the structure and metadata of a Google Sheets spreadsheet — title, sheet tab names, row/column counts. Use to discover available sheets before reading data.",
                parameters_model=SheetsGetRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_sheets_read",
                description="Read cell values from a Google Sheets range. Returns a 2D array of values. Use A1 notation for the range (e.g. 'Sheet1!A1:D10'). Use google_sheets_get first to discover sheet names and dimensions.",
                parameters_model=SheetsReadRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_sheets_write",
                description="Write values to a Google Sheets range. Overwrites cells in the specified range. Provide a 2D array where each inner list is a row. Use USER_ENTERED input so formulas and numbers are interpreted correctly.",
                parameters_model=SheetsWriteRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_sheets_append",
                description="Append rows to a Google Sheet after the last row that contains data. Use to add new records to a table without overwriting existing data. Provide rows as a 2D array.",
                parameters_model=SheetsAppendRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    # ----------------------------------------------------------------- Slides

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_slides_create",
                description="Create a new Google Slides presentation with a given title. Returns the presentation ID and URL. The new presentation will have one blank slide to start.",
                parameters_model=SlidesCreateRequest,
            ),
            executor=None,
            service_name="google",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_slides_get",
                description="Read the text content of a Google Slides presentation. Returns the title and text extracted from each slide (slide titles, body text, speaker notes text). Use to understand what a presentation contains.",
                parameters_model=SlidesGetRequest,
            ),
            executor=None,
            service_name="google",
        )
    )


def define_google_places_tools():
    """Define Google Places, Directions, and Geocoding tools."""
    registry = get_tool_registry()

    # Google: Search Places
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_search_places",
                description="Search for places using a text query via Google Places API. Use when the user asks to find restaurants, shops, hotels, landmarks, or any other type of place. Returns name, address, rating, opening hours, and coordinates. Requires Google Places API key.",
                parameters_model=SearchPlacesRequest,
            ),
            executor=None,
            service_name="google_navigator",
        )
    )

    # Google: Get Place Details
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_get_place_details",
                description="Get detailed information about a specific place using its Place ID (obtained from google_search_places or google_nearby_places). Returns reviews, opening hours, phone number, website, accessibility info, and more.",
                parameters_model=GetPlaceDetailsRequest,
            ),
            executor=None,
            service_name="google_navigator",
        )
    )

    # Google: Nearby Places
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_nearby_places",
                description="Find places near a specific location by type. Requires latitude,longitude coordinates and a search radius. Use to find nearby restaurants, gas stations, hospitals, ATMs, parking, etc. Use google_geocode_place first if you only have an address.",
                parameters_model=NearbyPlacesRequest,
            ),
            executor=None,
            service_name="google_navigator",
        )
    )

    # Google: Get Directions
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_get_directions",
                description="Get directions, travel time, and distance between two locations. Supports driving, walking, bicycling, and public transit modes. Can include traffic-aware estimates, waypoints, and alternative routes. Use for trip planning, commute estimation, and navigation.",
                parameters_model=GetDirectionsRequest,
            ),
            executor=None,
            service_name="google_navigator",
        )
    )

    # Google: Geocode Place
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_geocode_place",
                description="Convert an address or place name to geographic coordinates (latitude/longitude). Use when you need coordinates for google_nearby_places or to resolve a location before calling other tools.",
                parameters_model=GeocodePlaceRequest,
            ),
            executor=None,
            service_name="google_navigator",
        )
    )

    # Google: Reverse Geocode
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_reverse_geocode",
                description="Convert geographic coordinates (latitude/longitude) to a human-readable address. Use when you have coordinates and need to know the address or area name.",
                parameters_model=ReverseGeocodeRequest,
            ),
            executor=None,
            service_name="google_navigator",
        )
    )


def define_outlook_tools():
    """Define Outlook integration tools."""
    registry = get_tool_registry()

    # Outlook: Send Email
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_send_email",
                description="Send an email via Outlook/Microsoft 365. Use this when the user asks to send an email through Outlook.",
                parameters_model=OutlookSendEmailRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Create Calendar Event
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_create_event",
                description="Create a calendar event in Outlook Calendar. Use when user wants to schedule a meeting or event. Supports online meetings, attendees, and location.",
                parameters_model=CreateEventRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Read Emails
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_read_emails",
                description="Read emails from an Outlook/Microsoft 365 mailbox folder. Use to check recent emails or list messages in a specific folder.",
                parameters_model=OutlookReadEmailsRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Get Email
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_get_email",
                description="Get full details of a specific Outlook email message by its ID. Use when the user wants to read the complete content of a particular email.",
                parameters_model=OutlookGetEmailRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Search Emails
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_search_emails",
                description="Search Outlook emails by query string. Searches subject, body, and sender fields. Use when the user wants to find specific emails.",
                parameters_model=OutlookSearchEmailsRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Create Draft
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_create_draft",
                description="Create an email draft in Outlook without sending it. Use when the user wants to compose an email to review or send later.",
                parameters_model=OutlookCreateDraftRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: List Calendars
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_list_calendars",
                description="List all Outlook/Microsoft 365 calendars accessible to the user. Use this to discover available calendars before listing events from a specific calendar. Returns calendar IDs, names, and whether they are the default calendar.",
                parameters_model=OutlookListCalendarsRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: List Calendar Events
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_list_events",
                description="List events from Outlook Calendar. By default returns only future events from the default calendar. IMPORTANT: Always set both start_date AND end_date to the narrowest relevant window for the user's query (e.g. for 'today' use start/end of today, for 'this week' use start/end of the week). Only omit end_date for open-ended 'all upcoming' queries. Use calendar_id to list from a different calendar (discover IDs with outlook_list_calendars). Increase limit for multi-day ranges (e.g. limit=25 for a day, limit=50 for a week).",
                parameters_model=ListEventsRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Update Calendar Event
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_update_event",
                description="Update an existing Outlook Calendar event. Use when the user wants to change the time, subject, location, or body of an event. Only provide the fields that need to change.",
                parameters_model=OutlookUpdateEventRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Delete Calendar Event
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_delete_event",
                description="Delete an Outlook Calendar event. Use when the user wants to cancel or remove an event from their calendar.",
                parameters_model=OutlookDeleteEventRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: List Files
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_list_files",
                description="List files and folders in OneDrive. Use to browse the user's OneDrive storage.",
                parameters_model=OutlookListFilesRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Search Files
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_search_files",
                description="Search for files in OneDrive. Use to find specific documents or files by name or content.",
                parameters_model=OutlookSearchFilesRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Read File
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_read_file",
                description="Read and extract text content from a OneDrive/SharePoint file. Accepts a file_id (from outlook_list_files/outlook_search_files) or a direct file_path (e.g. '/Documents/report.pdf'). Supports: PDF (via Mistral OCR), Excel (.xlsx), Word (.docx), and text-based formats (.md, .txt, .json, .csv, .xml, .html). Returns extracted_text, filename, size, and format.",
                parameters_model=OutlookReadFileRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Get Attachment
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_get_attachment",
                description="Download and read an email attachment from Outlook. Automatically extracts text from PDF, DOCX, and text files. First get the email with outlook_get_email to find attachments, then use this tool.",
                parameters_model=OutlookGetAttachmentRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Upload File to OneDrive
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onedrive_upload_file",
                description="Upload a file to OneDrive. "
                "Required: folder_path (e.g. '/Documents') and filename. "
                "For local files, use source_path to point to the local filepath — "
                "the file will be read and uploaded without needing content. "
                "For text content, provide content as a plain string. "
                "Creates or overwrites the file at the target path.",
                parameters_model=OutlookUploadFileRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # Outlook: Refresh Credentials
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="outlook_refresh_credentials",
                description="Proactively refresh Outlook OAuth tokens to prevent credential expiry. Used by the system token refresh cron job to keep the MSAL token cache alive.",
                parameters_model=OutlookRefreshCredentialsRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )


def define_onenote_tools():
    """Define OneNote integration tools."""
    registry = get_tool_registry()

    # OneNote: List Notebooks
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_list_notebooks",
                description="List all OneNote notebooks. Use to discover available notebooks and their IDs. Set include_sections=True to also list sections within each notebook.",
                parameters_model=OnenoteListNotebooksRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Get Notebook
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_get_notebook",
                description="Get details of a specific OneNote notebook by ID.",
                parameters_model=OnenoteGetNotebookRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: List Sections
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_list_sections",
                description="List OneNote sections. Use notebook_id to filter by notebook, or omit to list all sections.",
                parameters_model=OnenoteListSectionsRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Get Section
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_get_section",
                description="Get details of a specific OneNote section by ID. Use to find the section ID needed for creating pages.",
                parameters_model=OnenoteGetSectionRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: List Pages
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_list_pages",
                description="List OneNote pages. Filter by section_id or notebook_id, or list all pages. Use include_content=True to retrieve full page HTML.",
                parameters_model=OnenoteListPagesRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Get Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_get_page",
                description="Get a specific OneNote page by ID. Returns page metadata and optionally the full HTML content.",
                parameters_model=OnenoteGetPageRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Create Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_create_page",
                description="Create a new OneNote page in a specific section. Content should be HTML. First use onenote_list_sections to find the section_id.",
                parameters_model=OnenoteCreatePageRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Update Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_update_page",
                description="Update (append content to) an existing OneNote page. Content is appended to the page body.",
                parameters_model=OnenoteUpdatePageRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Delete Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_delete_page",
                description="Delete a OneNote page by ID. Warning: this is permanent.",
                parameters_model=OnenoteDeletePageRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Search
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_search",
                description="Search OneNote pages by title. Use section_id or notebook_id to narrow the search scope when you have many pages. For full content search, use unified_search instead.",
                parameters_model=OnenoteSearchRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Copy Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_copy_page",
                description="Copy a OneNote page to a different section. Use onenote_list_sections to find the target section ID.",
                parameters_model=OnenoteCopyPageRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Extract Text
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_extract_text",
                description="Extract plain text content from a OneNote page, stripping HTML formatting. Useful for processing or analyzing note content.",
                parameters_model=OnenoteExtractTextRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Create from Markdown
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_create_markdown_page",
                description="Create a OneNote page from Markdown-formatted content. Automatically converts Markdown to HTML. Supports headers, lists, bold, italic, and code blocks.",
                parameters_model=OnenoteCreateMarkdownPageRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # OneNote: Create from Template
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="onenote_create_from_template",
                description="Create a OneNote page from a predefined template. Templates: 'meeting_notes', 'daily_journal', 'todo', 'project'. Use variables to customize template content.",
                parameters_model=OnenoteCreateFromTemplateRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )


def define_todo_tools():
    """Define Microsoft To Do integration tools."""
    registry = get_tool_registry()

    # To Do: List Task Lists
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_list_task_lists",
                description="List all Microsoft To Do task lists. Use this to discover available task lists and their IDs before creating or listing tasks.",
                parameters_model=TodoListTaskListsRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: Get Task List
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_get_task_list",
                description="Get details of a specific Microsoft To Do task list by ID.",
                parameters_model=TodoGetTaskListRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: Create Task List
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_create_task_list",
                description="Create a new Microsoft To Do task list. Use when the user wants to create a new list to organize tasks.",
                parameters_model=TodoCreateTaskListRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: Delete Task List
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_delete_task_list",
                description="Delete a Microsoft To Do task list. Warning: this deletes the list and all its tasks permanently.",
                parameters_model=TodoDeleteTaskListRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: List Tasks
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_list_tasks",
                description="List tasks in a Microsoft To Do task list. Use todo_list_task_lists first to find the list_id. Optionally filter by status (notStarted, inProgress, completed).",
                parameters_model=TodoListTasksRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: Get Task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_get_task",
                description="Get details of a specific Microsoft To Do task by ID.",
                parameters_model=TodoGetTaskRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: Create Task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_create_task",
                description="Create a new task in a Microsoft To Do task list. Supports setting title, body/notes, due date, importance (low/normal/high), and reminder. Use todo_list_task_lists first to find the list_id.",
                parameters_model=TodoCreateTaskRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: Update Task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_update_task",
                description="Update an existing Microsoft To Do task. Use to change title, body, due date, importance, status (notStarted/inProgress/completed), or reminder. Only provide the fields that need to change.",
                parameters_model=TodoUpdateTaskRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )

    # To Do: Delete Task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="todo_delete_task",
                description="Delete a Microsoft To Do task. Warning: this is permanent.",
                parameters_model=TodoDeleteTaskRequest,
            ),
            executor=None,
            service_name="outlook",
        )
    )


def define_notion_tools():
    """Define Notion integration tools."""
    registry = get_tool_registry()

    # Notion: Create Note
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_create_note",
                description=(
                    "Create a new note or page in Notion. "
                    "Use this when the user wants to save information, write a note, or document something. "
                    "Only 'title' is required — all other fields are optional. "
                    "To fill database columns (e.g. select, status, multi-select, date), pass them via "
                    "'properties' in Notion's property-value format; call notion_list_databases first to "
                    "discover the exact column names and types. "
                    "Do NOT provide database_id or parent_page_id unless the user explicitly specifies one; "
                    "the system will automatically find the right location."
                ),
                parameters_model=CreateNoteRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: Search
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_search",
                description="Search for pages and content in Notion. Use to find existing notes, pages, or information stored in Notion.",
                parameters_model=SearchRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: Get Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_get_page",
                description="Get the properties and metadata of a specific Notion page by its ID. Use after searching to get full details of a page. Returns page properties, creation time, last edit time, and URL.",
                parameters_model=GetPageRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: Get Page Content
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_get_page_content",
                description="Get the content blocks of a Notion page. Returns all text, headings, lists, and other content blocks within the page. Use this to read the actual content of a page (notion_get_page only returns properties/metadata).",
                parameters_model=GetPageContentRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: Update Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_update_page",
                description="Update properties of an existing Notion page. Use when the user wants to modify a page's metadata or properties.",
                parameters_model=UpdatePageRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: Append Content
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_append_content",
                description="Append content blocks to an existing Notion page. Use when the user wants to add text or content to an existing page.",
                parameters_model=AppendContentRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: List Databases (alias for list_data_sources)
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_list_databases",
                description="List all Notion databases/data sources accessible to the integration. Returns each database's ID, title, and property schema (column names, types, and the valid options for select/multi-select/status columns). Use this FIRST to discover available databases and their IDs before using notion_query_database, and to learn which column values are valid before setting them with notion_create_note or notion_update_page. This is the best way to find the correct database_id.",
                parameters_model=ListDatabasesRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: List Data Sources
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_list_data_sources",
                description="List all Notion data sources (databases) accessible to the integration. Returns each data source's ID, title, and property schema (column names, types, and the valid options for select/multi-select/status columns). Use this FIRST to discover available data sources before using notion_query_database, and to learn which column values are valid before setting them.",
                parameters_model=ListDataSourcesRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: Query Database
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_query_database",
                description=(
                    "Query entries from a Notion database with optional filters and sorting. "
                    "Use when the user wants to find, list, or filter records in a Notion database — "
                    "e.g. 'show me all In-progress articles' or 'find notes tagged Work due this week'. "
                    "Call notion_list_databases first to get the exact column names and valid option values. "
                    "The database_id is resolved to a data_source_id automatically."
                ),
                parameters_model=QueryDatabaseRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )

    # Notion: Delete Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notion_delete_page",
                description="Delete (archive) a Notion page. The page is moved to trash and can be recovered. Use when the user wants to remove a page.",
                parameters_model=DeletePageRequest,
            ),
            executor=None,
            service_name="notion",
        )
    )


def define_nextcloud_tools():
    """Define Nextcloud integration tools."""
    registry = get_tool_registry()

    # Nextcloud: List Files
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_list_files",
                description="List files and folders in Nextcloud. Use to browse files or check what's available in a specific folder.",
                parameters_model=ListFilesRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Search Files
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_search_files",
                description="Search for files in Nextcloud by filename. Searches recursively through all subdirectories by default. Use to find specific files or documents anywhere in the Nextcloud storage. Returns files with their full paths.",
                parameters_model=SearchFilesRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Read File
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_read_file",
                description="Read the content of a file stored in Nextcloud. Use when the user wants to view a file's text content.",
                parameters_model=ReadFileRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Download File
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_download_file",
                description="Download a file from Nextcloud to local storage. Use when the user wants to save a remote file locally.",
                parameters_model=DownloadFileRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Upload File
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_upload_file",
                description="Upload a file to Nextcloud. "
                "Required: remote_path (destination, e.g. '/Documents/report.pdf'). "
                "For local files, use source_path to point to the local filepath — "
                "the file will be read and uploaded without needing content. "
                "For text content, provide content as a plain string. "
                "Creates the file if it doesn't exist, or overwrites if it does.",
                parameters_model=UploadFileRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Create Folder
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_create_folder",
                description="Create a new folder in Nextcloud. Use when the user wants to organize files by creating a directory.",
                parameters_model=CreateFolderRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Delete File
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_delete_file",
                description="Delete a file or folder from Nextcloud. Use when the user wants to remove a file or directory. Warning: this permanently deletes the item.",
                parameters_model=DeleteFileRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Move File
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_move_file",
                description="Move or rename a file/folder in Nextcloud. Provide the current path and the new path. Can be used for both moving to a different location and renaming.",
                parameters_model=MoveFileRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Copy File
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_copy_file",
                description="Copy a file or folder in Nextcloud to a new location. The original file is preserved.",
                parameters_model=CopyFileRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Get File Info
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_get_file_info",
                description="Get metadata about a file in Nextcloud, including size, type, and modification date.",
                parameters_model=FileInfoRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Check File Exists
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_file_exists",
                description="Check whether a file exists at a given path in Nextcloud.",
                parameters_model=FileExistsRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )

    # Nextcloud: Read PDF (extract text via Mistral OCR)
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="nextcloud_read_pdf",
                description=(
                    "Extract and read the text content of a PDF file stored in Nextcloud using Mistral OCR. "
                    "Use this when the user wants to read, summarise, or search within a PDF document from their fileshare. "
                    "Requires Mistral OCR to be configured (mistral_ocr.api_key or llm.api_key in Settings). "
                    "Returns the full extracted text along with character count."
                ),
                parameters_model=ReadPdfRequest,
            ),
            executor=None,
            service_name="nextcloud",
        )
    )


def define_whatsapp_tools():
    """Define WhatsApp integration tools."""
    registry = get_tool_registry()

    # WhatsApp: Send Message
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="whatsapp_send_message",
                description="Send a WhatsApp message. Use when user wants to send a message via WhatsApp to a phone number.",
                parameters_model=SendMessageRequest,
            ),
            executor=None,
            service_name="whatsapp",
        )
    )

    # Notify Owner (WhatsApp or Slack)
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="notify_owner",
                description=(
                    "Send a notification or message to the owner via WhatsApp or Slack. "
                    "Use this when: (1) The user asks you to send them a message or notification "
                    "(e.g., 'send me a message', 'message me', 'notify me', 'WhatsApp me', 'Slack me'), "
                    "(2) You need to proactively notify the owner (e.g., scheduled task results, reminders, alerts). "
                    "The 'channel' parameter selects the delivery channel — defaults to 'whatsapp'; use 'slack' to send via Slack instead. "
                    "The phone number (WhatsApp) and default channel ID (Slack) are resolved automatically from settings. "
                    "The tool will inform you if the chosen channel is not enabled or not fully configured."
                ),
                parameters_model=NotifyOwnerRequest,
            ),
            executor=None,
            service_name="whatsapp",
        )
    )

    # WhatsApp: Get Status
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="whatsapp_get_status",
                description="Get WhatsApp connection status. Check if WhatsApp is connected and ready to send/receive messages. Returns ready state and QR code availability.",
                parameters_model=GetStatusRequest,
            ),
            executor=None,
            service_name="whatsapp",
        )
    )

    # WhatsApp: Configure Webhook
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="whatsapp_configure_webhook",
                description="Configure a webhook URL for receiving incoming WhatsApp messages. Use when setting up WhatsApp message forwarding.",
                parameters_model=WebhookConfigRequest,
            ),
            executor=None,
            service_name="whatsapp",
        )
    )


def define_slack_tools():
    """Define Slack integration tools."""
    registry = get_tool_registry()

    # Slack: Send Message
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="slack_send_message",
                description="Send a message to a Slack channel. Use when the user wants to post a message in a specific Slack channel.",
                parameters_model=SlackSendMessageRequest,
            ),
            executor=None,
            service_name="slack",
        )
    )

    # Slack: Send Message to Default Channel
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="slack_send_message_to_default_channel",
                description="Send a message to the default Slack channel configured in settings. Use this when: (1) The user asks you to send a Slack message without specifying a channel, (2) You need to proactively notify the owner via Slack (e.g., scheduled task results, reminders, alerts). No channel ID is needed — it is resolved automatically from settings.",
                parameters_model=SlackSendMessageToDefaultChannelRequest,
            ),
            executor=None,
            service_name="slack",
        )
    )


def define_system_tools():
    """Define system-level tools available to the LLM."""
    registry = get_tool_registry()

    # System: Fetch Logs
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="system_fetch_logs",
                description="Fetch recent application log lines to review system activity, diagnose issues, or understand recent errors. Use this when the user asks about errors, system status, or recent activity. Returns parsed log entries with timestamp, level, module, and message.",
                parameters_model=FetchLogsRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # System: Get Conversation Text
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="system_get_conversation_text",
                description="Retrieve conversation messages (user and assistant) within a given timespan. Use this to review what was discussed during a period, extract facts, or analyse communication patterns. Returns messages with role, content, timestamp, channel, and conversation_id.",
                parameters_model=GetConversationTextRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # System: Get Prompt
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="system_get_prompt",
                description="Read the current value of a prompt by key. Use this to inspect the current system prompt, memory, or soul prompt before updating them. Keys: 'system_prompt_default', 'system_prompt_custom', 'memory', 'soul'.",
                parameters_model=GetPromptRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # System: Update Memory Prompt
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="system_update_memory_prompt",
                description="Update the memory prompt with IDs and operational facts extracted from conversations. Keep this lean — only store facts the system needs on EVERY request: user name, timezone, account/contact IDs, critical preferences. For general/contextual facts (interests, project details, relationship context) use system_index_memory_facts instead. IMPORTANT: Always read the current memory first with system_get_prompt, then merge/append new facts. Do NOT remove existing content unless it is outdated or incorrect.",
                parameters_model=UpdateMemoryPromptRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # System: Index Memory Facts
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="system_index_memory_facts",
                description="Index general/contextual memory facts into the search index so they can be recalled later via search. Use this for facts that are useful for occasional recall but NOT needed on every request — e.g. interests, project context, relationship details, background info. Facts are stored under source 'memory' with a date-based ID. They can be searched later using the unified search tool with sources=['memory'].",
                parameters_model=IndexMemoryFactsRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # System: Recall Conversation Memory
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="memory_recall",
                description=(
                    "Recall information from memory by searching BOTH the indexed memory facts "
                    "(stored via system_index_memory_facts) AND the raw conversation message "
                    "history. Use this whenever you need to remember something about the user "
                    "that is not in the current context — past discussions, preferences, facts, "
                    "or decisions. A worker LLM synthesises the combined results into a focused "
                    "answer with source references (date, channel, memory index hits). "
                    "You MUST provide both 'query' (a list of short, specific keywords to search "
                    "for) and 'question' (the exact question to answer from the results). "
                    "Think about what keywords would actually appear in past messages — use "
                    "synonyms, proper nouns, or domain terms rather than conversational phrases."
                ),
                parameters_model=RecallConversationMemoryRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # System: Update Soul Prompt
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="system_update_soul_prompt",
                description="Update the soul/personality prompt based on communication style and personality preferences extracted from conversations. IMPORTANT: Always read the current soul first with system_get_prompt, then merge/append new personality traits or style preferences. Do NOT remove existing personality traits unless explicitly requested by the user.",
                parameters_model=UpdateSoulPromptRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # System: Clean Tmp Directory
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="system_clean_tmp_dir",
                description="Remove old files from the application temporary directory. Used by the nightly cleanup cron job. Deletes files and directories older than max_age_hours (default 24). Returns count of deleted items and freed bytes.",
                parameters_model=CleanTmpDirRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_cron_job_tools():
    """Define cron job management tools."""
    registry = get_tool_registry()

    # Cron: Create Job
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="create_cron_job",
                description=(
                    "Create a recurring scheduled recipe (job). A recipe is an ordered list of steps "
                    "executed in sequence on a cron schedule. Always prefer steps over the legacy "
                    "job_type/tool_name/prompt fields.\n\n"
                    "STEP DESIGN RULES:\n"
                    "- TOOL PINNING: When the integration is clear from context, set tool_name on the step. "
                    "This guarantees the same tool runs every time — never leaves selection to the LLM. "
                    "Wrong: prompt 'check my calendar' (may pick Google or Outlook randomly). "
                    "Right: tool_name 'google_calendar_list_events' (deterministic every run).\n"
                    "- SELF-CONTAINED PROMPTS: When a step needs a prompt_template, write it as if "
                    "starting fresh — no 'that file', no 'as mentioned', no conversation references.\n"
                    "- VARIABLE WIRING: Set stores_as on a producing step and uses_variable on the "
                    "consuming step to pass data between steps. Never rely on the LLM to 'remember' "
                    "output across steps.\n"
                    "- ONE ACTION PER STEP: One distinct external action = one step.\n\n"
                    "Example 3-step recipe: fetch API data (tool pinned, stores_as='api_data'), "
                    "analyse it (prompt_template, uses_variable='api_data'), "
                    "send summary email (tool pinned)."
                ),
                parameters_model=CreateCronJobRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Cron: List Jobs
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="list_cron_jobs",
                description="List all scheduled cron jobs. Use when the user asks about their scheduled tasks, recurring jobs, or wants to see what's been automated.",
                parameters_model=ListCronJobsRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Cron: Get Job
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="get_cron_job",
                description="Get details of a specific cron job including its schedule, configuration, and recent execution history.",
                parameters_model=GetCronJobRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Cron: Update Job
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="update_cron_job",
                description="Update a cron job's schedule, name, or parameters. Use when the user wants to change how often a job runs or what it does.",
                parameters_model=UpdateCronJobRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Cron: Delete Job
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="delete_cron_job",
                description="Delete a scheduled cron job permanently. Use when the user wants to remove a recurring task.",
                parameters_model=DeleteCronJobRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Cron: Toggle Job
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="toggle_cron_job",
                description="Enable or disable a cron job without deleting it. Use when the user wants to temporarily pause or resume a scheduled task.",
                parameters_model=ToggleCronJobRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_future_task_tools():
    """Define future task scheduling tools."""
    registry = get_tool_registry()

    # Future Task: Schedule
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="schedule_task",
                description="Schedule a task to run once at a specific time. Use for reminders, delayed actions, or one-time scheduled tasks. Examples: 'Remind me to call John tomorrow at 3pm', 'Send email in 2 hours', 'Check status next Monday at 9am'.",
                parameters_model=ScheduleTaskRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Future Task: List Tasks
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="list_future_tasks",
                description="List scheduled future tasks. Use when the user asks about their upcoming reminders, scheduled one-time tasks, or wants to see what's been scheduled.",
                parameters_model=ListFutureTasksRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Future Task: Get Task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="get_future_task",
                description="Get details of a specific future task including its schedule, status, and execution history.",
                parameters_model=GetFutureTaskRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Future Task: Cancel Task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="cancel_future_task",
                description="Cancel a pending future task. Use when the user wants to remove a scheduled reminder or one-time task.",
                parameters_model=CancelFutureTaskRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_brave_tools():
    """Define Brave Search integration tools."""
    registry = get_tool_registry()

    # Brave: Web Search
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="web_search",
                description="Search the web for information using Brave Search. Use when the user asks to search the web, find current information, look up facts, or research a topic. Returns search results with titles, snippets, and URLs. Falls back to DuckDuckGo if Brave Search is unavailable.",
                parameters_model=WebSearchRequest,
            ),
            executor=None,
            service_name="brave",
        )
    )


def define_browser_tools():
    """Define browser automation tools using accessibility tree."""
    registry = get_tool_registry()

    # Browser: Navigate to URL
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="browse_url",
                description=(
                    "Navigate to a URL and get its accessibility tree structure. "
                    "The tree shows interactive elements (links, buttons, inputs) with [ref=N] annotations. "
                    "Use these refs with browse_action to interact. "
                    "This is MUCH faster and more reliable than screenshot-based approaches. "
                    "Typical workflow: browse_url → examine tree → browse_action(ref=5, action='click')"
                ),
                parameters_model=BrowseUrlRequest,
            ),
            executor=None,
            service_name="browser",
        )
    )

    # Browser: Get Tree
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="browse_get_tree",
                description=(
                    "Get accessibility tree of current page without navigating. "
                    "Useful after actions to see updated page structure. "
                    "Modes: 'interactive' (links/buttons/inputs), 'forms' (form fields only), 'full' (everything)"
                ),
                parameters_model=BrowseGetTreeRequest,
            ),
            executor=None,
            service_name="browser",
        )
    )

    # Browser: Execute Action
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="browse_action",
                description=(
                    "Execute action on page element by reference ID. "
                    "Get ref IDs from browse_url or browse_get_tree output. "
                    "Actions: 'click' (click element), 'type' (fill text - requires value), "
                    "'focus' (focus element), 'check' (check checkbox), 'uncheck' (uncheck checkbox). "
                    "More reliable than pixel coordinates - survives layout changes!"
                ),
                parameters_model=BrowseActionRequest,
            ),
            executor=None,
            service_name="browser",
        )
    )

    # Browser: Scroll
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="browse_scroll",
                description=(
                    "Scroll the page up or down to see more content. "
                    "Each tick scrolls ~100 pixels. Use browse_get_tree after scrolling "
                    "to see newly visible elements."
                ),
                parameters_model=BrowseScrollRequest,
            ),
            executor=None,
            service_name="browser",
        )
    )

    # Browser: Extract Text
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="browse_extract",
                description=(
                    "Extract all visible text content from current page as plain text. "
                    "Use when you need the full text content rather than just interactive elements."
                ),
                parameters_model=BrowseExtractRequest,
            ),
            executor=None,
            service_name="browser",
        )
    )

    # Browser: Fetch Content (Scrapling)
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="browse_fetch",
                description=(
                    "Fetch and extract content from a URL using Scrapling. "
                    "Unlike browse_url (which opens a full browser for interaction), this is optimized "
                    "for content extraction with anti-bot bypass. Three modes: "
                    "'http' (fast, no JS, TLS fingerprint impersonation), "
                    "'stealth' (Camoufox browser, bypasses Cloudflare/anti-bot), "
                    "'dynamic' (Playwright with anti-detection for JS-heavy pages). "
                    "Use 'http' for simple pages, 'stealth' for protected sites, "
                    "'dynamic' for SPAs. Supports CSS selectors for targeted extraction. "
                    "Prefer this over browse_url when you only need to read content, not interact."
                ),
                parameters_model=BrowseFetchRequest,
            ),
            executor=None,
            service_name="browser",
        )
    )


def define_document_tools():
    """Define document generation tools."""
    registry = get_tool_registry()

    # Document: Compose Document (AI-powered writing with plan/write/review)
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="compose_document",
                description="Compose a long-form document using AI-powered planning, drafting, and review. "
                "The 'length' parameter controls output size: 'short' (default) runs a single-pass write; "
                "'medium' and 'long' write each section individually to overcome LLM token limits, "
                "producing substantially more content. Use 'medium' for detailed guides/reports (~6-8 sections), "
                "'long' for comprehensive documents (~8-12 sections with in-depth coverage). "
                "Returns the finished content, outline, and section count. "
                "Use this for any writing task that benefits from structured planning — guides, reports, "
                "articles, proposals, etc. After receiving the content, save it to Notion, create a .docx, "
                "or deliver it however the user prefers.",
                parameters_model=ComposeDocumentRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Document: Create DOCX
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="create_docx",
                description="Create a .docx (Word) document from markdown-formatted content. "
                "Supports headings, bullet lists, numbered lists, bold, italic, code blocks, "
                "and paragraphs. The file is saved to temporary storage. "
                "To upload to cloud storage, use nextcloud_upload_file or onedrive_upload_file "
                "with source_path pointing to the returned filepath.",
                parameters_model=CreateDocxRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Document: Create PDF
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="create_pdf",
                description="Create a PDF document from markdown-formatted content. "
                "Supports headings, bullet lists, numbered lists, bold, italic, code blocks, "
                "blockquotes, tables, and paragraphs. "
                "The result contains a filepath to the created PDF.",
                parameters_model=CreatePdfRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Document: Create HTML Page
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="create_html",
                description="Generate a complete HTML page from a plain-English description. "
                "The LLM writes the HTML directly — page CSS and JavaScript are inline; "
                "CDN chart libraries (Chart.js, Plotly.js) are used when charts are needed. "
                "Ideal for dashboards, reports, landing pages, and data displays. "
                "Much faster than writing Python to generate HTML. "
                "Optionally pass raw data (CSV, JSON, text) via 'context' to embed in the page. "
                "The file is saved to temporary storage. "
                "To upload to cloud storage, use nextcloud_upload_file or onedrive_upload_file "
                "with source_path pointing to the returned filepath.",
                parameters_model=CreateHtmlRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_python_tools():
    """Define Python code execution tools."""
    registry = get_tool_registry()

    # Python: Execute Code
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="python_execute",
                description=(
                    "Execute arbitrary Python code and return stdout, stderr, and exit code. "
                    "Use this for flexible scripting, data processing, HTTP requests (curl-like), "
                    "computations, data analysis, and creating visualizations or HTML reports. "
                    "The full standard library is available, as well as these installed packages: "
                    "'requests' (HTTP), 'pandas' (dataframes/CSV/Excel analysis), "
                    "'numpy' (numerical computing), 'scipy' (scientific computing), "
                    "'matplotlib' (static charts — save to /app/tmp/ as PNG), "
                    "'seaborn' (statistical charts on top of matplotlib), "
                    "'plotly' (interactive HTML charts — use plotly.io.write_html() to save to /app/tmp/), "
                    "'kaleido' (export plotly figures to PNG/SVG/PDF), "
                    "'jinja2' (HTML templating for rich reports), "
                    "'openpyxl' (read/write .xlsx files), 'yfinance' (financial market data), "
                    "'markdown' (Markdown-to-HTML conversion). "
                    "Print results to stdout so they are returned. "
                    "To produce a file (chart, HTML report, Excel sheet), write it to /app/tmp/ and print the path. "
                    "Note: stdout larger than ~8 000 characters is automatically saved to /app/tmp/ and only the "
                    "file path is returned — so always write large outputs (HTML reports, full datasets) directly "
                    "to /app/tmp/ rather than printing them, to get a stable, accessible path. "
                    "Examples: analyse a CSV with pandas, plot a time-series with plotly and save the HTML, "
                    "build a full HTML dashboard with jinja2, fetch JSON and aggregate with pandas. "
                    "For multi-step tasks that would otherwise need several round-trips (fetch-then-process, "
                    "explore-then-plot, scrape-then-aggregate), prefer `python_agent` — it iterates "
                    "autonomously and returns only the final result, keeping this context clean."
                ),
                parameters_model=PythonExecuteRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Python: Autonomous Sub-Agent
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="python_agent",
                description=(
                    "Delegate a multi-step Python task to a sub-agent that autonomously writes, runs, "
                    "and refines Python until the goal is met, then returns only a compact summary "
                    "and any output filepaths under /app/tmp/. "
                    "Prefer this over repeated `python_execute` calls when the task needs more than one "
                    "round-trip — e.g. fetch-then-process, explore-then-plot, scrape-then-aggregate, "
                    "build-a-multi-step-report. Saves main-context tokens because only the final result "
                    "comes back (no intermediate tracebacks, dataframe heads, or scratch prints). "
                    "Use plain `python_execute` for trivial one-shot snippets where you already know the code. "
                    "Returns: summary (str), output_files (list[str] of paths under /app/tmp/), "
                    "final_stdout_tail (str), iterations (int), success (bool), error (str, on failure)."
                ),
                parameters_model=PythonAgentRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_batch_tools():
    """Define batch/iteration tools."""
    registry = get_tool_registry()

    # Batch Tool: execute a tool repeatedly for a list of items
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="batch_tool",
                description=(
                    "Execute any tool multiple times — once per item in a list. "
                    "Use this whenever you need to apply the SAME action to MANY items "
                    "instead of calling the tool repeatedly yourself. "
                    "Examples: label 10 emails, trash 5 messages, move 8 files, "
                    "send calendar invites to a list of people. "
                    "Provide the tool name and a list of argument objects (one per item). "
                    "The backend runs them all and returns aggregated results."
                ),
                parameters_model=BatchToolRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_loop_tools():
    """Define loop/pipeline tools."""
    registry = get_tool_registry()

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="loop_tool",
                description=(
                    "Execute a pipeline of tools — in order — for each item in a list. "
                    "Use this when each item needs multiple sequential steps: "
                    "e.g. fetch an email then create a Notion page for each one, "
                    "or get a file's metadata then move it for each path. "
                    "Provide ordered steps (each with tool_name + shared arguments) "
                    "and items (per-item fields merged into every step's arguments). "
                    "If a step fails for an item, remaining steps for that item are "
                    "skipped but the next item continues. "
                    "For a single-tool loop over many items prefer batch_tool instead."
                ),
                parameters_model=LoopToolRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_calculator_tools():
    """Define calculator/math tools."""
    registry = get_tool_registry()

    # Calculator: Evaluate Expression
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="calculate",
                description="Evaluate a mathematical expression safely. Supports arithmetic (+, -, *, /, **, %), "
                "parentheses, and common math functions (sqrt, sin, cos, tan, log, abs, round, min, max, pi, e). "
                "Also handles '15% of 200' style queries. Use for any calculation, unit conversion, or math the user needs.",
                parameters_model=CalculateRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_search_tools():
    """Define unified search tools."""
    registry = get_tool_registry()

    # Unified Search
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="unified_search",
                description="Search across all connected sources (Notion, Gmail, Outlook, OneNote, Nextcloud, memory) using hybrid keyword + semantic matching. Returns ranked results from all enabled sources. Use sources=['memory'] to search the assistant's long-term memory (past learnings about the user). Use this as the first tool when the user asks to 'search everything', 'find something across my data', or when you need to search multiple sources at once.",
                parameters_model=UnifiedSearchRequest,
            ),
            executor=None,
            service_name="search",
        )
    )

    # Reindex Search
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="reindex_search",
                description="Rebuild the semantic search index by fetching content from connected sources and generating embeddings. Run this periodically (or via cron job) to keep semantic search results up to date. Only needed for semantic search — keyword search always queries live APIs.",
                parameters_model=ReindexSearchRequest,
            ),
            executor=None,
            service_name="search",
        )
    )


def define_analysis_tools():
    """Define LLM-powered analysis tools."""
    registry = get_tool_registry()

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="analyze_content",
                description="Analyze provided text content using an LLM to derive insights, summaries, extract key information, or answer specific questions. This is a general-purpose 'think' step for deep understanding of unstructured data. Use this tool when you need to analyze, summarize, or extract insights from any text content.",
                parameters_model=AnalyzeContentRequest,
            ),
            executor=None,
            service_name="analysis",
            requires_auth=False,
        )
    )


def define_plan_tools():
    """Define adaptive planning tools (revise_plan, ask_user).

    These are only injected into the tool list when a plan is active,
    but they must be registered in the global registry so
    ``ToolExecutor`` can route them.
    """
    registry = get_tool_registry()

    # Revise Plan: allow LLM to adjust remaining plan steps mid-execution
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="revise_plan",
                description=(
                    "Revise the current execution plan based on intermediate results. "
                    "Use this during a plan checkpoint when a step failed, returned "
                    "unexpected results, or when you realize the remaining steps need "
                    "adjustment. Actions: 'replace_remaining' (rewrite all pending steps), "
                    "'add_step' (insert a step), 'remove_step' (drop a pending step), "
                    "'skip_current' (skip the current step and move on)."
                ),
                parameters_model=RevisePlanRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # Ask User: pause execution to get user input
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="ask_user",
                description=(
                    "Pause execution and ask the user a question. Use this when you "
                    "need clarification, a decision, or additional information from "
                    "the user before you can proceed with the current plan. Execution "
                    "will be suspended until the user responds. Only use this when "
                    "the ambiguity genuinely blocks progress — do not ask unnecessary "
                    "questions."
                ),
                parameters_model=AskUserRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_async_task_tools():
    """Register dispatch_task and get_task_result in the global tool registry.

    These tools are injected alongside the other plan tools (revise_plan,
    ask_user) whenever a multi-step plan is active.  They allow the LLM to
    delegate complex sub-tasks to independent execution loops that run
    concurrently, then collect their results.
    """
    registry = get_tool_registry()

    # dispatch_task — spawn a background sub-task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="dispatch_task",
                description=(
                    "Dispatch a complex sub-task to run asynchronously in the background. "
                    "The sub-task gets its own planning loop, skill selection, and full tool "
                    "access — identical to a top-level user request. Use this when a plan step "
                    "involves substantial independent work (research, multi-step writing, "
                    "analysis) that can run in parallel with other steps. "
                    "Returns a task_id immediately. Use get_task_result to poll for completion "
                    "and retrieve the result. Multiple tasks can run simultaneously."
                ),
                parameters_model=DispatchTaskRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # get_task_result — poll a dispatched sub-task
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="get_task_result",
                description=(
                    "Retrieve the current status and result of a previously dispatched sub-task. "
                    "Status values: 'running' (still in progress — try again later), "
                    "'completed' (result field contains the full output), "
                    "'failed' (error field contains the reason). "
                    "You may call this multiple times for the same task_id until it completes. "
                    "Prefer wait_for_tasks when you need to block until one or more tasks finish."
                ),
                parameters_model=GetTaskResultRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )

    # wait_for_tasks — block until sub-tasks finish, notify originating channel
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="wait_for_tasks",
                description=(
                    "Block until one or more dispatched sub-tasks have finished, then return "
                    "their results. Automatically sends a progress notification back to the "
                    "channel where the original request came from (WhatsApp or Slack) so the "
                    "user knows the assistant is still working — no notification is sent for "
                    "webui requests since the user is already watching. "
                    "Use this after dispatch_task instead of polling get_task_result in a loop. "
                    "You MUST call this (or get_task_result) before providing a final response "
                    "whenever you have dispatched sub-tasks — the system will not allow a final "
                    "response while tasks are still running."
                ),
                parameters_model=WaitForTasksRequest,
            ),
            executor=None,
            service_name="system",
            requires_auth=False,
        )
    )


def define_google_ads_tools():
    """Define Google Ads integration tools."""
    registry = get_tool_registry()

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_get_account_info",
                description=(
                    "Get basic information about a Google Ads account (name, currency, "
                    "time zone, status). Provide customer_id or leave blank to use the default."
                ),
                parameters_model=GoogleAdsGetAccountInfoRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_list_campaigns",
                description=(
                    "List campaigns in a Google Ads account. Optionally filter by status "
                    "(ENABLED, PAUSED). Returns campaign names, statuses, budgets, and dates."
                ),
                parameters_model=GoogleAdsListCampaignsRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_get_campaign",
                description=(
                    "Get details for a single Google Ads campaign by its ID, including "
                    "budget, status, channel type, and dates."
                ),
                parameters_model=GoogleAdsGetCampaignRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_create_campaign",
                description=(
                    "Create a new Google Ads campaign with a campaign budget. The campaign "
                    "is created as PAUSED by default to prevent unintended spend. "
                    "Provide name, daily_budget (in account currency), and start_date (YYYYMMDD)."
                ),
                parameters_model=GoogleAdsCreateCampaignRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_update_campaign_status",
                description=(
                    "Update the status of a Google Ads campaign. "
                    "Use status ENABLED to activate, PAUSED to pause, or REMOVED to delete."
                ),
                parameters_model=GoogleAdsUpdateCampaignStatusRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_update_campaign_budget",
                description=(
                    "Update the daily budget of a Google Ads campaign. "
                    "Provide the new daily_budget in account currency units (not micros)."
                ),
                parameters_model=GoogleAdsUpdateCampaignBudgetRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_list_ad_groups",
                description=(
                    "List ad groups in a Google Ads account, optionally filtered by campaign_id. "
                    "Returns ad group names, statuses, and CPC bids."
                ),
                parameters_model=GoogleAdsListAdGroupsRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_create_ad_group",
                description=(
                    "Create an ad group within a Google Ads campaign. "
                    "Provide campaign_id, a name, and the default CPC bid in account currency units."
                ),
                parameters_model=GoogleAdsCreateAdGroupRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_list_keywords",
                description=(
                    "List keywords in a Google Ads account, optionally filtered by ad_group_id. "
                    "Returns keyword text, match type, status, and CPC bid."
                ),
                parameters_model=GoogleAdsListKeywordsRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_add_keyword",
                description=(
                    "Add a keyword to a Google Ads ad group. "
                    "Specify keyword_text, match_type (BROAD, PHRASE, or EXACT), "
                    "and an optional CPC bid override."
                ),
                parameters_model=GoogleAdsAddKeywordRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_get_campaign_performance",
                description=(
                    "Get performance metrics (impressions, clicks, cost, CTR, conversions) "
                    "for campaigns in a Google Ads account over a named date range such as "
                    "LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, or LAST_MONTH."
                ),
                parameters_model=GoogleAdsGetCampaignPerformanceRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )

    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_ads_get_ad_group_performance",
                description=(
                    "Get performance metrics (impressions, clicks, cost, CTR, conversions) "
                    "for ad groups in a Google Ads account over a named date range. "
                    "Optionally filter by campaign_id."
                ),
                parameters_model=GoogleAdsGetAdGroupPerformanceRequest,
            ),
            executor=None,
            service_name="google_ads",
        )
    )


def define_google_news_tools():
    """Define Google News integration tools (no API key required)."""
    registry = get_tool_registry()

    # Google News: Top Headlines
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_news_top_headlines",
                description=(
                    "Fetch the current top headlines from Google News. "
                    "Use this when the user asks for today's news, latest headlines, "
                    "what's happening in the world, or current events without a specific topic."
                ),
                parameters_model=GoogleNewsTopHeadlinesRequest,
            ),
            executor=None,
            service_name="google_news",
        )
    )

    # Google News: Search
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_news_search",
                description=(
                    "Search Google News for articles matching specific keywords. "
                    "Use this when the user asks to find news about a particular subject, "
                    "person, company, or event. "
                    "Examples: 'news about Tesla', 'latest on the Ukraine war', "
                    "'AI regulation updates'."
                ),
                parameters_model=GoogleNewsSearchRequest,
            ),
            executor=None,
            service_name="google_news",
        )
    )

    # Google News: By Topic
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_news_by_topic",
                description=(
                    "Fetch Google News articles for a predefined topic category. "
                    "Use this when the user asks for news in a broad category such as "
                    "technology news, sports news, health news, or business news. "
                    "Available topics: WORLD, NATION, BUSINESS, TECHNOLOGY, "
                    "ENTERTAINMENT, SCIENCE, SPORTS, HEALTH."
                ),
                parameters_model=GoogleNewsByTopicRequest,
            ),
            executor=None,
            service_name="google_news",
        )
    )

    # Google News: By Location
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_news_by_location",
                description=(
                    "Fetch Google News articles related to a specific geographic location. "
                    "Use this when the user asks for news from or about a country, city, "
                    "or region. "
                    "Examples: 'news from Germany', 'what's happening in Japan', "
                    "'local news in New York'."
                ),
                parameters_model=GoogleNewsByLocationRequest,
            ),
            executor=None,
            service_name="google_news",
        )
    )

    # Google News: By Site
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="google_news_by_site",
                description=(
                    "Fetch the latest news articles published by a specific news website. "
                    "Use this when the user wants news from a particular publisher or outlet. "
                    "Provide the bare domain (e.g. 'bbc.com', 'reuters.com', 'techcrunch.com')."
                ),
                parameters_model=GoogleNewsBySiteRequest,
            ),
            executor=None,
            service_name="google_news",
        )
    )


def define_yahoo_finance_tools():
    """Define Yahoo Finance market data tools (no API key required)."""
    registry = get_tool_registry()

    # Yahoo Finance: Get Quote
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="yahoo_finance_get_quote",
                description=(
                    "Get the current price and key market metrics for a stock, ETF, index, "
                    "cryptocurrency, or forex pair via Yahoo Finance. Returns current price, "
                    "day change, volume, market cap, P/E ratio, 52-week high/low, and more. "
                    "Use this for real-time price lookups. "
                    "Examples: 'AAPL' (Apple), 'TSLA' (Tesla), '^GSPC' (S&P 500), "
                    "'BTC-USD' (Bitcoin), 'EURUSD=X' (EUR/USD). "
                    "No API key required."
                ),
                parameters_model=YahooFinanceGetQuoteRequest,
            ),
            executor=None,
            service_name="yahoo_finance",
        )
    )

    # Yahoo Finance: Get Historical Data
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="yahoo_finance_get_history",
                description=(
                    "Get historical OHLCV (Open, High, Low, Close, Volume) price data for a "
                    "ticker symbol. Use this when the user asks about past performance, price "
                    "trends, or wants to see a chart. Supports flexible periods (1 day to max) "
                    "and intervals (1 minute to monthly). "
                    "Examples: AAPL 1-year daily history, BTC-USD 3-month weekly history. "
                    "No API key required."
                ),
                parameters_model=YahooFinanceGetHistoryRequest,
            ),
            executor=None,
            service_name="yahoo_finance",
        )
    )

    # Yahoo Finance: Get Company Info
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="yahoo_finance_get_info",
                description=(
                    "Get detailed company or fund profile from Yahoo Finance. Returns business "
                    "description, sector, industry, number of employees, website, country, "
                    "and key financial ratios (P/E, P/B, ROE, revenue, profit margins, debt, etc.). "
                    "Use this when the user asks about what a company does, its fundamentals, "
                    "or detailed financial statistics beyond a simple price quote. "
                    "No API key required."
                ),
                parameters_model=YahooFinanceGetInfoRequest,
            ),
            executor=None,
            service_name="yahoo_finance",
        )
    )

    # Yahoo Finance: Get Financial Statements
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="yahoo_finance_get_financials",
                description=(
                    "Get financial statements for a publicly traded company via Yahoo Finance. "
                    "Supports income statement (revenue, net income, EPS), balance sheet "
                    "(assets, liabilities, equity), and cash flow statement. "
                    "Available as annual (default) or quarterly. "
                    "Use this for in-depth financial analysis or when the user asks about "
                    "earnings, revenue growth, debt levels, or cash position. "
                    "No API key required."
                ),
                parameters_model=YahooFinanceGetFinancialsRequest,
            ),
            executor=None,
            service_name="yahoo_finance",
        )
    )

    # Yahoo Finance: Get News
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="yahoo_finance_get_news",
                description=(
                    "Get recent news articles for a ticker symbol from Yahoo Finance. "
                    "Returns article titles, publishers, links, and publish dates. "
                    "Use this when the user asks about recent news, announcements, or events "
                    "affecting a stock or company. "
                    "No API key required."
                ),
                parameters_model=YahooFinanceGetNewsRequest,
            ),
            executor=None,
            service_name="yahoo_finance",
        )
    )

    # Yahoo Finance: Search Tickers
    registry.register(
        Tool(
            schema=create_tool_schema(
                name="yahoo_finance_search",
                description=(
                    "Search Yahoo Finance for ticker symbols by company name or keyword. "
                    "Use this when the user mentions a company by name but you don't know the "
                    "exact ticker symbol (e.g. 'What is the stock price of Nvidia?' → search "
                    "'Nvidia' to get 'NVDA'). Returns matching symbols, company names, "
                    "exchanges, and instrument types. "
                    "No API key required."
                ),
                parameters_model=YahooFinanceSearchRequest,
            ),
            executor=None,
            service_name="yahoo_finance",
        )
    )


def initialize_all_tools():
    """Initialize all integration and system tools."""
    define_google_tools()
    define_google_drive_tools()
    define_google_places_tools()
    define_outlook_tools()
    define_onenote_tools()
    define_todo_tools()
    define_notion_tools()
    define_nextcloud_tools()
    define_whatsapp_tools()
    define_slack_tools()
    define_brave_tools()
    define_browser_tools()
    define_system_tools()
    define_cron_job_tools()
    define_future_task_tools()
    define_document_tools()
    define_calculator_tools()
    define_python_tools()
    define_batch_tools()
    define_loop_tools()
    define_search_tools()
    define_analysis_tools()
    define_plan_tools()
    define_async_task_tools()
    define_google_ads_tools()
    define_google_news_tools()
    define_yahoo_finance_tools()
