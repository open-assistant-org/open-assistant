-- Migration: 057_llm_consumption
-- Adds the per-call LLM consumption ledger used for accurate metered billing.
--
-- The previous billing source (SUM(messages.token_count)) only counted a local
-- tiktoken estimate of visible message text and could not represent the
-- provider's real usage — in particular all input/context tokens (system prompt,
-- tool schemas, conversation history re-sent each turn) and every auxiliary LLM
-- call were unbilled. This table stores the provider's authoritative
-- response.usage per call; /managed/usage sums it by month.
--
-- Growth is bounded by the nightly compaction job (migration-independent cron),
-- which collapses rows older than the retention window into one summary per
-- (year, month). See the compaction job for details.

CREATE TABLE IF NOT EXISTS llm_consumption (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    provider            TEXT,
    model               TEXT,
    prompt_tokens       INTEGER DEFAULT 0,   -- input (incl. cached)
    completion_tokens   INTEGER DEFAULT 0,   -- output (incl. reasoning)
    total_tokens        INTEGER DEFAULT 0,
    cached_tokens       INTEGER DEFAULT 0,   -- prompt_tokens_details.cached_tokens, if present
    reasoning_tokens    INTEGER DEFAULT 0,   -- completion_tokens_details.reasoning_tokens, if present
    conversation_id     TEXT,                -- nullable, for traceability
    metadata            JSON                 -- {missing_usage, openrouter_cost, compacted, baseline, ...}
);

CREATE INDEX IF NOT EXISTS idx_llm_consumption_ts ON llm_consumption(timestamp);

-- Single collapsed baseline = legacy trailing-12-month SUM(messages.token_count).
-- Dated NOW (current month) so it survives the trailing-12-month filter that
-- /managed/usage applies and the platform sums. This is ONE collapsed number,
-- not per-calendar-month buckets (billing cycles are per-user, handled by the
-- platform's watermarks). It bridges the platform's lifetime watermark so that
-- new accurate usage is credited immediately instead of being held back by the
-- max() guard until the new ledger re-crosses the old under-counted high.
-- Frozen at deploy; never updated. Single scan over messages (the legacy sum
-- is used for both completion_tokens and total_tokens).
INSERT INTO llm_consumption (timestamp, provider, model, prompt_tokens,
    completion_tokens, total_tokens, cached_tokens, reasoning_tokens, metadata)
SELECT datetime('now'), 'legacy', 'baseline', 0, s, s, 0, 0,
       '{"baseline": true, "source": "legacy messages.token_count estimate, trailing 12 months"}'
FROM (SELECT COALESCE(SUM(token_count), 0) AS s
      FROM messages
      WHERE timestamp >= datetime('now', '-12 months'));

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('057_llm_consumption');
