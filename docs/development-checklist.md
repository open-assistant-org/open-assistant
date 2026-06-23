# Agent & Tool Development Checklist

Step-by-step checklist for adding new tools, integrations, and agents to Open Assistant.

---

## Adding a New Tool (to an existing integration)

If you're adding a tool to an already-supported service (e.g. a new Google, Outlook, or Notion tool):

- [ ] **Pydantic request model** — add to `src/models/<service>.py`
  - Define all parameters with `Field(...)` descriptions (the LLM reads these)
  - Use `Optional` for non-required params, set sensible defaults
- [ ] **Client method** — add to `src/integrations/<service>/client.py`
  - Implement the actual API call, parse the response into a clean dict
  - Add logging and error handling
- [ ] **Service method** — add to `src/services/<service>.py`
  - Thin wrapper that gets the client and calls the method
  - Add audit logging via `self._log_web_request()`
- [ ] **Tool definition** — register in `src/core/tools/definitions.py`
  - Write a clear `description` — this is the prompt the LLM uses to decide when to call the tool
  - Reference the Pydantic model as `parameters_model`
- [ ] **Tool routing** — add `elif` branch in `src/core/tools/executor.py` `_route_tool_call()`
  - Map `tool_name` to `service.method_name(**arguments)`
- [ ] **Tool metadata** — add entry in `src/core/tools/metadata.py`
  - `display_name` and `description` shown in the Settings UI tools checklist
  - Pick a `category` (email, calendar, files, notes, places, navigation, search, messaging, etc.)
- [ ] **Enabled tools list** — add tool name to the `<service>.enabled_tools` default in `src/models/config.py`
- [ ] **Agent assignment** — add tool name to the relevant agent's `tools` list in `src/agents/base.py`
- [ ] **DB migration** — if an agent's tools list changes, create a migration to update the DB row (existing users won't re-seed from `base.py`)

---

## Adding a New Integration (new external service)

If you're adding an entirely new service (e.g. Slack, Spotify, etc.):

### Backend wiring

- [ ] **Integration client** — create `src/integrations/<service>/client.py`
  - Handles API auth, HTTP calls, and response parsing
  - If OAuth: add `auth.py` alongside it
  - If API key: read from settings in the service layer
- [ ] **Pydantic models** — create `src/models/<service>.py`
  - Request models for each tool, response models if needed
- [ ] **Service layer** — create `src/services/<service>.py`
  - Extend `BaseService`, implement `_get_client()`, add tool methods
  - Add audit logging
- [ ] **Tool definitions** — add `define_<service>_tools()` in `src/core/tools/definitions.py`
  - Call it from `initialize_all_tools()`
- [ ] **Tool routing** — add routing section in `src/core/tools/executor.py`
- [ ] **Tool metadata** — add entries in `src/core/tools/metadata.py`
- [ ] **Executor init** — add `<service>_service` parameter to `ToolExecutor.__init__()` and register in `self.services` dict
- [ ] **Dependency injection** — add `get_<service>_service()` in `src/core/dependencies.py` and wire into the chat endpoint

### Configuration & settings

- [ ] **Config category** — add to `ConfigCategory` enum in `src/models/config.py` if it's a new category
- [ ] **Setting definitions** — add `<service>.enabled`, credentials, and `<service>.enabled_tools` to `SETTING_DEFINITIONS` in `src/models/config.py`
- [ ] **DB migration for settings** — create `XXX_<service>_default_settings.sql` in `src/core/migrations/`
  - `INSERT OR IGNORE` the settings rows so existing DBs pick them up

### UI integration

- [ ] **Service icon** — add to `getServiceIcon()` in `src/ui/static/js/settings.js`
- [ ] **Service list** — add service name to the `services` array in `loadIntegrations()` in `settings.js`
- [ ] **Doc URL** — add to `getIntegrationDocUrl()` in `settings.js`
- [ ] **Integration status** — add to `integrations_config` in `src/api/integrations.py` (if applicable)
- [ ] **Tool registry mapping** — add `<service>: "<service>.enabled"` to `service_to_setting` in `src/core/tools/registry.py`

### Optional

- [ ] **API endpoints** — add `src/api/<service>.py` route if the service needs direct REST endpoints (beyond tool calls)
- [ ] **Documentation** — add `docs/integrations/<service>.md`
- [ ] **Dependencies** — add any new Python packages to `pyproject.toml`

---

## Adding a New Agent

- [ ] **Agent definition** — add to `DEFAULT_AGENTS` dict in `src/agents/base.py`
  - `name`: lowercase identifier (used as DB key)
  - `display_name`: shown in UI
  - `role`: CrewAI role (used for delegation matching)
  - `goal`: one-line description
  - `backstory`: detailed system prompt — tell the agent exactly which tools to use and when
  - `tools`: list of tool names this agent can use
  - `enabled`: `True`
  - `allow_delegation`: `False` (only coordinator should delegate)
- [ ] **Update coordinator** — in `base.py`, add the new agent to the coordinator's backstory:
  - Add a bullet describing what the agent does with example use cases
  - Add the delegation role name under the `IMPORTANT` section
- [ ] **DB migration (agent seed)** — create `XXX_seed_<agent>_agent.sql` in `src/core/migrations/`
  - `INSERT OR IGNORE INTO agent_definitions (...)` with the full agent config
  - `UPDATE agent_definitions SET backstory = '...' WHERE name = 'coordinator'` — include the full updated coordinator backstory
  - `INSERT INTO schema_migrations (version)` at the end
  - Remember: single quotes in SQL values must be escaped as `''`

---

## Migration Tips

- Migrations live in `src/core/migrations/` and are sorted alphabetically by filename
- Use the next number in sequence: check the latest with `ls src/core/migrations/ | tail -1`
- Always use `INSERT OR IGNORE` for idempotency (safe to re-run)
- Always end with `INSERT INTO schema_migrations (version) VALUES ('XXX_name')`
- For agent backstory updates: include the **full** coordinator backstory (it's a complete replace, not a patch)
- JSON arrays in SQLite: use `json_array('tool_a', 'tool_b', ...)`
- Test locally: the migration runner in `src/core/database.py` applies pending migrations on startup

---

## Quick Verification

After making changes, verify everything compiles:

```bash
# Syntax check modified files
python -m py_compile src/models/<service>.py
python -m py_compile src/integrations/<service>/client.py
python -m py_compile src/services/<service>.py
python -m py_compile src/core/tools/definitions.py
python -m py_compile src/core/tools/executor.py
python -m py_compile src/core/tools/metadata.py
python -m py_compile src/agents/base.py
```

---

## File Reference

| What | Where |
|------|-------|
| Pydantic request/response models | `src/models/<service>.py` |
| API client (HTTP calls) | `src/integrations/<service>/client.py` |
| Auth (OAuth, API keys) | `src/integrations/<service>/auth.py` |
| Service layer (business logic) | `src/services/<service>.py` |
| Tool registration | `src/core/tools/definitions.py` |
| Tool routing | `src/core/tools/executor.py` |
| Tool UI metadata | `src/core/tools/metadata.py` |
| Tool registry & filtering | `src/core/tools/registry.py` |
| Agent definitions | `src/agents/base.py` |
| Setting definitions | `src/models/config.py` |
| DB migrations | `src/core/migrations/XXX_*.sql` |
| Settings UI (JS) | `src/ui/static/js/settings.js` |
| Integration status API | `src/api/integrations.py` |
| Dependencies | `pyproject.toml` |
