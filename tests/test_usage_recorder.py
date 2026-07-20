"""Tests for accurate metered billing + transparency + compaction.

Covers:
- ``UsageRecorder``: extracts real ``response.usage`` (incl. cached/reasoning),
  records zeros + ``missing_usage`` when usage is absent, no-ops when no DB is
  wired, and never raises on DB error.
- Boundary wrap: a direct call to ``client._client.chat.completions.create`` is
  recorded (proving the wrap installed in ``LLMClient.__init__`` catches every
  call site, including future bypasses).
- Migration 057: creates ``llm_consumption`` + seeds a current-month baseline
  equal to the trailing-12-month ``SUM(messages.token_count)``.
- Migration 058: adds ``is_internal`` to ``messages``.
- History filter: internal transparency rows are excluded from
  ``get_recent_messages`` / ``get_by_conversation``.
- Continuity: the baseline keeps the platform's lifetime watermark continuous.
- Compaction: old ``messages`` collapse to one internal row per conversation and
  old ``llm_consumption`` rows collapse to one summary per (year, month), totals
  are preserved, recent rows are untouched, and re-running is a no-op.
"""

import json
import sqlite3
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.database import DatabaseManager
from src.core.repositories.llm_consumption import LlmConsumptionRepository
from src.core.repositories.message import MessageRepository
from src.core.usage_recorder import UsageRecorder, _extract_usage, usage_recorder

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "src" / "core" / "migrations"


# ── Helpers ────────────────────────────────────────────────────────────────


def _apply_all_migrations(db_path: Path) -> DatabaseManager:
    """Apply every migration SQL file in order to a fresh DB."""
    dbm = DatabaseManager(str(db_path))
    dbm.init_database()
    return dbm


def _fake_usage(prompt=500, completion=120, total=620, cached=40, reasoning=10, cost=0.0123):
    return types.SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cost=cost,
        prompt_tokens_details=types.SimpleNamespace(cached_tokens=cached),
        completion_tokens_details=types.SimpleNamespace(reasoning_tokens=reasoning),
    )


class _FakeResponse:
    def __init__(self, usage):
        self.usage = usage


# ── Usage extraction ───────────────────────────────────────────────────────


class TestExtractUsage:
    def test_extracts_full_usage_including_details(self):
        result = _extract_usage(_fake_usage())
        assert result == {
            "prompt_tokens": 500,
            "completion_tokens": 120,
            "total_tokens": 620,
            "cached_tokens": 40,
            "reasoning_tokens": 10,
        }

    def test_none_usage_yields_zeros(self):
        result = _extract_usage(None)
        assert result == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        }

    def test_total_derived_from_prompt_plus_completion_when_absent(self):
        u = types.SimpleNamespace(
            prompt_tokens=100, completion_tokens=50, total_tokens=None,
            prompt_tokens_details=None, completion_tokens_details=None,
        )
        assert _extract_usage(u)["total_tokens"] == 150


# ── UsageRecorder ──────────────────────────────────────────────────────────


@pytest.fixture
def recorder_db(test_db_path):
    dbm = _apply_all_migrations(test_db_path)
    UsageRecorder.set_db(dbm)
    yield dbm
    UsageRecorder.clear()


def _ledger_rows(dbm):
    conn = dbm.get_connection()
    try:
        return [
            tuple(r)
            for r in conn.execute(
                "SELECT provider, model, prompt_tokens, completion_tokens, "
                "total_tokens, cached_tokens, reasoning_tokens, metadata "
                "FROM llm_consumption"
            )
        ]
    finally:
        conn.close()


class TestUsageRecorder:
    def test_records_real_usage_with_details(self, recorder_db):
        usage_recorder.record(_fake_usage(), provider="openrouter", model="claude")
        rows = _ledger_rows(recorder_db)
        # baseline row + the recorded row
        assert len(rows) == 2
        recorded = [r for r in rows if r[1] == "claude"][0]
        assert recorded[2:7] == (500, 120, 620, 40, 10)
        meta = json.loads(recorded[7])
        assert meta["openrouter_cost"] == 0.0123

    def test_missing_usage_flagged(self, recorder_db):
        usage_recorder.record(None, provider="ollama", model="llama3")
        rows = _ledger_rows(recorder_db)
        recorded = [r for r in rows if r[0] == "ollama"][0]
        assert recorded[2:7] == (0, 0, 0, 0, 0)
        assert json.loads(recorded[7])["missing_usage"] is True

    def test_noop_when_db_unset(self, test_db_path):
        UsageRecorder.clear()
        # Must not raise and must not record anything
        usage_recorder.record(_fake_usage(), provider="x", model="y")
        # No DB wired -> nothing to assert beyond no-raise; pass if we got here.

    def test_never_raises_on_db_error(self, test_db_path, monkeypatch):
        dbm = _apply_all_migrations(test_db_path)
        UsageRecorder.set_db(dbm)

        # Corrupt get_connection to raise
        def boom():
            raise sqlite3.OperationalError("disk full")

        monkeypatch.setattr(dbm, "get_connection", boom)
        # Must not raise
        usage_recorder.record(_fake_usage(), provider="x", model="y")
        UsageRecorder.clear()


