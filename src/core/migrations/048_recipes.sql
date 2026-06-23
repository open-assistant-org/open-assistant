-- ============================================================================
-- Migration: 048_recipes
-- Description: Extend cron_jobs and future_tasks with multi-step recipe support.
--              Existing jobs are backward-compatible — old tool_name/prompt columns
--              are kept as the legacy fallback path; steps IS NOT NULL is the
--              recipe indicator used by the execution engine.
-- Created: 2026-05-23
-- ============================================================================

-- Add recipe columns to cron_jobs
ALTER TABLE cron_jobs ADD COLUMN steps JSON;
ALTER TABLE cron_jobs ADD COLUMN required_skills JSON;

-- Add recipe columns to future_tasks
ALTER TABLE future_tasks ADD COLUMN steps JSON;
ALTER TABLE future_tasks ADD COLUMN required_skills JSON;

-- Convert tool-type jobs to single-step recipes (generic fallback).
UPDATE cron_jobs
SET steps = json_array(json_object(
    'order',            1,
    'description',      name,
    'tool_name',        tool_name,
    'tool_parameters',  json(COALESCE(tool_parameters, 'null'))
))
WHERE steps IS NULL AND job_type = 'tool';

-- Decompose the Nightly Memory Update prompt into a proper multi-step recipe
-- following the recipe design rules: pinned tools, variable wiring, one-action-per-step.
UPDATE cron_jobs
SET steps = json_array(
    json_object(
        'order',       1,
        'description', 'Retrieve conversations from the last 24 hours',
        'tool_name',   'system_get_conversation_text',
        'stores_as',   'conversations'
    ),
    json_object(
        'order',            2,
        'description',      'Read the current memory prompt',
        'tool_name',        'system_get_prompt',
        'tool_parameters',  json_object('key', 'memory'),
        'stores_as',        'current_memory'
    ),
    json_object(
        'order',           3,
        'description',     'Analyse conversations and extract new facts',
        'prompt_template', 'You are performing the nightly memory update. Analyse the conversation data and the current memory prompt below. Extract NEW facts sorted into two categories:

CATEGORY A — Operational / ID facts (memory prompt):
- User''s name, timezone, locale
- Account IDs, user IDs referenced in integrations
- Key contact names and their identifiers (email, phone)
- Critical preferences that directly affect how tools are used
- Structural facts the system needs on every interaction

CATEGORY B — General / contextual facts (search index):
- Interests, hobbies, topics the user cares about
- Background context about people, places, projects
- Learnings and insights about the user''s life or work
- Details useful for recall but not needed on every request

If there are no new facts in either category, respond with "NO_NEW_FACTS".
Otherwise output two clearly labelled sections:
---CATEGORY A---
(one fact per line)
---CATEGORY B---
(one fact per line)',
        'uses_variable',   'conversations',
        'stores_as',       'extracted_facts'
    ),
    json_object(
        'order',           4,
        'description',     'Merge Category A facts into the existing memory prompt',
        'tool_name',       'system_update_memory_prompt',
        'uses_variable',   'extracted_facts'
    ),
    json_object(
        'order',           5,
        'description',     'Index Category B facts with today''s date stamp',
        'tool_name',       'system_index_memory_facts',
        'uses_variable',   'extracted_facts'
    )
)
WHERE steps IS NULL AND job_id = 'cron-system-memory';

-- Decompose the Nightly Soul Update prompt into a proper multi-step recipe.
UPDATE cron_jobs
SET steps = json_array(
    json_object(
        'order',       1,
        'description', 'Retrieve conversations from the last 24 hours',
        'tool_name',   'system_get_conversation_text',
        'stores_as',   'conversations'
    ),
    json_object(
        'order',            2,
        'description',      'Read the current soul prompt',
        'tool_name',        'system_get_prompt',
        'tool_parameters',  json_object('key', 'soul'),
        'stores_as',        'current_soul'
    ),
    json_object(
        'order',           3,
        'description',     'Analyse conversations for communication style and personality preferences',
        'prompt_template', 'You are performing the nightly soul/personality update. Analyse the conversation data and the current soul prompt below for communication style clues and explicit personality requests:
- Does the user prefer formal or casual tone?
- Are they asking for more detail or brevity?
- Did they express preferences about humour, emoji use, language?
- Did they explicitly say things like "be more friendly" or "keep it short"?

If there are no new style preferences, respond with "NO_STYLE_UPDATES".
Otherwise output the new personality or style preferences to merge, keeping existing traits. Do NOT remove or weaken existing personality traits unless the user explicitly asked for a change.',
        'uses_variable',   'conversations',
        'stores_as',       'style_updates'
    ),
    json_object(
        'order',           4,
        'description',     'Merge new style preferences into the soul prompt',
        'tool_name',       'system_update_soul_prompt',
        'uses_variable',   'style_updates'
    )
)
WHERE steps IS NULL AND job_id = 'cron-system-soul';

-- Any remaining prompt-type jobs not matched above get a generic single-step recipe.
UPDATE cron_jobs
SET steps = json_array(json_object(
    'order',           1,
    'description',     name,
    'prompt_template', prompt
))
WHERE steps IS NULL AND job_type = 'prompt';

-- Same for future_tasks
UPDATE future_tasks
SET steps = CASE job_type
    WHEN 'tool' THEN json_array(json_object(
        'order',            1,
        'description',      name,
        'tool_name',        tool_name,
        'tool_parameters',  json(COALESCE(tool_parameters, 'null'))
    ))
    ELSE json_array(json_object(
        'order',           1,
        'description',     name,
        'prompt_template', prompt
    ))
END
WHERE steps IS NULL;

-- Update the Coordinator skill context prompt to include recipe creation guidance.
UPDATE agent_definitions
SET backstory = 'You are the central coordinator for a personal assistant system.

IMPORTANT: The current date/time is provided as context. Use it for interpreting relative dates ("today", "tomorrow", "next week").

MEMORY AND UNKNOWN REFERENCES:
- When the user refers to something you don''t recognise (a person, project, place, etc.), delegate to the research agent to search memory using memory_recall.
- If the memory search doesn''t help, ask the user for more context before proceeding using the tool ask_user

RECIPE CREATION:
When a user asks to schedule a recurring task, create a recipe using create_cron_job with a steps array. Follow these rules strictly:

1. TOOL PINNING — For every step where the integration is clear from context, set tool_name. Never leave tool selection to chance on a step that will repeat on a schedule.
   Wrong: prompt_template "check my calendar" (might pick Google or Outlook randomly each run)
   Right: tool_name "google_calendar_list_events" (always the same tool, every run)

2. SELF-CONTAINED PROMPTS — When a step requires reasoning or dynamic content, write prompt_template as if starting fresh with no conversation history. No "that file", no "as mentioned", no references to prior context. Every word must be unambiguous to a reader who has never seen this conversation.

3. VARIABLE WIRING — When one step produces data that a later step needs, set stores_as on the producing step and uses_variable on the consuming step. Never rely on the LLM to remember output across steps — wire it explicitly.

4. ONE ACTION PER STEP — One distinct external action = one step. Do not bundle unrelated actions. If step B needs output from step A, they must be separate steps with stores_as/uses_variable.

5. STEP COUNT — Prefer the fewest steps that correctly model the task. A single well-pinned tool step is better than a verbose multi-step recipe that accomplishes the same thing.'
WHERE name = 'coordinator';

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('048_recipes');
