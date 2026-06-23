# Browser Integration

The browser integration provides two complementary approaches for web interaction:

| Approach | Tool | Use Case |
|----------|------|----------|
| **Interactive Browsing** | `browse_url`, `browse_click`, etc. | Click, type, scroll, interact with pages |
| **Content Fetching** | `browse_fetch` | Fast content extraction with anti-bot bypass |

## Interactive Browsing (Playwright)

Full browser automation for tasks requiring interaction. Uses Playwright with Chromium and accessibility-tree-based page understanding.

### Available Tools

| Tool | Description |
|------|-------------|
| `browse_url` | Navigate to URL, get screenshot + accessibility tree with `[ref=N]` element markers. Supports `wait_until` parameter (default: `domcontentloaded`) |
| `browse_get_tree` | Get current page's accessibility tree (elements marked with clickable refs). Supports `mode` filter: `interactive` (default, clickable elements), `full` (all elements), `forms` (form fields only) |
| `browse_action` | Execute action on element by ref ID: `click`, `type`, `focus`, `check`, `uncheck` |
| `browse_scroll` | Scroll page up/down |
| `browse_extract` | Extract all visible text from current page |

### Workflow

```
1. browse_url(url)         → Navigate, get page structure with [ref=N] markers
2. browse_get_tree(mode)   → Optional: get filtered tree (interactive/forms/full)
3. browse_action(ref, ...) → Click, type, or interact with elements
4. browse_extract()        → Get text content when done
```

### Example

```python
# Navigate and get page structure
result = browse_url("https://example.com/login")
# Response includes accessibility tree with [ref=1], [ref=2], etc.

# Click login button (ref from tree)
browse_action(ref_id=5, action="click")

# Type in form field
browse_action(ref_id=3, action="type", value="username")

# Extract results
text = browse_extract()
```

## Content Fetching (Scrapling)

Optimized for content extraction with anti-bot bypass. No browser interaction—just fetch and extract.

### Tool: `browse_fetch`

**Parameters**:
- `url` (required): URL to fetch
- `mode` (optional): `http`, `stealth`, or `dynamic` (default: `http`)
- `selector` (optional): CSS selector for targeted extraction
- `wait_for` (optional): CSS selector to wait for (dynamic mode only)

**Modes**:

| Mode | Backend | Best For |
|------|---------|----------|
| `http` | TLS fingerprint impersonation | Static pages, APIs (fastest) |
| `stealth` | Camoufox browser | Cloudflare-protected sites |
| `dynamic` | Playwright with anti-detection | JS-heavy SPAs |

**Returns**: `url`, `title`, `text`, `status`, `selected_content`, `message`

### Examples

```python
# Simple fetch (static page)
browse_fetch("https://example.com/article")

# Cloudflare-protected site
browse_fetch("https://protected-site.com", mode="stealth")

# JS-rendered content
browse_fetch("https://spa-app.com", mode="dynamic", wait_for=".content")

# Extract specific elements
browse_fetch("https://news.site.com", selector="article .headline")
```

## When to Use Which

| Task | Tool |
|------|------|
| Read a URL's content | `browse_fetch` (faster) or `browse_url` (includes structure) |
| Click buttons, fill forms | `browse_url` + `browse_action` |
| Cloudflare-protected content | `browse_fetch(mode="stealth")` |
| JS-heavy SPA content | `browse_fetch(mode="dynamic")` |
| Extract specific elements | `browse_fetch(selector="...")` |

## Configuration

Settings are in the `browser` category:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `browser.enabled` | bool | `true` | Enable browser integration |
| `browser.headless` | bool | `true` | Run browser in headless mode |
| `browser.viewport_width` | int | `1280` | Viewport width in pixels |
| `browser.viewport_height` | int | `720` | Viewport height in pixels |
| `browser.screenshot_quality` | int | `85` | JPEG quality (0-100) |
| `browser.scrapling_default_mode` | string | `http` | Default `browse_fetch` mode |
| `browser.scrapling_timeout` | int | `30` | Scrapling timeout in seconds |

## Architecture

```
src/integrations/browser/
├── driver.py          # Playwright browser management (interactive)
├── fetcher.py         # Scrapling content fetcher
├── screenshots.py     # Screenshot capture
└── accessibility.py   # Accessibility tree building

src/services/
└── browser.py         # BrowserService with all tools
```

### Browser Session (Interactive)

- **Lazy initialization**: Launches on first use
- **Session reuse**: Single instance reused across requests
- **Idle timeout**: 5 minutes (auto-closes)
- **Viewport**: 1280x720 (configurable)
- **Cookie consent auto-dismissal**: Automatically detects and dismisses cookie consent banners on every navigation
- **Sparse tree retry**: If the accessibility tree returns fewer than 5 elements, `browse_url` automatically waits 3 seconds, retries cookie dismissal, then reloads with `networkidle` for a second attempt — useful for JS-heavy SPAs and consent overlays

## Docker Setup

The Docker image includes all required browsers:

```dockerfile
# Playwright Chromium
RUN playwright install chromium

# Scrapling Camoufox (for stealth mode)
RUN python -c "import scrapling; scrapling.StealthyFetcher.setup()"
```

Environment variables:
- `PLAYWRIGHT_BROWSERS_PATH`: Override Chromium location

## Limitations

1. **Single session**: One browser instance per application
2. **No cookie persistence**: Sessions don't persist between restarts
3. **Text truncation**: Extracted text limited to ~10,000 characters
4. **Headless only in Docker**: GUI mode requires X11 forwarding
5. **Session timeout**: 5 minutes idle closes the browser

## Error Handling

| Error | Solution |
|-------|----------|
| "Browser integration is not enabled" | Set `browser.enabled = true` |
| "Playwright browser not installed" | Run `playwright install chromium` |
| "Page load timeout" | Check URL accessibility; try different `wait_until` |
| Scrapling stealth mode fails | Ensure Camoufox installed: `pip install scrapling[camoufox]` |

## API Endpoint

Test browser connectivity:

```bash
POST /api/browser/test-connection
```

Returns:
```json
{
  "service_name": "browser",
  "status": "success",
  "message": "Browser launched and navigated successfully"
}
```

## Security Considerations

1. Run headless in production
2. Browser can access internal networks—firewall appropriately
3. Validate user-provided URLs
4. Monitor memory usage in production
