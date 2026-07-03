# Capabilities

### Web Search

Web search capability using Brave Search API (privacy-focused, free tier available).

**How it works**:
- Research Agent has access to web search tools
- Search results include titles, snippets, and URLs
- Results are cited for factuality

### Web Browsing

Interactive web browsing using Playwright with an accessibility-tree-based page understanding.

**Why accessibility trees?**
- More reliable than XPath/CSS selectors which break on site changes
- Works on JavaScript-heavy sites via Playwright's accessibility snapshot API
- Captures semantic structure (roles, names, values) for precise interaction
- Click targets use `role` + `name` references rather than fragile selectors

**Browser Agent capabilities**:
- Navigate to URLs and extract content
- Click, type, scroll interactions
- Form filling and multi-step workflows
- Accessibility tree extraction (interactive, forms, or full modes)
- Screenshot capture for vision fallback

### Cron Job Scheduling

Recurring task scheduling with APScheduler running within the main process.

**Job types**:
- **Tool Jobs**: Execute a specific tool with fixed parameters
- **Prompt Jobs**: Send a prompt to the coordinator for complex reasoning

**Features**:
- Cron expressions for flexible scheduling
- Enable/disable jobs without deletion
- Execution history tracking
- Run immediately option

### Artifact Store

Durable file storage for generated artifacts (HTML pages, PDFs, DOCX, images, Python outputs) with public/private visibility, signed temporary links, and an optional passphrase gate.

**How it works**:
- The coordinator agent calls `store_artifact` with a `source_path` (e.g. a file path returned by `create_html` or `python_execute`) to persist it into `data/artifacts/<uuid>/<filename>`
- Artifacts survive the nightly temp-dir cleanup because they live under `data/`, not `tmp/`
- Each artifact can be individually deleted by the user from the Artifacts tab

**Visibility and sharing**:
- **Private** (default): only accessible via a 300s signed temporary link (`?token=<HS256 JWT>`)
- **Public**: gets a stable permanent link at `/api/artifacts/{id}/view` — no token required

**Passphrase gate** (optional per artifact):
- Owner sets a passphrase via the Artifacts tab; it is hashed with PBKDF2-SHA256 (200k iterations) and never stored in plaintext
- Unauthenticated visitors see a branded gate page prompting for the passphrase
- On success an httpOnly `SameSite=Lax` cookie (`oa_artifact_{id}`, 1h TTL) is set; subsequent views skip the prompt
- Owner can change or remove the passphrase at any time; the API only exposes `has_secret: bool`

**Artifacts tab** (`/artifacts`):
- Table view: Name, Type, Size, Visibility badge, Created date
- Per-row actions: View, Copy link (permanent or 5-min temp), Make public/private, Set/Change/Remove passphrase, Delete

**`store_artifact` tool**:
- System tool assigned to the coordinator agent by default (always available, no integration toggle needed)
- Parameters: `source_path` (required), `title` (optional), `make_public` (default: false)
- Returns: artifact ID, management URL, and permanent link (if public)

### Future Task Scheduling

One-time task scheduling for future execution.

**Use cases**:
- Reminders ("Remind me tomorrow at 3pm")
- Scheduled actions ("Send this email Monday morning")
- Deferred tasks ("Check my calendar tomorrow at 8am")

### Monitoring UI

Web-based monitoring dashboard with:

**System tab**:
- Health checks (database, LLM API, disk space)
- Performance metrics
- System logs viewer
- Service connection status

**Jobs tab**:
- Cron job management with enable/disable
- Future task management
- Execution history with status and duration

### Unified Search

Single search interface across all integrated data sources.

**Concept**:
- Keyword search using each service's native API
- Semantic search using local embeddings (cosine similarity threshold: 0.3)
- Results merged with Reciprocal Rank Fusion (k=60)
- Automatic index updates (opportunistic + on-demand rebuild)

**Tools**:
- `unified_search` - Search across all sources with hybrid keyword + semantic matching
- `reindex_search` - Rebuild the semantic index from connected sources

**Parameters**:
- `query`: Search query string (required)
- `sources`: Filter by source (optional) — `notion`, `gmail`, `outlook_email`, `outlook_files`, `onenote`, `nextcloud`, `memory`
- `search_type`: `hybrid` (default), `keyword` (API-only), or `semantic` (embedding-only)
- `limit`: Maximum results per source (default: 10, max: 50)

**Sources**:
- **Notion** — Pages and databases via Notion API
- **Gmail** — Emails via Google Gmail API
- **Outlook Email** — Emails via Microsoft Graph API
- **Outlook Files** — OneDrive files via Microsoft Graph API (text extraction for .txt, .md, .docx, .pdf, etc.)
- **OneNote** — Pages via Microsoft Graph API
- **Nextcloud** — Files via WebDAV (text extraction for common formats)
- **Memory** — Assistant's long-term facts indexed via `system_index_memory_facts`

**Index Behavior**:
- Hybrid/semantic searches trigger automatic background reindex if index is empty
- Keyword search results are opportunistically embedded in the background after each search
- Semantic search requires LLM provider with embedding support

---

## Related Documentation

- [Agent Architecture](agents.md) - Multi-agent system design
- [Software Architecture](software-architecture.md) - System design
- [Database Schema](database-schema.md) - Data models
