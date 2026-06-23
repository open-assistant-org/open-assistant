# Notion Integration Guide

This guide covers setting up Notion integration for creating and managing notes.

## Prerequisites

- Notion account
- Notion workspace with appropriate permissions

## Step 1: Create Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click **New integration**
3. Configure:
   - Name: "Open Assistant"
   - Associated workspace: Select your workspace
   - Type: Internal integration
4. Click **Submit**
5. Copy the **Internal Integration Token** (starts with `secret_`)

## Step 2: Grant Integration Access to Pages

The integration needs to be explicitly granted access to pages/databases:

1. Open the Notion page or database you want the bot to access
2. Click the **...** menu in the top right
3. Select **Add connections**
4. Search for "Open Assistant" and select it

**Important**: You must do this for each page/database you want to access.

## Step 3: Get Database IDs (Optional)

If you want to write to specific databases:

1. Open the database in Notion
2. Click **...** menu > **Copy link**
3. Extract the database ID from the URL:
   ```
   https://www.notion.so/{workspace}/{database_id}?v={view_id}
   ```
4. The `database_id` is a 32-character string (dashes removed)

## Step 4: Configure Application

Configuration is managed through the Settings UI or environment variables:

```bash
NOTION_API_TOKEN=secret_your_integration_token
NOTION_DATABASE_ID=your-database-id
```

In **Settings > Integrations > Notion**, enable the integration and paste your API token. Set a **Database ID** if you want transcriptions and notes to go to a specific database.

## Available Operations

### Create Page

```python
# Create a page in a database
page = notion_agent.create_page(
    database_id="your-database-id",
    properties={
        "Name": {"title": [{"text": {"content": "Meeting Notes"}}]},
        "Date": {"date": {"start": "2024-01-15"}},
        "Tags": {"multi_select": [{"name": "Work"}, {"name": "Important"}]}
    },
    content="# Meeting Notes\n\nDiscussed project timeline..."
)

# Create a page under another page
page = notion_agent.create_child_page(
    parent_page_id="parent-page-id",
    title="New Note",
    content="This is a new note..."
)
```

### Update Page

```python
# Update page properties
notion_agent.update_page(
    page_id="page-id",
    properties={
        "Status": {"select": {"name": "In Progress"}}
    }
)

# Append content to page
notion_agent.append_blocks(
    page_id="page-id",
    blocks=[
        {"type": "paragraph", "paragraph": {"text": [{"text": {"content": "Additional notes..."}}]}}
    ]
)
```

### Search

```python
# Search for pages
results = notion_agent.search(
    query="meeting notes",
    filter={"property": "object", "value": "page"}
)

# Get recent pages
pages = notion_agent.search(
    filter={"property": "object", "value": "page"},
    sort={"direction": "descending", "timestamp": "last_edited_time"}
)
```

### Read Page

```python
# Get page properties
page = notion_agent.get_page(page_id="page-id")

# Get page content (blocks)
blocks = notion_agent.get_blocks(page_id="page-id")
```

### Database Operations

```python
# Query database
entries = notion_agent.query_database(
    database_id="database-id",
    filter={
        "property": "Status",
        "select": {"equals": "In Progress"}
    },
    sorts=[
        {"property": "Created", "direction": "descending"}
    ]
)

# Create database entry
entry = notion_agent.create_database_entry(
    database_id="database-id",
    properties={
        "Name": {"title": [{"text": {"content": "New Task"}}]},
        "Status": {"select": {"name": "To Do"}},
        "Priority": {"select": {"name": "High"}}
    }
)
```

## Content Block Types

Notion uses blocks for content. Common block types:

### Paragraph
```python
{
    "type": "paragraph",
    "paragraph": {
        "rich_text": [{"text": {"content": "This is a paragraph."}}]
    }
}
```

### Heading
```python
{
    "type": "heading_2",
    "heading_2": {
        "rich_text": [{"text": {"content": "Section Title"}}]
    }
}
```

### Bulleted List
```python
{
    "type": "bulleted_list_item",
    "bulleted_list_item": {
        "rich_text": [{"text": {"content": "List item"}}]
    }
}
```

### To-Do
```python
{
    "type": "to_do",
    "to_do": {
        "rich_text": [{"text": {"content": "Task item"}}],
        "checked": False
    }
}
```

### Code Block
```python
{
    "type": "code",
    "code": {
        "rich_text": [{"text": {"content": "console.log('Hello');"}}],
        "language": "javascript"
    }
}
```

## Property Types

Common property types in databases:

```python
properties = {
    # Title
    "Name": {"title": [{"text": {"content": "Page Title"}}]},

    # Rich text
    "Description": {"rich_text": [{"text": {"content": "Description text"}}]},

    # Number
    "Priority": {"number": 1},

    # Select (single choice)
    "Status": {"select": {"name": "In Progress"}},

    # Multi-select
    "Tags": {"multi_select": [{"name": "Work"}, {"name": "Important"}]},

    # Date
    "Due Date": {"date": {"start": "2024-01-15"}},

    # Date range
    "Period": {"date": {"start": "2024-01-15", "end": "2024-01-20"}},

    # Checkbox
    "Completed": {"checkbox": True},

    # URL
    "Link": {"url": "https://example.com"},

    # Email
    "Email": {"email": "user@example.com"},

    # Phone
    "Phone": {"phone_number": "+1234567890"}
}
```

## Rate Limits

- 3 requests per second per integration
- Automatic retry with exponential backoff implemented in client

## Error Handling

### Common Errors

**Error: `object_not_found`**
- Solution: Ensure integration has access to the page/database

**Error: `unauthorized`**
- Solution: Verify API token is correct and not expired

**Error: `validation_error`**
- Solution: Check property types match database schema

**Error: `rate_limited`**
- Solution: Reduce request frequency, client will auto-retry

## Best Practices

1. **Database Schema**
   - Define consistent property names across databases
   - Use select/multi-select for categorization
   - Add descriptions to database properties

2. **Content Structure**
   - Use headings for organization
   - Keep paragraphs concise
   - Use proper block types (lists, code blocks, etc.)

3. **Access Control**
   - Only share necessary pages with integration
   - Regularly audit integration connections
   - Use separate integrations for different purposes

4. **Performance**
   - Cache frequently accessed pages
   - Batch operations when possible
   - Use database queries instead of searching all pages

## Troubleshooting

### Integration Not Appearing
- Refresh the connections menu
- Ensure integration is active in settings

### Can't Access Page
- Verify page has been shared with integration
- Check workspace permissions
- Ensure page hasn't been deleted or moved

### Property Validation Errors
- Check database schema in Notion
- Verify property names match exactly (case-sensitive)
- Ensure property types are correct

## API Reference

- [Notion API Documentation](https://developers.notion.com/)
- [Working with Pages](https://developers.notion.com/reference/page)
- [Working with Databases](https://developers.notion.com/reference/database)
- [Block Types](https://developers.notion.com/reference/block)