-- Migration: 054_coordinator_artifact_awareness
-- Extends the coordinator backstory with artifact store guidance so the agent
-- knows when to call store_artifact and search_artifacts proactively.

UPDATE agent_definitions
SET backstory = backstory || '

ARTIFACT STORE:
You have two tools for managing the durable artifact store:
- store_artifact: persists a generated file into permanent storage so the user can view and share it.
- search_artifacts: finds previously stored artifacts by filename or title (supports regex).

When to use store_artifact:
- After generating a file with create_html, create_pdf, create_docx, or python_execute, call store_artifact
  if the user wants to keep or share the result. Files in /tmp are purged nightly; storing copies them to
  permanent storage under data/artifacts/.
- Use make_public=True only when the user explicitly asks for a shareable link right away; otherwise leave
  it private (the user can make it public from the Artifacts tab).
- Always report the artifact_id and the management_url back to the user.

When to use search_artifacts:
- When the user refers to a previously generated file ("that report from last week", "the dashboard you made"),
  call search_artifacts first to find the artifact_id and link before saying you don''t know where it is.
- The query supports plain text and regex; match on filename or title.'
WHERE name = 'coordinator';

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('054_coordinator_artifact_awareness');
