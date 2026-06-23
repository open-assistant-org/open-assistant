"""Notion API client for page and database operations."""

import re
from typing import Any, Dict, List, Optional

from notion_client import Client
from notion_client.errors import APIResponseError

from src.utils.logger import get_logger

logger = get_logger(__name__)


def markdown_to_notion_blocks(text: str) -> List[Dict[str, Any]]:
    """
    Convert markdown-formatted text to Notion block objects.

    Supports: headings (# ## ###), bullet lists (- *), numbered lists (1.),
    code blocks (```), blockquotes (>), horizontal rules (---), to-do lists (- [ ] / - [x]),
    and paragraphs. Inline formatting: **bold**, *italic*, `code`, ~~strikethrough~~.

    Args:
        text: Markdown-formatted text

    Returns:
        List of Notion block objects
    """
    blocks: List[Dict[str, Any]] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Blank line — skip
        if not line.strip():
            i += 1
            continue

        # Code block (fenced)
        if line.strip().startswith("```"):
            language = line.strip().removeprefix("```").strip() or "plain text"
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            blocks.append(
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                        "language": language,
                    },
                }
            )
            continue

        # Heading 3
        if line.startswith("### "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {"rich_text": _parse_inline(line[4:].strip())},
                }
            )
            i += 1
            continue

        # Heading 2
        if line.startswith("## "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": _parse_inline(line[3:].strip())},
                }
            )
            i += 1
            continue

        # Heading 1
        if line.startswith("# "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {"rich_text": _parse_inline(line[2:].strip())},
                }
            )
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", line.strip()):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # To-do item
        todo_match = re.match(r"^[-*]\s+\[([ xX])\]\s+(.*)", line)
        if todo_match:
            checked = todo_match.group(1).lower() == "x"
            blocks.append(
                {
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": _parse_inline(todo_match.group(2).strip()),
                        "checked": checked,
                    },
                }
            )
            i += 1
            continue

        # Bulleted list item
        if re.match(r"^[-*]\s+", line):
            content = re.sub(r"^[-*]\s+", "", line).strip()
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _parse_inline(content)},
                }
            )
            i += 1
            continue

        # Numbered list item
        num_match = re.match(r"^\d+[.)]\s+", line)
        if num_match:
            content = line[num_match.end() :].strip()
            blocks.append(
                {
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": _parse_inline(content)},
                }
            )
            i += 1
            continue

        # Blockquote
        if line.startswith("> "):
            quote_lines = [line[2:].strip()]
            i += 1
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:].strip())
                i += 1
            blocks.append(
                {
                    "object": "block",
                    "type": "quote",
                    "quote": {"rich_text": _parse_inline("\n".join(quote_lines))},
                }
            )
            continue

        # Default: paragraph (collect consecutive non-blank, non-special lines)
        para_lines = [line.strip()]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if not next_line.strip():
                break
            if re.match(r"^(#{1,3}\s|[-*]\s|>\s|\d+[.)]\s|```|---+|\*\*\*+|___+)", next_line):
                break
            para_lines.append(next_line.strip())
            i += 1

        # Split long paragraphs to respect Notion's 2000 char limit per block
        full_text = " ".join(para_lines)
        max_chunk_size = 1500  # Safe margin below 2000 char limit

        if len(full_text) <= max_chunk_size:
            # Short paragraph - add as single block
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": _parse_inline(full_text)},
                }
            )
        else:
            # Long paragraph - split into multiple blocks
            chunks = []
            for chunk_start in range(0, len(full_text), max_chunk_size):
                chunks.append(full_text[chunk_start : chunk_start + max_chunk_size])

            for chunk in chunks:
                blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": _parse_inline(chunk)},
                    }
                )

    return blocks


