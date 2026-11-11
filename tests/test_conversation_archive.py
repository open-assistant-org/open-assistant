"""Tests for archiving conversations.

Archived conversations keep their messages but drop out of the default
conversation list and search; ``archived=True`` lists only them.
"""

from src.core.repositories.conversation import ConversationRepository
from src.core.repositories.message import MessageRepository
from src.services.conversation import ConversationService


class _NoSummarize:
    def should_summarize(self, conversation_id):
        return False


def _service(db):
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)
    return conv_repo, msg_repo, ConversationService(conv_repo, msg_repo, _NoSummarize())


def _ids(result):
    return [c["conversation_id"] for c in result["conversations"]]


def test_archived_conversation_leaves_default_search_and_list(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-keep", channel="webui")
    msg_repo.create("c-keep", "user", "keep me")
    conv_repo.create(conversation_id="c-old", channel="webui")
    msg_repo.create("c-old", "user", "archive me")

    updated = svc.set_archived("c-old", True)

    assert updated["archived"] is True
    assert updated["title"] == "archive me"

    search = svc.search_conversations()
    assert _ids(search) == ["c-keep"]
    assert search["conversations"][0]["archived"] is False

    listed = svc.list_conversations()
    assert _ids(listed) == ["c-keep"]
    assert listed["total"] == 1

    archived_search = svc.search_conversations(archived=True)
    assert _ids(archived_search) == ["c-old"]
    assert archived_search["conversations"][0]["archived"] is True

    archived_list = svc.list_conversations(archived=True)
    assert _ids(archived_list) == ["c-old"]
    assert archived_list["total"] == 1

    # Messages are kept
    assert msg_repo.count_messages("c-old") == 1


def test_archived_search_matches_query(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-a", channel="webui")
    msg_repo.create("c-a", "user", "invoice for Acme")
    conv_repo.create(conversation_id="c-b", channel="webui")
    msg_repo.create("c-b", "user", "invoice for Globex")
    svc.set_archived("c-a", True)

    assert _ids(svc.search_conversations(query="invoice")) == ["c-b"]
    assert _ids(svc.search_conversations(query="invoice", archived=True)) == ["c-a"]


def test_unarchive_restores_conversation(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-1", channel="webui")
    svc.set_archived("c-1", True)

    updated = svc.set_archived("c-1", False)

    assert updated["archived"] is False
    assert _ids(svc.search_conversations()) == ["c-1"]
    assert _ids(svc.search_conversations(archived=True)) == []


def test_archiving_unpins_and_keeps_other_metadata(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(
        conversation_id="c-1", channel="webui", metadata={"title": "Trip plans", "pinned": True}
    )

    updated = svc.set_archived("c-1", True)

    assert updated["pinned"] is False
    assert updated["title"] == "Trip plans"
    assert conv_repo.get_by_id("c-1")["metadata"] == {
        "title": "Trip plans",
        "pinned": False,
        "archived": True,
    }


def test_set_archived_unknown_conversation_returns_none(clean_temp_db):
    _, _, svc = _service(clean_temp_db)

    assert svc.set_archived("missing", True) is None


def test_new_user_message_unarchives(clean_temp_db):
    conv_repo, msg_repo, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-wa", channel="whatsapp", contact_identifier="+32")
    svc.set_archived("c-wa", True)

    # Assistant and internal messages leave it archived
    svc.add_message("c-wa", "assistant", "reminder")
    svc.add_message("c-wa", "user", "system prompt row", is_internal=True)
    assert conv_repo.get_by_id("c-wa")["metadata"]["archived"] is True

    svc.add_message("c-wa", "user", "hi again")
    assert conv_repo.get_by_id("c-wa")["metadata"]["archived"] is False


def test_repo_filters_by_archived_and_channel(clean_temp_db):
    conv_repo, _, svc = _service(clean_temp_db)
    conv_repo.create(conversation_id="web-active", channel="webui")
    conv_repo.create(conversation_id="web-archived", channel="webui", metadata={"archived": True})
    conv_repo.create(conversation_id="sys-archived", channel="system", metadata={"archived": True})
    conv_repo.create(conversation_id="no-meta", channel="webui")

    assert conv_repo.count_conversations() == 4
    assert conv_repo.count_conversations(archived=False) == 2
    assert conv_repo.count_conversations(archived=True) == 2
    assert conv_repo.count_conversations("webui", archived=True) == 1
    ids = {c["conversation_id"] for c in conv_repo.list_conversations("webui", archived=False)}
    assert ids == {"web-active", "no-meta"}


def test_malformed_metadata_counts_as_not_archived(clean_temp_db):
    conv_repo, _, _ = _service(clean_temp_db)
    conv_repo.create(conversation_id="c-ok", channel="webui")
    conv_repo.execute_query(
        "UPDATE conversations SET metadata = ? WHERE conversation_id = ?", ("{not json", "c-ok")
    )

    assert conv_repo.count_conversations(archived=False) == 1
    assert conv_repo.count_conversations(archived=True) == 0


def test_archive_endpoints(clean_temp_db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api import conversations as api
    from src.core import dependencies

    conv_repo = ConversationRepository(clean_temp_db)
    msg_repo = MessageRepository(clean_temp_db)
    conv_repo.create(conversation_id="c-1", channel="webui")
    msg_repo.create("c-1", "user", "hello")

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[dependencies.get_conversation_repo] = lambda: conv_repo
    app.dependency_overrides[dependencies.get_message_repo] = lambda: msg_repo
    for dep in (
        dependencies.get_memory_repo,
        dependencies.get_prompts_repo,
        dependencies.get_settings_repo,
        dependencies.get_db_manager,
    ):
        app.dependency_overrides[dep] = lambda: None
    monkeypatch.setattr(api, "MemoryService", lambda *a, **k: _NoSummarize())
    client = TestClient(app)

    res = client.post("/api/conversations/c-1/archive")
    assert res.status_code == 200
    assert res.json()["archived"] is True

    assert client.get("/api/conversations/search").json()["conversations"] == []
    archived = client.get("/api/conversations/search?archived=true").json()
    assert [c["conversation_id"] for c in archived["conversations"]] == ["c-1"]
    listed = client.get("/api/conversations?archived=true").json()
    assert [c["conversation_id"] for c in listed["conversations"]] == ["c-1"]

    res = client.post("/api/conversations/c-1/unarchive")
    assert res.status_code == 200
    assert res.json()["archived"] is False

    assert client.post("/api/conversations/missing/archive").status_code == 404
