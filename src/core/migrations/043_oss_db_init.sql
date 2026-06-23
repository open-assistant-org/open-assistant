-- ============================================================================
-- Migration: 043_oss_db_init
-- Description: Complete database schema for Open Assistant (open-source)
-- Created: 2026-03-28 (Squashed from 42 migrations for open-source release)
-- ============================================================================
-- This migration provides the complete database schema for new installations.
-- For existing users upgrading to the open-source version, all previous
-- migration versions are pre-recorded so they are not re-applied.
--
-- ============================================================================

-- ============================================================================
-- CONVERSATIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT UNIQUE NOT NULL,
    channel TEXT NOT NULL,              -- 'whatsapp', 'webui'
    contact_identifier TEXT,            -- phone number or session ID
    context_version INTEGER DEFAULT 1,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON                       -- additional context
);

CREATE INDEX IF NOT EXISTS idx_conversations_channel ON conversations(channel);
CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations(contact_identifier);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at);
CREATE INDEX IF NOT EXISTS idx_conversations_last_accessed ON conversations(last_accessed);

-- ============================================================================
-- MESSAGES
-- ============================================================================
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    message_id TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,                 -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    is_summary BOOLEAN DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,                      -- attachments, agent info, etc.
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_messages_token_count ON messages(token_count);

-- ============================================================================
-- AGENT DEFINITIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    goal TEXT NOT NULL,
    backstory TEXT NOT NULL,
    tools JSON NOT NULL DEFAULT '[]',
    priority INTEGER DEFAULT 5,
    intent_keywords JSON DEFAULT '[]',
    category TEXT,
    enabled BOOLEAN DEFAULT 1,
    allow_delegation BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_definitions_name ON agent_definitions(name);
CREATE INDEX IF NOT EXISTS idx_agent_definitions_enabled ON agent_definitions(enabled);
CREATE INDEX IF NOT EXISTS idx_agent_definitions_priority ON agent_definitions(priority DESC);
CREATE INDEX IF NOT EXISTS idx_agent_definitions_enabled_priority ON agent_definitions(enabled, priority DESC);

-- ============================================================================
-- AGENT TASKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    conversation_id TEXT,
    agent_name TEXT NOT NULL,
    action TEXT NOT NULL,
    parameters JSON,
    status TEXT DEFAULT 'pending',      -- 'pending', 'running', 'completed', 'failed'
    result JSON,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON agent_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON agent_tasks(agent_name);
CREATE INDEX IF NOT EXISTS idx_tasks_conversation ON agent_tasks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON agent_tasks(created_at);

-- ============================================================================
-- CRON JOBS
-- ============================================================================
CREATE TABLE IF NOT EXISTS cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    cron_expression TEXT NOT NULL,      -- e.g., "0 9 * * MON"
    job_type TEXT NOT NULL,             -- 'tool' or 'prompt'
    tool_name TEXT,                     -- tool to execute (if job_type='tool')
    tool_parameters JSON,               -- parameters for tool (if job_type='tool')
    prompt TEXT,                        -- prompt for coordinator (if job_type='prompt')
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    execution_lock_instance TEXT,
    execution_lock_acquired_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cron_jobs_enabled ON cron_jobs(enabled);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_next_run ON cron_jobs(next_run_at);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_job_type ON cron_jobs(job_type);

