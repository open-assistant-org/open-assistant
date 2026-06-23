# Microsoft Platform Integration (Outlook)

This guide covers integrating with Microsoft Outlook services: email, calendar, OneDrive, OneNote, and Microsoft To Do using Microsoft Graph API with device code authentication.

## Overview

Open Assistant integrates with Microsoft's platform through Azure Active Directory and Microsoft Graph API using **device code flow** for authentication.

**Services Covered**:
- Outlook Mail (email reading and sending)
- Outlook Calendar (event management)
- OneDrive (file access)
- OneNote (notebook management)
- Microsoft To Do (task management)

## Prerequisites

- Microsoft 365 account (Outlook.com or organizational account)
- Azure Portal access for app registration

## Step 1: Register Application in Azure

### Option A: Public Client (Recommended for Personal Use)

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to **Azure Active Directory > App registrations**
3. Click **New registration**
4. Configure:
   - **Name**: "Open Assistant"
   - **Supported account types**: "Accounts in any organizational directory and personal Microsoft accounts"
   - **Redirect URI**: Leave empty (not needed for device code flow)
5. Click **Register**
6. Note the **Application (client) ID** (you'll need this)
7. Go to **Authentication** in the left menu
8. Under **Advanced settings**, set **Allow public client flows** to **Yes**
9. Click **Save**

### Option B: Confidential Client (For Organizations)

Follow steps 1-6 above, then:

7. Go to **Certificates & secrets**
8. Click **New client secret**
9. **Description**: "Open Assistant Secret"
10. **Expires**: Choose duration (24 months recommended)
11. Click **Add**
12. **Important**: Copy the secret value immediately (won't be shown again)

## Step 2: Configure API Permissions

1. In your app registration, go to **API permissions**
2. Click **Add a permission > Microsoft Graph > Delegated permissions**
3. Add the following permissions:

### Required Permissions
- `Mail.Read` - Read user mail and attachments
- `Mail.ReadWrite` - Read and write access to user mail
- `Mail.Send` - Send emails (REQUIRED for sending emails)
- `Calendars.Read` - Read user calendars
- `Calendars.ReadWrite` - Full access to user calendars
- `Files.ReadWrite.All` - Read and write all files user can access (REQUIRED for OneDrive upload)
- `User.Read` - Sign in and read user profile
- `Notes.Read` - Read OneNote notebooks and pages
- `Notes.ReadWrite` - Create, update, and delete OneNote pages (REQUIRED for creating notes)
- `Tasks.ReadWrite` - Create, read, update, and delete Microsoft To Do tasks and task lists

**Note**: Do NOT manually add `offline_access` - the MSAL library adds this automatically.

**Important**: The application will automatically request these scopes during device code authentication.

4. Click **Grant admin consent** (if required for organizational accounts)

## Step 3: Configure the Application

1. Open the Open Assistant web interface
2. Go to **Settings**
3. Navigate to **Integrations > Outlook**
4. Configure the following:

### Required Settings
- **Enable Outlook**: Toggle to ON
- **Client ID**: Paste your Application (client) ID from Azure Portal
- **Tenant ID**:
  - Use `common` for personal Microsoft accounts
  - Use `organizations` for work/school accounts only
  - Use `consumers` for personal accounts only
  - Or use your specific tenant ID

### Optional Settings (For Confidential Client Only)
- **Client Secret**: Only needed if you created a client secret in Azure Portal
- Leave empty if using public client authentication

5. Click **Save**

## Step 4: Authenticate with Microsoft

Authentication happens automatically when you first try to use Outlook:

1. In the chat, ask the assistant to perform an Outlook action (e.g., "send an email to test@example.com")
2. The assistant will respond with authentication instructions:
   - A URL to visit (usually https://microsoft.com/devicelogin)
   - A code to enter
3. Visit the URL and enter the code
4. Sign in with your Microsoft account
5. Grant permissions to the app
6. Wait 30 seconds for the background authentication to complete
7. Try your request again

**Token Storage**: Tokens are cached in `data/outlook_token_cache.json` and automatically refresh.

## Using Outlook Through Chat

Once configured and authenticated, you can use Outlook directly through the chat interface. The AI assistant will automatically use the Outlook integration when you ask it to perform email or calendar operations.

### Example Conversations

**Sending Email**:
```
You: Send an email to john@example.com with subject "Meeting Tomorrow" and body "Hi John, let's meet at 3pm"
Assistant: I've sent the email to john@example.com with subject "Meeting Tomorrow".
```

**Reading Emails**:
```
You: Show me my recent emails
Assistant: Here are your 10 most recent emails: [list of emails]
```

**Creating Calendar Events**:
```
You: Create a calendar event for tomorrow at 2pm called "Team Sync"
Assistant: I've created the calendar event "Team Sync" for tomorrow at 2:00 PM.
```

**Searching Files**:
```
You: Search for "invoice.pdf" in my OneDrive
Assistant: I found 3 files matching "invoice.pdf": [list of files]
```

**Managing Tasks (Microsoft To Do)**:
```
You: Show me my to-do lists
Assistant: Here are your Microsoft To Do task lists: [list of task lists]

You: Add a task "Buy groceries" to my Tasks list with due date tomorrow
Assistant: I've created the task "Buy groceries" in your Tasks list, due 2026-03-05.

You: Mark "Buy groceries" as completed
Assistant: Done! I've marked "Buy groceries" as completed.

You: Show my incomplete tasks
Assistant: Here are your incomplete tasks: [list of tasks with status notStarted or inProgress]
```

The assistant will automatically handle authentication prompts if needed.

## Outlook Mail Operations (API Reference)

### Read Emails

```python
# Read emails from inbox
emails = microsoft_agent.read_emails(
    folder="inbox",
    filter="isRead eq false",  # OData filter
    limit=10
)

# Search emails
emails = microsoft_agent.search_emails(
    query="from:example@outlook.com subject:invoice"
)

# Get emails from specific folder
emails = microsoft_agent.read_emails(
    folder="archive",
    limit=20
)
```

### Create Draft

```python
draft = microsoft_agent.create_draft(
    to=["recipient@example.com"],
    subject="Meeting Notes",
    body="<p>Hi,</p><p>Here are the notes...</p>",
    body_type="html",  # or "text"
    cc=["cc@example.com"],  # Optional
    bcc=["bcc@example.com"]  # Optional
)
```

### Send Email

```python
microsoft_agent.send_email(
    to=["recipient@example.com"],
    subject="Quick Update",
    body="Brief message here"
)
```

## Outlook Calendar Operations

### Get Events

```python
# Get calendar events
events = microsoft_agent.get_calendar_events(
    start_date="2024-01-01T00:00:00",
    end_date="2024-01-31T23:59:59",
    timezone="America/New_York"
)

# Get today's events
from datetime import datetime, timedelta
today = datetime.now()
tomorrow = today + timedelta(days=1)

events = microsoft_agent.get_calendar_events(
    start_date=today.isoformat(),
    end_date=tomorrow.isoformat()
)
```

### Create Event

```python
event = microsoft_agent.create_calendar_event(
    subject="Team Meeting",
    start="2024-01-15T10:00:00",
    end="2024-01-15T11:00:00",
    timezone="America/New_York",
    location="Conference Room A",
    body="Discuss Q1 goals",
    attendees=["attendee@example.com"],
    is_online_meeting=True  # Create Teams meeting
)
```

### Update Event

```python
microsoft_agent.update_calendar_event(
    event_id="event-id-here",
    subject="Updated Meeting Title",
    start="2024-01-15T11:00:00",
    end="2024-01-15T12:00:00"
)
```

### Delete Event

```python
microsoft_agent.delete_calendar_event(
    event_id="event-id-here"
)
```

## OneDrive Operations

### List Files

```python
# List files in folder
files = microsoft_agent.list_onedrive_files(
    folder_path="/Documents"
)

# List root folder
files = microsoft_agent.list_onedrive_files(
    folder_path="/"
)
```

### Read File

```python
# Get file content
content = microsoft_agent.read_onedrive_file(
    file_id="file-id-here"
)

# Get file by path
content = microsoft_agent.read_onedrive_file_by_path(
    file_path="/Documents/report.pdf"
)
```

### Search Files

```python
# Search for files
files = microsoft_agent.search_onedrive_files(
    query="invoice.pdf"
)

# Search with filters
files = microsoft_agent.search_onedrive_files(
    query="presentation",
    file_type="powerpoint"
)
```

### Download File

```python
# Download file to local storage
microsoft_agent.download_onedrive_file(
    file_id="file-id-here",
    destination="./downloads/file.pdf"
)
```

## OneNote Operations

### List Notebooks

```python
# List all notebooks
notebooks = microsoft_agent.list_notebooks()

# Include sections in response
notebooks = microsoft_agent.list_notebooks(include_sections=True)
```

### List Sections

```python
# List all sections
sections = microsoft_agent.list_sections()

# List sections in specific notebook
sections = microsoft_agent.list_sections(notebook_id="notebook-id-here")
```

### List Pages

```python
# List recent pages
pages = microsoft_agent.list_pages(limit=20)

# List pages in specific section
pages = microsoft_agent.list_pages(section_id="section-id-here")

# Include full content
pages = microsoft_agent.list_pages(include_content=True)
```

### Get Page

```python
# Get page (include_content defaults to True)
page = microsoft_agent.get_page(
    page_id="page-id-here"
)
```

### Create Page

```python
# Create a new page
page = microsoft_agent.create_page(
    section_id="section-id-here",
    title="Meeting Notes",
    content="<p>Notes from today's meeting...</p><ul><li>Item 1</li></ul>"
)
```

### Update Page (Append)

```python
# Append content to existing page
microsoft_agent.update_page(
    page_id="page-id-here",
    content="<p>Additional notes...</p>"
)
```

### Delete Page

```python
# Delete a page
microsoft_agent.delete_page(page_id="page-id-here")
```

### Search Pages

```python
# Search OneNote content
pages = microsoft_agent.search_onenote(
    query="project deadline",
    limit=10
)
```

### Copy Page to Another Section

```python
# Copy a page to a different section
result = microsoft_agent.copy_page(
    page_id="page-id-here",
    target_section_id="target-section-id"
)
```

### Create Page from Markdown

```python
# Create page with Markdown formatting
page = microsoft_agent.create_page_from_markdown(
    section_id="section-id-here",
    title="My Notes",
    markdown_content="""
# Heading 1
## Heading 2

This is **bold** and *italic* text.

- List item 1
- List item 2

`inline code` and code blocks work too.
"""
)
```

### Create Page from Template

```python
# Create meeting notes from template
page = microsoft_agent.create_page_from_template(
    section_id="section-id-here",
    template="meeting_notes",
    title="Team Sync",
    variables={
        "attendees": "John, Jane, Bob",
        "date": "2024-01-15"
    }
)

# Other templates: "daily_journal", "todo", "project"
```

### Extract Plain Text

```python
# Get just the text content, no HTML
result = microsoft_agent.extract_page_text(page_id="page-id-here")
print(result["text"])  # Plain text content
```

### Available Templates

| Template | Description |
|----------|-------------|
| `meeting_notes` | Meeting notes with agenda, notes, action items |
| `daily_journal` | Daily journal with goals, notes, reflections |
| `todo` | Prioritized to-do list |
| `project` | Project overview with objectives, timeline, resources |

## Microsoft To Do Operations

### List Task Lists

```python
# List all To Do task lists
lists = microsoft_agent.list_todo_lists()
```

### Create Task List

```python
# Create a new task list
new_list = microsoft_agent.create_todo_list(
    display_name="Work Projects"
)
```

### Delete Task List

```python
# Delete a task list (and all its tasks)
microsoft_agent.delete_todo_list(list_id="list-id-here")
```

### List Tasks

```python
# List all tasks in a list
tasks = microsoft_agent.list_todo_tasks(
    list_id="list-id-here",
    limit=50
)

# Filter by status
tasks = microsoft_agent.list_todo_tasks(
    list_id="list-id-here",
    status="notStarted"  # or "inProgress", "completed"
)
```

### Create Task

```python
# Create a simple task
task = microsoft_agent.create_todo_task(
    list_id="list-id-here",
    title="Review quarterly report"
)

# Create a task with all options
task = microsoft_agent.create_todo_task(
    list_id="list-id-here",
    title="Prepare presentation",
    body="Include Q1 sales data and projections",
    due_date="2026-03-15",
    importance="high",  # "low", "normal", or "high"
    reminder_date_time="2026-03-14T09:00:00"
)
```

### Update Task

```python
# Mark task as completed
microsoft_agent.update_todo_task(
    list_id="list-id-here",
    task_id="task-id-here",
    status="completed"
)

# Update multiple fields
microsoft_agent.update_todo_task(
    list_id="list-id-here",
    task_id="task-id-here",
    title="Updated title",
    due_date="2026-03-20",
    importance="high"
)
```

### Delete Task

```python
# Delete a task permanently
microsoft_agent.delete_todo_task(
    list_id="list-id-here",
    task_id="task-id-here"
)
```

### Available Tools

| Tool | Description |
|------|-------------|
| `todo_list_task_lists` | List all To Do task lists |
| `todo_get_task_list` | Get details of a specific task list |
| `todo_create_task_list` | Create a new task list |
| `todo_delete_task_list` | Delete a task list |
| `todo_list_tasks` | List tasks in a task list (with optional status filter) |
| `todo_get_task` | Get details of a specific task |
| `todo_create_task` | Create a new task (title, body, due date, importance, reminder) |
| `todo_update_task` | Update a task (title, body, due date, importance, status, reminder) |
| `todo_delete_task` | Delete a task |
| `onenote_extract_page_text` | Extract plain text from a OneNote page (returns text content) |

## Token Management

Microsoft Graph API uses OAuth 2.0 with MSAL (Microsoft Authentication Library).

**Token Storage**: `data/outlook_token_cache.json`

Token contains:
- **access_token**: Expires in 1 hour
- **refresh_token**: Used to get new access tokens
- **expires_at**: Timestamp when token expires

Tokens automatically refresh using the refresh token.

## Troubleshooting

### Common Authentication Errors

**Error: `AADSTS7000218: The request body must contain the following parameter: 'client_assertion' or 'client_secret'`**

This error occurs when your Azure app is registered as a **Web app** (confidential client) but no client secret is configured in the Open Assistant settings.

**Solutions**:
1. **Option A: Add Client Secret** (if you want to keep it as a Web app)
   - Go to Azure Portal > Your app > Certificates & secrets
   - Create a new client secret
   - Copy the secret value
   - In Open Assistant Settings > Integrations > Outlook, add the secret to **Client Secret** field
   - Save and try authenticating again

2. **Option B: Change to Public Client** (recommended for personal use)
   - Go to Azure Portal > Your app > Authentication
   - Under **Advanced settings**, set **Allow public client flows** to **Yes**
   - Click Save
   - In Open Assistant Settings > Integrations > Outlook, ensure **Client Secret** is empty
   - Delete `data/outlook_token_cache.json` if it exists
   - Try authenticating again

**Error: `AADSTS65001: The user or administrator has not consented`**
- Solution: Re-authenticate using device code flow
- Check that all required permissions are added in Azure Portal > API permissions
- Grant admin consent if required for organizational accounts

**Error: `invalid_client`**
- Solution: Verify client_id in Settings matches the Application (client) ID in Azure Portal
- If using client secret, verify it's correct and hasn't expired
- Check tenant_id is correct (`common`, `organizations`, `consumers`, or your specific tenant ID)

**Error: `insufficient_permissions`**
- Solution: Check API permissions are granted in Azure Portal
- Required: `Mail.Read`, `Mail.ReadWrite`, `Calendars.Read`, `Calendars.ReadWrite`, `Files.Read.All`, `User.Read`, `Notes.Read`, `Notes.ReadWrite`, `Tasks.ReadWrite`
- Click "Grant admin consent" if available

**Error: `AADSTS50020: User account from identity provider does not exist in tenant`**
- Solution: Check that **Supported account types** in Azure app includes the type of account you're using
- For personal Microsoft accounts, ensure "Accounts in any organizational directory and personal Microsoft accounts" is selected

### Token Issues

**Authentication keeps asking for device code repeatedly**
- Problem: Token is not being saved or cached properly
- Solutions:
  1. Check that `data/` directory exists and is writable
  2. Look for errors in logs related to token cache
  3. Verify settings are saved correctly in the database
  4. Try: `rm data/outlook_token_cache.json` and re-authenticate

**Token expired or invalid**
- Solution: Delete `data/outlook_token_cache.json` and re-authenticate
- The token will automatically refresh if valid refresh token exists

### Service-Specific Issues

**Outlook Mail**:
- Check folder names (case-sensitive)
- Verify OData filter syntax
- Test with simple queries first

**Calendar**:
- Ensure timezone format is valid
- Check date/time formats (ISO 8601)
- Verify calendar permissions

**OneDrive**:
- Check file paths (use forward slashes)
- Verify file permissions
- Test with root folder first

**OneNote**:
- Content must be valid HTML for page creation
- Page updates append content (cannot replace existing content)
- Section ID required for creating new pages
- Use `onenote_list_sections` to discover section IDs

**Microsoft To Do**:
- Use `todo_list_task_lists` first to discover list IDs before creating/listing tasks
- Status values: `notStarted`, `inProgress`, `completed`
- Importance values: `low`, `normal`, `high`
- Due dates use `YYYY-MM-DD` format
- Reminder datetimes use ISO format (e.g. `2026-03-05T09:00:00`)

## Rate Limits

Microsoft Graph API has throttling limits:

- **Mail**: 10,000 requests per 10 minutes
- **Calendar**: 1,500 requests per 30 seconds
- **Files**: 5,000 requests per 10 minutes

**Handling Throttling**:
- Watch for `429 Too Many Requests` responses
- Implement exponential backoff
- Check `Retry-After` header

See [Microsoft Graph throttling guidance](https://learn.microsoft.com/en-us/graph/throttling) for details.

## Security Best Practices

1. **Credentials**:
   - Store client_secret in environment variables
   - Never commit credentials to version control
   - Rotate secrets before expiration

2. **Permissions**:
   - Request minimum required scopes
   - Use least privilege principle
   - Regularly audit permissions

3. **Token Security**:
   - Encrypt token file at rest
   - Restrict file permissions (600)
   - Monitor token usage

4. **Account Security**:
   - Enable conditional access policies
   - Monitor sign-in logs in Azure Portal
   - Use organizational accounts with MFA

## API References

- [Microsoft Graph API Documentation](https://learn.microsoft.com/en-us/graph/api/overview)
- [Mail API](https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview)
- [Calendar API](https://learn.microsoft.com/en-us/graph/api/resources/calendar)
- [OneDrive API](https://learn.microsoft.com/en-us/graph/api/resources/onedrive)
- [OneNote API](https://learn.microsoft.com/en-us/graph/api/resources/onenote-api-overview)
- [To Do API](https://learn.microsoft.com/en-us/graph/api/resources/todo-overview)
- [MSAL Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)

## Related Documentation

- [Solution Architecture](../architecture/solution-architecture.md) - Technology details
- [Software Architecture](../architecture/software-architecture.md) - Integration implementation
- [Configuration Guide](../setup/configuration.md) - Configuration options
