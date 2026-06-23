# Toggl Track Integration

This guide covers setting up the Toggl Track integration for time-tracking queries.

## Overview

Toggl Track is a time-tracking tool. This integration lets Open Assistant read your
time-tracking data — running timers, logged entries, projects, and workspaces — so
you can ask questions like *"How many hours did I log this week?"* or *"What am I
tracking right now?"*

**Capabilities (read-only)**:
- Get your Toggl user profile and default workspace
- List all accessible workspaces
- List projects in a workspace
- List time entries with optional date-range filtering
- Check whether a timer is currently running

No write operations are exposed — the integration cannot start, stop, or edit timers.

## Prerequisites

- A [Toggl Track](https://toggl.com/track/) account (free tier is sufficient)
- Your personal API token

## Step 1: Get Your API Token

1. Log in to [toggl.com/track](https://toggl.com/track/)
2. Click your avatar / profile picture in the bottom-left corner
3. Select **Profile Settings**
4. Scroll to the **API Token** section at the bottom of the page
5. Copy the token (a 32-character hex string)

> Your API token gives full access to your Toggl account. Treat it like a password.

## Step 2: Configure in Settings

1. Go to **Settings > Integrations > Toggl**
2. Enable the Toggl integration
3. Paste your API token into the **API Token** field
4. Click **Save**
5. Click **Test Connection** to verify — you should see your name and email confirmed

Or use environment variables:

```bash
TOGGL_ENABLED=true
TOGGL_API_TOKEN=your-32-character-token-here
```

## Available Tools

Once enabled, the following tools are available to the assistant:

| Tool | Description |
|------|-------------|
| `toggl_get_me` | Get your profile, email, timezone, and default workspace ID |
| `toggl_list_workspaces` | List all workspaces you have access to |
| `toggl_list_projects` | List projects in a workspace (requires workspace ID) |
| `toggl_list_time_entries` | List time entries, optionally filtered by date range |
| `toggl_get_current_timer` | Check whether a timer is currently running |

## Example Conversations

```
You: How many hours did I track this week?
Assistant: [Calls toggl_list_time_entries with this week's date range,
           sums the durations, and reports the total]

You: What am I tracking right now?
Assistant: [Calls toggl_get_current_timer and reports the running entry
           or "No timer is currently running."]

You: Show me all my projects in my default workspace.
Assistant: [Calls toggl_get_me to get the workspace ID, then
           toggl_list_projects to list them]

You: What did I work on last Monday?
Assistant: [Calls toggl_list_time_entries with start_date and end_date
           set to last Monday, then summarises the entries]
```

## Date Range Filtering

`toggl_list_time_entries` accepts `start_date` and `end_date` in ISO 8601 format:

| Format | Example |
|--------|---------|
| Date only | `2026-04-01` |
| Full datetime | `2026-04-01T00:00:00+00:00` |

When both are omitted the Toggl API returns the past 9 days (its default).
The API returns at most **1 000 entries** per request — use a narrower range for
high-volume workspaces.

## Troubleshooting

### "Toggl integration is not enabled"

- Go to **Settings > Integrations > Toggl**
- Make sure the toggle is on and click **Save**

### "Toggl API token not configured"

- Confirm the token was saved in Settings
- Try deleting and re-entering the token
- Click **Test Connection** to verify it is accepted

### Test Connection returns "connected: false"

- Double-check the token copied from Toggl Profile Settings
- Ensure your Toggl account is active
- Check that the token has not been reset (Toggl lets you regenerate it)

### Empty time entries list

- Confirm the date range covers a period when you actually tracked time
- Check the workspace ID — entries belong to a specific workspace

## Security Considerations

- **API Token**: Stored encrypted at rest using the application's built-in
  `EncryptionService`. It is never logged or exposed in plain text.
- **Read-only**: This integration cannot create, edit, or delete any Toggl data.
- **Data sent to Toggl**: Queries (date ranges, workspace IDs) are sent to
  `api.track.toggl.com` over HTTPS.

## API Reference

- **Toggl API v9 docs**: [developers.track.toggl.com](https://developers.track.toggl.com/docs/)
- **Authentication**: HTTP Basic Auth — API token as username, `"api_token"` as password

---

**Last Updated**: April 2026
