-- Migration: 062_create_html_context_path
-- Teaches the file_handler agent to pass large data to create_html by file path
-- (context_path) instead of re-typing it, and gives it store_artifact so the
-- generated page can be kept/shared directly.

UPDATE agent_definitions
SET backstory = backstory || '

HTML PAGES:
- Use create_html to build a web page/dashboard. Do NOT paste large datasets into its
  "context" argument: if the data already lives in a file (a "file" path from an offloaded
  tool result, or a file written by python_execute), pass that path as "context_path".
  Use "context" only for small inline data.
- create_html returns a filepath. Call store_artifact with that path as source_path to keep
  the page and get a shareable link.',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'file_handler'
  AND backstory NOT LIKE '%context_path%';

UPDATE agent_definitions
SET
    tools = json_insert(tools, '$[#]', 'store_artifact'),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'file_handler'
  AND tools NOT LIKE '%store_artifact%';

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('062_create_html_context_path');