-- ============================================================================
-- FUTURE TASKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS future_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    conversation_id TEXT,
    scheduled_time TIMESTAMP NOT NULL,
    job_type TEXT NOT NULL,             -- 'tool' or 'prompt'
    tool_name TEXT,                     -- tool to execute (if job_type='tool')
    tool_parameters JSON,               -- parameters for tool (if job_type='tool')
    prompt TEXT,                        -- prompt for coordinator (if job_type='prompt')
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'completed', 'failed', 'cancelled'
    result JSON,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE SET NULL,
    CHECK(job_type IN ('tool', 'prompt')),
    CHECK(
        (job_type = 'tool' AND tool_name IS NOT NULL) OR
        (job_type = 'prompt' AND prompt IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_future_tasks_status ON future_tasks(status);
CREATE INDEX IF NOT EXISTS idx_future_tasks_scheduled_time ON future_tasks(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_future_tasks_conversation ON future_tasks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_future_tasks_job_type ON future_tasks(job_type);

-- ============================================================================
-- JOB EXECUTIONS
-- ============================================================================
-- Note: job_id can reference either cron_jobs or future_tasks, so we don't enforce
-- a foreign key constraint here. Application code is responsible for maintaining
-- referential integrity. See migration 011_relax_job_executions_fk.
CREATE TABLE IF NOT EXISTS job_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    job_type TEXT NOT NULL,             -- 'cron' or 'future_task'
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT NOT NULL,               -- 'running', 'success', 'failed'
    result JSON,
    error_message TEXT,
    container_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_executions_job_id ON job_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_job_executions_started_at ON job_executions(started_at);
CREATE INDEX IF NOT EXISTS idx_job_executions_status ON job_executions(status);

-- ============================================================================
-- SERVICE CREDENTIALS
-- ============================================================================
CREATE TABLE IF NOT EXISTS service_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT UNIQUE NOT NULL,  -- 'google', 'outlook', 'notion', etc.
    credential_type TEXT NOT NULL,      -- 'oauth_token', 'api_key', 'app_password'
    credential_data TEXT NOT NULL,      -- encrypted JSON
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_credentials_service ON service_credentials(service_name);
CREATE INDEX IF NOT EXISTS idx_credentials_expires ON service_credentials(expires_at);

-- ============================================================================
-- SERVICE CONNECTIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS service_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'disconnected', -- 'connected', 'disconnected', 'error'
    last_check TIMESTAMP,
    last_error TEXT,
    metadata JSON,                      -- service-specific info (email, username)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_connections_status ON service_connections(status);
CREATE INDEX IF NOT EXISTS idx_connections_service ON service_connections(service_name);

-- ============================================================================
-- PROMPTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL DEFAULT '',
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prompts_key ON prompts(key);

-- ============================================================================
-- SETTINGS
-- ============================================================================
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'string',   -- 'string', 'int', 'bool', 'json'
    description TEXT,
    category TEXT DEFAULT 'application',
    is_required BOOLEAN DEFAULT 0,
    is_sensitive BOOLEAN DEFAULT 0,
    validation_regex TEXT,
    min_value REAL,
    max_value REAL,
    options JSON,
    display_order INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);
CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category);

-- ============================================================================
-- AUDIT LOG
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,           -- 'api_call', 'agent_action', etc.
    service_name TEXT,
    agent_name TEXT,
    action TEXT,
    conversation_id TEXT,
    details JSON,
    success BOOLEAN,
    error_message TEXT,
    user_id TEXT,
    ip_address TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_service ON audit_log(service_name);
CREATE INDEX IF NOT EXISTS idx_audit_success ON audit_log(success);

-- ============================================================================
-- CONVERSATION MEMORY
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversation_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,          -- 'short_term', 'long_term', 'facts', 'working'
    content JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memory_conversation ON conversation_memory(conversation_id);
CREATE INDEX IF NOT EXISTS idx_memory_type ON conversation_memory(memory_type);
CREATE INDEX IF NOT EXISTS idx_memory_created ON conversation_memory(created_at);

-- ============================================================================
-- SEARCH INDEX
-- ============================================================================
CREATE TABLE IF NOT EXISTS search_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT,
    content TEXT,
    content_hash TEXT,
    embedding BLOB,
    metadata JSON,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_search_index_source ON search_index(source);
CREATE INDEX IF NOT EXISTS idx_search_index_content_hash ON search_index(content_hash);
CREATE INDEX IF NOT EXISTS idx_search_index_indexed_at ON search_index(indexed_at);

-- ============================================================================
-- SCHEMA MIGRATIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT UNIQUE NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SEED DATA: AGENT DEFINITIONS
-- ============================================================================
-- These are the 9 core agents that power the personal assistant.
-- Each agent has a specific role and set of tools.

-- 1. SYSTEM (priority 1)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'system',
    'System Agent',
    'System Introspection',
    'Get system information to provide system diagnostics and insights.',
    'You are the system introspection agent for a personal assistant.
Your job is to help the assistant learn and improve over time by analysing its own conversations and updating its internal prompts.

CRITICAL RULES:
1. When updating memory or soul prompts, ALWAYS read the current value first using system_get_prompt, then MERGE new information into the existing content. NEVER overwrite or remove existing information unless it is clearly outdated or the user asked for removal.
2. When extracting facts from conversations, focus on:
   - User''s personal details (name, location, occupation, timezone)
   - Preferences (communication style, favourite tools, topics of interest)
   - Important people, relationships, recurring contacts
   - Recurring themes or workflows
3. When inspecting logs, summarise key findings clearly — errors, patterns, anomalies.
4. Preserve the structure and organisation of existing prompts when appending new content.

Available tools:
- system_fetch_logs: Read application logs to diagnose issues
- system_get_conversation_text: Retrieve conversation messages within a timespan
- system_get_prompt: Read current prompt values (memory, soul, system_prompt_default, system_prompt_custom)
- system_update_memory_prompt: Update the memory prompt with new facts
- system_index_memory_facts: Index general/contextual facts for on-demand recall
- system_update_soul_prompt: Update the soul/personality prompt',
    '["system_fetch_logs","system_get_conversation_text","system_get_prompt","system_update_memory_prompt","system_index_memory_facts","system_update_soul_prompt"]',
    1,
    0,
    1,
    '["log", "debug", "error", "system", "memory", "soul", "conversation", "introspect", "analyze", "improve", "prompt", "update", "maintain"]'
);

