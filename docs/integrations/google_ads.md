# Google Ads Integration

This guide explains how to connect Open Assistant to the Google Ads API so the
assistant can manage campaigns, ad groups, keywords, and pull performance
reports on your behalf.

> **Google Ads is a separate integration from the regular Google (Gmail /
> Calendar / Drive) integration.** It uses its own OAuth 2.0 credentials,
> its own access token, and its own settings namespace (`google_ads.*`).
> You cannot share credentials between the two integrations.

---

## Prerequisites

- A Google account with access to at least one Google Ads account
- A Google Cloud project (can be new or existing — does **not** need to be the
  same project used for the regular Google integration)
- A Google Ads **Developer Token** (explained below)

---

## Step 1: Obtain a Google Ads Developer Token

The Developer Token is a **22-character alphanumeric string** that lets your app
connect to the Google Ads API. It is tied to your **Google Ads Manager Account**
(MCC), not to the individual advertising account.

1. Sign in to your [Google Ads Manager Account](https://ads.google.com/).
   If you do not have one, create one at
   <https://ads.google.com/home/tools/manager-accounts/>.
2. Navigate to the **API Center**:
   - Click the **tools icon (⚙)** in the top-right → **Setup** → **API Center**
   - Or go directly to <https://ads.google.com/aw/apicenter>
3. Apply for API access by filling out the form. You'll need:
   - A live company website
   - An actively monitored contact email
4. Your Developer Token will be shown on the API Center page after approval.

### Access Levels

| Level | Description |
|-------|-------------|
| **Explorer** | Default for new applications. Allows production API calls with daily limits. |
| **Test Account** | Only allows calls against [test accounts](https://developers.google.com/google-ads/api/docs/first-call/test-accounts) (no real spend). |
| **Basic** | Higher daily limits. Apply after your app is working. |
| **Standard** | Highest limits. For production apps with significant API usage. |

> **Note:** You can start testing immediately with Explorer access. Apply for
> Basic access when you're ready for production use.

---

## Step 2: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project picker at the top → **New Project**.
3. Give it a name (e.g. "Open Assistant Ads") and note the **Project ID**.

---

## Step 3: Enable the Google Ads API

1. In your Cloud project go to **APIs & Services → Library**.
2. Search for **Google Ads API** and click **Enable**.

---

## Step 4: Configure the OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**.
2. Choose **External** user type (unless your organisation uses Google
   Workspace and you want Internal-only access).
3. Fill in the required fields:
   - **App name**: e.g. "Open Assistant"
   - **User support email**: your email
   - **Developer contact email**: your email
4. Click **Save and Continue**.
5. On the **Scopes** step click **Add or Remove Scopes** and add:
   ```
   https://www.googleapis.com/auth/adwords
   ```
6. Click **Update** → **Save and Continue**.
7. Add yourself (and any other users who will authenticate) as **Test Users**
   while the app is in *Testing* mode.
8. Click **Save and Continue** → **Back to Dashboard**.

> **Publishing the app**: While in *Testing* mode only the listed test users
> can authenticate. To allow any Google account to connect, click
> **Publish App** on the OAuth consent screen page. Google may ask you to
> complete a verification process for sensitive scopes.

---

## Step 5: Create OAuth 2.0 Credentials

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth client ID**.
3. Set **Application type** to **Web application**.
4. Give it a name, e.g. "Open Assistant Ads Client".
5. Under **Authorised redirect URIs** add the appropriate URI for your deployment:

   **Self-hosted / local**
   ```
   http://localhost:8080/auth/google_ads/callback
   ```

   **Custom domain**
   ```
   https://yourdomain.com/auth/google_ads/callback
   ```

   **Managed (Open Assistant Platform)**  
   The redirect URI is derived automatically from `APP_URL`, which the platform
   already sets for your instance:
   ```
   {APP_URL}/auth/google_ads/callback
   ```
   Register that URL in the Google Cloud Console. No additional environment
   variable is needed — `APP_URL` is shared by all integrations.

   > `GOOGLE_ADS_REDIRECT_URI` exists as an optional override if you ever need
   > to point the callback at a different URL than `{APP_URL}/auth/google_ads/callback`,
   > but this is rarely (if ever) necessary.
6. Click **Create**.
7. Copy the **Client ID** and **Client Secret** that appear — you will enter
   these in Settings.

---

## Step 6: Find Your Customer ID

Each Google Ads advertising account has a unique 10-digit **Customer ID**
(formatted as `XXX-XXX-XXXX`). You will need this to tell the API which
account to operate on.

- In the Google Ads UI the Customer ID is shown in the top-right corner next
  to the account name.
- If you manage multiple accounts through a Manager Account (MCC), use the
  individual sub-account IDs for operations, and the Manager Account ID as the
  `login_customer_id`.

---

## Step 7: Configure in Open Assistant Settings

1. Open the Open Assistant web UI and go to **Settings → Integrations**.
2. Find the **Google Ads** card and enter:

   | Setting | Value |
   |---------|-------|
   | **Client ID** | The OAuth Client ID from Step 5 |
   | **Client Secret** | The OAuth Client Secret from Step 5 |
   | **Developer Token** | The token from Step 1 |
   | **Customer ID** | Your 10-digit advertising account ID (dashes optional) |
   | **Login Customer ID** *(optional)* | Your Manager Account (MCC) ID — only needed if authenticating via a manager account |
   | **Project ID** *(optional)* | Your Google Cloud Project ID |

3. Toggle **Enable Google Ads** to **ON**.
4. Click **Save**.

---

## Step 8: Authenticate (OAuth Flow)

After saving settings, you need to complete the OAuth flow once so Open
Assistant can obtain a refresh token.

### Via the Settings UI (recommended)

1. On the Google Ads settings card click **Connect / Authenticate**.
2. A popup (or redirect) opens the Google consent screen.
3. Sign in with the Google account that has access to your Ads account.
4. Grant the requested `Google Ads API` permission.
5. The popup closes automatically and the integration shows as **Connected**.

### Via a direct URL

Navigate your browser to:
```
http://localhost:8080/auth/google_ads/initiate
```
(POST request — use the Settings UI button instead for a browser-based flow.)

---

## Available Tools

Once authenticated, the following tools are available to the assistant:

| Tool | Description |
|------|-------------|
| `google_ads_get_account_info` | Account name, currency, time zone, status |
| `google_ads_list_campaigns` | List all (or filtered) campaigns |
| `google_ads_get_campaign` | Details for a single campaign |
| `google_ads_create_campaign` | Create a new campaign (starts PAUSED) |
| `google_ads_update_campaign_status` | Enable, pause, or remove a campaign |
| `google_ads_update_campaign_budget` | Change a campaign's daily budget |
| `google_ads_list_ad_groups` | List ad groups (optionally by campaign) |
| `google_ads_create_ad_group` | Create an ad group in a campaign |
| `google_ads_list_keywords` | List keywords (optionally by ad group) |
| `google_ads_add_keyword` | Add a keyword to an ad group |
| `google_ads_get_campaign_performance` | Impressions, clicks, cost, CTR, conversions |
| `google_ads_get_ad_group_performance` | Ad-group-level performance metrics |

---

## Example Chat Usage

```
You: What campaigns do I have running in Google Ads?
Assistant: [lists active campaigns with budget and status]

You: Pause the "Summer Sale" campaign
Assistant: [updates campaign status to PAUSED]

You: Show me the performance of all campaigns for the last 7 days
Assistant: [returns impressions, clicks, cost, CTR per campaign]

You: Create a new Search campaign called "Q4 Promo" with a $50 daily budget
     starting 20241101
Assistant: [creates campaign in PAUSED state, confirms details]
```

---

## Token Management

- The OAuth refresh token is stored **encrypted** in the database under the
  `google_ads` service name, completely separate from the regular Google token.
- The Google Ads Python library handles access-token renewal automatically
  using the stored refresh token — no manual re-authentication is needed until
  the refresh token is revoked.
- To disconnect, revoke access in your
  [Google Account security settings](https://myaccount.google.com/permissions)
  and delete the stored token via Settings → Google Ads → Disconnect.

---

## Troubleshooting

### `DEVELOPER_TOKEN_NOT_APPROVED`
Your Developer Token has not been approved for access to live accounts. Either
use a [test account](https://developers.google.com/google-ads/api/docs/first-call/test-accounts)
or apply for Basic access at the API Center page of your Manager Account.

### `CUSTOMER_NOT_FOUND` / `403 Forbidden`
- Verify the Customer ID is correct (10 digits, dashes optional).
- If authenticating via a Manager Account, set `login_customer_id` to the MCC
  ID and `customer_id` to the sub-account ID.
- Make sure the authenticated Google account has access to the target account.

### `invalid_grant` on OAuth
The refresh token has been revoked or expired. Re-authenticate via Settings →
Google Ads → Connect.

### `Google Ads OAuth credentials not configured`
The `google_ads.client_id` and/or `google_ads.client_secret` settings are
missing. Complete Step 7 above. Note that the Google Ads integration does
**not** share credentials with the regular Google integration.

### `Google Ads developer token not configured`
Add `google_ads.developer_token` in Settings (Step 7).

---

## Rate Limits

| Resource | Limit |
|----------|-------|
| Operations per mutate request | 2,000 |
| Rows per GAQL response page | 10,000 |
| Daily API units | Varies by access level (Basic: higher limits) |

See the
[Google Ads API quotas page](https://developers.google.com/google-ads/api/docs/best-practices/quotas)
for current limits.

---

## API References

- [Google Ads API Documentation](https://developers.google.com/google-ads/api/docs/start)
- [GAQL Query Language](https://developers.google.com/google-ads/api/docs/query/overview)
- [google-ads-python library](https://github.com/googleads/google-ads-python)
- [API Center (Developer Token)](https://ads.google.com/aw/apicenter)
- [OAuth 2.0 for Web Server Apps](https://developers.google.com/identity/protocols/oauth2/web-server)

> **API Version:** This integration uses Google Ads API v20. The client library
> will be updated periodically to support newer API versions.

## Related Documentation

- [Google Integration](./google.md) — Gmail, Calendar, Drive (separate credentials)
- [Configuration Guide](../setup/configuration.md)
