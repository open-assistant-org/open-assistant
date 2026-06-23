-- Migration: 050_add_create_html_tool
-- Adds create_html to the file_handler agent's tools list and 'html' to its
-- intent_keywords so the agent is selected for HTML generation requests.
-- create_html sits alongside create_docx and create_pdf (added in migration 044)
-- as a document generation tool that writes HTML pages via the LLM.

UPDATE agent_definitions
SET
    tools = json_insert(tools, '$[#]', 'create_html'),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'file_handler'
  AND tools NOT LIKE '%create_html%';

UPDATE agent_definitions
SET
    intent_keywords = json_insert(intent_keywords, '$[#]', 'html'),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'file_handler'
  AND intent_keywords NOT LIKE '%html%';

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('050_add_create_html_tool');
