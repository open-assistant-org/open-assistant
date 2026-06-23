# Google Platform Integration

This guide covers integrating with Google services: Gmail, Google Calendar, Google Drive, Google Docs, Google Sheets, and Google Slides.

## Overview

Open Assistant integrates with Google's platform through the Google Cloud Console and Google APIs.

**Services Covered**:
- Gmail (email reading, draft creation, sending, label management)
- Google Calendar (event management)
- Google Drive (file listing, searching, reading, uploading, organizing)
- Google Docs (create, read, append, update documents)
- Google Sheets (create, read, write, append to spreadsheets)
- Google Slides (create presentations, read slide content)

## Prerequisites

- Google Cloud Console account
- Google Workspace or personal Google account

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note your Project ID

## Step 2: Enable APIs

Enable the required APIs for your project:

1. Go to **APIs & Services > Library**
2. Search and enable:
   - **Gmail API**
   - **Google Calendar API**
   - **Google Drive API**
   - **Google Docs API**
   - **Google Sheets API**
   - **Google Slides API**

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. Configure consent screen:
   - **User Type**: External (for personal use)
   - **App name**: "Open Assistant"
   - **User support email**: Your email
   - **Developer contact**: Your email
3. Add scopes (will be configured in app)
4. Add test users if in development mode

## Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Choose **Application type**: Web application
4. **Name**: "Open Assistant Client"
5. Add **Authorized redirect URI**: `http://localhost:8080/auth/google/callback`
   - Note: If deploying to production, also add your production URL (e.g., `https://yourdomain.com/auth/google/callback`)
