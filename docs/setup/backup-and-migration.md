# Backup & Migration

Open Assistant supports exporting all instance data into a single portable JSON
bundle and importing it on another instance. This is the supported way to
migrate from one server to another.

## How it works

- **Export** (`POST /api/backup/export`) dumps every data table (conversations,
  messages, agent definitions, tasks, cron jobs, prompts, settings, artifacts,
  run history, LLM consumption, audit log, …), the long-term memory facts, and
  the files under `data/plugins/`, `data/mcp_servers/` and the artifacts
  directory into one bundle that is downloaded to your machine.
- Only the derived part of the search index is left out; the target rebuilds it
  automatically on first search. Memory facts (which live only in the search
  index) are included.
- Secrets (`service_credentials` and the Outlook token cache) are decrypted with
  the source instance's `ENCRYPTION_KEY` and stored **re-encrypted with a key
  derived from your backend secret** (PBKDF2). The bundle never contains
  plaintext secrets.

### Not included

- **`.env` / environment variables** (API keys and settings configured through
  the environment). Copy them to the target yourself, but keep the target's own
  `ENCRYPTION_KEY`.
- **WhatsApp session** (`data/whatsapp_session`): it is a browser profile bound
  to the machine. Re-link WhatsApp by scanning the QR code on the target.
- **Import** (`POST /api/backup/import`) re-encrypts the credentials with the
  *target* instance's `ENCRYPTION_KEY`, so migrating between instances with
  different keys works out of the box.

## The backend secret

Because the bundle contains (encrypted) secrets, both endpoints require you to
prove knowledge of the backend secret:

- **Export**: the secret must match the source instance's `ENCRYPTION_KEY`
  (from its `.env`).
- **Import**: the secret must be the one the bundle was exported with (i.e. the
  *source* instance's key). The target instance's own `ENCRYPTION_KEY` is picked
  up from its environment automatically.

## Bundle format

The export is a gzip-compressed JSON file (`open-assistant-backup.json.gz`). It
contains the data tables and data-dir files, but **not** the SQLite database
file itself — the JSON *is* the database content. Import accepts both the
`.json.gz` file as-is and a plain (decompressed) `.json` file.

## Migrating instances

```bash
SOURCE_KEY="<source ENCRYPTION_KEY>"

# 1. On the source server: export and download the bundle
curl -X POST http://old-server:8080/api/backup/export \
  -H 'Content-Type: application/json' \
  -d "{\"secret\": \"$SOURCE_KEY\"}" \
  -o open-assistant-backup.json.gz

# 2. On the target server (already set up with its own ENCRYPTION_KEY): import
curl -X POST http://new-server:8080/api/backup/import \
  -F "bundle=@open-assistant-backup.json.gz" \
  -F "secret=$SOURCE_KEY"

# 3. Restart the target so cron jobs, future tasks, plugins and MCP servers
#    are loaded from the imported data.
```

Run the **same app version** on both instances. If the versions differ, the
import still succeeds, but columns that don't exist on the target are dropped;
the import response lists them under `warnings` / `ignored_columns`.

### Conflict modes

- `mode=fail` (default): the import is aborted if the target contains rows that
  are **not** in the bundle (data that would be lost). A freshly set-up target
  instance imports cleanly: its pre-seeded default rows are replaced by the
  bundle's version (so customised defaults carry over), and history tables
  (`job_executions`, `llm_consumption`, `audit_log`) are merged, not treated as
  conflicts.
- `mode=overwrite`: clears all included tables on the target first, then imports
  the bundle verbatim. Use this to force a full replacement. Files already on
  the target that are not in the bundle are left in place.

The database part of the import runs in a single transaction: if anything
fails, the target database is left untouched.

## Managed instances

On instances run by the Open Assistant Platform (`MANAGED_API_KEY` is set) the
Backup & Migration section is hidden and `/api/backup/*` returns `403`. Backups
are run by the platform admin instead, through `POST /managed/backup/export`
and `POST /managed/backup/import` (authenticated with `X-Managed-Key`).

- The bundle's credentials are encrypted with a secret held by the platform
  (at least 32 characters) instead of the instance `ENCRYPTION_KEY`.
- `llm_consumption` is **not** exported, and is ignored on import. The target's
  usage ledger is never changed, so billing is not duplicated or rolled back.
- After an import the platform re-pushes its credentials and settings and
  restarts the instance.

## Security notes

- Keep the bundle file and the backend secret confidential — together they
  contain all your credentials.
- The secret is only accepted in the request body/form, never as a query
  parameter, and is never logged.
- After migrating, consider rotating credentials if the bundle may have been
  exposed.