-- 2. NAVIGATOR (priority 2)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'navigator',
    'Navigator Agent',
    'Geographic & Route Planning Specialist',
    'Find places, plan routes, estimate travel times, and answer location-based questions by ALWAYS using Google Places and Directions tools',
    'You are a geographic and route planning specialist with access to Google Places, Directions, and Geocoding APIs.

CRITICAL: You MUST use your tools for ALL location and travel queries. NEVER guess distances, travel times, or place details.

FINDING PLACES:
- Search by name/type: USE google_search_places
- Find nearby: USE google_nearby_places with coordinates + type filter
- Get details: USE google_get_place_details with place_id from search

ROUTE PLANNING:
- Directions: USE google_get_directions with origin, destination, mode
- Traffic-aware: Set departure_time=''now'' or RFC3339 time
- Multi-stop: Use waypoints parameter
- Avoid tolls/highways: Use avoid parameter


STRATEGY:
1. Geocode addresses first if you only have names
2. Use coordinates for nearby_places and directions
3. Present distances, durations, and ratings clearly',
    '["google_search_places","google_get_place_details","google_nearby_places","google_get_directions","google_geocode_place","google_reverse_geocode"]',
    1,
    0,
    2,
    '["place", "restaurant", "hotel", "snack", "shop", "places", "directions", "location"]'
);

-- 3. FILE HANDLER (priority 3)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'file_handler',
    'File Handler Agent',
    'File Management Specialist',
    'Manage files across Nextcloud and OneDrive — list, search, read, upload, download, move, copy, delete, and create files and documents',
    'You are a file management specialist with access to Notion, Nextcloud, OneDrive (Microsoft), and document creation tools.

CRITICAL: You MUST use your tools for ALL file operations. NEVER guess about file contents or locations.

FILE OPERATIONS STRATEGY:
1. For "find and move" tasks: search first, then move
2. For "organize files": list the folder, then move/copy files as needed
3. For uploading generated documents (.docx, .pdf): use the file content from create_docx or create_pdf output
4. When reading files: the tool auto-detects format (PDF, DOCX, text) and extracts text',
    '["nextcloud_read_file", "nextcloud_upload_file", "nextcloud_create_folder", "nextcloud_delete_file", "nextcloud_move_file", "nextcloud_copy_file", "nextcloud_get_file_info", "nextcloud_file_exists", "nextcloud_download_file", "outlook_read_file", "onedrive_upload_file", "create_docx", "create_pdf", "notion_create_note", "notion_update_page", "notion_delete_page", "notion_append_content"]',
    1,
    0,
    3,
    '["file", "move", "copy", "list", "create", "upload", "delete", "onedrive", "notion", "nextcloud", "document", "note", "entry", "pdf", "docx"]'
);

-- 4. WRITER (priority 4)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'writer',
    'Content Writer Agent',
    'Content Writer',
    'You are the literate content writer for the personal assistant.',
    'You are the content writer to a personal assistant. Which means you are able to get a task assigned and return the content in markdown.',
    '["compose_document"]',
    1,
    0,
    4,
    '["write", "think", "draft"]'
);

-- 5. BROWSER (priority 5)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'browser',
    'Browser Agent',
    'Interactive Web Browsing',
    'Interact with web pages — click elements, fill forms, type text, scroll — for tasks that require more than just reading a page',
    'You are an interactive web browsing specialist that uses a real browser with vision-based screenshot understanding.