6. Click **Create**
7. Copy the **Client ID** and **Client Secret** (you'll enter these in Settings)

## Step 5: Configure Scopes

The following scopes are **required** and will be requested automatically during OAuth setup:

### Gmail Scopes (All Required)
```yaml
gmail_scopes:
  - https://www.googleapis.com/auth/gmail.readonly  # Read emails and attachments
  - https://www.googleapis.com/auth/gmail.compose   # Create drafts
  - https://www.googleapis.com/auth/gmail.send      # Send emails
  - https://www.googleapis.com/auth/gmail.modify    # Manage labels, trash, star emails (REQUIRED for email classification)
```

### Google Calendar Scopes (All Required)
```yaml
calendar_scopes:
  - https://www.googleapis.com/auth/calendar.readonly    # Read calendar
  - https://www.googleapis.com/auth/calendar.events      # Create, update, delete events
```

### Google Drive, Docs, Sheets & Slides Scopes (All Required)
```yaml
drive_scopes:
  - https://www.googleapis.com/auth/drive                # Full Drive access (list, read, upload, delete, move)
  - https://www.googleapis.com/auth/documents            # Create and edit Google Docs
  - https://www.googleapis.com/auth/spreadsheets         # Create and edit Google Sheets
  - https://www.googleapis.com/auth/presentations        # Create and read Google Slides
```

**Note**: All scopes are automatically requested during authentication. You don't need to configure them manually. If you previously authenticated before Drive support was added, you will need to re-authenticate so the new scopes are granted.

## Step 6: Configure in Settings

1. Go to the **Settings** page in your Open Assistant web UI
2. Navigate to the **Integrations** tab
3. Find the **Google** integration card
4. Enter your credentials:
   - **Client ID**: Paste the Client ID from Step 4
   - **Client Secret**: Paste the Client Secret from Step 4
   - **Project ID** (optional): Your Google Cloud Project ID
5. Click **Save Google Settings**
6. Toggle **Enable Google Services** to ON

## Step 7: Initial Authentication

### Via Chat (Recommended)

When you first try to use a Google service through chat (e.g., "check my emails"), the assistant will:

1. Detect that authentication is needed
2. Provide you with an authorization URL
3. Ask you to visit the URL and authorize the application
4. After you authorize, you'll be redirected and the authentication completes automatically
5. You can then retry your original request

Example chat flow:
```
You: Check my emails
Assistant: I need to authenticate with Google first. Please visit this URL to authorize:
https://accounts.google.com/o/oauth2/auth?...

After authorizing, try your request again.

You: Check my emails
Assistant: [Shows your emails]
```

### Via Web UI

Alternatively, you can complete authentication through the Settings page:

1. Go to Settings > Integrations > Google
2. Click "Test Connection"
3. A browser window will open for authorization
4. After authorizing, the connection will be active

**Note**: The token will be automatically refreshed when it expires.

## Gmail Operations

### Read Emails

```python
# List messages (unread, from specific label, etc.)
emails = google_client.list_messages(
    query="is:unread",
    max_results=10
)

# Search emails
emails = google_client.search_messages(
    query="from:example@gmail.com subject:invoice",
    max_results=20
)

# List messages from specific label (via label IDs)
emails = google_client.list_messages(
    label_ids=["INBOX"],
    max_results=20
)

# Get full message details by ID
message = google_client.get_message(message_id="abc123...")
```

### Create Draft

```python
draft = google_client.create_draft(
    to="recipient@example.com",
    subject="Meeting Follow-up",
    body="Hi,\n\nThanks for the meeting today...",
    cc=["cc@example.com"],  # Optional
    bcc=["bcc@example.com"]  # Optional
)
```

### Send Email

```python
google_client.send_message(
    to="recipient@example.com",
    subject="Quick Update",
    body="Brief message here"
)
```

### Reply to Email

```python
google_client.reply_to_message(
    message_id="original-message-id",
    thread_id="thread-id",
    body="Thanks for your email!"
)
```

### Manage Labels

```python
# Add/remove labels (e.g., mark read/unread, star, archive)
google_client.modify_labels(
    message_id="abc123...",
    add_labels=["STARRED"],
    remove_labels=["UNREAD"]
)

# Trash a message
google_client.trash_message(message_id="abc123...")
```

### Attachments

```python
# List attachments on a message
attachments = google_client.list_attachments(message_id="abc123...")

# Download an attachment
attachment = google_client.get_attachment(
    message_id="abc123...",
    attachment_id="attachment-id"
)
# Returns {"data": bytes, "size": int}
```

### Get Labels

```python
labels = google_client.get_labels()
```

## Google Calendar Operations

### View Events

```python
# List upcoming events
events = google_client.list_events(
    time_min="2024-01-01T00:00:00Z",
    time_max="2024-01-31T23:59:59Z",
    max_results=10,
    calendar_id="primary"
)

# Get today's events
from datetime import datetime, timedelta
today = datetime.now()
tomorrow = today + timedelta(days=1)

events = google_client.list_events(
    time_min=today.isoformat() + "Z",
    time_max=tomorrow.isoformat() + "Z",
    calendar_id="primary"
)
```

### Get Event

```python
event = google_client.get_event(
    event_id="event-id-here",
    calendar_id="primary"
)
```

### Create Event

```python
event = google_client.create_event(
    summary="Team Meeting",
    start="2024-01-15T10:00:00",
    end="2024-01-15T11:00:00",
    timezone="America/New_York",
    location="Conference Room A",
    description="Discuss Q1 goals",
    attendees=["attendee@example.com"]
)
```

### Update Event

```python
google_client.update_event(
    event_id="event-id-here",
    summary="Updated Meeting Title",
    start="2024-01-15T11:00:00",
    end="2024-01-15T12:00:00",
    calendar_id="primary"
)
```

### Delete Event

```python
google_client.delete_event(
    event_id="event-id-here",
    calendar_id="primary"
)
```
```

## Google Drive Operations

Google Drive lets you store, search, and organize any file. Google-native formats (Docs, Sheets, Slides) are also accessible through Drive's file metadata and export APIs.

### List Files

```python
# List files in My Drive root
files = google_drive_client.list_files()

# List files in a specific folder
files = google_drive_client.list_files(folder_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs")

# List only Google Docs
files = google_drive_client.list_files(
    file_types=["application/vnd.google-apps.document"]
)
```

### Search Files

```python
# Search by name or content
results = google_drive_client.search_files(query="budget 2025")

# Search only spreadsheets
results = google_drive_client.search_files(
    query="Q1 report",
    file_type="application/vnd.google-apps.spreadsheet"
)
```

### Read File Content

```python
# Read any file (Google Docs exported as text, Sheets as CSV, Slides as text)
content = google_drive_client.read_file(file_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs")
# Returns: {"name": "...", "mime_type": "...", "export_format": "...", "content": "..."}
```

### Upload a File

```python
# Upload a plain text file to Drive root
file = google_drive_client.upload_file(
    name="report.txt",
    content="Report content here...",
)

# Upload to a specific folder as CSV
file = google_drive_client.upload_file(
    name="data.csv",
    content="Name,Age\nAlice,30\nBob,25",
    folder_id="<folder_id>",
    mime_type="text/csv",
)
```

### Create Folder / Delete / Move

```python
# Create a folder
folder = google_drive_client.create_folder(name="My Project", parent_id="<parent_folder_id>")

# Delete a file permanently
google_drive_client.delete_file(file_id="<file_id>")

# Move a file to a different folder
google_drive_client.move_file(file_id="<file_id>", new_folder_id="<folder_id>")
```

## Google Docs Operations

### Create a Document

```python
# Create empty document
doc = google_docs_client.docs_create(title="Meeting Notes")
# Returns: {"document_id": "...", "title": "...", "url": "..."}

# Create document with initial content
doc = google_docs_client.docs_create(
    title="Project Proposal",
    content="# Project Proposal\n\nThis document outlines..."
)
```

### Read a Document

```python
doc = google_docs_client.docs_get(document_id="<document_id>")
# Returns: {"document_id": "...", "title": "...", "content": "full text...", "url": "..."}
```

### Edit a Document

```python
# Append to an existing document
google_docs_client.docs_append(
    document_id="<document_id>",
    content="\n\n## New Section\nContent to add at the end."
)

# Replace all content
google_docs_client.docs_update(
    document_id="<document_id>",
    content="Completely new document content."
)
```

## Google Sheets Operations

### Create a Spreadsheet

```python
# Single sheet
sheet = google_sheets_client.sheets_create(title="Budget 2025")
# Returns: {"spreadsheet_id": "...", "title": "...", "sheets": ["Sheet1"], "url": "..."}

# Multiple sheets
sheet = google_sheets_client.sheets_create(
    title="Annual Report",
    sheet_names=["Q1", "Q2", "Q3", "Q4"]
)
```

### Read Data

```python
# Get spreadsheet structure
info = google_sheets_client.sheets_get(spreadsheet_id="<id>")

# Read a range
data = google_sheets_client.sheets_read(
    spreadsheet_id="<id>",
    range_notation="Sheet1!A1:D10"
)
# Returns: {"values": [["Name", "Age"], ["Alice", "30"], ...]}
```

### Write Data

```python
# Write values to a range
google_sheets_client.sheets_write(
    spreadsheet_id="<id>",
    range_notation="Sheet1!A1",
    values=[
        ["Name", "Age", "City"],
        ["Alice", 30, "London"],
        ["Bob", 25, "Paris"],
    ]
)

# Append rows after existing data
google_sheets_client.sheets_append(
    spreadsheet_id="<id>",
    range_notation="Sheet1!A1",
    values=[["Charlie", 35, "Berlin"]]
)
```

## Google Slides Operations

### Create a Presentation

```python
pres = google_slides_client.slides_create(title="Q4 Review")
# Returns: {"presentation_id": "...", "title": "...", "slides_count": 1, "url": "..."}
```

### Read Slide Content

```python
pres = google_slides_client.slides_get(presentation_id="<id>")
# Returns: {"title": "...", "slides_count": N, "slides": [{"slide_number": 1, "text": "..."}, ...]}
```

## Token Management

- **Access Token**: Expires in 1 hour
- **Refresh Token**: Used to get new access tokens
- **Auto-refresh**: Handled automatically by the client library
- **Token Storage**: Encrypted in database (credentials table)
- **Portable**: Tokens persist across deployments and version upgrades

Token structure (stored encrypted):
```json
{
  "token": "ya29.a0...",
  "refresh_token": "1//0g...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "...",
  "client_secret": "...",
  "scopes": ["..."],
  "expiry": "2024-01-15T10:30:00Z"
}
```

**Benefits of Database Storage:**
- Tokens survive container restarts and redeployments
- Encrypted at rest using application encryption key
- No file system dependencies
- Easier backup and restore

## Troubleshooting

### Common Errors

**Error: `invalid_grant`**
- Solution: Re-authenticate via the chat interface or Settings UI (old token will be replaced)

**Error: `Access blocked: This app's request is invalid`**
- Solution: Verify OAuth consent screen is properly configured
- Check that app is not in restricted mode

**Error: `insufficient permissions`**
- Solution: Verify all required scopes are configured
- Check that APIs are enabled in Google Cloud Console

**Error: `quotaExceeded`**
- Solution: Check quota limits in Google Cloud Console
- Consider implementing rate limiting

### Token Refresh Issues

If token refresh fails:
1. Re-authenticate through the chat interface or Settings UI
2. The system will automatically obtain new access and refresh tokens
3. Tokens are stored encrypted in the database

### Gmail-Specific Issues

**Emails not appearing**:
- Check label filters
- Verify query syntax
- Test with simple queries first

**Draft creation fails**:
- Verify `gmail.compose` scope is enabled
- Check email format and encoding

### Calendar-Specific Issues

**Events not appearing**:
- Verify calendar ID (use "primary" for main calendar)
- Check timezone formatting
- Ensure time_min/time_max are in RFC3339 format

**Cannot create events**:
- Verify `calendar.events` scope is enabled
- Check start_time < end_time
- Ensure timezone is valid

## Rate Limits

### Gmail API
- **Default quota**: 1 billion quota units per day
- **Per-user rate**: 250 quota units per second
- **Most operations**: 5-25 quota units

Monitor usage: [Google Cloud Console > APIs & Services > Dashboard](https://console.cloud.google.com/apis/dashboard)

### Google Calendar API
- **Queries per day**: 1,000,000
- **Queries per 100 seconds per user**: 500
- **Queries per 100 seconds**: 10,000

## Security Best Practices

1. **Credentials**:
   - OAuth tokens are automatically encrypted and stored in the database
   - Never commit credential files to version control
   - Use environment variables for configuration
   - Rotate credentials periodically

2. **Scopes**:
   - Request minimum required scopes
   - Use read-only scopes when possible
   - Review scope usage regularly

3. **Account Security**:
   - Enable 2FA on your Google account
   - Regularly review authorized apps
   - Monitor OAuth consent screen activity

4. **Token Storage**:
   - Tokens are encrypted in database using application encryption key
   - Database backups should be encrypted
   - Never share or log tokens

## API References

- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [Google Calendar API Documentation](https://developers.google.com/calendar/api)
- [Google Drive API Documentation](https://developers.google.com/drive/api)
- [Google Docs API Documentation](https://developers.google.com/docs/api)
- [Google Sheets API Documentation](https://developers.google.com/sheets/api)
- [Google Slides API Documentation](https://developers.google.com/slides/api)
- [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)
- [Python Client Library](https://github.com/googleapis/google-api-python-client)

## Related Documentation

- [Solution Architecture](../architecture/solution-architecture.md) - Technology details
- [Software Architecture](../architecture/software-architecture.md) - Integration implementation
- [Configuration Guide](../setup/configuration.md) - Configuration options
