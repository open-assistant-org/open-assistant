-- ============================================================================
-- Migration: 051_scheduled_prompts_messaging
-- Description: Add optional delivery routing to cron_jobs and future_tasks.
--              NULL delivery_channel = legacy silent system execution (no change
--              to existing rows). 'whatsapp' or 'slack' = proactive outbound
--              delivery of the LLM-generated response to the user.
-- Created: 2026-05-31
-- ============================================================================

ALTER TABLE cron_jobs ADD COLUMN delivery_channel TEXT;
ALTER TABLE cron_jobs ADD COLUMN delivery_contact_identifier TEXT;

ALTER TABLE future_tasks ADD COLUMN delivery_channel TEXT;
ALTER TABLE future_tasks ADD COLUMN delivery_contact_identifier TEXT;

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('051_scheduled_prompts_messaging');
