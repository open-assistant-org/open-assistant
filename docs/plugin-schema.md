# Plugin Schema — Open Assistant

Plugins are JSON files that define lightweight REST API integrations. Each plugin's endpoints become LLM tools that are injected into context at runtime.

**Built-in plugins** live in `src/plugins/builtins/`. **User-installed plugins** are stored in `data/plugins/` and can be added through the Settings → Plugins tab.

---

## Quick Start

```json
{
  "id": "my_service",
  "display_name": "My Service",
  "description": "Short description of what this integrates with.",
  "icon": "🔧",
  "base_url": "https://api.myservice.com/v1",
  "auth": { "type": "bearer" },
  "config_fields": [],
  "endpoints": [
    {
      "name": "list_items",
      "display_name": "List Items",
      "description": "Retrieve a list of items from My Service.",
      "method": "GET",
      "path": "/items",
      "parameters": [
        {
          "name": "limit",
          "in": "query",
          "type": "integer",
          "description": "Maximum number of results.",
          "required": false
        }
      ]
    }
  ]
}
```

---

## Full Schema Reference

### Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | ✅ | Unique identifier — must start with a letter, then lowercase letters, digits, underscores. Used as tool name prefix: `plugin_{id}_{endpoint}`. |
| `display_name` | string | ✅ | Human-readable name shown in the UI. |
| `description` | string | ✅ | Short description of the integration. |
| `icon` | string | | Emoji displayed next to the plugin name. Default: `🔌` |
| `base_url` | string (URI) | ✅ | Base URL for all API calls. Supports `{config_field}` substitution. |
| `auth` | object | ✅ | Authentication configuration. See below. |
| `config_fields` | array | | Non-credential fields (e.g. org name, site URL). See below. |
| `endpoints` | array (min 1) | ✅ | List of API endpoints exposed as tools. See below. |

---

### `auth` object

| Field | Type | Description |
|---|---|---|
| `type` | `"bearer"` \| `"header"` \| `"basic"` \| `"api_key_with_jwt"` | Auth mechanism. |
| `header_name` | string | Required when `type = "header"`. The HTTP header name (e.g. `X-API-Key`). |
| `fixed_password` | string | Optional, `type = "basic"` only. Hardcodes the password — the user only provides a token/username. Example: Toggl uses `"api_token"`. |
| `api_key_header` | string | `type = "api_key_with_jwt"` only. **Optional.** Header name for the static API key (e.g. `"X-apikey"`). Omit for pure JWT login flows. |
| `token_endpoint` | string | `type = "api_key_with_jwt"` only. Path to POST credentials to (default: `"/token"`). |
| `token_field` | string | `type = "api_key_with_jwt"` only. JSON field in the login response containing the JWT (default: `"access_token"`). |
| `token_prefix` | string | `type = "api_key_with_jwt"` only. Prefix for the `Authorization` header value (default: `"Bearer"`). |

**`bearer`** — Sends `Authorization: Bearer {token}`. User provides one secret field (token).

**`header`** — Sends `{header_name}: {token}`. User provides one secret field (token).

**`basic`** — Sends `Authorization: Basic base64(username:password)`. User provides username + password. If `fixed_password` is set, only a single token field is shown.

**`api_key_with_jwt`** — For APIs that use a username + password login to obtain a short-lived JWT. Covers two patterns:

- **JWT login only** (omit `api_key_header`): POSTs `{"username": ..., "password": ...}` to `{token_endpoint}`, then attaches `Authorization: {token_prefix} {jwt}` to every API call. User provides **Username** and **Password**.
- **JWT login + static API key** (set `api_key_header`): same as above, but also sends `{api_key_header}: {api_key}` on both the login request and every API call. User provides **API Key**, **Username**, and **Password**.

In both cases the JWT is cached (TTL from the `exp` claim; defaults to 55 minutes) and refreshed automatically before expiry. If the server rejects a request with a 401 (e.g. the token was revoked early or there is clock skew), the cache is cleared and the request is retried once with a freshly fetched token.

---

### `config_fields` items

Non-secret values needed to build request URLs (e.g. organisation name, instance URL).

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | string | ✅ | Must start with a letter, then lowercase letters, digits, underscores. Used as `{key}` URL placeholder and settings key. |
| `display_name` | string | ✅ | Label shown in the UI. |
| `description` | string | | Help text below the input. |
| `required` | boolean | | Default: `true`. |
| `sensitive` | boolean | | If `true`, stored encrypted in credentials instead of settings. Default: `false`. |
| `placeholder` | string | | Input placeholder text. |

Config field values are automatically substituted into URL paths and `base_url`:

```json
"base_url": "https://dev.azure.com",
"config_fields": [{"key": "organization", ...}],
"path": "/{organization}/{project}/_apis/wit/wiql"
```

---

### `endpoints` items

Each endpoint becomes one LLM tool named `plugin_{id}_{endpoint.name}`.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Must start with a letter, then lowercase letters, digits, underscores. |
| `display_name` | string | ✅ | Shown in the Tools assignment screen. |
| `description` | string | ✅ | Shown to the LLM. Be specific about when to use it. |
| `method` | `GET`\|`POST`\|`PUT`\|`PATCH`\|`DELETE` | ✅ | HTTP method. |
| `path` | string | ✅ | URL path appended to `base_url`. Supports `{variable}` placeholders. |
| `parameters` | array | | Parameters the LLM passes when calling the tool. |

