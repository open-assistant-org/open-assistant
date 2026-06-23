-- ============================================================================
-- Migration: 052_add_cron_execution_lock_columns
-- Description: Add missing execution lock columns to cron_jobs.
--              Migration 043 registered '008_cron_execution_locking' as applied
--              but omitted execution_lock_instance and execution_lock_acquired_at
--              from its CREATE TABLE. Without them the scheduler silently skips
--              every job: the UPDATE ... WHERE execution_lock_instance IS NULL
--              raises OperationalError, which the caller treats as a failed lock
--              acquisition and returns without running the job.
--
--              Uses a table rebuild (create → copy → drop → rename) rather than
--              ALTER TABLE ADD COLUMN so the migration is safe regardless of
--              whether the lock columns already exist (e.g. from a partial
--              previous run). Lock state is intentionally not preserved — any
--              in-flight lock at migration time is stale.
-- Created: 2026-06-02
-- ============================================================================

-- Clean up any residue from a previous partial run of this migration.
DROP TABLE IF EXISTS cron_jobs_new;

CREATE TABLE cron_jobs_new (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id                      TEXT UNIQUE NOT NULL,
    name                        TEXT NOT NULL,
    description                 TEXT,
    cron_expression             TEXT NOT NULL,
    job_type                    TEXT NOT NULL,
    tool_name                   TEXT,
    tool_parameters             JSON,
    prompt                      TEXT,
    enabled                     BOOLEAN DEFAULT 1,
    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_run_at                 TIMESTAMP,
    next_run_at                 TIMESTAMP,
    steps                       JSON,
    required_skills             JSON,
    delivery_channel            TEXT,
    delivery_contact_identifier TEXT,
    execution_lock_instance     TEXT,
    execution_lock_acquired_at  TIMESTAMP
);

-- Copy all persistent columns. Lock-state columns (execution_lock_*) are left
-- NULL in the new table — any in-flight locks are stale after a restart.
-- steps / required_skills (048) and delivery_* (051) are always present by the
-- time this migration runs, as migrations execute in filename order.
INSERT INTO cron_jobs_new (
    id, job_id, name, description, cron_expression, job_type,
    tool_name, tool_parameters, prompt, enabled,
    created_at, updated_at, last_run_at, next_run_at,
    steps, required_skills,
    delivery_channel, delivery_contact_identifier
)
SELECT
    id, job_id, name, description, cron_expression, job_type,
    tool_name, tool_parameters, prompt, enabled,
    created_at, updated_at, last_run_at, next_run_at,
    steps, required_skills,
    delivery_channel, delivery_contact_identifier
FROM cron_jobs;

DROP TABLE cron_jobs;

ALTER TABLE cron_jobs_new RENAME TO cron_jobs;

CREATE INDEX IF NOT EXISTS idx_cron_jobs_enabled  ON cron_jobs(enabled);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_next_run ON cron_jobs(next_run_at);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_job_type ON cron_jobs(job_type);

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('052_add_cron_execution_lock_columns');