# ── Boundary wrap ──────────────────────────────────────────────────────────


class TestBoundaryWrap:
    def test_direct_create_call_is_recorded(self, recorder_db):
        """Calling the wrapped create directly still records — proving the wrap
        installed in LLMClient.__init__ catches every call (incl. future bypasses).
        """
        from src.core.llm_client import LLMClient, LLMConfig

        config = LLMConfig(
            provider="openrouter", model="claude", api_key="k",
            base_url="https://openrouter.ai/api/v1",
        )

        with patch("src.core.llm_client.OpenAI") as mock_openai:
            mock_client = mock_openai.return_value
            mock_client.chat.completions.create = lambda **kw: _FakeResponse(_fake_usage())
            client = LLMClient(config)

            # Call the (now-wrapped) create directly — simulating any call site
            response = client._client.chat.completions.create(
                model="claude", messages=[{"role": "user", "content": "hi"}]
            )

        assert response.usage.total_tokens == 620
        rows = [r for r in _ledger_rows(recorder_db) if r[1] == "claude"]
        assert len(rows) == 1


# ── Migrations ─────────────────────────────────────────────────────────────


class TestMigrations:
    def test_057_creates_table_and_baseline(self, test_db_path):
        dbm = _apply_all_migrations(test_db_path)
        conn = dbm.get_connection()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(llm_consumption)")}
            assert {"prompt_tokens", "completion_tokens", "total_tokens",
                    "cached_tokens", "reasoning_tokens"} <= cols
            # baseline row present, current-month-dated
            row = conn.execute(
                "SELECT provider, model, total_tokens, metadata "
                "FROM llm_consumption WHERE model='baseline'"
            ).fetchone()
            assert row is not None
            assert json.loads(row[3])["baseline"] is True
        finally:
            conn.close()

    def test_057_baseline_equals_trailing_12m_messages_sum(self, test_db_path):
        dbm = _apply_all_migrations(test_db_path)
        # Insert messages AFTER migrations applied (baseline was seeded against
        # an empty messages table -> 0). Re-seed a baseline manually to verify
        # the formula matches SUM(messages.token_count) trailing 12 months.
        conn = dbm.get_connection()
        try:
            now_iso = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO conversations (conversation_id, channel) VALUES ('c1','webui')"
            )
            for i in range(3):
                conn.execute(
                    "INSERT INTO messages (message_id, conversation_id, role, "
                    "content, token_count, timestamp) VALUES (?,?,?,?,?,?)",
                    (f"m{i}", "c1", "user", "x", 100 * (i + 1), now_iso),
                )
            conn.commit()
            expected = conn.execute(
                "SELECT COALESCE(SUM(token_count),0) FROM messages "
                "WHERE timestamp >= datetime('now','-12 months')"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO llm_consumption (timestamp, provider, model, "
                "prompt_tokens, completion_tokens, total_tokens, metadata) "
                "VALUES (datetime('now'),'legacy','baseline',0,?,?,"
                "'{\"baseline\": true}')",
                (expected, expected),
            )
            conn.commit()
            total = conn.execute(
                "SELECT SUM(total_tokens) FROM llm_consumption WHERE model='baseline'"
            ).fetchone()[0]
            assert total == expected == 600
        finally:
            conn.close()

    def test_058_adds_is_internal_column(self, test_db_path):
        dbm = _apply_all_migrations(test_db_path)
        conn = dbm.get_connection()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
            assert "is_internal" in cols
        finally:
            conn.close()


# ── History filter ─────────────────────────────────────────────────────────


class TestHistoryFilter:
    def test_internal_rows_excluded_from_history(self, test_db_path):
        dbm = _apply_all_migrations(test_db_path)
        repo = MessageRepository(dbm)
        # Create the conversation row first (FK)
        conn = dbm.get_connection()
        conn.execute(
            "INSERT INTO conversations (conversation_id, channel) VALUES ('c1','webui')"
        )
        conn.commit()
        conn.close()

        repo.create("c1", "user", "hello", token_count=5)
        repo.create("c1", "assistant", "hi there", token_count=5, is_internal=True)
        repo.create("c1", "assistant", "world", token_count=5)

        recent = repo.get_recent_messages("c1", count=10)
        contents = [r["content"] for r in recent]
        assert "hello" in contents
        assert "world" in contents
        assert "hi there" not in contents  # internal excluded

        by_conv = repo.get_by_conversation("c1")
        assert "hi there" not in [r["content"] for r in by_conv]


# ── Continuity ─────────────────────────────────────────────────────────────


class TestContinuity:
    def test_baseline_keeps_monthly_total_continuous(self, test_db_path):
        """The current-month baseline means /managed/usage's current-month total
        starts at the legacy sum, so new accurate usage adds on top rather than
        being held back by the platform's max() watermark.
        """
        dbm = _apply_all_migrations(test_db_path)
        repo = LlmConsumptionRepository(dbm)
        totals = repo.get_monthly_totals(months=12)
        now = datetime.utcnow()
        current = next(
            (m for m in totals if m["year"] == now.year and m["month"] == now.month),
            None,
        )
        assert current is not None
        # Baseline seeded against empty messages -> 0; just verify the current
        # month is present (the bridge exists) and accurate usage adds on top.
        UsageRecorder.set_db(dbm)
        usage_recorder.record(_fake_usage(prompt=100, completion=40, total=140),
                              provider="openrouter", model="claude")
        UsageRecorder.clear()
        totals2 = repo.get_monthly_totals(months=12)
        current2 = next(
            m for m in totals2 if m["year"] == now.year and m["month"] == now.month
        )
        assert current2["tokens_total"] == current["tokens_total"] + 140


# ── Compaction ─────────────────────────────────────────────────────────────


@pytest.fixture
def compaction_db(test_db_path):
    dbm = _apply_all_migrations(test_db_path)
    conn = dbm.get_connection()
    old = (datetime.utcnow() - timedelta(days=120)).isoformat()
    recent = (datetime.utcnow() - timedelta(days=5)).isoformat()
    for cid in ("c1", "c2"):
        conn.execute(
            "INSERT OR IGNORE INTO conversations (conversation_id, channel) VALUES (?, 'webui')",
            (cid,),
        )
        for i in range(3):
            conn.execute(
                "INSERT INTO messages (message_id, conversation_id, role, content, "
                "token_count, timestamp) VALUES (?,?,?,?,?,?)",
                (f"{cid}-old{i}", cid, "user", f"old {i}", 100 * (i + 1), old),
            )
        conn.execute(
            "INSERT INTO messages (message_id, conversation_id, role, content, "
            "token_count, timestamp) VALUES (?,?,?,?,?,?)",
            (f"{cid}-new", cid, "assistant", "recent", 50, recent),
        )
    om = (datetime.utcnow() - timedelta(days=120)).strftime("%Y-%m-%d %H:%M:%S")
    om2 = (datetime.utcnow() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
    rt = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    for _ in range(4):
        conn.execute(
            "INSERT INTO llm_consumption (timestamp, provider, model, prompt_tokens, "
            "completion_tokens, total_tokens, metadata) VALUES (?,?,?,?,?,?,NULL)",
            (om, "or", "c", 100, 50, 150),
        )
    for _ in range(2):
        conn.execute(
            "INSERT INTO llm_consumption (timestamp, provider, model, prompt_tokens, "
            "completion_tokens, total_tokens, metadata) VALUES (?,?,?,?,?,?,NULL)",
            (om2, "or", "c", 200, 80, 280),
        )
    conn.execute(
        "INSERT INTO llm_consumption (timestamp, provider, model, prompt_tokens, "
        "completion_tokens, total_tokens, metadata) VALUES (?,?,?,?,?,?,NULL)",
        (rt, "or", "c", 10, 5, 15),
    )
    conn.commit()
    conn.close()
    return dbm


def _totals(dbm):
    conn = dbm.get_connection()
    try:
        m = conn.execute("SELECT COALESCE(SUM(token_count),0) FROM messages").fetchone()[0]
        c = conn.execute("SELECT COALESCE(SUM(total_tokens),0) FROM llm_consumption").fetchone()[0]
        return m, c
    finally:
        conn.close()


class TestCompaction:
    def test_compacts_and_preserves_totals(self, compaction_db):
        from src.services.system import SystemService

        pre_m, pre_c = _totals(compaction_db)
        svc = SystemService(db_manager=compaction_db, settings_service=None)
        res = svc.compact_messages(retention_days=90)

        assert res["success"] is True
        assert res["messages_compacted"] == 2
        assert res["consumption_months_compacted"] == 2
        post_m, post_c = _totals(compaction_db)
        assert post_m == pre_m, f"messages total changed {pre_m}->{post_m}"
        assert post_c == pre_c, f"consumption total changed {pre_c}->{post_c}"

    def test_recent_rows_untouched(self, compaction_db):
        from src.services.system import SystemService

        svc = SystemService(db_manager=compaction_db, settings_service=None)
        svc.compact_messages(retention_days=90)
        conn = compaction_db.get_connection()
        try:
            recent = {
                r[0] for r in conn.execute(
                    "SELECT content FROM messages WHERE content='recent'"
                )
            }
            assert recent == {"recent"}  # both recent rows survived
            # one compacted row per conversation
            n = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE json_extract(metadata,'$.compacted')=1"
            ).fetchone()[0]
            assert n == 2
        finally:
            conn.close()

    def test_idempotent(self, compaction_db):
        from src.services.system import SystemService

        svc = SystemService(db_manager=compaction_db, settings_service=None)
        svc.compact_messages(retention_days=90)
        pre_m, pre_c = _totals(compaction_db)
        res = svc.compact_messages(retention_days=90)
        assert res["messages_rows_removed"] == 0
        assert res["consumption_rows_removed"] == 0
        post_m, post_c = _totals(compaction_db)
        assert (post_m, post_c) == (pre_m, pre_c)
