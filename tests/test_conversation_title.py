"""Tests for worker-model conversation title generation."""

from unittest.mock import MagicMock

from src.services.conversation import ConversationService
from src.services.memory import MemoryService


def _memory_with_llm(reply):
    svc = MemoryService.__new__(MemoryService)
    llm = MagicMock()
    llm.complete_text.return_value = reply
    svc._get_worker_llm_client = MagicMock(return_value=llm)
    return svc


def test_generate_title_cleans_and_caps_words():
    svc = _memory_with_llm('"Planning a very long trip to Japan next spring."\nextra')
    assert svc.generate_title("hi") == "Planning a very long trip to"


def test_generate_title_failure_returns_none():
    svc = MemoryService.__new__(MemoryService)
    svc._get_worker_llm_client = MagicMock(side_effect=RuntimeError("boom"))
    assert svc.generate_title("hi") is None
    assert svc.generate_title("   ") is None


def test_set_initial_title_stores_in_metadata_and_keeps_existing():
    repo = MagicMock()
    repo.get_by_id.return_value = {"metadata": {"pinned": True}}
    memory = MagicMock()
    memory.generate_title.return_value = "Trip planning"
    svc = ConversationService(repo, MagicMock(), memory)

    assert svc.set_initial_title("c1", "plan a trip") == "Trip planning"
    repo.update_metadata.assert_called_once_with("c1", {"pinned": True, "title": "Trip planning"})

    repo.reset_mock()
    repo.get_by_id.return_value = {"metadata": {"title": "Existing"}}
    assert svc.set_initial_title("c1", "x") == "Existing"
    repo.update_metadata.assert_not_called()


def test_with_title_and_pinned_overlays_metadata():
    from src.services.conversation import with_title_and_pinned

    out = with_title_and_pinned(
        {"conversation_id": "c1", "metadata": {"title": "T", "pinned": True}}
    )
    assert out["title"] == "T" and out["pinned"] is True
    out = with_title_and_pinned({"conversation_id": "c1", "metadata": None})
    assert out["title"] is None and out["pinned"] is False
    out = with_title_and_pinned({"conversation_id": "c1", "metadata": '{"title": "J"}'})
    assert out["title"] == "J"


def test_generate_conversation_title_uses_worker_and_never_stores_truncated_text():
    repo = MagicMock()
    repo.get_by_id.return_value = {"metadata": {"title": "Old", "pinned": True}}
    msgs = MagicMock()
    msgs.get_by_conversation.return_value = [{"role": "user", "content": "plan a trip to Japan"}]
    memory = MagicMock()
    memory.generate_title.return_value = "Japan trip planning"
    svc = ConversationService(repo, msgs, memory)

    assert svc.generate_conversation_title("c1") == "Japan trip planning"
    repo.update_metadata.assert_called_once_with(
        "c1", {"title": "Japan trip planning", "pinned": True}
    )

    repo.reset_mock()
    memory.generate_title.return_value = None
    assert svc.generate_conversation_title("c1") is None
    repo.update_metadata.assert_not_called()