def _parse_inline(text: str) -> List[Dict[str, Any]]:
    """
    Parse inline markdown formatting into Notion rich_text objects.

    Supports **bold**, *italic*, `code`, ~~strikethrough~~.

    Args:
        text: Text with inline markdown formatting

    Returns:
        List of Notion rich_text objects
    """
    rich_text: List[Dict[str, Any]] = []
    # Pattern matches: **bold**, *italic*, `code`, ~~strikethrough~~
    pattern = re.compile(
        r"(\*\*(.+?)\*\*)"  # bold
        r"|(~~(.+?)~~)"  # strikethrough
        r"|(`(.+?)`)"  # inline code
        r"|(\*(.+?)\*)"  # italic
    )

    last_end = 0
    for match in pattern.finditer(text):
        # Add plain text before this match
        if match.start() > last_end:
            plain = text[last_end : match.start()]
            if plain:
                rich_text.append({"type": "text", "text": {"content": plain}})

        if match.group(2):  # bold
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": match.group(2)},
                    "annotations": {"bold": True},
                }
            )
        elif match.group(4):  # strikethrough
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": match.group(4)},
                    "annotations": {"strikethrough": True},
                }
            )
        elif match.group(6):  # inline code
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": match.group(6)},
                    "annotations": {"code": True},
                }
            )
        elif match.group(8):  # italic
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": match.group(8)},
                    "annotations": {"italic": True},
                }
            )

        last_end = match.end()

    # Add remaining text
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            rich_text.append({"type": "text", "text": {"content": remaining}})

    # If no formatting found, return single text block
    if not rich_text:
        rich_text.append({"type": "text", "text": {"content": text}})

    return rich_text


