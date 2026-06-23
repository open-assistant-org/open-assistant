-- Migration: 049_remove_google_drive_write_tools
-- Removes Google Drive write tools from agent definitions following the scope
-- reduction from drive -> drive.readonly (Google OAuth verification requirement).
-- Removed tools: google_drive_upload_file, google_drive_create_folder,
-- google_drive_delete_file, google_drive_move_file.

-- ============================================================================
-- Strip the four removed tools from any agent's tools array.
-- Uses successive replace() calls; idempotent because the tokens are unique.
-- Each tool is matched in three forms to handle position in the JSON array:
--   ,"tool"   (middle or end)
--   "tool",   (start)
--   "tool"    (only element)
-- ============================================================================

UPDATE agent_definitions
SET
    tools = json(
        replace(
            replace(
                replace(
                    replace(
                        replace(
                            replace(
                                replace(
                                    replace(
                                        replace(
                                            replace(
                                                replace(
                                                    replace(
                                                        json_extract(tools, '$'),
                                                        ',"google_drive_upload_file"', ''
                                                    ),
                                                    '"google_drive_upload_file",', ''
                                                ),
                                                '"google_drive_upload_file"', ''
                                            ),
                                            ',"google_drive_create_folder"', ''
                                        ),
                                        '"google_drive_create_folder",', ''
                                    ),
                                    '"google_drive_create_folder"', ''
                                ),
                                ',"google_drive_delete_file"', ''
                            ),
                            '"google_drive_delete_file",', ''
                        ),
                        '"google_drive_delete_file"', ''
                    ),
                    ',"google_drive_move_file"', ''
                ),
                '"google_drive_move_file",', ''
            ),
            '"google_drive_move_file"', ''
        )
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE tools LIKE '%google_drive_upload_file%'
   OR tools LIKE '%google_drive_create_folder%'
   OR tools LIKE '%google_drive_delete_file%'
   OR tools LIKE '%google_drive_move_file%';

-- ============================================================================
-- Update file_handler agent goal to reflect read-only Drive access.
-- ============================================================================

UPDATE agent_definitions
SET
    goal = 'Manage files across Nextcloud, OneDrive, and Google Drive — list, search, read, upload, download, move, copy, and delete files (Google Drive is read-only). Create and edit Google Docs, Google Sheets, and Google Slides.',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'file_handler';

-- ============================================================================
-- Record migration as applied
-- ============================================================================
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('049_remove_google_drive_write_tools');
