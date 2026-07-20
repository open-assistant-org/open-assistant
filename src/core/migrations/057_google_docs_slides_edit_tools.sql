-- Migration: 057_google_docs_slides_edit_tools
-- Adds targeted editing tools for Google Docs, Sheets, and Slides so agents can
-- UPDATE existing files instead of only creating/appending/full-replacing them.
-- New tools (all within already-granted documents/spreadsheets/presentations scopes):
--   google_docs_replace_text   - find & replace in a Doc (non-destructive)
--   google_sheets_clear        - clear a range's values
--   google_slides_add_slide    - add a slide with optional title/body
--   google_slides_replace_text - find & replace across a presentation
--   google_slides_insert_text  - insert a text box onto a slide
--
-- Only the write-capable agents (writer, file_handler) receive these; the
-- research agent stays read-only. Each UPDATE anchors on a sibling tool token
-- guaranteed present from migration 044 and is guarded by NOT LIKE for idempotency.

-- ============================================================================
-- Google Docs: add find-and-replace next to google_docs_update
-- ============================================================================
UPDATE agent_definitions
SET
    tools = json(
        replace(
            json_extract(tools, '$'),
            '"google_docs_update"',
            '"google_docs_update","google_docs_replace_text"'
        )
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name IN ('writer', 'file_handler')
  AND tools LIKE '%google_docs_update%'
  AND tools NOT LIKE '%google_docs_replace_text%';

-- ============================================================================
-- Google Sheets: add clear next to google_sheets_append
-- ============================================================================
UPDATE agent_definitions
SET
    tools = json(
        replace(
            json_extract(tools, '$'),
            '"google_sheets_append"',
            '"google_sheets_append","google_sheets_clear"'
        )
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name IN ('writer', 'file_handler')
  AND tools LIKE '%google_sheets_append%'
  AND tools NOT LIKE '%google_sheets_clear%';

-- ============================================================================
-- Google Slides: add editing tools next to google_slides_get
-- ============================================================================
UPDATE agent_definitions
SET
    tools = json(
        replace(
            json_extract(tools, '$'),
            '"google_slides_get"',
            '"google_slides_get","google_slides_add_slide","google_slides_replace_text","google_slides_insert_text"'
        )
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name IN ('writer', 'file_handler')
  AND tools LIKE '%google_slides_get%'
  AND tools NOT LIKE '%google_slides_add_slide%';

-- ============================================================================
-- Refresh file_handler goal to advertise the richer edit capability.
-- ============================================================================
UPDATE agent_definitions
SET
    goal = 'Manage files across Nextcloud, OneDrive, and Google Drive — list, search, read, upload, download, move, copy, and delete files (Google Drive is read-only). Create and edit Google Docs, Google Sheets, and Google Slides, including targeted find-and-replace edits and adding slides.',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'file_handler';

-- ============================================================================
-- Record migration as applied
-- ============================================================================
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('057_google_docs_slides_edit_tools');