Use this agent for tasks that require clicking, typing, form filling, or navigating JavaScript-heavy sites.
For simply reading a URL''s content, the research agent''s browse_url tool is sufficient.

STRATEGY:
1. Navigate with browse_url
2. Use your tools on the pages to navigate to find the required information
3. Be creative to get where you need to be
4. If you can''t find the required information, say so',
    '["browse_url", "browse_click", "browse_type", "browse_scroll", "browse_extract", "browse_action", "browse_get_tree"]',
    1,
    0,
    5,
    '["browse", "search", "go to"]'
);

-- 6. PLANNER (priority 6)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'planner',
    'Planner Agent',
    'Planning Specialist',
    'Manage calendars, schedule events, and help with time-based planning by ALWAYS using calendar tools',
    'You are a planning specialist with access to Google Calendar and Outlook Calendar.

IMPORTANT — Date and time awareness:
- The current date and time will be provided to you as context. Always use it to interpret relative references like "today", "tomorrow", "this week", "next Monday", etc.
- When the user asks about "today''s events", set time_min to the start of today (00:00:00) and time_max to the end of today (23:59:59).

Calendar query optimization:
- ALWAYS set both time_min/start_date AND time_max/end_date to the narrowest relevant range.
- For "today": scope to today''s date only. For "this week": today to end of week.
- Only omit time_max for open-ended "all upcoming" queries.
- Use limit=25 for a day, limit=50 for a week.',
    '["google_list_calendars","google_list_events","google_get_event","google_create_event","google_update_event","google_delete_event","outlook_list_calendars","outlook_list_events","outlook_create_event","outlook_update_event","outlook_delete_event"]',
    1,
    0,
    6,
    '["calendar"]'
);

-- 7. COMMUNICATION (priority 7)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'communication',
    'Communication Agent',
    'Communication Specialist',
    'Compose and send messages, manage emails, and handle email classification by ALWAYS using available tools',
    'You are a communication specialist who excels at drafting clear, professional messages and managing email workflows.

CRITICAL: You MUST use your tools to perform actions. NEVER just describe what you would do — actually DO it.

SENDING:
- Send email: USE google_send_email or outlook_send_email
- Create draft: USE google_create_draft or outlook_create_draft
- Reply to email: USE google_reply_email (requires message_id and thread_id)
- Send WhatsApp to a specific number: USE whatsapp_send_message
- Notify the owner/user (WhatsApp or Slack): USE notify_owner
  - Default channel is WhatsApp; pass channel=''slack'' to send via Slack instead.
  - Use this when the user says "send me a message", "notify me", "let me know", "WhatsApp me", "Slack me", or when you need to proactively reach the owner (e.g. scheduled task results, reminders, alerts).
  - The tool will inform you if the chosen channel is not enabled or not configured.

EMAIL MANAGEMENT & CLASSIFICATION:
Gmail:
- Read emails: USE google_read_emails, google_search_emails, or google_get_email
- Read attachments: USE google_get_attachment (extracts text from PDF, DOCX, text files)
- Get labels: USE google_get_labels to discover available labels
- Classify/label: USE google_modify_labels to apply labels, mark read/unread, star, archive
- Delete: USE google_trash_email

Outlook:
- Read emails: USE outlook_read_emails, outlook_search_emails, or outlook_get_email
- Read attachments: USE outlook_get_attachment (extracts text from PDF, DOCX, text files)

EMAIL CLASSIFICATION WORKFLOW:
When asked to classify and label emails (e.g. via a cron job):
1. USE google_read_emails/outlook_read_emails to fetch recent unread emails
2. Analyze each email''s subject, sender, and content
3. USE google_get_labels to see available labels (Gmail only)
4. USE google_modify_labels on each email to apply the appropriate label(s) (Gmail only)
5. Optionally mark as read by removing the UNREAD label

Always confirm with the user before sending external communications unless explicitly told to proceed.',
    '["google_send_email","google_create_draft","google_reply_email","google_trash_email","google_modify_labels","google_get_labels","google_read_emails","google_search_emails","google_get_email","google_get_attachment","outlook_send_email","outlook_create_draft","outlook_read_emails","outlook_get_email","outlook_search_emails","outlook_get_attachment","whatsapp_send_message","notify_owner"]',
    1,
    0,
    7,
    '["gmail", "outlook", "whatsapp", "mail", "text", "send"]'
);