#### `parameters` items

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Parameter name. |
| `in` | `"path"` \| `"query"` \| `"body"` \| `"header"` | ✅ | Where the parameter is placed. |
| `type` | `"string"` \| `"integer"` \| `"number"` \| `"boolean"` \| `"array"` | ✅ | JSON Schema type. Use `array` for a list of primitives (see below). |
| `items` | object | required **when** `type = "array"` | Describes the array element type: `{ "type": "<primitive>" }`. |
| `description` | string | ✅ | Description shown to the LLM. |
| `required` | boolean | | Default: `true`. |
| `default` | any | | Default value when not provided. |

**Parameter placement:**

| `in` | Effect |
|---|---|
| `path` | Substituted into the URL: `/{variable}` → `/value` |
| `query` | Appended as `?name=value` |
| `body` | Included in the JSON request body |
| `header` | Added as an HTTP request header |

#### Array parameters

Set `type: "array"` when the target API expects a JSON array (e.g. a list of
IDs in the request body). Pair it with an `items` object describing the element
type — one of `string`, `integer`, `number`, or `boolean`:

```json
{
  "name": "social_accounts",
  "in": "body",
  "type": "array",
  "items": { "type": "integer" },
  "description": "Numeric social account IDs to post to.",
  "required": true
}
```

Serialization depends on placement:

| `in` | Serialization |
|---|---|
| `body` | Native JSON array in the request body: `"social_accounts": [75205, 75209]` |
| `query` | Repeated query params: `?type=image&type=video` |

**Rules:**

- `items` is required **if and only if** `type` is `array`. Declaring `array`
  without `items`, or supplying `items` on a non-array parameter, is rejected
  with a descriptive error.
- `items.type` must be one of the four primitives. Nested arrays and objects
  are not supported in this iteration.
- Array parameters are only meaningful for `in: "body"` and `in: "query"`.
  `path` and `header` placements reject `type: "array"`.

Because the tool schema advertises a real array type, the model emits an actual
JSON array — no stringified `"[75205]"` workaround, and no runtime coercion.

---

## Examples

### Bearer token (Azure DevOps PAT)

```json
{
  "id": "azure_devops",
  "display_name": "Azure DevOps",
  "description": "Work items, repos, pipelines.",
  "icon": "🔷",
  "base_url": "https://dev.azure.com",
  "auth": { "type": "bearer" },
  "config_fields": [
    {"key": "organization", "display_name": "Organization", "placeholder": "my-org"}
  ],
  "endpoints": [
    {
      "name": "list_pipelines",
      "display_name": "List Pipelines",
      "description": "List build pipelines in a project.",
      "method": "GET",
      "path": "/{organization}/{project}/_apis/pipelines?api-version=7.1",
      "parameters": [
        {"name": "project", "in": "path", "type": "string", "description": "Project name.", "required": true}
      ]
    }
  ]
}
```

### Custom header (e.g. `X-API-Key`)

```json
"auth": {
  "type": "header",
  "header_name": "X-API-Key"
}
```

### Basic auth with fixed password (Toggl-style)

```json
"auth": {
  "type": "basic",
  "fixed_password": "api_token"
}
```

The user enters only their API token; the password `api_token` is hardcoded.

### JWT login (username + password → JWT)

Use `api_key_with_jwt` for any API that issues a short-lived JWT via a login endpoint. The simplest form — no static API key required:

```json
"auth": {
  "type": "api_key_with_jwt",
  "token_endpoint": "/auth/login",
  "token_field": "token",
  "token_prefix": "Bearer"
}
```

The user provides **Username** and **Password**. The plugin POSTs them to `{base_url}/auth/login`, caches the returned JWT, and attaches `Authorization: Bearer {jwt}` to every request.

### JWT login + static API key

Some APIs additionally require a permanent API key header alongside the JWT. Add `api_key_header` to enable it:

```json
{
  "id": "my_service",
  "display_name": "My Service",
  "description": "Invoicing, timesheet registration, and master data management.",
  "icon": "🧾",
  "base_url": "https://api.myservice.example.com",
  "auth": {
    "type": "api_key_with_jwt",
    "api_key_header": "X-apikey",
    "token_endpoint": "/token",
    "token_field": "access_token",
    "token_prefix": "Access_Token"
  },
  "endpoints": [
    {
      "name": "list_invoices",
      "display_name": "List Invoices",
      "description": "Retrieve a list of invoices. Search by date range or customer.",
      "method": "GET",
      "path": "/invoices",
      "parameters": [
        {
          "name": "from_date",
          "in": "query",
          "type": "string",
          "description": "Start date in yyyyMMdd format (e.g. 20260101).",
          "required": false
        },
        {
          "name": "to_date",
          "in": "query",
          "type": "string",
          "description": "End date in yyyyMMdd format (e.g. 20261231).",
          "required": false
        }
      ]
    },
    {
      "name": "list_timesheets",
      "display_name": "List Timesheets",
      "description": "Retrieve timesheet registrations for the given date range.",
      "method": "GET",
      "path": "/timesheets",
      "parameters": [
        {
          "name": "from_date",
          "in": "query",
          "type": "string",
          "description": "Start date in yyyyMMdd format.",
          "required": true
        },
        {
          "name": "to_date",
          "in": "query",
          "type": "string",
          "description": "End date in yyyyMMdd format.",
          "required": true
        }
      ]
    }
  ]
}
```

The user provides **API Key**, **Username**, and **Password**. The API key is sent as `X-apikey` on both the login request and every subsequent API call. The JWT is cached, refreshed automatically before expiry, and re-fetched on 401 responses.

---

## Validation

The machine-readable JSON Schema lives at `src/plugins/plugin_schema.json`. You can validate your plugin locally with any JSON Schema validator, for example:

```bash
npx ajv validate -s src/plugins/plugin_schema.json -d my_plugin.json
```

The server also validates on install — invalid definitions are rejected with a 422 error and a descriptive message.
