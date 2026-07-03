-- Migration: 053_artifacts
-- Adds the artifact store: a durable table tracking generated files (HTML, PDF,
-- DOCX, images, etc.) that the user can view, share, and delete from the new
-- Artifacts tab. Files live under the persistent data dir (not tmp), and rows
-- track visibility (public/private) and an optional passphrase gate.
--
-- Also registers the `store_artifact` system tool on the coordinator agent so
-- it can persist a generated file (by source_path) into this store by default.

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id TEXT UNIQUE NOT NULL,
    title TEXT,
    filename TEXT NOT NULL,
    rel_path TEXT NOT NULL,            -- path relative to the artifacts directory
    mime_type TEXT,
    size INTEGER,
    is_public INTEGER NOT NULL DEFAULT 0,
    secret_hash TEXT,                 -- NULL = no passphrase gate; else salted PBKDF2 hash
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at);

-- Assign the store_artifact tool to the coordinator agent by default.
UPDATE agent_definitions
SET
    tools = json_insert(tools, '$[#]', 'store_artifact'),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'coordinator'
  AND tools NOT LIKE '%store_artifact%';

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('053_artifacts');
