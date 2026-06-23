-- ============================================================================
-- Migration: 047_plugin_system
-- Description: Migrate Toggl settings to the plugin namespace
-- Created: 2026-04-14
-- ============================================================================
-- The plugin system reuses the existing `settings` and `service_credentials`
-- tables.  This migration renames the old Toggl settings key so that the
-- plugin system picks it up automatically.
--
-- Credential migration (toggl → plugin_toggl) is handled in Python by
-- PluginService._migrate_legacy_toggl() on first startup, because the
-- credential data is Fernet-encrypted and cannot be rewritten in plain SQL.
-- ============================================================================

-- Rename the legacy Toggl enabled flag to the plugin namespace
UPDATE settings
SET key = 'plugin.toggl.enabled'
WHERE key = 'toggl.enabled';

-- Remove the old Toggl API token placeholder row from settings
-- (the actual secret lives in service_credentials and is migrated in Python)
DELETE FROM settings WHERE key = 'toggl.api_token';

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('047_plugin_system');
