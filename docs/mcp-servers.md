# MCP Servers (Model Context Protocol)

Open Assistant can connect to remote **MCP servers** and expose their tools to
the LLM. Each server is added from **Settings → MCP Servers**, and you choose an
**intent keyword** that activates the server's tools — the server behaves like a
built-in "agent".

Servers are remote, over **Streamable HTTP**, and authenticate with **static
headers**, **OAuth 2.1 (PKCE)**, or nothing. Local `stdio` servers are not
supported.

## How it works

MCP is wired in the same way as the [plugin system](./plugin-schema.md):

1. **Add a server** (`POST /api/mcp`) — the backend connects, calls `tools/list`,
   and caches each tool's schema in `data/mcp_servers/{id}.json`.
2. **Tool registration** — every discovered tool is registered in the global
   tool registry as `mcp_{id}_{tool}` (`service_name = mcp_{id}`), gated on the
   setting `mcp.{id}.enabled`.
3. **Agent/skill row** — an `agent_definitions` row named `mcp_{id}` is created
   with the server's tools and your intent keywords. Because agents and skills
   are the same table, a message containing a keyword selects the row and offers
   its tools to the LLM (see `src/models/skill.py`).
4. **Execution** — a tool call is routed through `McpService.execute_tool`, which
   opens a short-lived HTTP session, calls the tool, and returns its content.

## Authentication (static headers)

Auth uses one or more **static HTTP headers**. Common shapes:

- **Bearer token** — header `Authorization`, value `Bearer <token>`.
- **API-key header** — e.g. `X-API-Key: <key>`.
- **Multiple headers** — e.g. Cloudflare Access needs both
  `CF-Access-Client-Id` and `CF-Access-Client-Secret`.

Header **values are stored encrypted** in the `service_credentials` table under
`mcp_{id}` (via `CredentialsRepository`). Only the header **names** are written
to the config JSON — no secrets touch disk in plaintext. You can add or update
header values later via `PUT /api/mcp/{id}/credentials`.

## Authentication (OAuth 2.1)

Choose **OAuth 2.1 (PKCE)** when adding a server whose provider requires a
browser sign-in. After adding it, click **Connect via OAuth**; tokens are stored
encrypted and refreshed automatically.

**Discovery** follows the MCP authorization spec: the server's
`WWW-Authenticate` challenge or `/.well-known/oauth-protected-resource`
(RFC 9728, path-aware) points to an authorization server, whose metadata is read
from `/.well-known/oauth-authorization-server` or OpenID Connect discovery.
Servers publishing neither fall back to `/authorize`, `/token`, `/register` on
their own origin. Requests carry the RFC 8707 `resource` parameter.

**The OAuth client** is obtained one of two ways:

- **Dynamic registration (default)** — if the provider has a registration
  endpoint, a client is registered automatically for this instance's callback URL
  (and registered again if the instance is reached from a different origin).
- **Your own OAuth app** — for providers without dynamic registration (GitHub,
  many enterprise identity providers), register an app with the provider and
  enter its **client ID** (and **client secret**, if it has one) when adding the
  server, or later via `PUT /api/mcp/{id}/credentials`. Register this redirect
  URI: `{your origin}{prefix}/api/mcp/oauth/callback`
  (e.g. `https://example.com/api/mcp/oauth/callback`). The secret is stored
  encrypted and never returned by the API. Changing the client clears stored
  tokens; connect again afterwards.

The in-progress authorization state is kept in memory, so restarting the app between
clicking **Connect via OAuth** and finishing sign-in shows "Unknown or expired OAuth
state"; just connect again.

## API

| Method & path | Purpose |
|---|---|
| `GET /api/mcp` | List configured servers |
| `POST /api/mcp` | Add a server (connect + discover + wire agent row) |
| `PUT /api/mcp/{id}/enable` | Enable/disable a server and its agent row |
| `PUT /api/mcp/{id}/credentials` | Update stored (encrypted) header values, or the OAuth client ID/secret |
| `POST /api/mcp/{id}/oauth/start` | Begin the OAuth flow (returns the authorization URL) |
| `GET /api/mcp/oauth/callback` | OAuth redirect target (exchanges the code for tokens) |
| `POST /api/mcp/{id}/refresh` | Re-discover tools |
| `GET /api/mcp/{id}/test` | Test connectivity + report tool count |
| `DELETE /api/mcp/{id}` | Remove server, tools, credentials, and agent row |

## Requirements

The `mcp` Python SDK must be installed (declared in `pyproject.toml`). The app
boots and registers previously-cached tools even without it; live discovery and
execution require the SDK and will return a clear error if it is missing.
