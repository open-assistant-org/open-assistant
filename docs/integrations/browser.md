# Browser Integration

The browser integration provides two complementary approaches for web interaction:

| Approach | Tool | Use Case |
|----------|------|----------|
| **Interactive Browsing** | `browse_url`, `browse_click`, etc. | Click, type, scroll, interact with pages |
| **Content Fetching** | `browse_fetch` | Fast content extraction with anti-bot bypass |
| **Authenticated Sessions** | *(used automatically)* | Browse your own logged-in accounts using cookies you save, without the AI ever seeing them |

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

## Authenticated Sessions (Saved Logins)

Give the browser access to your own accounts (a webmail, a dashboard, an intranet) by saving a
logged-in session. You paste or upload a cookie export in **Settings → Integrations → Browser →
Authenticated sessions**; Open Assistant stores it encrypted and loads it into the browser behind
the scenes. As with every integration, the runtime and the LLM are kept apart from the secret:

| | The AI / LLM | Open Assistant runtime |
|---|---|---|
| Cookie values | **Never sees them** (not in prompts, tool results, logs or the audit log) | Decrypts them only to hand to the browser |
| Which login is active | Sees the profile *name* only, e.g. `authenticated_session: "Personal Gmail"` | Matches profiles to pages by domain |
| Logging in | Told not to try, and never to ask you for a password | You do it once, in your own browser |

> **Step-by-step instructions:** see the manual, [Authenticated Sessions](browser-sessions.md), and
> [Session Security & Troubleshooting](browser-sessions-security.md).

### How it works

1. Each saved login is a **profile** (a name plus cookies and, optionally, `localStorage`). All profiles
   are stored in one Fernet-encrypted row of `service_credentials` (`service_name = browser_sessions`,
   `credential_type = cookie_jar`) using the same `ENCRYPTION_KEY` as every other credential.
2. When the interactive browser starts, all **enabled** profiles are merged and loaded with Playwright's
   `storage_state`, so the browser is already signed in. Expired cookies are skipped.
3. `browse_fetch` gets the cookies that match the target URL (domain, path and `Secure`), in all three
   modes. Cookies are never sent to unrelated domains.
