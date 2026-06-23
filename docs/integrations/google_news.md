# Google News Integration

Fetch real-time news headlines, search for articles, and browse news by topic, location, or publisher — all without needing an API key.

> **No API key required.** Google News is accessed via public RSS feeds through the [`gnews`](https://pypi.org/project/gnews/) package.

---

## Setup

1. Go to **Settings → Integrations → Google News**
2. Toggle **Enable Google News** to on
3. (Optional) Set your preferred **Language**, **Country**, and **Max Results**
4. Click **Test Connection** to verify everything works
5. Click **Save Settings**

That's it — no account, no API key, no OAuth flow.

---

## Settings

| Setting | Description | Default |
|---------|-------------|---------|
| **Enable Google News** | Toggle the integration on/off | `false` |
| **Language** | ISO 639-1 language code for news results (`en`, `de`, `fr`, `es`, `nl`, …) | `en` |
| **Country** | ISO 3166-1 alpha-2 country code to localise results (`US`, `GB`, `DE`, `FR`, …) | `US` |
| **Max Results** | Maximum articles returned per request (1–50) | `10` |

---

## Available Tools

### `google_news_top_headlines`

Fetches the current top headlines from Google News.

**Parameters:** none

**Use when:** the user asks for today's news, latest headlines, what's happening in the world, or general current events.

---

### `google_news_search`

Searches Google News for articles matching specific keywords.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | ✅ | Keywords to search for. Supports multi-word queries and quoted phrases. |

**Examples:**
- *"Find news about the US election"*
- *"What's the latest on OpenAI?"*
- *"Search news for 'climate summit 2025'"*

---

### `google_news_by_topic`

Fetches news for a predefined Google News topic category.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `topic` | enum | ✅ | One of: `WORLD`, `NATION`, `BUSINESS`, `TECHNOLOGY`, `ENTERTAINMENT`, `SCIENCE`, `SPORTS`, `HEALTH` |

**Examples:**
- *"Show me technology news"*
- *"What's in sports news today?"*
- *"Give me health headlines"*

---

### `google_news_by_location`

Fetches news related to a specific geographic location.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `location` | string | ✅ | City, country, or region name |

**Examples:**
- *"News from Germany"*
- *"What's happening in Tokyo?"*
- *"Local news for New York"*

---

### `google_news_by_site`

Fetches the latest articles from a specific news publisher.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site` | string | ✅ | Publisher domain without `https://` (e.g. `bbc.com`, `reuters.com`) |

**Examples:**
- *"Get latest news from BBC"* → site: `bbc.com`
- *"Show me TechCrunch articles"* → site: `techcrunch.com`
- *"Reuters news"* → site: `reuters.com`

---

## Article Fields

Each article returned contains:

| Field | Description |
|-------|-------------|
| `title` | Headline |
| `description` | Article summary / snippet |
| `published_date` | Publication timestamp (RFC 2822 format) |
| `url` | Link to the full article |
| `publisher` | Publisher name (e.g. "BBC") |
| `publisher_url` | Publisher homepage URL |

---

## Notes

- Google News access is via public RSS feeds — no rate-limit guarantees apply. Occasional throttling by Google is possible under heavy use.
- The `gnews` package supports 141+ countries and 41+ languages.
- Full article text extraction is not included; use the `browse_url` tool to read a full article after fetching its URL.
