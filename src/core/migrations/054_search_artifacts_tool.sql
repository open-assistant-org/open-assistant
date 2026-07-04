-- Migration: 054_search_artifacts_tool
-- Assigns the search_artifacts system tool to the coordinator agent so it can
-- look up previously stored artifacts by filename or title (regex match) across
-- conversations without the user having to open the Artifacts tab.

UPDATE agent_definitions
SET
    tools = json_insert(tools, '$[#]', 'search_artifacts'),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'coordinator'
  AND tools NOT LIKE '%search_artifacts%';

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('054_search_artifacts_tool');
