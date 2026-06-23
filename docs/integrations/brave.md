# Brave Search Integration

This guide covers setting up Brave Search for web search operations.

## Overview

Brave Search provides fast, privacy-respecting web search results. When configured, Open Assistant uses Brave Search for web search operations.

**Capabilities**:
- Web search with freshness filters (day, week, month, year)
- Adjustable result count (up to 20)
- Safe search filtering (off, moderate, strict)
- Built-in rate-limit handling with automatic retry

## Prerequisites

- Brave Search API key (free tier available)

## Step 1: Get an API Key

1. Go to [https://brave.com/search/api/](https://brave.com/search/api/)
2. Sign up for a free account (or log in)
3. Under **Developer Resources**, click **Get Started**
4. Create a new API key
5. Copy the API key (starts with `BSA...`)

The free tier allows 1 request per second.

## Step 2: Configure in Settings

1. Go to **Settings > Integrations > Brave Search**
2. Enable the Brave Search integration
3. Paste your API key
4. Configure optional settings:
   - **Results Limit**: Maximum number of results (default: 10, max: 20)
   - **Safe Search**: Filtering level — `off`, `moderate` (default), or `strict`
5. Click **Save**
6. Click **Test Connection** to verify

Or use environment variables:

```bash
BRAVE_ENABLED=true
BRAVE_API_KEY=BSA...
BRAVE_RESULTS_LIMIT=10
BRAVE_SAFE_SEARCH=moderate
```

## How It Works

The Brave Search integration is used automatically when you ask the assistant to search the web. Example conversations:

```
You: Search for the latest news about AI assistants
Assistant: [Uses Brave Search to find current news articles]

You: Find restaurants near me that are open now
Assistant: [Uses Brave Search to find nearby restaurants with current hours]
```

### Freshness Filters

You can request results from a specific time period:

| Filter | Brave API Value | Description |
|--------|----------------|-------------|
| `day` | `pd` | Past 24 hours |
| `week` | `pw` | Past 7 days |
| `month` | `pm` | Past 30 days |
| `year` | `py` | Past 365 days |

Example:
```
You: Find news about space exploration from the past week
```

## Rate Limits

| Tier | Rate Limit |
|------|------------|
| Free | 1 request per second |
| Paid | Higher limits available |

If you exceed the rate limit, the client automatically retries with exponential backoff (up to 2 retries).

## Troubleshooting

### "Brave Search integration is not enabled"

- Go to **Settings > Integrations > Brave Search**
- Ensure the toggle is enabled
- Verify an API key is saved

### "Brave Search API key not found"

- Check that the API key was saved correctly in Settings
- The key starts with `BSA...`
- Try deleting and re-entering the key

### Rate limit errors in logs

- Reduce the number of search requests
- Upgrade to a paid Brave Search plan for higher limits
- The system will automatically retry with backoff

### Poor search results

- Try using freshness filters to get more recent content

## Security Considerations

- **API Key**: Store securely — it grants access to your Brave Search quota
- **Search Queries**: Search terms are sent to Brave's servers

## API Reference

- **Brave Search API**: [https://brave.com/search/api/](https://brave.com/search/api/)
- **Rate Limits**: [https://brave.com/search/api/#rate-limits](https://brave.com/search/api/#rate-limits)

---

**Last Updated**: March 2026
