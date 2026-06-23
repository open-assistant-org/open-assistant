-- Migration: 044_google_drive_tools
-- Adds Google Drive, Docs, Sheets, and Slides tools to agent definitions.
-- Updates file_handler and research agents to include Drive tools.
-- Updates file_handler goal and keywords to mention Google Drive.

-- ============================================================================
-- Update file_handler agent: add Google Drive tools + update goal/keywords
-- ============================================================================

UPDATE agent_definitions
SET
    goal = 'Manage files across Nextcloud, OneDrive, and Google Drive — list, search, read, upload, download, move, copy, and delete files. Create and edit Google Docs, Google Sheets, and Google Slides.',
    tools = json(
        '["nextcloud_read_file","nextcloud_upload_file","nextcloud_create_folder","nextcloud_delete_file","nextcloud_move_file","nextcloud_copy_file","nextcloud_get_file_info","nextcloud_file_exists","nextcloud_download_file","outlook_read_file","onedrive_upload_file","google_drive_list_files","google_drive_search_files","google_drive_get_file","google_drive_read_file","google_drive_upload_file","google_drive_create_folder","google_drive_delete_file","google_drive_move_file","google_docs_create","google_docs_get","google_docs_append","google_docs_update","google_sheets_create","google_sheets_get","google_sheets_read","google_sheets_write","google_sheets_append","google_slides_create","google_slides_get","create_docx","create_pdf","notion_create_note","notion_update_page","notion_delete_page","notion_append_content"]'
    ),
    intent_keywords = json(
        '["file","move","copy","list","create","upload","delete","onedrive","notion","nextcloud","google drive","drive","gdrive","docs","google docs","sheets","google sheets","spreadsheet","slides","google slides","presentation","document","note","entry","pdf","docx"]'
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'file_handler';

-- ============================================================================
-- Update research agent: add Drive read tools for searching/reading files
-- ============================================================================

UPDATE agent_definitions
SET
    tools = json(
        replace(
            replace(
                json_extract(tools, '$'),
                -- Add Drive tools at the end (idempotent via string replacement trick):
                -- We rebuild the array to include new tools if not already present
                '"nextcloud_search_files"]',
                '"nextcloud_search_files","google_drive_list_files","google_drive_search_files","google_drive_get_file","google_drive_read_file","google_docs_get","google_sheets_get","google_sheets_read","google_slides_get"]'
            ),
            -- Handle case where nextcloud_search_files is already followed by other tools
            '"nextcloud_search_files","google_drive_list_files"',
            '"nextcloud_search_files","google_drive_list_files"'
        )
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'research'
  AND tools NOT LIKE '%google_drive_list_files%';

-- Fallback: if the replace approach didn't match (tools array structure differs),
-- do a direct update with the full known tool set for research agent
UPDATE agent_definitions
SET
    tools = json(
        '["web_search","browse_url","browse_extract","unified_search","reindex_search","analyze_content","google_search_emails","google_get_email","google_read_emails","google_get_labels","google_get_attachment","google_drive_list_files","google_drive_search_files","google_drive_get_file","google_drive_read_file","google_docs_get","google_sheets_get","google_sheets_read","google_slides_get","outlook_read_emails","outlook_get_email","outlook_search_emails","outlook_get_attachment","outlook_read_file","nextcloud_read_file","nextcloud_get_file_info","nextcloud_file_exists","notion_query_database","notion_get_page","notion_get_page_content","notion_search","notion_list_databases","outlook_list_files","outlook_search_files","nextcloud_list_files","nextcloud_search_files"]'
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'research'
  AND tools NOT LIKE '%google_drive_list_files%';

-- ============================================================================
-- Update writer agent: add Docs/Sheets/Slides creation tools
-- ============================================================================

UPDATE agent_definitions
SET
    tools = json(
        replace(
            json_extract(tools, '$'),
            '"create_pdf"]',
            '"create_pdf","google_docs_create","google_docs_get","google_docs_append","google_docs_update","google_sheets_create","google_sheets_get","google_sheets_read","google_sheets_write","google_sheets_append","google_slides_create","google_slides_get"]'
        )
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'writer'
  AND tools NOT LIKE '%google_docs_create%';

-- ============================================================================
-- Record migration as applied
-- ============================================================================
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('044_google_drive_tools');