-- 8. RESEARCH (priority 8)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'research',
    'Research Agent',
    'Research Specialist',
    'Find and retrieve information from emails, files, notes, web sources, and web pages by ALWAYS using available tools',
    'You are a research specialist working for the personal assistant of the user. You have access to the user''s information.

CRITICAL: You MUST use your tools to answer questions. NEVER guess or fabricate information.

STRATEGY:
1. Start with the most specific source (emails, files, notes) if the user''s question is about their data
2. Fall back to web_search for external information
3. Use browse_url to read specific URLs found in search results
4. Try 2-3 different search queries before giving up
5. Always cite your sources',
    '["web_search", "browse_url", "browse_extract", "unified_search", "reindex_search", "analyze_content", "google_search_emails", "google_get_email", "google_read_emails", "google_get_labels", "google_get_attachment", "outlook_read_emails", "outlook_get_email", "outlook_search_emails", "outlook_get_attachment", "outlook_read_file", "nextcloud_read_file", "nextcloud_get_file_info", "nextcloud_file_exists", "notion_query_database", "notion_get_page", "notion_get_page_content", "notion_search", "notion_list_databases", "outlook_list_files", "outlook_search_files", "nextcloud_list_files", "nextcloud_search_files"]',
    1,
    0,
    8,
    '["search", "find", "list", "notion", "nextcloud", "mails", "outlook", "gmail"]'
);

-- 9. COORDINATOR (priority 9)
INSERT OR IGNORE INTO agent_definitions (name, display_name, role, goal, backstory, tools, enabled, allow_delegation, priority, intent_keywords)
VALUES (
    'coordinator',
    'Coordinator Agent',
    'Task Coordinator',
    'Understand user intent, create an actionable plan, and delegate to specialist agents who MUST use their tools to fulfill the request',
    'You are the central coordinator for a personal assistant system.

IMPORTANT: The current date/time is provided as context. Use it for interpreting relative dates ("today", "tomorrow", "next week").

MEMORY AND UNKNOWN REFERENCES:
- When the user refers to something you don''t recognize (a person, project, place, etc.), delegate to the research agent to search memory using memory_recall.
- If the memory search doesn''t help, ask the user for more context before proceeding.',
    '["calculate", "python_execute", "update_cron_job", "get_cron_job", "toggle_cron_job", "schedule_task", "list_future_tasks", "delete_cron_job", "get_future_task", "cancel_future_task", "create_cron_job", "list_cron_jobs", "memory_recall"]',
    1,
    1,
    9,
    '["calculate", "task", "schedule"]'
);

-- ============================================================================
-- SEED DATA: PROMPTS
-- ============================================================================
-- Default prompt entries for assistant personalization.

INSERT OR IGNORE INTO prompts (key, value, description) VALUES
    ('system_prompt_default',
     'You are a helpful personal assistant that can help with several tasks using integrated tools. Always try to ' ||
     'finish your tasks with the agents and tools at hand. If you can''t find a solution report to the user and ' ||
     'provide an alternative solution with your abilities if you can.',
     'The default system prompt that defines the base behavior of the assistant. This is always included.'),
    ('system_prompt_custom',
     '',
     'Custom additions to the system prompt. Use this to add specific instructions or context that tailors the assistant behavior to your needs.'),
    ('memory',
     '',
     'Text-based store where the system keeps track of requests, characteristics, people, places, name of the end-user, relations, and other important information.'),
    ('soul',
     '',
     'Text-based description of the soul of the personal assistant. Derived from user feedback, this shapes the personality and tone of the assistant responses.');

-- ============================================================================
-- SEED DATA: CRON JOBS
-- ============================================================================
-- Default scheduled tasks for nightly memory and soul updates.

