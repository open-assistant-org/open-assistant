"""Tests for ConversationService.search_conversations channel filtering.

The portal's Recent chats rail only wants chats started in the web UI. Without
a channel filter, a burst of scheduled runs (system), subagents (subtask) or
Slack/WhatsApp threads can push every webui chat off the first page.
"""

from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.message import MessageRepository
from src.services.conversation import ConversationService


def _service(db):
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)
    return conv_repo, msg_repo, ConversationService(conv_repo, msg_repo, memory_service=None)


def test_channel_filter_keeps_only_that_channel(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-web", channel="webui", contact_identifier="u1")
    msg_repo.create("c-web", "user", "trip plans")
    # More automated chats than a page holds, all newer than the webui chat
    for i in range(25):
        conv_repo.create(conversation_id=f"c-sys-{i}", channel="system", contact_identifier="cron")
        msg_repo.create(f"c-sys-{i}", "user", "morning briefing")

    res = svc.search_conversations(channel="webui", limit=20)

    assert [c["conversation_id"] for c in res["conversations"]] == ["c-web"]
    assert res["total"] == 1
    assert res["has_more"] is False
    assert res["conversations"][0]["title"] == "trip plans"


def test_channel_filter_combines_with_query(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-web", channel="webui", contact_identifier="u1")
    msg_repo.create("c-web", "user", "invoice for Acme")
    conv_repo.create(conversation_id="c-slack", channel="slack", contact_identifier="u2")
    msg_repo.create("c-slack", "user", "invoice for Globex")

    res = svc.search_conversations(query="invoice", channel="webui")

    assert [c["conversation_id"] for c in res["conversations"]] == ["c-web"]


def test_no_channel_returns_every_channel(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-web", channel="webui", contact_identifier="u1")
    conv_repo.create(conversation_id="c-sys", channel="system", contact_identifier="cron")

    res = svc.search_conversations()

    assert {c["conversation_id"] for c in res["conversations"]} == {"c-web", "c-sys"}
