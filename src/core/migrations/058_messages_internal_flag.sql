-- Migration: 058_messages_internal_flag
-- Adds an is_internal flag to messages so transparency rows (the system prompt
-- and auxiliary LLM outputs persisted for visibility) can be excluded from the
-- conversation history that is re-sent to the LLM on subsequent turns.
--
-- Without this flag, persisting the system prompt / planner / memory / document
-- outputs as regular message rows would pollute the LLM context (they'd be
-- pulled back by get_recent_messages / get_by_conversation and re-sent every
-- turn), distorting the prompt and the very usage we're trying to bill
-- accurately. Internal rows are billing-neutral (billing reads llm_consumption).

ALTER TABLE messages ADD COLUMN is_internal BOOLEAN DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_messages_internal ON messages(is_internal);

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('058_messages_internal_flag');