class NotionClient:
    """Client for interacting with Notion API."""

    def __init__(self, api_token: str):
        """
        Initialize Notion client.

        Args:
            api_token: Notion integration token
        """
        self.api_token = api_token
        self.client = Client(auth=api_token)
        logger.info("Notion client initialized")

    def get_data_source_id(self, database_id: str) -> str:
        """
        Get the data_source_id for a database.

        In Notion API version 2025-09-03, databases have data_source IDs that
        are used for creating pages and querying. This method discovers the
        data_source_id from a database_id.

        Args:
            database_id: The database ID to look up

        Returns:
            The data_source_id for the database

        Raises:
            ValueError: If no data sources are found for the database
            APIResponseError: If Notion API request fails
        """
        try:
            logger.info(f"Getting data_source_id for database: {database_id}")
            db = self.client.databases.retrieve(database_id=database_id)
            data_sources = db.get("data_sources", [])
            if not data_sources:
                raise ValueError(f"No data sources found for database {database_id}")
            data_source_id = data_sources[0]["id"]
            logger.info(f"Found data_source_id: {data_source_id}")
            return data_source_id
        except APIResponseError as e:
            logger.error(f"Failed to get data_source_id: {e}")
            raise

    def create_page(
        self,
        database_id: Optional[str] = None,
        parent_page_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        children: Optional[List[Dict[str, Any]]] = None,
        data_source_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new page in Notion.

        Args:
            database_id: Database ID to create page in (mutually exclusive with parent_page_id).
                         Will be resolved to data_source_id automatically.
            parent_page_id: Parent page ID to create child page under
            properties: Page properties (required if database_id provided)
            children: Page content blocks
            data_source_id: Optional data source ID (bypasses discovery if provided)

        Returns:
            Created page object

        Raises:
            ValueError: If neither database_id nor parent_page_id is provided
            APIResponseError: If Notion API request fails
        """
        try:
            if not database_id and not parent_page_id and not data_source_id:
                raise ValueError(
                    "Either database_id, data_source_id, or parent_page_id must be provided"
                )

            parent = {}
            if data_source_id:
                # Use provided data_source_id directly
                parent = {"data_source_id": data_source_id}
            elif database_id:
                # Resolve data_source_id from database_id
                resolved_data_source_id = self.get_data_source_id(database_id)
                parent = {"data_source_id": resolved_data_source_id}
            else:
                parent = {"page_id": parent_page_id}

            page_data = {
                "parent": parent,
                "properties": properties or {},
            }

            if children:
                page_data["children"] = children

            logger.info(
                f"Creating Notion page in {'database' if database_id or data_source_id else 'page'}"
            )
            page = self.client.pages.create(**page_data)
            logger.info(f"Created Notion page: {page['id']}")
            return page

        except APIResponseError as e:
            logger.error(f"Failed to create Notion page: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating Notion page: {e}")
            raise

    def create_child_page(
        self, parent_page_id: str, title: str, content: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a child page under an existing page.

        Args:
            parent_page_id: Parent page ID
            title: Page title
            content: Optional markdown content (auto-converted to Notion blocks)

        Returns:
            Created page object
        """
        properties = {"title": {"title": [{"text": {"content": title}}]}}

        children = []
        if content:
            children = markdown_to_notion_blocks(content)

        return self.create_page(
            parent_page_id=parent_page_id,
            properties=properties,
            children=children if children else None,
        )

    def update_page(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update page properties.

        Args:
            page_id: Page ID to update
            properties: Properties to update

        Returns:
            Updated page object
        """
        try:
            logger.info(f"Updating Notion page: {page_id}")
            page = self.client.pages.update(page_id=page_id, properties=properties)
            logger.info(f"Updated Notion page: {page_id}")
            return page

        except APIResponseError as e:
            logger.error(f"Failed to update Notion page: {e}")
            raise

    def append_blocks(self, page_id: str, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Append content blocks to a page.

        Args:
            page_id: Page ID
            blocks: List of block objects to append

        Returns:
            Response with appended blocks
        """
        try:
            logger.info(f"Appending blocks to Notion page: {page_id}")
            result = self.client.blocks.children.append(block_id=page_id, children=blocks)
            logger.info(f"Appended {len(blocks)} blocks to page: {page_id}")
            return result

        except APIResponseError as e:
            logger.error(f"Failed to append blocks: {e}")
            raise

    def search(
        self,
        query: str,
        filter_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for pages and databases.

        Args:
            query: Search query string
            filter_dict: Optional filter criteria
            sort: Optional sort criteria

        Returns:
            List of matching pages/databases
        """
        try:
            logger.info(f"Searching Notion: {query}")
            search_params = {"query": query}

            if filter_dict:
                search_params["filter"] = filter_dict

            if sort:
                search_params["sort"] = sort

            results = self.client.search(**search_params)
            pages = results.get("results", [])
            logger.info(f"Found {len(pages)} results")
            return pages

        except APIResponseError as e:
            logger.error(f"Failed to search Notion: {e}")
            raise

    def get_page(self, page_id: str) -> Dict[str, Any]:
        """
        Get page properties.

        Args:
            page_id: Page ID

        Returns:
            Page object
        """
        try:
            logger.info(f"Getting Notion page: {page_id}")
            page = self.client.pages.retrieve(page_id=page_id)
            return page

        except APIResponseError as e:
            logger.error(f"Failed to get Notion page: {e}")
            raise

    def get_blocks(self, page_id: str) -> List[Dict[str, Any]]:
        """
        Get page content blocks.

        Args:
            page_id: Page ID

        Returns:
            List of block objects
        """
        try:
            logger.info(f"Getting blocks for Notion page: {page_id}")
            results = self.client.blocks.children.list(block_id=page_id)
            blocks = results.get("results", [])
            logger.info(f"Retrieved {len(blocks)} blocks")
            return blocks

        except APIResponseError as e:
            if e.status == 404:
                logger.warning(
                    f"Page {page_id} not accessible via blocks API — "
                    f"the page may not be shared with the integration"
                )
                raise ValueError(
                    f"Cannot read content of page {page_id}. "
                    f"The page exists but is not shared with the Notion integration. "
                    f"Ask the user to share the page with the integration in Notion."
                )
            logger.error(f"Failed to get blocks: {e}")
            raise

    def query_database(
        self,
        database_id: str,
        filter_dict: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        data_source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query database entries.

        Args:
            database_id: Database ID (will be resolved to data_source_id)
            filter_dict: Optional filter criteria
            sorts: Optional sort criteria
            data_source_id: Optional data source ID (bypasses discovery if provided)

        Returns:
            List of database entries (pages)
        """
        try:
            # Resolve data_source_id
            if data_source_id:
                resolved_id = data_source_id
            else:
                resolved_id = self.get_data_source_id(database_id)

            logger.info(f"Querying Notion data source: {resolved_id}")
            query_params = {"data_source_id": resolved_id}

            if filter_dict:
                query_params["filter"] = filter_dict

            if sorts:
                query_params["sorts"] = sorts

            results = self.client.data_sources.query(**query_params)
            entries = results.get("results", [])
            logger.info(f"Found {len(entries)} database entries")
            return entries

        except APIResponseError as e:
            logger.error(f"Failed to query database: {e}")
            raise

    def create_database_entry(self, database_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create entry in a database.

        Args:
            database_id: Database ID
            properties: Entry properties

        Returns:
            Created page object
        """
        return self.create_page(database_id=database_id, properties=properties)

    def list_data_sources(self) -> List[Dict[str, Any]]:
        """
        List all data sources (databases) accessible to the integration.

        In Notion API version 2025-09-03, databases are exposed as data sources.
        This method searches for data_source objects and returns their information.

        Returns:
            List of data source objects with id, title, and property schemas. Each
            property maps to its type, plus the available choices for select,
            multi_select, and status columns so callers know which values are valid.
        """
        try:
            logger.info("Listing all accessible Notion data sources")
            results = self.client.search(filter={"property": "object", "value": "data_source"})
            data_sources = results.get("results", [])

            parsed = []
            for ds in data_sources:
                title = "Untitled"
                title_parts = ds.get("title", [])
                if title_parts:
                    title = "".join(t.get("plain_text", "") for t in title_parts)

                # Extract property schema: name → {type, options?}.
                # For choice-based columns, expose the valid option names so callers
                # can set them correctly (status options can't be created via the API).
                props = {}
                for prop_name, prop_def in ds.get("properties", {}).items():
                    prop_type = prop_def.get("type", "unknown")
                    schema: Dict[str, Any] = {"type": prop_type}
                    if prop_type in ("select", "multi_select", "status"):
                        options = (prop_def.get(prop_type) or {}).get("options", [])
                        schema["options"] = [opt.get("name") for opt in options]
                    props[prop_name] = schema

                parsed.append(
                    {
                        "id": ds["id"],
                        "title": title,
                        "url": ds.get("url", ""),
                        "properties": props,
                        "created_time": ds.get("created_time"),
                        "last_edited_time": ds.get("last_edited_time"),
                    }
                )

            logger.info(f"Found {len(parsed)} data sources")
            return parsed

        except APIResponseError as e:
            logger.error(f"Failed to list data sources: {e}")
            raise

    def list_databases(self) -> List[Dict[str, Any]]:
        """
        List all databases accessible to the integration.

        This is an alias for list_data_sources() for backward compatibility.
        In Notion API version 2025-09-03, databases are exposed as data sources.

        Returns:
            List of database/data source objects with id, title, and property schemas
        """
        return self.list_data_sources()

    def archive_page(self, page_id: str) -> Dict[str, Any]:
        """
        Archive (soft-delete) a Notion page.

        Args:
            page_id: Page ID to archive

        Returns:
            Updated page object with archived=True
        """
        try:
            logger.info(f"Archiving Notion page: {page_id}")
            page = self.client.pages.update(page_id=page_id, archived=True)
            logger.info(f"Archived Notion page: {page_id}")
            return page

        except APIResponseError as e:
            logger.error(f"Failed to archive Notion page: {e}")
            raise
