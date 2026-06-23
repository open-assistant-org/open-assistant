-- Migration: 045_toggl_integration
-- Description: Seed default settings rows for the Toggl Track integration.
-- All inserts use INSERT OR IGNORE so the migration is safe to re-run.

-- ============================================================================
-- Default settings for Toggl
-- ============================================================================

INSERT OR IGNORE INTO settings (key, value, category, is_sensitive, description)
VALUES
    ('toggl.enabled',   'false',  'toggl', 0, 'Enable Toggl Track integration'),
    ('toggl.api_token', '',       'toggl', 1, 'Toggl Track API token');

-- ============================================================================
-- Record migration as applied
-- ============================================================================
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('045_toggl_integration');
