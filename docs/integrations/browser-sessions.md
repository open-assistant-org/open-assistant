# Authenticated Sessions (Manual)

A step-by-step guide to letting the [browser integration](browser.md) use your own logged-in
accounts, such as a webmail, a dashboard or an intranet, **without** the AI ever seeing your
password or cookies.

!!! info "How the secret stays separate from the AI"
    You hand Open Assistant a cookie export once. It is stored **encrypted** in the database and
    loaded into the browser by the runtime, behind the scenes. The AI only learns *that* a login is
    active (for example `authenticated_session: "Personal Gmail"`), never the cookie values, and it is
    told never to ask you for a password. Details: [Session Security & Troubleshooting](browser-sessions-security.md).

## When to use this (and when not to)

| Use saved sessions when… | Prefer something else when… |
|---|---|
| The site has **no API** or integration you can use | Open Assistant already has a native integration (Gmail/Calendar → [Google](google.md), Outlook → [Microsoft](microsoft.md), [Notion](notion.md), [Nextcloud](nextcloud.md)). They use proper, revocable OAuth/API credentials |
| You want the assistant to **read** pages behind a login (orders, dashboards, tickets) | The site offers an API key or app password: use a [plugin](../plugin-schema.md) instead |
| It is **your own** account, on your own instance | The account is high-stakes (banking, primary email, admin consoles): if you do use it, keep the profile **disabled** except while a task needs it |

A saved session is a *bearer credential*: whoever holds it **is** you on that site. Treat it like a password.

## Before you start

- [ ] **The Browser integration is on.** In **Settings → Integrations**, the Browser card's switch must be on.
  On a fresh install it can *display* as on (the default) before a value is stored. If browse tools answer
  "Browser integration is not enabled", switch it **off and on once**.
