"""Notion service for managing notes and pages."""

from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.notion.client import NotionClient, markdown_to_notion_blocks
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NotionService(BaseService):
    """Service for Notion integration operations."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        """
        Initialize Notion service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository (optional)
        """
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_client(self) -> NotionClient:
        """
        Get configured Notion client.

        Returns:
            NotionClient instance

        Raises:
            ValueError: If Notion is not configured or credentials are missing
        """
        # Check if Notion is enabled
        enabled = self.settings_repo.get("notion.enabled")
        if not enabled:
            raise ValueError("Notion integration is not enabled")

        # Get API token from credentials
        creds = self.credentials_repo.get("notion")
        if not creds:
            raise ValueError("Notion credentials not found. Please configure API token first.")

        credential_data = creds.get("credential_data", {})
        api_token = credential_data.get("api_key") or credential_data.get("value")
        if not api_token:
            raise ValueError("Notion API token is empty")

        return NotionClient(api_token=api_token)

    def create_note(
        self,
        title: str,
        content: Optional[str] = None,
        database_id: Optional[str] = None,
        parent_page_id: Optional[str] = None,
        data_source_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new note in Notion.

        Args:
            title: Note title
            content: Note content (markdown-style text)
            database_id: Optional database ID to create in
            parent_page_id: Optional parent page ID to create under
            data_source_id: Optional data source ID (bypasses discovery if provided)
            properties: Optional extra database column values in Notion property-value
                format (e.g. select, status, date). Merged with the title; only applied
                when creating inside a database.

        Returns:
            Created page object

        Raises:
            ValueError: If Notion is not configured
        """
        client = self._get_client()

        # If no database_id or parent_page_id provided, try to get from settings
        # If still not available, search for an accessible page to use as parent
        if not database_id and not parent_page_id:
            database_id = self.settings_repo.get("notion.database_id")

            if not database_id:
                # Try to find a page to use as parent
                try:
                    # Search for any accessible pages
                    pages = client.search(
                        query="", filter_dict={"property": "object", "value": "page"}
                    )
                    if pages and len(pages) > 0:
                        # Use the first accessible page as parent
                        parent_page_id = pages[0]["id"]
                        page_title = "Unknown"
                        try:
                            # Try to extract page title
                            props = pages[0].get("properties", {})
                            if "title" in props:
                                title_obj = props["title"]
                                if "title" in title_obj and len(title_obj["title"]) > 0:
                                    page_title = title_obj["title"][0].get("plain_text", "Unknown")
                        except:
                            pass
                        logger.info(f"Auto-selected '{page_title}' as parent page")
                    else:
                        raise ValueError(
                            "No parent page or database configured. Please either:\n"
                            "1. Set 'notion.database_id' in Settings to a database ID, OR\n"
                            "2. Share a page with your Notion integration\n"
                            "You can find page/database IDs in the URL when viewing them in Notion."
                        )
                except ValueError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to search for parent page: {e}")
                    raise ValueError(
                        f"Could not find a parent page: {e}\n"
                        "Please configure 'notion.database_id' in Settings or share a page with your integration."
                    )

        if database_id or data_source_id:
            # Create in database with title property, plus any extra column values
            note_properties = {"Name": {"title": [{"text": {"content": title}}]}}
            if properties:
                note_properties.update(properties)

            children = []
            if content:
                children = markdown_to_notion_blocks(content)

            return client.create_page(
                database_id=database_id,
                properties=note_properties,
                children=children if children else None,
                data_source_id=data_source_id,
            )
        else:
            # Create as child page
            return client.create_child_page(
                parent_page_id=parent_page_id, title=title, content=content
            )

    def search_pages(self, query: str, filter_type: Optional[str] = "page") -> List[Dict[str, Any]]:
        """
        Search for pages in Notion.

        Args:
            query: Search query
            filter_type: Filter by type ("page" or "database")

        Returns:
            List of matching pages
        """
        client = self._get_client()

        filter_dict = None
        if filter_type:
            filter_dict = {"property": "object", "value": filter_type}

        return client.search(query=query, filter_dict=filter_dict)

    def get_page(self, page_id: str) -> Dict[str, Any]:
        """
        Get page details.

        Args:
            page_id: Page ID

        Returns:
            Page object
        """
        client = self._get_client()
        return client.get_page(page_id=page_id)

    def get_page_content(self, page_id: str) -> List[Dict[str, Any]]:
        """
        Get page content blocks.

        Args:
            page_id: Page ID

        Returns:
            List of content blocks
        """
        client = self._get_client()
        return client.get_blocks(page_id=page_id)

    def update_page(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update page properties.

        Args:
            page_id: Page ID
            properties: Properties to update

        Returns:
            Updated page object
        """
        client = self._get_client()
        return client.update_page(page_id=page_id, properties=properties)

    def append_content(self, page_id: str, content: str) -> Dict[str, Any]:
        """
        Append content to a page. Markdown is auto-converted to Notion blocks.

        Args:
            page_id: Page ID
            content: Content to append (supports markdown formatting)

        Returns:
            Response with appended blocks
        """
        client = self._get_client()
        blocks = markdown_to_notion_blocks(content)
        return client.append_blocks(page_id=page_id, blocks=blocks)

    def query_database(
        self,
        database_id: Optional[str] = None,
        filter_dict: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        data_source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query database entries.

        Args:
            database_id: Database ID (uses default if not provided)
            filter_dict: Optional filter criteria
            sorts: Optional sort criteria
            data_source_id: Optional data source ID (bypasses discovery if provided)

        Returns:
            List of database entries
        """
        client = self._get_client()

        if not database_id and not data_source_id:
            database_id = self.settings_repo.get("notion.database_id")
            if not database_id:
                raise ValueError("No database_id provided and no default database configured")

        return client.query_database(
            database_id=database_id,
            filter_dict=filter_dict,
            sorts=sorts,
            data_source_id=data_source_id,
        )

    def list_databases(self) -> List[Dict[str, Any]]:
        """
        List all databases accessible to the Notion integration.

        Returns:
            List of database objects with id, title, and property schemas
        """
        client = self._get_client()
        return client.list_databases()

    def list_data_sources(self) -> List[Dict[str, Any]]:
        """
        List all data sources (databases) accessible to the Notion integration.

        Returns:
            List of data source objects with id, title, and property schemas
        """
        client = self._get_client()
        return client.list_data_sources()

    def delete_page(self, page_id: str) -> Dict[str, Any]:
        """
        Delete (archive) a Notion page.

        Args:
            page_id: Page ID to archive

        Returns:
            Archived page object
        """
        client = self._get_client()
        return client.archive_page(page_id=page_id)

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Notion connection.

        Returns:
            Dictionary with test results
        """
        try:
            client = self._get_client()

            # Try a simple search to verify connection
            client.search(query="", filter_dict={"property": "object", "value": "page"})

            return {
                "service_name": "notion",
                "status": "success",
                "message": "Connection successful",
            }

        except ValueError as e:
            return {"service_name": "notion", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Notion connection test failed: {e}")
            return {
                "service_name": "notion",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }
