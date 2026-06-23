"""Search providers for unified search across different sources."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# File extensions we can extract text from (must match src/services/document.py)
_EXTRACTABLE_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".sql",
    ".sh",
    ".docx",
}


@dataclass
class SearchResult:
    """Represents a single search result from any source."""

    source: str
    source_id: str
    title: str
    snippet: str
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class IndexableDocument:
    """Represents a document that can be indexed for semantic search."""

    source: str
    source_id: str
    title: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class SearchProvider(ABC):
    """Abstract base class for search providers."""

    source_name: str = ""

    @abstractmethod
    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """
        Run keyword search using the source's native API.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of search results
        """
        pass

    @abstractmethod
    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """
        Retrieve content from this source for embedding indexing.

        Args:
            limit: Maximum documents to retrieve

        Returns:
            List of indexable documents
        """
        pass


class NotionSearchProvider(SearchProvider):
    """Search provider for Notion pages and databases."""

    source_name = "notion"

    def __init__(self, notion_service):
        self.service = notion_service

    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search Notion pages by keyword using Notion's native search API."""
        try:
            pages = self.service.search_pages(query=query, filter_type="page")
            results = []
            for page in pages[:limit]:
                page_id = page.get("id", "")
                title = _extract_notion_title(page)
                url = page.get("url", "")

                # Extract snippet from properties, then try to enrich with page content
                snippet = _extract_notion_snippet(page, title)
                try:
                    blocks = self.service.get_page_content(page_id)
                    block_text = _notion_blocks_to_text(blocks)
                    if block_text.strip():
                        snippet = f"{snippet}\n\n{block_text[:500]}"
                except Exception:
                    # Page not accessible via blocks API — use properties-only snippet
                    pass

                results.append(
                    SearchResult(
                        source="notion",
                        source_id=page_id,
                        title=title,
                        snippet=snippet,
                        url=url,
                        metadata={
                            "last_edited": page.get("last_edited_time", ""),
                            "created": page.get("created_time", ""),
                        },
                    )
                )
            return results
        except Exception as e:
            logger.error(f"Notion keyword search failed: {e}")
            return []

    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """Get Notion pages for indexing."""
        try:
            pages = self.service.search_pages(query="", filter_type="page")
            documents = []
            for page in pages[:limit]:
                page_id = page.get("id", "")
                title = _extract_notion_title(page)

                # Fetch page content blocks
                try:
                    blocks = self.service.get_page_content(page_id)
                    content = _notion_blocks_to_text(blocks)
                except Exception:
                    content = title

                if content.strip():
                    documents.append(
                        IndexableDocument(
                            source="notion",
                            source_id=page_id,
                            title=title,
                            content=f"{title}\n\n{content}",
                            metadata={
                                "url": page.get("url", ""),
                                "last_edited": page.get("last_edited_time", ""),
                            },
                        )
                    )
            return documents
        except Exception as e:
            logger.error(f"Notion indexing failed: {e}")
            return []


class GmailSearchProvider(SearchProvider):
    """Search provider for Gmail emails."""

    source_name = "gmail"

    def __init__(self, google_service):
        self.service = google_service

    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search Gmail by keyword."""
        try:
            emails = self.service.search_emails(query=query, limit=limit)
            results = []
            if isinstance(emails, dict):
                email_list = emails.get("emails", emails.get("results", []))
            elif isinstance(emails, list):
                email_list = emails
            else:
                email_list = []

            for email in email_list[:limit]:
                subject = email.get("subject", "(no subject)")
                sender = email.get("from", email.get("sender", ""))
                snippet = email.get("snippet", email.get("body", ""))[:200]
                msg_id = email.get("id", email.get("message_id", ""))

                results.append(
                    SearchResult(
                        source="gmail",
                        source_id=str(msg_id),
                        title=subject,
                        snippet=f"From: {sender} - {snippet}",
                        metadata={
                            "from": sender,
                            "date": email.get("date", ""),
                            "thread_id": email.get("thread_id", ""),
                        },
                    )
                )
            return results
        except Exception as e:
            logger.error(f"Gmail keyword search failed: {e}")
            return []

    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """Get Gmail emails for indexing."""
        try:
            emails = self.service.read_emails(limit=min(limit, 100))
            documents = []
            if isinstance(emails, dict):
                email_list = emails.get("emails", emails.get("results", []))
            elif isinstance(emails, list):
                email_list = emails
            else:
                email_list = []

            for email in email_list[:limit]:
                subject = email.get("subject", "(no subject)")
                body = email.get("body", email.get("snippet", ""))
                sender = email.get("from", email.get("sender", ""))
                msg_id = email.get("id", email.get("message_id", ""))

                content = f"Subject: {subject}\nFrom: {sender}\n\n{body}"
                if content.strip():
                    documents.append(
                        IndexableDocument(
                            source="gmail",
                            source_id=str(msg_id),
                            title=subject,
                            content=content[:8000],
                            metadata={
                                "from": sender,
                                "date": email.get("date", ""),
                            },
                        )
                    )
            return documents
        except Exception as e:
            logger.error(f"Gmail indexing failed: {e}")
            return []


class OutlookEmailSearchProvider(SearchProvider):
    """Search provider for Outlook emails."""

    source_name = "outlook_email"

    def __init__(self, outlook_service):
        self.service = outlook_service

    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search Outlook emails by keyword."""
        try:
            emails = self.service.search_emails(query=query, limit=limit)
            results = []
            if isinstance(emails, dict):
                email_list = emails.get("emails", emails.get("results", emails.get("value", [])))
            elif isinstance(emails, list):
                email_list = emails
            else:
                email_list = []

            for email in email_list[:limit]:
                subject = email.get("subject", "(no subject)")
                # Graph API returns from as {"emailAddress": {"name": "...", "address": "..."}}
                from_obj = email.get("from", {})
                if isinstance(from_obj, dict):
                    email_addr = from_obj.get("emailAddress", {})
                    sender_name = email_addr.get("name", "")
                    sender_address = email_addr.get("address", "")
                    sender = f"{sender_name} <{sender_address}>" if sender_name else sender_address
                else:
                    sender = str(from_obj) if from_obj else ""
                snippet = email.get("bodyPreview", email.get("snippet", email.get("body", "")))[
                    :200
                ]
                msg_id = email.get("id", email.get("message_id", ""))

                results.append(
                    SearchResult(
                        source="outlook_email",
                        source_id=str(msg_id),
                        title=subject,
                        snippet=f"From: {sender} - {snippet}",
                        metadata={
                            "from": sender,
                            "date": email.get("receivedDateTime", email.get("date", "")),
                        },
                    )
                )
            return results
        except Exception as e:
            logger.error(f"Outlook email search failed: {e}")
            return []

    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """Get Outlook emails for indexing."""
        try:
            emails = self.service.read_emails(limit=min(limit, 100))
            documents = []
            if isinstance(emails, dict):
                email_list = emails.get("emails", emails.get("results", emails.get("value", [])))
            elif isinstance(emails, list):
                email_list = emails
            else:
                email_list = []

            for email in email_list[:limit]:
                subject = email.get("subject", "(no subject)")
                body = email.get("body", email.get("bodyPreview", ""))
                # Graph API returns from as {"emailAddress": {"name": "...", "address": "..."}}
                from_obj = email.get("from", {})
                if isinstance(from_obj, dict):
                    email_addr = from_obj.get("emailAddress", {})
                    sender_name = email_addr.get("name", "")
                    sender_address = email_addr.get("address", "")
                    sender = f"{sender_name} <{sender_address}>" if sender_name else sender_address
                else:
                    sender = str(from_obj) if from_obj else ""
                msg_id = email.get("id", email.get("message_id", ""))

                content = f"Subject: {subject}\nFrom: {sender}\n\n{body}"
                if content.strip():
                    documents.append(
                        IndexableDocument(
                            source="outlook_email",
                            source_id=str(msg_id),
                            title=subject,
                            content=content[:8000],
                            metadata={
                                "from": sender,
                                "date": email.get("receivedDateTime", email.get("date", "")),
                            },
                        )
                    )
            return documents
        except Exception as e:
            logger.error(f"Outlook email indexing failed: {e}")
            return []


class OutlookFileSearchProvider(SearchProvider):
    """Search provider for OneDrive files via Outlook service."""

    source_name = "outlook_files"

    def __init__(self, outlook_service):
        self.service = outlook_service

    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search OneDrive files by keyword."""
        try:
            files = self.service.search_files(query=query)
            results = []
            if isinstance(files, dict):
                file_list = files.get("files", files.get("results", files.get("value", [])))
            elif isinstance(files, list):
                file_list = files
            else:
                file_list = []

            for f in file_list[:limit]:
                name = f.get("name", "(unnamed)")
                file_id = f.get("id", "")
                web_url = f.get("webUrl", "")
                size = f.get("size", 0)

                results.append(
                    SearchResult(
                        source="outlook_files",
                        source_id=str(file_id),
                        title=name,
                        snippet=f"OneDrive file: {name} ({_format_size(size)})",
                        url=web_url,
                        metadata={
                            "size": size,
                            "modified": f.get("lastModifiedDateTime", ""),
                        },
                    )
                )
            return results
        except Exception as e:
            logger.error(f"OneDrive file search failed: {e}")
            return []

    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """Index OneDrive files — extracts text content for supported formats."""
        try:
            files = self.service.list_files()
            documents = []
            if isinstance(files, dict):
                file_list = files.get("files", files.get("results", files.get("value", [])))
            elif isinstance(files, list):
                file_list = files
            else:
                file_list = []

            for f in file_list[:limit]:
                name = f.get("name", "(unnamed)")
                file_id = f.get("id", "")
                modified = f.get("lastModifiedDateTime", "")
                size = f.get("size", 0)

                # Use modified date + size as change key (avoids re-downloading)
                content_key = f"{modified}:{size}"

                # Try to extract text for supported file types
                ext = os.path.splitext(name)[1].lower()
                content = f"File: {name}"
                if ext in _EXTRACTABLE_EXTENSIONS and file_id:
                    try:
                        result = self.service.read_file(file_id=file_id)
                        extracted = result.get("extracted_text")
                        if extracted:
                            content = f"{name}\n\n{extracted}"
                    except Exception as e:
                        logger.debug(f"Could not extract text from {name}: {e}")

                documents.append(
                    IndexableDocument(
                        source="outlook_files",
                        source_id=str(file_id),
                        title=name,
                        content=content[:8000],
                        metadata={
                            "size": size,
                            "webUrl": f.get("webUrl", ""),
                            "content_key": content_key,
                        },
                    )
                )
            return documents
        except Exception as e:
            logger.error(f"OneDrive file indexing failed: {e}")
            return []


class NextcloudSearchProvider(SearchProvider):
    """Search provider for Nextcloud files."""

    source_name = "nextcloud"

    def __init__(self, nextcloud_service):
        self.service = nextcloud_service

    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search Nextcloud files by keyword."""
        try:
            files = self.service.search_files(query=query)
            results = []
            if isinstance(files, dict):
                file_list = files.get("files", files.get("results", []))
            elif isinstance(files, list):
                file_list = files
            else:
                file_list = []

            for f in file_list[:limit]:
                name = f.get("name", f.get("path", "(unnamed)"))
                path = f.get("path", name)

                results.append(
                    SearchResult(
                        source="nextcloud",
                        source_id=path,
                        title=name,
                        snippet=f"Nextcloud file: {path}",
                        metadata={
                            "path": path,
                            "size": f.get("size", 0),
                            "modified": f.get("modified", f.get("last_modified", "")),
                        },
                    )
                )
            return results
        except Exception as e:
            logger.error(f"Nextcloud search failed: {e}")
            return []

    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """Index Nextcloud files — extracts text content for supported formats."""
        try:
            from src.services.document import extract_text_from_bytes

            files = self.service.list_files()
            documents = []
            if isinstance(files, dict):
                file_list = files.get("files", files.get("results", []))
            elif isinstance(files, list):
                file_list = files
            else:
                file_list = []

            for f in file_list[:limit]:
                name = f.get("name", f.get("path", "(unnamed)"))
                path = f.get("path", name)
                modified = f.get("modified", f.get("last_modified", ""))
                size = f.get("size", 0)

                # Use modified date + size as change key
                content_key = f"{modified}:{size}"

                # Try to extract text for supported file types
                ext = os.path.splitext(name)[1].lower()
                content = f"File: {name} at {path}"
                if ext in _EXTRACTABLE_EXTENSIONS:
                    try:
                        file_bytes = self.service.read_file_bytes(path)
                        extracted = extract_text_from_bytes(file_bytes, name)
                        if extracted.get("success") and extracted.get("text"):
                            content = f"{name}\n\n{extracted['text']}"
                    except Exception as e:
                        logger.debug(f"Could not extract text from {path}: {e}")

                documents.append(
                    IndexableDocument(
                        source="nextcloud",
                        source_id=path,
                        title=name,
                        content=content[:8000],
                        metadata={
                            "path": path,
                            "size": size,
                            "content_key": content_key,
                        },
                    )
                )
            return documents
        except Exception as e:
            logger.error(f"Nextcloud indexing failed: {e}")
            return []


class OnenoteSearchProvider(SearchProvider):
    """Search provider for OneNote pages."""

    source_name = "onenote"

    def __init__(self, outlook_service):
        self.service = outlook_service

    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search OneNote pages by keyword."""
        try:
            pages = self.service.search_onenote(query=query, limit=limit)
            results = []

            for page in pages[:limit]:
                page_id = page.get("id", "")
                title = page.get("title", "(untitled)")

                # Get parent info for context
                parent_section = page.get("parentSection", {})
                parent_notebook = page.get("parentNotebook", {})
                section_name = parent_section.get("displayName", "")
                notebook_name = parent_notebook.get("displayName", "")

                snippet = f"OneNote page: {title}"
                if notebook_name:
                    snippet += f" (Notebook: {notebook_name})"
                if section_name:
                    snippet += f" (Section: {section_name})"

                results.append(
                    SearchResult(
                        source="onenote",
                        source_id=page_id,
                        title=title,
                        snippet=snippet,
                        metadata={
                            "page_id": page_id,
                            "notebook": notebook_name,
                            "section": section_name,
                            "last_modified": page.get("lastModifiedDateTime", ""),
                            "created": page.get("createdDateTime", ""),
                            "web_url": page.get("links", {})
                            .get("oneNoteWebUrl", {})
                            .get("href", ""),
                        },
                    )
                )
            return results
        except Exception as e:
            logger.error(f"OneNote search failed: {e}")
            return []

    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """Index OneNote pages — fetches content for semantic search."""
        try:
            documents = []

            # Get all notebooks
            notebooks = self.service.list_notebooks(include_sections=True)

            page_count = 0
            for notebook in notebooks:
                if page_count >= limit:
                    break

                notebook_name = notebook.get("displayName", "")
                sections = notebook.get("sections", [])

                for section in sections:
                    if page_count >= limit:
                        break

                    section_id = section.get("id", "")
                    section_name = section.get("displayName", "")

                    try:
                        # Get pages with content
                        pages = self.service.list_pages(
                            section_id=section_id,
                            limit=min(100, limit - page_count),
                            include_content=True,
                        )

                        for page in pages:
                            if page_count >= limit:
                                break

                            page_id = page.get("id", "")
                            title = page.get("title", "(untitled)")
                            content_html = page.get("content", "")
                            last_modified = page.get("lastModifiedDateTime", "")

                            # Extract text from HTML for indexing
                            content_text = self._html_to_text(content_html)

                            # Use last modified as change key
                            content_key = last_modified

                            documents.append(
                                IndexableDocument(
                                    source="onenote",
                                    source_id=page_id,
                                    title=title,
                                    content=f"{title}\n\n{content_text}"[:8000],
                                    metadata={
                                        "page_id": page_id,
                                        "notebook": notebook_name,
                                        "section": section_name,
                                        "content_key": content_key,
                                    },
                                )
                            )
                            page_count += 1

                    except Exception as e:
                        logger.debug(f"Could not index section {section_name}: {e}")
                        continue

            logger.info(f"Indexed {len(documents)} OneNote pages")
            return documents

        except Exception as e:
            logger.error(f"OneNote indexing failed: {e}")
            return []

    def _html_to_text(self, html: str) -> str:
        """Extract plain text from OneNote HTML content."""
        if not html:
            return ""

        import re
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self.skip_tags = {"script", "style", "head", "meta", "title"}
                self.current_skip = False

            def handle_starttag(self, tag, attrs):
                if tag in self.skip_tags:
                    self.current_skip = True
                elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
                    self.text_parts.append("\n")

            def handle_endtag(self, tag):
                if tag in self.skip_tags:
                    self.current_skip = False
                elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
                    self.text_parts.append("\n")

            def handle_data(self, data):
                if not self.current_skip:
                    self.text_parts.append(data)

        try:
            extractor = TextExtractor()
            extractor.feed(html)
            text = "".join(extractor.text_parts)
            # Clean up whitespace
            text = re.sub(r"\n\s*\n", "\n\n", text).strip()
            return text
        except Exception:
            return html  # Fallback to raw HTML


def _extract_notion_title(page: dict) -> str:
    """Extract title from a Notion page object."""
    properties = page.get("properties", {})

    # Try common title property names
    for prop_name in ["Name", "Title", "title", "name"]:
        prop = properties.get(prop_name, {})
        if "title" in prop:
            title_array = prop["title"]
            if isinstance(title_array, list) and len(title_array) > 0:
                return title_array[0].get("plain_text", "(untitled)")

    # Try any property with type "title"
    for prop_name, prop_value in properties.items():
        if isinstance(prop_value, dict) and prop_value.get("type") == "title":
            title_array = prop_value.get("title", [])
            if isinstance(title_array, list) and len(title_array) > 0:
                return title_array[0].get("plain_text", "(untitled)")

    return "(untitled)"


def _extract_notion_snippet(page: dict, title: str) -> str:
    """Extract a meaningful snippet from Notion page properties."""
    parts = []
    properties = page.get("properties", {})

    for prop_name, prop_value in properties.items():
        if not isinstance(prop_value, dict):
            continue
        prop_type = prop_value.get("type", "")
        text = ""

        if prop_type == "title":
            continue  # Already have the title
        elif prop_type == "rich_text":
            rich_text = prop_value.get("rich_text", [])
            text = " ".join(rt.get("plain_text", "") for rt in rich_text if isinstance(rt, dict))
        elif prop_type == "select":
            sel = prop_value.get("select")
            if sel:
                text = sel.get("name", "")
        elif prop_type == "multi_select":
            text = ", ".join(s.get("name", "") for s in prop_value.get("multi_select", []))
        elif prop_type == "date":
            date_val = prop_value.get("date")
            if date_val:
                text = date_val.get("start", "")
        elif prop_type == "number":
            num = prop_value.get("number")
            if num is not None:
                text = str(num)
        elif prop_type == "url":
            text = prop_value.get("url", "") or ""

        if text.strip():
            parts.append(f"{prop_name}: {text.strip()}")

    if parts:
        return f"{title} — {'; '.join(parts)}"
    return title


def _notion_blocks_to_text(blocks: list) -> str:
    """Convert Notion blocks to plain text."""
    if not blocks:
        return ""

    text_parts = []
    for block in blocks:
        block_type = block.get("type", "")
        block_data = block.get(block_type, {})

        if isinstance(block_data, dict):
            rich_text = block_data.get("rich_text", [])
            if isinstance(rich_text, list):
                for rt in rich_text:
                    text_parts.append(rt.get("plain_text", ""))

    return "\n".join(text_parts)


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class MemorySearchProvider(SearchProvider):
    """Search provider for the assistant's own long-term memory facts.

    Facts are stored in the search_index table under source='memory' by the
    system_index_memory_facts tool during nightly memory updates. This provider
    makes them searchable via the unified search infrastructure.

    Keyword search is implemented as a simple SQL LIKE query against the stored
    content. Semantic (embedding-based) search is handled automatically by the
    UnifiedSearchService using the stored embeddings.
    """

    source_name = "memory"

    def __init__(self, db_manager) -> None:
        self._db_manager = db_manager

    def keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search memory facts using SQL LIKE on stored content."""
        try:
            conn = self._db_manager.get_connection()
            try:
                # Use LOWER() for case-insensitive matching
                pattern = f"%{query.lower()}%"
                rows = conn.execute(
                    """SELECT source_id, title, content, metadata
                       FROM search_index
                       WHERE source = 'memory'
                         AND (LOWER(content) LIKE ? OR LOWER(title) LIKE ?)
                       ORDER BY indexed_at DESC
                       LIMIT ?""",
                    (pattern, pattern, limit),
                ).fetchall()
            finally:
                conn.close()

            results = []
            for row in rows:
                source_id, title, content, metadata_raw = row
                metadata = {}
                try:
                    if metadata_raw:
                        import json as _json

                        metadata = _json.loads(metadata_raw)
                except Exception:
                    pass
                snippet = (content or "")[:200]
                results.append(
                    SearchResult(
                        source="memory",
                        source_id=source_id,
                        title=title or source_id,
                        snippet=snippet,
                        url=None,
                        metadata=metadata,
                    )
                )
            return results
        except Exception as e:
            logger.debug(f"MemorySearchProvider keyword search failed: {e}")
            return []

    def get_indexable_content(self, limit: int = 500) -> List[IndexableDocument]:
        """Memory facts are indexed directly via system_index_memory_facts; nothing to reindex here."""
        return []