- [ ] `ENCRYPTION_KEY` is set and backed up (the installer does this). Saved sessions are encrypted with it, and
  changing it makes them unreadable: see [Encryption key](../setup/install-and-update.md#encryption-key).
- [ ] Open Assistant is not exposed to the internet without authentication (the settings API has no login of its
  own). See [Operational guidance](browser-sessions-security.md#operational-guidance).

---

## Step 1: Capture your login

Log in to the site **in a normal browser first** (including any 2FA), then export its cookies with **one**
of the methods below. Prefer **Method B** if the site is a single-page app (Gmail-style web apps, dashboards):
it also captures `localStorage`, which these apps often use for their auth tokens.

=== "A. Cookie-Editor (quickest)"

    1. Install the **Cookie-Editor** extension for Chrome, Edge or Firefox.
    2. Open the site you are logged in to and click the Cookie-Editor icon.
    3. Click **Export → JSON**. The cookies for the current site are copied to your clipboard.
    4. Paste them into Open Assistant in [Step 2](#step-2-add-it-in-open-assistant) (format **Cookie-Editor / browser extension (JSON)**, or leave it on Auto-detect).

    !!! tip
        Cookie-Editor exports only the site in the active tab, which is what you want: it keeps the
        saved session narrow. If the login spans several domains (for example `example.com` and
        `accounts.example.com`), export from each and add them as separate sessions or merge the arrays.

=== "B. Playwright capture (most reliable)"

    Saves cookies **and** `localStorage` from a real, headed browser window. Requires Python 3 on your own computer.

    ```bash
    pip install playwright
    playwright install chromium
    ```

    ```python title="capture_session.py"
    import sys
    from playwright.sync_api import sync_playwright

    url = sys.argv[1]  # e.g. https://mail.example.com

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        input("Log in in the browser window (including any 2FA), then press Enter here... ")
        context.storage_state(path="state.json")
        print("User-Agent used:", page.evaluate("navigator.userAgent"))
        print("Saved state.json - paste its contents into Open Assistant, then delete the file.")
        browser.close()
    ```

    ```bash
    python capture_session.py https://mail.example.com
    ```

    Paste the contents of `state.json` in [Step 2](#step-2-add-it-in-open-assistant) (format **Playwright storage_state**).
    **Delete `state.json` afterwards.** It is an unencrypted copy of your login. The script also prints the
    User-Agent it used; see [Matching your browser's User-Agent](#matching-your-browsers-user-agent).

=== "C. cookies.txt"

    1. Install a *"Get cookies.txt LOCALLY"*-style extension and export the current site as `cookies.txt` (Netscape format).
    2. Open the file in a text editor, copy everything, and paste it in Step 2 (format **cookies.txt (Netscape)**), or use the file picker.

    Command-line tools such as `yt-dlp --cookies-from-browser chrome --cookies cookies.txt` can also write this
    format, but they may export cookies for **all** sites. Trim the file to the domains you need before importing.

=== "D. Raw Cookie header (quick test only)"

    1. In your browser, open DevTools → **Network**, reload the page and click the main request.
    2. Under **Request Headers**, copy the value of `Cookie:`.
    3. In Step 2 choose format **Raw "Cookie:" header** and also enter the site's **Domain** (for example `example.com`).

    A header carries no expiry or flags, so it is imported as a session cookie. Use it to try things out, not for a long-lived login.

---

## Step 2: Add it in Open Assistant

1. Open **Settings → Integrations** and expand the **Browser** card.
2. Scroll to **🔐 Authenticated sessions** and click **➕ Add a session**.
3. Fill in the form:

    | Field | What to enter |
    |---|---|
    | **Name** | A label you will recognise, such as `Personal Gmail` or `Work dashboard`. Unique, up to 64 characters. The AI sees this name |
    | **Format** | Leave on **Auto-detect**, or pick the format you exported |
    | **Domain** | Only for the raw `Cookie:` header format |
    | **Cookie export** | Paste the export, **or** use *Choose file* to load a `.json`/`.txt` file (max 2 MB) |
    | **Keep refreshed** | On by default. Saves cookies the site renews while the browser is in use, so the login lasts longer. Untick for a read-only profile |

4. Click **💾 Save session**.

You will see a confirmation such as *Saved "Personal Gmail": 14 cookies for example.com*, plus
warnings if the importer adjusted anything (see [import fixes](browser.md#supported-import-formats)). The paste box is
**cleared** and the values are never shown again. The list shows only the name, domains, cookie count and an expiry badge.

!!! warning "If the import fails"
    A red message such as *Could not parse cookie export…* means nothing was saved. Pick the format
    explicitly, check that the export is complete (not cut off), and try again. The message never contains cookie values.

---

## Step 3: Check that it works

Click **🔍 Test** on the session's row, enter a page that **requires** the login (for example your
inbox URL), and press OK. Open Assistant opens it in a throwaway browser that carries *only* this session
and tells you where the site landed:

| Result | Meaning | What to do |
|---|---|---|
| ✅ *Loaded "Inbox (3)" at https://mail.example.com/inbox. Check that it is the logged-in view.* | The site accepted the cookies | You're done |
| ⚠️ *Landed on a login page (…). The session has probably expired* | The site bounced you to its login form | Re-export and **Replace** the session; if it happens again immediately, see [troubleshooting](browser-sessions-security.md#troubleshooting) |
| ❌ *Could not load the page: …* | Network error, bad URL or the browser is unavailable | Check the URL and the [error table](browser.md#error-handling) |

The test never saves cookies and never returns page content or cookie data. A **disabled** session can still be tested.

---

## Step 4: Use it in chat

Just ask, and name the site or URL. You do not need to mention the session: enabled sessions are loaded
automatically, and a session is only used on pages whose domain it covers.

> *"Open https://mail.example.com/inbox and list the senders and subjects of my 5 newest unread emails."*
>
> *"Go to https://shop.example.com/orders and tell me the status of my latest order."*
>
> *"Check my open tickets on https://support.example.com and summarise anything marked urgent."*

In the tool results the AI sees something like `authenticated_session: "Personal Gmail"` and
*"Using saved session 'Personal Gmail' (already logged in; do not try to log in)."* If the site shows a
login page anyway, the result says the session has probably expired, and the assistant stops and asks you to refresh it
instead of trying to log in.

!!! tip "Be specific, and prefer read-only tasks"
    Say exactly what you want done. For anything irreversible (sending, buying, deleting, changing settings) the
    browser agent is instructed to ask you to confirm first. Pages on a logged-in site are treated as untrusted, so text
    inside an email or comment cannot give the assistant new orders.

---

## Keeping a session alive

- **Keep refreshed** (per session) saves cookies the site renews, right after the assistant opens a page or clicks
  something and again when the browser session closes, which extends the life of most logins automatically. If nothing
  was renewed, nothing is written (so the session's *updated* time only changes when something actually rotated).
- Watch the **expiry badge**: green (valid), amber (**< 7 days left**: re-import soon), red (**expired**),
  grey (session cookies: valid until the site ends the session).
- To refresh a login by hand: capture a new export ([Step 1](#step-1-capture-your-login)), click **♻️ Replace** on the session,
  paste it and click **♻️ Replace cookies**. The name and settings are kept.
- If you **replace** a session while the browser is mid-task, your fresh import is protected: the older browser
  session will not overwrite it when it closes.

## Matching your browser's User-Agent

Some sites tie a login to the browser that created it and reject the cookies from a different User-Agent. If a
session logs you out straight away:

1. In the browser you exported from, open the console and run `navigator.userAgent` (Method B prints it for you).
2. In **Settings → Integrations → Browser**, paste it into **User Agent** and click **💾 Save Settings**.
3. **Test** the session again.

Leave **User Agent** empty to use the built-in Chrome user agent. It applies to the interactive browser
tools (not to `browse_fetch`).

## Several accounts on the same site

Cookies are matched by domain, so two **enabled** sessions for the same site would be merged, and for any
cookie they share the **newer session wins**. Keep one session enabled per site at a time. Untick **Enabled** on
the others and switch when you need a different account.

## Removing access

1. Click **🗑️ Delete** on the session (or untick **Enabled** to pause it without deleting).
2. **Also end the login on the website** (sign out of all devices, or revoke the session in the site's security
   settings). Deleting the cookies here does not invalidate them on the server, and an exported copy (for example
   `state.json`) would still work until the site expires it.

## Automating the import (optional)

The same import is available over the API, which is handy for scripted setups:

```bash
jq -n --arg name "Personal Gmail" --rawfile payload state.json \
   '{name: $name, payload: $payload, format: "playwright"}' \
 | curl -sS -X POST http://localhost:8080/api/browser/sessions \
        -H 'content-type: application/json' -d @-
```

See the [API reference](browser.md#saved-login-endpoints). Responses never contain cookie values.

## Quick reference

| I want to… | Do this |
|---|---|
| Add a login | Browser card → **➕ Add a session** → **💾 Save session** |
| Check a login still works | **🔍 Test** |
| Refresh an expiring login | **♻️ Replace** with a new export |
| Pause a login | Untick **Enabled** |
| Stop saving renewed cookies | Untick **Keep refreshed** |
| Fix "logged out immediately" | Set **User Agent**, then re-test; see [troubleshooting](browser-sessions-security.md#troubleshooting) |
| Remove a login completely | **🗑️ Delete**, then sign out on the website |
