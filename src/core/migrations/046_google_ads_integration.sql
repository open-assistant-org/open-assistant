-- Migration: 046_google_ads_integration
-- Description: Seed default settings rows for the Google Ads integration.
-- All inserts use INSERT OR IGNORE so the migration is safe to re-run.

-- ============================================================================
-- Default settings for Google Ads
-- ============================================================================

INSERT OR IGNORE INTO settings (key, value, category, is_sensitive, description)
VALUES
    ('google_ads.enabled', 'false', 'google_ads', 0, 'Enable Google Ads integration'),
    ('google_ads.client_id', '', 'google_ads', 1, 'Google OAuth 2.0 Client ID for Google Ads'),
    ('google_ads.client_secret', '', 'google_ads', 1, 'Google OAuth 2.0 Client Secret for Google Ads'),
    ('google_ads.developer_token', '', 'google_ads', 1, 'Google Ads Developer Token'),
    ('google_ads.customer_id', '', 'google_ads', 0, 'Google Ads Customer ID'),
    ('google_ads.login_customer_id', '', 'google_ads', 0, 'Google Ads Manager Account ID (MCC)'),
    ('google_ads.project_id', '', 'google_ads', 0, 'Google Cloud Project ID');

-- ============================================================================
-- Record migration as applied
-- ============================================================================
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('046_google_ads_integration');
