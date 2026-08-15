-- ============================================================================
-- Migration: 060_recipe_skip_guards
-- Description: Make the two default nightly jobs skip their expensive LLM steps
--              on days with no genuine user activity.
--
--              cron-system-memory (Nightly Memory Update) and cron-system-soul
--              (Nightly Soul Update) fire every night regardless of whether the
--              user talked to the assistant. Each runs several full LLM
--              conversations per night (memory: 3, soul: 2), so quiet days cost
--              real money for no benefit.
--
--              This patches their recipe `steps` JSON (defined in 048_recipes)
--              with the generic skip-guard fields added to the recipe engine:
--                - Step 1 (system_get_conversation_text): request a true rolling
--                  24h window, and skip the rest of the recipe when it returns no
--                  messages (skip_remaining_if_empty). Step 1 is a free SQL fetch,
--                  so a fully idle night now costs zero LLM calls.
--                - Step 3 (the extraction LLM step): skip the remaining
--                  update/index steps when the model emits its "nothing to do"
--                  sentinel (NO_NEW_FACTS / NO_STYLE_UPDATES), which the prompts
--                  already produce but nothing previously acted on.
--
--              Uses surgical json_set on specific array indices so any other
--              step content is preserved, and is scoped by job_id.
-- Created: 2026-08-14
-- ============================================================================

-- Nightly Memory Update: step index 0 = fetch, step index 2 = extract facts.
UPDATE cron_jobs
SET steps = json_set(
        json_set(
            json_set(steps, '$[0].tool_parameters', json_object('hours', 24)),
            '$[0].skip_remaining_if_empty', json('true')
        ),
        '$[2].skip_remaining_if_output_contains', 'NO_NEW_FACTS'
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = 'cron-system-memory' AND steps IS NOT NULL;

-- Nightly Soul Update: step index 0 = fetch, step index 2 = extract style.
UPDATE cron_jobs
SET steps = json_set(
        json_set(
            json_set(steps, '$[0].tool_parameters', json_object('hours', 24)),
            '$[0].skip_remaining_if_empty', json('true')
        ),
        '$[2].skip_remaining_if_output_contains', 'NO_STYLE_UPDATES'
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = 'cron-system-soul' AND steps IS NOT NULL;

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('060_recipe_skip_guards');
