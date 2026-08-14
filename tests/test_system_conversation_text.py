"""Tests for SystemService.get_conversation_text activity filtering.

These cover the fixes that make the nightly memory/soul jobs' "is there any
activity?" probe accurate:
- internal/transparency rows (is_internal=1) are excluded
- the 'system' channel (the jobs' own scheduled runs) is excluded when no
  explicit channel is requested
- the `hours` parameter yields a true rolling window
"""

from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.message import MessageRepository
from src.services.system import SystemService


def _seed(db):
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    # A real user conversation on the webui channel.
    conv_repo.create(conversation_id="c-user", channel="webui", contact_identifier="u1")
    msg_repo.create("c-user", "user", "hello there")
    msg_repo.create("c-user", "assistant", "hi, how can I help?")
    # A transparency/internal row inside the same conversation — must be ignored.
    msg_repo.create("c-user", "assistant", "SYSTEM PROMPT DUMP", is_internal=True)

    # The nightly job's own scheduled run, on the 'system' channel — must be
    # ignored so the job never counts itself as user activity.
    conv_repo.create(conversation_id="c-sys", channel="system", contact_identifier="cron_x")
    msg_repo.create("c-sys", "user", "nightly memory update prompt")
    msg_repo.create("c-sys", "assistant", "extracted some facts")


def test_excludes_internal_and_system_channel(clean_temp_db):
    _seed(clean_temp_db)
    svc = SystemService(db_manager=clean_temp_db)

    res = svc.get_conversation_text(hours=24)

    assert res["success"] is True
    # Only the 2 real user/assistant rows from the webui conversation.
    assert res["total_messages"] == 2
    channels = {m["channel"] for m in res["messages"]}
    assert channels == {"webui"}
    contents = [m["content"] for m in res["messages"]]
    assert "SYSTEM PROMPT DUMP" not in contents


def test_empty_when_only_system_activity(clean_temp_db):
    """A day where only the jobs themselves 'talked' reads as idle."""
    conv_repo = ConversationRepository(clean_temp_db)
    msg_repo = MessageRepository(clean_temp_db)
    conv_repo.create(conversation_id="c-sys", channel="system", contact_identifier="cron_x")
    msg_repo.create("c-sys", "assistant", "job chatter")

    svc = SystemService(db_manager=clean_temp_db)
    res = svc.get_conversation_text(hours=24)

    assert res["success"] is True
    assert res["total_messages"] == 0
    assert res["messages"] == []


def test_explicit_channel_still_filters_internal(clean_temp_db):
    _seed(clean_temp_db)
    svc = SystemService(db_manager=clean_temp_db)

    res = svc.get_conversation_text(hours=24, channel="webui")

    assert res["total_messages"] == 2
    assert all(m["channel"] == "webui" for m in res["messages"])
