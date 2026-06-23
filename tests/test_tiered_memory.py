"""Tests for tiered memory functionality."""

import pytest

from src.services.search.providers import MemorySearchProvider
from src.services.system import SystemService


class TestMemorySearchProvider:
    """Tests for MemorySearchProvider."""

    def test_keyword_search_finds_match(self, clean_temp_db):
        """Test that keyword search finds matching memory facts."""
        conn = clean_temp_db.get_connection()
        conn.execute(
            """INSERT INTO search_index (source, source_id, title, content, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "memory",
                "memory_facts_2026-03-12",
                "Memory Facts – 2026-03-12",
                "User enjoys hiking and outdoor activities.",
                '{"date": "2026-03-12"}',
            ),
        )
        conn.commit()
        conn.close()

        provider = MemorySearchProvider(clean_temp_db)
        results = provider.keyword_search("hiking", limit=10)

        assert len(results) == 1
        assert results[0].source == "memory"
        assert "hiking" in results[0].snippet.lower()

    def test_keyword_search_case_insensitive(self, clean_temp_db):
        """Test that keyword search is case-insensitive."""
        conn = clean_temp_db.get_connection()
        conn.execute(
            """INSERT INTO search_index (source, source_id, title, content, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "memory",
                "memory_facts_2026-03-12",
                "Memory Facts – 2026-03-12",
                "User lives in PARIS, France.",
                '{"date": "2026-03-12"}',
            ),
        )
        conn.commit()
        conn.close()

        provider = MemorySearchProvider(clean_temp_db)

        # Search with lowercase
        results = provider.keyword_search("paris", limit=10)
        assert len(results) == 1

        # Search with uppercase
        results = provider.keyword_search("PARIS", limit=10)
        assert len(results) == 1

    def test_keyword_search_no_match(self, clean_temp_db):
        """Test that keyword search returns empty when no match."""
        conn = clean_temp_db.get_connection()
        conn.execute(
            """INSERT INTO search_index (source, source_id, title, content, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "memory",
                "memory_facts_2026-03-12",
                "Memory Facts – 2026-03-12",
                "User likes coffee.",
                '{"date": "2026-03-12"}',
            ),
        )
        conn.commit()
        conn.close()

        provider = MemorySearchProvider(clean_temp_db)
        results = provider.keyword_search("tea", limit=10)
        assert len(results) == 0

    def test_keyword_search_matches_title(self, clean_temp_db):
        """Test that keyword search matches title as well as content."""
        conn = clean_temp_db.get_connection()
        conn.execute(
            """INSERT INTO search_index (source, source_id, title, content, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "memory",
                "memory_facts_2026-03-12",
                "Memory Facts – Important Project",
                "Some unrelated content.",
                '{"date": "2026-03-12"}',
            ),
        )
        conn.commit()
        conn.close()

        provider = MemorySearchProvider(clean_temp_db)
        results = provider.keyword_search("project", limit=10)
        assert len(results) == 1

    def test_get_indexable_content_returns_empty(self, clean_temp_db):
        """Test that get_indexable_content returns empty list."""
        provider = MemorySearchProvider(clean_temp_db)
        results = provider.get_indexable_content(limit=10)
        assert results == []


class TestIndexMemoryFacts:
    """Tests for SystemService.index_memory_facts."""

    def test_index_memory_facts_stores_content(self, clean_temp_db):
        """Test that facts are stored in search_index."""
        service = SystemService(db_manager=clean_temp_db, embedding_service=None)

        result = service.index_memory_facts(
            date="2026-03-12", facts="User enjoys playing tennis on weekends."
        )

        assert result["success"] is True
        assert result["source_id"] == "memory_facts_2026-03-12"

        conn = clean_temp_db.get_connection()
        row = conn.execute(
            "SELECT title, content FROM search_index WHERE source = 'memory'"
        ).fetchone()
        conn.close()

        assert row is not None
        assert "tennis" in row[1]

    def test_index_memory_facts_upserts_same_date(self, clean_temp_db):
        """Test that calling with same date updates existing record."""
        service = SystemService(db_manager=clean_temp_db, embedding_service=None)

        service.index_memory_facts(date="2026-03-12", facts="First fact.")
        service.index_memory_facts(date="2026-03-12", facts="Updated fact.")

        conn = clean_temp_db.get_connection()
        rows = conn.execute(
            "SELECT COUNT(*), content FROM search_index WHERE source = 'memory'"
        ).fetchone()
        conn.close()

        assert rows[0] == 1
        assert "Updated fact" in rows[1]

    def test_index_memory_facts_different_dates(self, clean_temp_db):
        """Test that different dates create separate records."""
        service = SystemService(db_manager=clean_temp_db, embedding_service=None)

        service.index_memory_facts(date="2026-03-11", facts="Monday fact.")
        service.index_memory_facts(date="2026-03-12", facts="Tuesday fact.")

        conn = clean_temp_db.get_connection()
        rows = conn.execute(
            "SELECT source_id FROM search_index WHERE source = 'memory' ORDER BY source_id"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] == "memory_facts_2026-03-11"
        assert rows[1][0] == "memory_facts_2026-03-12"

    def test_index_memory_facts_no_database(self):
        """Test that missing database returns error."""
        service = SystemService(db_manager=None, embedding_service=None)

        result = service.index_memory_facts(date="2026-03-12", facts="Some fact.")

        assert result["success"] is False
        assert "Database not available" in result["error"]