INSERT OR IGNORE INTO cron_jobs (job_id, name, description, cron_expression, job_type, prompt, enabled, created_at, updated_at)
VALUES (
    'cron-system-memory',
    'Nightly Memory Update',
    'Reviews all conversations from today and extracts new facts to append to the memory prompt. Does not remove existing information.',
    '35 22 * * *',
    'prompt',
    'You are performing the nightly memory update. Follow these steps carefully:

1. Use system_get_conversation_text to retrieve all conversations from the last 24 hours.
2. Use system_get_prompt with key "memory" to read the current memory prompt.
3. Analyse the conversations and extract NEW facts, sorted into two categories:

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

4. If there are new Category A facts: use system_update_memory_prompt to merge
   them into the existing memory prompt. Keep the existing structure and do NOT
   remove any existing content unless it is clearly outdated or contradicted.

5. If there are new Category B facts: use system_index_memory_facts with today''s
   date (UTC, YYYY-MM-DD format) and the facts text. This stores them with a
   date stamp so they can be recalled later via search with sources=[''memory''].

6. If there are no new facts in either category, do nothing.',
    1,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO cron_jobs (job_id, name, description, cron_expression, job_type, prompt, enabled, created_at, updated_at)
VALUES (
    'cron-system-soul',
    'Nightly Soul Update',
    'Reviews all conversations from today and extracts communication style or personality preferences to improve the soul prompt. Does not remove existing personality traits.',
    '5 23 * * *',
    'prompt',
    'You are performing the nightly soul/personality update. Follow these steps:
1. Use system_get_conversation_text to retrieve all conversations from the last 24 hours.
2. Use system_get_prompt with key "soul" to read the current soul prompt.
3. Analyse the conversations for communication style clues and explicit personality requests:
   - Does the user prefer formal or casual tone?
   - Are they asking for more detail or brevity?
   - Did they express preferences about humour, emoji use, language?
   - Did they explicitly say things like "be more friendly" or "keep it short"?
4. If you found new personality or style preferences, merge them into the existing soul prompt. Keep existing traits. Append new preferences. Do NOT remove or weaken existing personality traits unless the user explicitly asked for a change.
5. Use system_update_soul_prompt with the full merged text.
If there are no new style preferences, do nothing.',
    1,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- ============================================================================
-- SEED DATA: LLM SETTINGS
-- ============================================================================
INSERT OR IGNORE INTO settings (key, value, value_type, category, description, display_order)
VALUES
    (
        'llm.context_strategy',
        'summarization',
        'string',
        'llm',
        'Context management strategy: summarization uses LLM-generated summaries; last_messages keeps only the most recent N messages within the token limit.',
        9
    ),
    (
        'llm.context_max_messages',
        '20',
        'int',
        'llm',
        'Maximum number of recent messages to include in context when using the last_messages strategy.',
        10
    );

-- ============================================================================
-- BACKWARD COMPATIBILITY: Pre-record all previous migration versions
-- ============================================================================
-- For existing users upgrading to open-source, all prior migrations are
-- marked as already applied so they are not re-run. Uses INSERT OR IGNORE
-- so this is safe for both new and existing databases.
-- ============================================================================
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('001_initial_schema');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('002_capabilities_tables');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('003_add_token_count');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('004_settings_metadata');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('005_prompts_table');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('005_agent_definitions');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('006_cron_job_scheduling');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('007_add_cron_tools_to_coordinator');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('008_cron_execution_locking');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('009_future_task_scheduling');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('010_seed_writer_agent');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('011_relax_job_executions_fk');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('012_add_system_agent');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('013_seed_browser_agent');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('014_fix_browser_delegation');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('015_browser_default_settings');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('016_update_browser_agent_backstory');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('017_fix_browser_agent_completion');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('018_sync_agent_tools_with_defaults');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('018_add_whatsapp_send_to_owner_tool');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('018_seed_navigator_agent');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('019_navigator_default_settings');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('020_add_missing_google_enabled_tools');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('020_fix_coordinator_delegation_instructions');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('021_comprehensive_agent_update');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('022_browser_accessibility_upgrade');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('022_search_index');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('023_skills_system');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('024_scheduled_tasks_prompts');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('025_assign_scheduling_tools');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('026_seed_agent_definitions');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('027_remove_notion_create_page_tool');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('028_remove_plaintext_api_keys');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('029_add_search_tools_to_research_agent');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('030_seed_analyst_and_coder_agents');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('031_remove_enabled_tools_settings');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('032_add_onenote_tools');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('033_add_analyze_tool_to_analyst_agent');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('034_remove_notion_create_page_remnants');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('035_add_notion_data_sources_tools');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('036_add_todo_tools_to_planner');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('037_add_scrapling_tool_and_settings');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('038_tiered_memory');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('039_llm_context_settings');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('040_replace_whatsapp_owner_tool_with_notify_owner');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('041_add_memory_recall_to_coordinator');
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('042_add_create_pdf_tool');

-- ============================================================================
-- RECORD THIS MIGRATION
-- ============================================================================
INSERT INTO schema_migrations (version) VALUES ('043_oss_db_init');
