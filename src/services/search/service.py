"""Unified search service combining keyword and semantic search across all sources."""

import json
import sqlite3
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.core.repositories.settings import SettingsRepository
from src.services.embedding import EmbeddingService
from src.services.search.providers import (
    GmailSearchProvider,
    IndexableDocument,
    MemorySearchProvider,
    NextcloudSearchProvider,
    NotionSearchProvider,
    OnenoteSearchProvider,
    OutlookEmailSearchProvider,
    OutlookFileSearchProvider,
    SearchProvider,
    SearchResult,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# RRF constant (standard value from literature)
RRF_K = 60


class UnifiedSearchService:
    """Orchestrates hybrid search across all connected sources."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        db_manager,
        google_service=None,
        outlook_service=None,
        notion_service=None,
        nextcloud_service=None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """
        Initialize unified search service.

        Args:
            settings_repo: Settings repository for checking enabled integrations
            db_manager: Database manager for search_index access
            google_service: Google service (Gmail)
            outlook_service: Outlook service (email + files)
            notion_service: Notion service
            nextcloud_service: Nextcloud service
            embedding_service: Embedding service for semantic search
        """
        self.settings_repo = settings_repo
        self.db_manager = db_manager
        self.embedding_service = embedding_service or EmbeddingService()

        # Build providers based on available services
        self._providers: Dict[str, SearchProvider] = {}

        if notion_service:
            self._providers["notion"] = NotionSearchProvider(notion_service)
        if google_service:
            self._providers["gmail"] = GmailSearchProvider(google_service)
        if outlook_service:
            self._providers["outlook_email"] = OutlookEmailSearchProvider(outlook_service)
            self._providers["outlook_files"] = OutlookFileSearchProvider(outlook_service)
            self._providers["onenote"] = OnenoteSearchProvider(outlook_service)
        if nextcloud_service:
            self._providers["nextcloud"] = NextcloudSearchProvider(nextcloud_service)

        # Memory provider is always registered — facts are indexed by system_index_memory_facts
        self._providers["memory"] = MemorySearchProvider(db_manager)

    def _get_enabled_providers(
        self, sources: Optional[List[str]] = None
    ) -> Dict[str, SearchProvider]:
        """
        Get providers for enabled integrations, optionally filtered by source list.

        Args:
            sources: Optional list of source names to filter

        Returns:
            Dictionary of source_name -> provider
        """
        # Map source names to settings keys.
        # A value of None means the source is always enabled (no settings toggle).
        source_to_setting = {
            "notion": "notion.enabled",
            "gmail": "google.enabled",
            "outlook_email": "outlook.enabled",
            "outlook_files": "outlook.enabled",
            "onenote": "outlook.enabled",
            "nextcloud": "nextcloud.enabled",
            "memory": None,  # Always enabled — no external integration required
        }

        enabled = {}
        for name, provider in self._providers.items():
            # Skip if sources filter is set and this source isn't in it
            if sources and name not in sources:
                continue

            # Check if the integration is enabled (None means always enabled)
            setting_key = source_to_setting.get(name, f"{name}.enabled")
            if setting_key is None or self.settings_repo.get(setting_key):
                enabled[name] = provider

        return enabled

    def search(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        search_type: str = "hybrid",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Search across all enabled sources using hybrid keyword + semantic search.

        The semantic index is populated automatically:
        - Keyword results are opportunistically indexed in the background after each search
        - On hybrid/semantic searches, if the index is empty for a source, a background
          index build is triggered (the current search proceeds with keyword results only)

        Args:
            query: Search query
            sources: Optional list of sources to search
            search_type: 'hybrid', 'keyword', or 'semantic'
            limit: Maximum results per source

        Returns:
            Dictionary with search results and metadata
        """
        providers = self._get_enabled_providers(sources)

        if not providers:
            return {
                "results": [],
                "total": 0,
                "sources_searched": [],
                "search_type": search_type,
                "message": "No enabled search sources found. Enable integrations in Settings.",
            }

        keyword_results = []
        semantic_results = []

        # Keyword search
        if search_type in ("hybrid", "keyword"):
            keyword_results = self._keyword_search(query, providers, limit)

        # Semantic search
        if search_type in ("hybrid", "semantic"):
            # Auto-index: if the index is empty for any searched source, do
            # a lightweight index build so the first hybrid search is useful
            if self.embedding_service.is_available():
                self._auto_index_if_empty(providers)

            semantic_results = self._semantic_search(query, providers, limit)

        # Opportunistic indexing: embed keyword results in the background so the
        # semantic index grows organically as the user searches
        if keyword_results and self.embedding_service.is_available():
            self._index_keyword_results_async(keyword_results)

        # Merge results
        if search_type == "keyword":
            merged = keyword_results
        elif search_type == "semantic":
            merged = semantic_results
        else:
            # Hybrid: merge with RRF
            merged = self._reciprocal_rank_fusion([keyword_results, semantic_results], limit)

        # Format results
        formatted = []
        for result in merged[:limit]:
            formatted.append(
                {
                    "source": result.source,
                    "source_id": result.source_id,
                    "title": result.title,
                    "snippet": result.snippet,
                    "url": result.url,
                    "score": round(result.score, 4),
                    "metadata": result.metadata,
                }
            )

        return {
            "results": formatted,
            "total": len(formatted),
            "sources_searched": list(providers.keys()),
            "search_type": search_type,
            "query": query,
        }

    def _auto_index_if_empty(self, providers: Dict[str, SearchProvider]) -> None:
        """
        Check if any searched source has zero indexed documents.
        If so, trigger a background index build for those sources.

        The current search proceeds with keyword results only — semantic
        results will be available on subsequent searches once the background
        index build completes.
        """
        sources_to_index = []
        conn = self.db_manager.get_connection()
        try:
            for source_name in providers:
                row = conn.execute(
                    "SELECT COUNT(*) FROM search_index WHERE source = ?",
                    (source_name,),
                ).fetchone()

                if not row or row[0] == 0:
                    sources_to_index.append(source_name)
        except sqlite3.OperationalError:
            # Table doesn't exist yet — will be created by migration
            return
        finally:
            conn.close()

        if sources_to_index:
            logger.info(
                f"Search index empty for {sources_to_index}, "
                f"triggering background index build..."
            )

            def _do_reindex():
                try:
                    self.reindex(sources=sources_to_index)
                except Exception as e:
                    logger.error(f"Background index build failed: {e}")

            thread = threading.Thread(target=_do_reindex, daemon=True)
            thread.start()

    def _index_keyword_results_async(self, results: List[SearchResult]) -> None:
        """
        Opportunistically index keyword search results in a background thread.

        This ensures the semantic index grows naturally as the user searches —
        every keyword hit gets an embedding stored so future semantic queries
        can find it.
        """

        def _do_index():
            try:
                conn = self.db_manager.get_connection()
                indexed = 0
                try:
                    for result in results:
                        # Skip if already indexed with same content
                        content = f"{result.title}\n\n{result.snippet}"
                        content_hash = EmbeddingService.content_hash(content)

                        existing = conn.execute(
                            "SELECT content_hash FROM search_index "
                            "WHERE source = ? AND source_id = ?",
                            (result.source, result.source_id),
                        ).fetchone()

                        if existing and existing[0] == content_hash:
                            continue

                        embedding = self.embedding_service.embed_single(content)
                        if embedding is None:
                            continue

                        embedding_blob = EmbeddingService.serialize_embedding(embedding)
                        metadata_json = json.dumps(result.metadata) if result.metadata else None

                        conn.execute(
                            """INSERT INTO search_index
                               (source, source_id, title, content, content_hash,
                                embedding, metadata, indexed_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                               ON CONFLICT(source, source_id) DO UPDATE SET
                                   title = excluded.title,
                                   content = excluded.content,
                                   content_hash = excluded.content_hash,
                                   embedding = excluded.embedding,
                                   metadata = excluded.metadata,
                                   indexed_at = CURRENT_TIMESTAMP""",
                            (
                                result.source,
                                result.source_id,
                                result.title,
                                content[:8000],
                                content_hash,
                                embedding_blob,
                                metadata_json,
                            ),
                        )
                        indexed += 1

                    conn.commit()
                    if indexed:
                        logger.info(f"Opportunistically indexed {indexed} keyword results")
                except sqlite3.OperationalError as e:
                    logger.debug(f"Opportunistic indexing skipped (table may not exist): {e}")
                finally:
                    conn.close()
            except Exception as e:
                logger.debug(f"Background indexing failed: {e}")

        thread = threading.Thread(target=_do_index, daemon=True)
        thread.start()

    def _keyword_search(
        self,
        query: str,
        providers: Dict[str, SearchProvider],
        limit: int,
    ) -> List[SearchResult]:
        """Run keyword search across all providers."""
        all_results = []

        for source_name, provider in providers.items():
            try:
                results = provider.keyword_search(query, limit)
                # Assign decreasing scores by rank position
                for i, result in enumerate(results):
                    result.score = 1.0 / (i + 1)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Keyword search failed for {source_name}: {e}")

        return all_results

    def _semantic_search(
        self,
        query: str,
        providers: Dict[str, SearchProvider],
        limit: int,
    ) -> List[SearchResult]:
        """Run semantic search against the local embedding index."""
        if not self.embedding_service.is_available():
            logger.info("Embedding service not available, skipping semantic search")
            return []

        # Generate query embedding
        query_embedding = self.embedding_service.embed_single(query)
        if query_embedding is None:
            logger.warning("Failed to generate query embedding")
            return []

        # Load indexed documents for the relevant sources
        source_names = list(providers.keys())
        indexed_docs = self._load_indexed_documents(source_names)

        if not indexed_docs:
            logger.info("No indexed documents found for semantic search")
            return []

        # Compute similarities
        scored_results = []
        for doc in indexed_docs:
            similarity = EmbeddingService.cosine_similarity(query_embedding, doc["embedding"])
            if similarity > 0.3:  # Minimum similarity threshold
                scored_results.append(
                    SearchResult(
                        source=doc["source"],
                        source_id=doc["source_id"],
                        title=doc["title"] or "",
                        snippet=(doc["content"] or "")[:200],
                        url=doc.get("url", ""),
                        metadata=doc.get("metadata", {}),
                        score=similarity,
                    )
                )

        # Sort by similarity score descending
        scored_results.sort(key=lambda r: r.score, reverse=True)
        return scored_results[:limit]

    def _load_indexed_documents(self, source_names: List[str]) -> List[Dict[str, Any]]:
        """Load indexed documents with their embeddings from the database."""
        conn = self.db_manager.get_connection()
        try:
            placeholders = ",".join("?" for _ in source_names)
            cursor = conn.execute(
                f"""SELECT source, source_id, title, content, embedding, metadata
                   FROM search_index
                   WHERE source IN ({placeholders}) AND embedding IS NOT NULL""",
                source_names,
            )

            documents = []
            for row in cursor.fetchall():
                try:
                    embedding = EmbeddingService.deserialize_embedding(row[4])
                    metadata = json.loads(row[5]) if row[5] else {}
                    documents.append(
                        {
                            "source": row[0],
                            "source_id": row[1],
                            "title": row[2],
                            "content": row[3],
                            "embedding": embedding,
                            "metadata": metadata,
                            "url": metadata.get("url", ""),
                        }
                    )
                except Exception as e:
                    logger.debug(f"Failed to load indexed doc: {e}")

            return documents
        except sqlite3.OperationalError as e:
            logger.warning(f"search_index table may not exist yet: {e}")
            return []
        finally:
            conn.close()

    def _reciprocal_rank_fusion(
        self,
        result_lists: List[List[SearchResult]],
        limit: int,
    ) -> List[SearchResult]:
        """
        Merge multiple ranked result lists using Reciprocal Rank Fusion.

        RRF_score(d) = sum(1 / (k + rank_i(d))) for each list i

        Args:
            result_lists: List of ranked result lists
            limit: Maximum results to return

        Returns:
            Merged and re-ranked results
        """
        # Track RRF scores and best result per document
        rrf_scores: Dict[str, float] = defaultdict(float)
        best_result: Dict[str, SearchResult] = {}

        for result_list in result_lists:
            for rank, result in enumerate(result_list):
                doc_key = f"{result.source}:{result.source_id}"
                rrf_scores[doc_key] += 1.0 / (RRF_K + rank + 1)

                # Keep the result with better metadata (prefer keyword results for snippets)
                if doc_key not in best_result or len(result.snippet) > len(
                    best_result[doc_key].snippet
                ):
                    best_result[doc_key] = result

        # Sort by RRF score
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        merged = []
        for key in sorted_keys[:limit]:
            result = best_result[key]
            result.score = rrf_scores[key]
            merged.append(result)

        return merged

    def index_document(
        self,
        source: str,
        source_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Index a single document into the search index.

        Call this from other services when content is created or retrieved
        to keep the semantic index fresh without a full reindex.

        Args:
            source: Source name (e.g. 'notion', 'gmail')
            source_id: Unique ID in the source system
            title: Document title
            content: Document text content
            metadata: Optional source-specific metadata

        Returns:
            True if indexed successfully, False otherwise
        """
        if not self.embedding_service.is_available():
            return False

        try:
            full_content = f"{title}\n\n{content}" if title else content
            content_hash = EmbeddingService.content_hash(full_content)

            conn = self.db_manager.get_connection()
            try:
                existing = conn.execute(
                    "SELECT content_hash FROM search_index " "WHERE source = ? AND source_id = ?",
                    (source, source_id),
                ).fetchone()

                if existing and existing[0] == content_hash:
                    return True  # Already indexed, unchanged

                embedding = self.embedding_service.embed_single(full_content)
                if embedding is None:
                    return False

                embedding_blob = EmbeddingService.serialize_embedding(embedding)
                metadata_json = json.dumps(metadata) if metadata else None

                conn.execute(
                    """INSERT INTO search_index
                       (source, source_id, title, content, content_hash,
                        embedding, metadata, indexed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(source, source_id) DO UPDATE SET
                           title = excluded.title,
                           content = excluded.content,
                           content_hash = excluded.content_hash,
                           embedding = excluded.embedding,
                           metadata = excluded.metadata,
                           indexed_at = CURRENT_TIMESTAMP""",
                    (
                        source,
                        source_id,
                        title,
                        full_content[:8000],
                        content_hash,
                        embedding_blob,
                        metadata_json,
                    ),
                )
                conn.commit()
                return True
            finally:
                conn.close()

        except Exception as e:
            logger.debug(f"index_document failed for {source}:{source_id}: {e}")
            return False

    def reindex(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Rebuild the search index for specified sources.

        Args:
            sources: Sources to reindex (all enabled if None)

        Returns:
            Indexing summary with counts per source
        """
        providers = self._get_enabled_providers(sources)

        if not providers:
            return {
                "success": False,
                "message": "No enabled sources to index",
                "indexed": {},
            }

        if not self.embedding_service.is_available():
            return {
                "success": False,
                "message": "Embedding service not available. Check LLM provider configuration.",
                "indexed": {},
            }

        conn = self.db_manager.get_connection()
        indexed_counts = {}

        try:
            for source_name, provider in providers.items():
                try:
                    documents = provider.get_indexable_content(limit=500)
                    count = 0

                    for doc in documents:
                        content_hash = EmbeddingService.content_hash(doc.content)

                        # Check if content has changed
                        existing = conn.execute(
                            "SELECT content_hash FROM search_index WHERE source = ? AND source_id = ?",
                            (doc.source, doc.source_id),
                        ).fetchone()

                        if existing and existing[0] == content_hash:
                            continue  # Content unchanged, skip

                        # Generate embedding
                        embedding = self.embedding_service.embed_single(doc.content)
                        if embedding is None:
                            continue

                        embedding_blob = EmbeddingService.serialize_embedding(embedding)
                        metadata_json = json.dumps(doc.metadata) if doc.metadata else None

                        # Upsert into index
                        conn.execute(
                            """INSERT INTO search_index
                               (source, source_id, title, content, content_hash, embedding, metadata, indexed_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                               ON CONFLICT(source, source_id) DO UPDATE SET
                                   title = excluded.title,
                                   content = excluded.content,
                                   content_hash = excluded.content_hash,
                                   embedding = excluded.embedding,
                                   metadata = excluded.metadata,
                                   indexed_at = CURRENT_TIMESTAMP""",
                            (
                                doc.source,
                                doc.source_id,
                                doc.title,
                                doc.content[:8000],
                                content_hash,
                                embedding_blob,
                                metadata_json,
                            ),
                        )
                        count += 1

                    conn.commit()
                    indexed_counts[source_name] = count
                    logger.info(f"Indexed {count} documents from {source_name}")

                except Exception as e:
                    logger.error(f"Indexing failed for {source_name}: {e}")
                    indexed_counts[source_name] = f"error: {str(e)}"

        finally:
            conn.close()

        total = sum(v for v in indexed_counts.values() if isinstance(v, int))
        return {
            "success": True,
            "message": f"Indexed {total} documents across {len(indexed_counts)} sources",
            "indexed": indexed_counts,
        }