4. Tool results gain an `authenticated_session` field and a one-line note ("Using saved session
   '…'"). If the site bounces back to a login page the result carries `session_expired_suspected` instead,
   and the agent tells you to refresh the session rather than trying to log in.
5. **Keep refreshed** (on by default, per profile): sites rotate session cookies. After `browse_url` and
   `browse_action` (and again when the browser session closes), cookies the site renewed for that profile's
   *existing* domains are re-encrypted and saved, so the login lasts longer. Nothing is written when nothing
   changed, and new domains are never added. Turn it off for a read-only profile. If you **Replace** a profile
   while a browser session is still open, your fresh import is protected from being overwritten by that older session.

The browser session itself closes when you call `browse_url` again (it starts fresh), after
5 idle minutes on the next browser call, or when Open Assistant shuts down.

### Supported import formats

Pick **Auto-detect** or choose a format explicitly. Everything is normalized to Playwright's shape.

| Format | Typical source | Notes |
|---|---|---|
| **Playwright `storage_state`** (JSON object with `cookies` and `origins`) | A Playwright login capture | **Recommended**: also carries `localStorage`, which many single-page apps use for auth tokens |
| **Cookie-Editor / extension JSON** (array of cookies) | Cookie-Editor, EditThisCookie and similar | `expirationDate`, `hostOnly`, `sameSite: no_restriction/lax/strict/unspecified` are translated |
| **`cookies.txt`** (Netscape) | "Get cookies.txt LOCALLY", `yt-dlp --cookies-from-browser` | `#HttpOnly_` lines are honored |
| **Raw `Cookie:` header** | DevTools → Network → request headers | Needs a **domain**; no expiry or flags, so treated as a session cookie. Quick tests only |

The importer fixes combinations Chromium would reject, and tells you when it does:

- `SameSite=None` cookies are forced to `Secure`.
- `__Host-` cookies become host-only, `Secure`, `path=/`; `__Secure-` cookies become `Secure`.
- Already-expired cookies are dropped (and counted in the warning).
- Millisecond expiry timestamps are converted to seconds.
- Malformed entries and duplicates are skipped; the import fails only if nothing usable remains.

### Managing sessions

Each row in the UI shows the profile name, its domains, the cookie count and an expiry badge:

| Badge | Meaning |
|---|---|
| Green: *Valid until …* | The longest-lived cookie is still valid |
| Amber: *Expires in N d* | Within 7 days: plan to re-import |
| Red: *Expired* | Every dated cookie has expired: **Replace** it |
| Grey: *Session cookies* | No expiry set; valid until the site ends the session |

Controls: **Enabled** (load it or not), **Keep refreshed**, **Test** (opens a page you choose in a
throwaway browser with only this login and reports whether the site bounced you to a login page),
**Replace** (swap in a fresh export) and **Delete**.

### Matching your browser's User-Agent

Some sites bind a login to the User-Agent (and sometimes the IP address) it was created with. If a
session logs you out immediately, set **User Agent** (`browser.user_agent`) to the exact
`navigator.userAgent` of the browser you exported from. Leave it empty for the built-in Chrome UA.

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
| `browser.user_agent` | string | *(empty)* | Override the interactive browser's User-Agent (empty = built-in Chrome UA). Match it to the browser you exported saved-session cookies from |

Saved logins are **not** a setting: they live in their own encrypted store and are managed through
`/api/browser/sessions` (see [API Endpoint](#api-endpoint)).

## Architecture

```
src/integrations/browser/
├── driver.py          # Playwright browser management (interactive)
├── fetcher.py         # Scrapling content fetcher (+ per-URL session cookies)
├── sessions.py        # Saved logins: cookie-export parser, encrypted profile store, write-back
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
- **Saved logins**: enabled session profiles are injected into the browser context at start (`storage_state`), and rotated cookies are saved back when it closes
- **URL scheme allow-list**: only `http://` and `https://` URLs can be opened (`javascript:`, `file:`, `chrome:` and the like are rejected)
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
2. **Logins are not remembered automatically**: the browser starts fresh each time. To stay signed in to a site, save its session under [Authenticated Sessions](#authenticated-sessions-saved-logins). Saved sessions still expire when the site says so, and sites that bind a login to IP address, device or User-Agent may reject them (see the [troubleshooting guide](browser-sessions-security.md#troubleshooting))
3. **Text truncation**: Extracted text limited to ~10,000 characters
4. **Headless only in Docker**: GUI mode requires X11 forwarding
5. **Session timeout**: 5 minutes idle closes the browser

## Error Handling

| Error | Solution |
|-------|----------|
| "Browser integration is not enabled" | Set `browser.enabled = true`. On a fresh install the toggle can show *on* (the default) before a value is stored; switch the Browser toggle **off and on once** in Settings → Integrations |
| "Playwright browser not installed" | Run `playwright install chromium` |
| "Page load timeout" | Check URL accessibility; try different `wait_until` |
| Scrapling stealth mode fails | Ensure Camoufox installed: `pip install scrapling[camoufox]` |
| Result has `session_expired_suspected`, or **Test** says "login page" | The saved session expired or was revoked: **Replace** it with a fresh export |
| `422 Could not parse cookie export` | The export is empty, truncated, or in an unexpected format: pick the format explicitly. The message never includes cookie values |
| Import warning "SameSite=None cookie(s) forced to Secure" | Informational: Chromium requires `Secure` for `SameSite=None`, so it was set for you |
| `Only absolute http:// and https:// URLs can be opened` | A tool was given a `javascript:`, `file:`, relative or other non-web URL |

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

### Saved login endpoints

All are **write-only**: responses contain names, domains, counts and expiry, never cookie names or values.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/browser/sessions` | List profiles (metadata only) |
| `POST` | `/api/browser/sessions` | Create a profile from `{name, payload, format?, domain?, persist_updates?}`. Returns the profile and any import `warnings`. `422` if the export can't be parsed, `409` if the name is taken |
| `PATCH` | `/api/browser/sessions/{id}` | Rename, enable/disable, toggle `persist_updates`, or replace the cookies by sending a new `payload` |
| `DELETE` | `/api/browser/sessions/{id}` | Delete a profile |
| `POST` | `/api/browser/sessions/{id}/test` | Body `{url}`. Opens it in a throwaway browser with only this profile and returns `{final_url, title, redirected_to_login}`. Never writes cookies back |

Every create/update/delete is recorded in the audit log with the cookie values masked as `***MASKED***`.

## Security Considerations

1. Run headless in production
2. Browser can access internal networks—firewall appropriately
3. Validate user-provided URLs
4. Monitor memory usage in production
5. **Saved logins are credentials.** Anyone who can read the database *and* `ENCRYPTION_KEY` can use them: protect both, and keep backups encrypted
6. The settings and browser APIs have no authentication of their own, so keep Open Assistant behind your reverse proxy, VPN or SSO. See [Session Security & Troubleshooting](browser-sessions-security.md)
7. **Prompt injection:** a web page, email or comment on a site you are logged in to can contain text that tries to steer the AI (for example "forward this message"). The browser agent is instructed to ignore such text and to confirm irreversible actions, but the safest defence is to enable only the sessions a task needs and prefer read-only tasks
8. Deleting a saved login here does not log it out on the website: also sign out or end the session in the site's security settings
