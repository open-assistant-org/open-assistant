"""Nextcloud service for file operations."""

import base64
import uuid
from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.nextcloud.client import NextcloudClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NextcloudService(BaseService):
    """Service for Nextcloud integration operations."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        """
        Initialize Nextcloud service.

        Args:
            settings_repo: Settings repository
            credentials_repo: Credentials repository
            audit_repo: Audit log repository (optional)
        """
        super().__init__(settings_repo, credentials_repo, audit_repo)

    def _get_client(self) -> NextcloudClient:
        """
        Get configured Nextcloud client.

        Returns:
            NextcloudClient instance

        Raises:
            ValueError: If Nextcloud is not configured or credentials are missing
        """
        # Check if Nextcloud is enabled
        enabled = self.settings_repo.get("nextcloud.enabled")
        if not enabled:
            raise ValueError("Nextcloud integration is not enabled")

        # Get server URL and username from settings
        server_url = self.settings_repo.get("nextcloud.url")
        username = self.settings_repo.get("nextcloud.username")

        if not server_url:
            raise ValueError("Nextcloud server URL not configured")
        if not username:
            raise ValueError("Nextcloud username not configured")

        # Get password from credentials
        creds = self.credentials_repo.get("nextcloud")
        if not creds:
            raise ValueError("Nextcloud credentials not found. Please configure password first.")

        password = creds.get("credential_data", {}).get("password")
        if not password:
            raise ValueError("Nextcloud password is empty")

        # Get optional SSL verification setting (default: True)
        verify_ssl = self.settings_repo.get("nextcloud.verify_ssl")
        if verify_ssl is None:
            verify_ssl = True

        return NextcloudClient(
            server_url=server_url, username=username, password=password, verify_ssl=verify_ssl
        )

    def list_files(self, folder_path: str = "/") -> List[Dict[str, Any]]:
        """
        List files in a folder.

        Args:
            folder_path: Folder path (default: root)

        Returns:
            List of file information

        Raises:
            ValueError: If Nextcloud is not configured
        """
        client = self._get_client()
        return client.list_files(folder_path=folder_path)

    def read_file(self, file_path: str) -> str:
        """
        Read file content as text.

        Args:
            file_path: File path

        Returns:
            File content as string

        Raises:
            ValueError: If Nextcloud is not configured
        """
        client = self._get_client()
        return client.read_file(file_path=file_path)

    def read_file_bytes(self, file_path: str) -> bytes:
        """
        Read file content as bytes.

        Args:
            file_path: File path

        Returns:
            File content as bytes

        Raises:
            ValueError: If Nextcloud is not configured
        """
        client = self._get_client()
        return client.read_file_bytes(file_path=file_path)

    def read_pdf(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text from a PDF file stored in Nextcloud using Mistral OCR.

        Downloads the PDF bytes from Nextcloud and sends them to Mistral OCR for
        text extraction. If Mistral OCR is not configured, returns a clear error
        message for both the LLM and the user.

        Args:
            file_path: Path to the PDF file in Nextcloud

        Returns:
            Dict with extracted_text, filename, char_count, and success flag.
            On failure, returns success=False with a descriptive error message.
        """
        import base64

        from src.services.mistral_ocr import MistralOCRService

        filename = file_path.split("/")[-1] or "document.pdf"

        # Validate it's a PDF
        if not filename.lower().endswith(".pdf"):
            return {
                "success": False,
                "error": (
                    f"The file '{filename}' does not appear to be a PDF. "
                    "This tool only supports PDF text extraction. "
                    "For plain text files use the nextcloud_read_file tool instead."
                ),
            }

        # Check Mistral OCR is reachable before downloading the (potentially large) file
        ocr_service = MistralOCRService(self.settings_repo, self.credentials_repo, self.audit_repo)
        config = ocr_service._get_config()
        if not config["api_key"]:
            return {
                "success": False,
                "error": (
                    "Mistral OCR is not configured. PDF text extraction requires a Mistral API key. "
                    "Please set 'mistral_ocr.api_key' (or 'llm.api_key') in Settings to enable this feature."
                ),
            }

        # Download PDF bytes from Nextcloud
        try:
            pdf_bytes = self.read_file_bytes(file_path=file_path)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to download '{file_path}' from Nextcloud: {str(e)}",
            }

        # Run OCR
        try:
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
            result = ocr_service.extract_text_from_pdf(pdf_base64=pdf_base64, filename=filename)
            return {
                "success": True,
                "filename": filename,
                "file_path": file_path,
                "extracted_text": result["text"],
                "char_count": result["char_count"],
                "model": result["model"],
                "message": f"Successfully extracted {result['char_count']} characters from '{filename}' using Mistral OCR.",
            }
        except Exception as e:
            error_str = str(e)
            # Surface a friendly message when the OCR model or credentials are invalid
            if (
                "api_key" in error_str.lower()
                or "authentication" in error_str.lower()
                or "unauthorized" in error_str.lower()
            ):
                user_message = (
                    "Mistral OCR authentication failed. "
                    "Please verify the API key under Settings → Mistral OCR."
                )
            elif "model" in error_str.lower() or "not found" in error_str.lower():
                user_message = (
                    f"The configured Mistral OCR model ('{config['model']}') was not found. "
                    "Check the model name under Settings → Mistral OCR."
                )
            else:
                user_message = f"Mistral OCR extraction failed for '{filename}': {error_str}"
            return {
                "success": False,
                "error": user_message,
            }

    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Download file to local storage.

        Args:
            remote_path: Remote file path
            local_path: Local file path

        Raises:
            ValueError: If Nextcloud is not configured
        """
        client = self._get_client()
        client.download_file(remote_path=remote_path, local_path=local_path)

    def search_files(
        self,
        query: str,
        folder_path: Optional[str] = None,
        recursive: bool = True,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search for files by name.

        Args:
            query: Search query (case-insensitive filename pattern)
            folder_path: Optional folder to start search in (default: root)
            recursive: If True, search in subdirectories as well (default: True)
            max_results: Maximum number of results to return (default: 100)

        Returns:
            List of matching files with full paths

        Raises:
            ValueError: If Nextcloud is not configured
        """
        client = self._get_client()
        return client.search_files(
            query=query, folder_path=folder_path, recursive=recursive, max_results=max_results
        )

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get file metadata.

        Args:
            file_path: File path

        Returns:
            File information

        Raises:
            ValueError: If Nextcloud is not configured
        """
        client = self._get_client()
        return client.get_file_info(file_path=file_path)

    def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists.

        Args:
            file_path: File path

        Returns:
            True if file exists

        Raises:
            ValueError: If Nextcloud is not configured
        """
        client = self._get_client()
        return client.file_exists(file_path=file_path)

    def upload_file(
        self,
        remote_path: str,
        content: Optional[str] = None,
        content_encoding: str = "text",
        source_path: Optional[str] = None,
    ) -> bool:
        """
        Upload content to a file in Nextcloud.

        Args:
            remote_path: Remote file path to create/overwrite
            content: File content as text or base64-encoded string
            content_encoding: 'text' for plain text (default), 'base64' for binary
            source_path: Local file path to read and upload. Takes precedence over content.

        Returns:
            True if uploaded successfully
        """
        client = self._get_client()
        if source_path:
            with open(source_path, "rb") as f:
                content_bytes = f.read()
        elif isinstance(content, bytes):
            content_bytes = content
        elif content_encoding == "base64":
            content_bytes = base64.b64decode(content)
        else:
            content_bytes = (content or "").encode("utf-8")

        return client.upload_file(remote_path=remote_path, content=content_bytes)

    def create_folder(self, folder_path: str) -> bool:
        """
        Create a folder in Nextcloud.

        Args:
            folder_path: Folder path to create

        Returns:
            True if created
        """
        client = self._get_client()
        return client.create_folder(folder_path=folder_path)

    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file or folder from Nextcloud.

        Args:
            file_path: Path to delete

        Returns:
            True if deleted
        """
        client = self._get_client()
        return client.delete_file(file_path=file_path)

    def move_file(self, source_path: str, destination_path: str) -> bool:
        """
        Move or rename a file/folder in Nextcloud.

        Args:
            source_path: Current path
            destination_path: New path

        Returns:
            True if moved
        """
        client = self._get_client()
        return client.move_file(source_path=source_path, destination_path=destination_path)

    def copy_file(self, source_path: str, destination_path: str) -> bool:
        """
        Copy a file/folder in Nextcloud.

        Args:
            source_path: Source path
            destination_path: Destination path

        Returns:
            True if copied
        """
        client = self._get_client()
        return client.copy_file(source_path=source_path, destination_path=destination_path)

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Nextcloud connection.

        Returns:
            Dictionary with test results
        """
        try:
            client = self._get_client()

            # Try to test connection
            success = client.test_connection()

            if success:
                return {
                    "service_name": "nextcloud",
                    "status": "success",
                    "message": "Connection successful",
                }
            else:
                return {
                    "service_name": "nextcloud",
                    "status": "error",
                    "message": "Connection test failed",
                }

        except ValueError as e:
            return {"service_name": "nextcloud", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Nextcloud connection test failed: {e}")
            return {
                "service_name": "nextcloud",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }
