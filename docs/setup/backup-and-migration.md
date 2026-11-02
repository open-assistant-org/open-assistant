# Backup & Migration

Open Assistant supports exporting all instance data into a single portable JSON
bundle and importing it on another instance. This is the supported way to
migrate from one server to another.

## How it works

- **Export** (`POST /api/backup/export`) dumps every data table (conversations,
  messages, agent definitions, tasks, cron jobs, prompts, settings, artifacts,
  …) plus the files under `data/plugins/` and `data/mcp_servers/` into one JSON
  bundle that is downloaded to your machine.
- Run-history and derived data (`job_executions`, `llm_consumption`,
  `search_index`, `audit_log`) are intentionally **not** included.
- Secrets (`service_credentials`) are decrypted with the source instance's
  `ENCRYPTION_KEY` and stored **re-encrypted with a key derived from your
  backend secret** (PBKDF2). The bundle never contains plaintext secrets.
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

## Migrating instances

```bash
SOURCE_KEY="<source ENCRYPTION_KEY>"

# 1. On the source server: export and download the bundle
curl -X POST http://old-server:8080/api/backup/export \
  -H 'Content-Type: application/json' \
  -d "{\"secret\": \"$SOURCE_KEY\"}" \
  -o open-assistant-backup.json

# 2. On the target server (already set up with its own ENCRYPTION_KEY): import
curl -X POST http://new-server:8080/api/backup/import \
  -F "bundle=@open-assistant-backup.json" \
  -F "secret=$SOURCE_KEY"
```

### Conflict modes

- `mode=fail` (default): the import is aborted if the target contains rows that
  are **not** in the bundle (data that would be lost). A freshly set-up target
  instance whose pre-seeded defaults are also in the bundle imports cleanly —
  matching default rows are skipped, not duplicated.
- `mode=overwrite`: clears all included tables on the target first, then imports
  the bundle verbatim. Use this to force a full replacement.

Import runs in a single transaction: if anything fails, the target database is
left untouched.

## Security notes

- Keep the bundle file and the backend secret confidential — together they
  contain all your credentials.
- The secret is only accepted in the request body/form, never as a query
  parameter, and is never logged.
- After migrating, consider rotating credentials if the bundle may have been
  exposed.