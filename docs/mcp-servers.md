# MCP Servers (Model Context Protocol)

Open Assistant can connect to remote **MCP servers** and expose their tools to
the LLM. Each server is added from **Settings → MCP Servers**, and you choose an
**intent keyword** that activates the server's tools — the server behaves like a
built-in "agent".

This is **Phase 1**: remote servers over **Streamable HTTP**, authenticated with
**static headers** (no OAuth yet). Local `stdio` servers and the MCP OAuth 2.1
flow are planned for later phases.

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

> Servers that *require* the interactive MCP OAuth 2.1 handshake are **not**
> supported in this version. Use a static token/header, or wait for the OAuth
> phase.

## API

| Method & path | Purpose |
|---|---|
| `GET /api/mcp` | List configured servers |
| `POST /api/mcp` | Add a server (connect + discover + wire agent row) |
| `PUT /api/mcp/{id}/enable` | Enable/disable a server and its agent row |
| `PUT /api/mcp/{id}/credentials` | Update stored (encrypted) header values |
| `POST /api/mcp/{id}/refresh` | Re-discover tools |
| `GET /api/mcp/{id}/test` | Test connectivity + report tool count |
| `DELETE /api/mcp/{id}` | Remove server, tools, credentials, and agent row |

## Requirements

The `mcp` Python SDK must be installed (declared in `pyproject.toml`). The app
boots and registers previously-cached tools even without it; live discovery and
execution require the SDK and will return a clear error if it is missing.
