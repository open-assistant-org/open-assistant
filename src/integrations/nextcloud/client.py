"""Nextcloud WebDAV client for file operations."""

import io
from typing import Any, Dict, List, Optional

from webdav3.client import Client
from webdav3.exceptions import WebDavException

from src.utils.logger import get_logger

logger = get_logger(__name__)


class NextcloudClient:
    """Client for interacting with Nextcloud via WebDAV."""

    def __init__(self, server_url: str, username: str, password: str, verify_ssl: bool = True):
        """
        Initialize Nextcloud WebDAV client.

        Args:
            server_url: Nextcloud server URL (e.g., https://cloud.example.com)
            username: Nextcloud username
            password: Nextcloud password or app password
            verify_ssl: Whether to verify SSL certificates (default: True)
        """
        self.server_url = server_url
        self.username = username

        # Construct WebDAV root path
        webdav_root = f"/remote.php/dav/files/{username}/"

        # Configure WebDAV client
        options = {
            "webdav_hostname": server_url,
            "webdav_login": username,
            "webdav_password": password,
            "webdav_root": webdav_root,
        }

        if not verify_ssl:
            options["disable_check"] = True
            logger.warning(
                "SSL verification disabled for Nextcloud - not recommended for production"
            )

        self.client = Client(options)
        logger.info(f"Nextcloud client initialized for {server_url}")

    def list_files(self, folder_path: str = "/") -> List[Dict[str, Any]]:
        """
        List files in a folder.

        Args:
            folder_path: Folder path (relative to user root, default: "/")

        Returns:
            List of file/folder information dictionaries

        Raises:
            WebDavException: If listing fails
        """
        try:
            logger.info(f"Listing files in Nextcloud folder: {folder_path}")

            # Get list of resources
            resources = self.client.list(folder_path)

            files = []
            for resource in resources:
                # Handle both string paths and dict resources
                if isinstance(resource, dict):
                    resource_path = resource.get("path", "")
                    # Skip the folder itself
                    if not resource_path or resource_path == folder_path:
                        continue

                    # Use info from dict if available
                    files.append(
                        {
                            "name": resource.get("name", resource_path.split("/")[-1]),
                            "path": resource_path,
                            "type": resource.get("type", "unknown"),
                            "size": resource.get("size"),
                            "modified": resource.get("modified"),
                            "created": resource.get("created"),
                        }
                    )
                else:
                    # resource is a string path
                    # Skip the folder itself
                    if resource == folder_path or resource.endswith(folder_path):
                        continue

                    # Get info for each resource
                    try:
                        info = self.client.info(resource)
                    except Exception as e:
                        logger.warning(f"Failed to get info for {resource}: {e}")
                        info = {}

                    files.append(
                        {
                            "name": (
                                resource.split("/")[-2]
                                if resource.endswith("/")
                                else resource.split("/")[-1]
                            ),
                            "path": resource,
                            "type": "directory" if resource.endswith("/") else "file",
                            "size": int(info.get("size", 0)) if info.get("size") else None,
                            "modified": info.get("modified"),
                            "created": info.get("created"),
                        }
                    )

            logger.info(f"Found {len(files)} items in {folder_path}")
            return files

        except WebDavException as e:
            logger.error(f"Failed to list Nextcloud files: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing files: {e}")
            raise

    def read_file(self, file_path: str) -> str:
        """
        Read file content as text.

        Args:
            file_path: File path (relative to user root)

        Returns:
            File content as string

        Raises:
            WebDavException: If reading fails
        """
        try:
            logger.info(f"Reading Nextcloud file: {file_path}")

            # Download to buffer
            buffer = io.BytesIO()
            self.client.download_from(buffer, file_path)
            buffer.seek(0)

            # Decode as UTF-8 text
            content = buffer.read().decode("utf-8")
            logger.info(f"Read {len(content)} characters from {file_path}")
            return content

        except WebDavException as e:
            logger.error(f"Failed to read Nextcloud file: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading file: {e}")
            raise

    def read_file_bytes(self, file_path: str) -> bytes:
        """
        Read file content as bytes.

        Args:
            file_path: File path (relative to user root)

        Returns:
            File content as bytes

        Raises:
            WebDavException: If reading fails
        """
        try:
            logger.info(f"Reading Nextcloud file as bytes: {file_path}")

            # Download to buffer
            buffer = io.BytesIO()
            self.client.download_from(buffer, file_path)
            buffer.seek(0)

            content = buffer.read()
            logger.info(f"Read {len(content)} bytes from {file_path}")
            return content

        except WebDavException as e:
            logger.error(f"Failed to read Nextcloud file: {e}")
            raise

    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Download file to local storage.

        Args:
            remote_path: Remote file path
            local_path: Local file path to save to

        Raises:
            WebDavException: If download fails
        """
        try:
            logger.info(f"Downloading Nextcloud file: {remote_path} -> {local_path}")
            self.client.download_sync(remote_path=remote_path, local_path=local_path)
            logger.info(f"Downloaded file to {local_path}")

        except WebDavException as e:
            logger.error(f"Failed to download file: {e}")
            raise

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
            query: Search query (file name pattern, case-insensitive substring match)
            folder_path: Optional folder to start search in (default: root "/")
            recursive: If True, search in subdirectories as well (default: True)
            max_results: Maximum number of results to return (default: 100)

        Returns:
            List of matching files with their full paths

        Note:
            This is a client-side search by filename.
            When recursive=True, it traverses subdirectories to find all matches.
        """
        try:
            logger.info(
                f"Searching Nextcloud for: {query} (recursive={recursive}, folder={folder_path})"
            )

            # If folder specified, search in that folder
            # Otherwise search from root
            search_path = folder_path if folder_path else "/"
            query_lower = query.lower()
            matching_files = []

            def search_in_folder(path: str, depth: int = 0) -> None:
                """Recursively search in folder."""
                # Limit recursion depth to prevent infinite loops
                if depth > 10 or len(matching_files) >= max_results:
                    return

                try:
                    items = self.list_files(path)
                    for item in items:
                        if len(matching_files) >= max_results:
                            return

                        # Check if name matches query
                        if query_lower in item["name"].lower():
                            # Add full path for clarity
                            item["full_path"] = (
                                f"{path.rstrip('/')}/{item['name']}"
                                if path != "/"
                                else f"/{item['name']}"
                            )
                            matching_files.append(item)

                        # Recursively search in subdirectories
                        if recursive and item["type"] == "directory":
                            subdir_path = (
                                f"{path.rstrip('/')}/{item['name']}"
                                if path != "/"
                                else f"/{item['name']}"
                            )
                            search_in_folder(subdir_path, depth + 1)
                except Exception as e:
                    logger.warning(f"Error searching in {path}: {e}")

            search_in_folder(search_path)

            logger.info(f"Found {len(matching_files)} files matching '{query}'")
            return matching_files

        except Exception as e:
            logger.error(f"Failed to search files: {e}")
            raise

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get file metadata.

        Args:
            file_path: File path

        Returns:
            File information dictionary

        Raises:
            WebDavException: If file doesn't exist or info retrieval fails
        """
        try:
            logger.info(f"Getting info for Nextcloud file: {file_path}")

            info = self.client.info(file_path)

            file_info = {
                "name": file_path.split("/")[-1],
                "path": file_path,
                "type": "directory" if info.get("isdir") else "file",
                "size": int(info.get("size", 0)) if info.get("size") else None,
                "modified": info.get("modified"),
                "created": info.get("created"),
                "mime_type": info.get("content_type"),
                "etag": info.get("etag"),
            }

            return file_info

        except WebDavException as e:
            logger.error(f"Failed to get file info: {e}")
            raise

    def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists.

        Args:
            file_path: File path to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            return self.client.check(file_path)
        except Exception as e:
            logger.error(f"Error checking file existence: {e}")
            return False

    def upload_file(self, remote_path: str, content: bytes = None, source_path: str = None) -> bool:
        """
        Upload file content to Nextcloud.

        Args:
            remote_path: Remote file path to create/overwrite
            content: File content as bytes
            source_path: Local file path to read and upload. Takes precedence over content.

        Returns:
            True if upload successful

        Raises:
            WebDavException: If upload fails
        """
        try:
            if source_path:
                with open(source_path, "rb") as f:
                    content = f.read()
            logger.info(f"Uploading to Nextcloud: {remote_path}")

            buffer = io.BytesIO(content)
            self.client.upload_to(buffer, remote_path)

            logger.info(f"Uploaded {len(content)} bytes to {remote_path}")
            return True

        except WebDavException as e:
            logger.error(f"Failed to upload file: {e}")
            raise

    def create_folder(self, folder_path: str) -> bool:
        """
        Create a folder in Nextcloud.

        Args:
            folder_path: Folder path to create

        Returns:
            True if created successfully

        Raises:
            WebDavException: If creation fails
        """
        try:
            logger.info(f"Creating Nextcloud folder: {folder_path}")
            self.client.mkdir(folder_path)
            logger.info(f"Created folder: {folder_path}")
            return True

        except WebDavException as e:
            logger.error(f"Failed to create folder: {e}")
            raise

    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file or folder from Nextcloud.

        Args:
            file_path: Path to delete

        Returns:
            True if deleted successfully

        Raises:
            WebDavException: If deletion fails
        """
        try:
            logger.info(f"Deleting from Nextcloud: {file_path}")
            self.client.clean(file_path)
            logger.info(f"Deleted: {file_path}")
            return True

        except WebDavException as e:
            logger.error(f"Failed to delete: {e}")
            raise

    def move_file(self, source_path: str, destination_path: str) -> bool:
        """
        Move or rename a file/folder in Nextcloud.

        Args:
            source_path: Current path
            destination_path: New path

        Returns:
            True if moved successfully

        Raises:
            WebDavException: If move fails
        """
        try:
            logger.info(f"Moving in Nextcloud: {source_path} -> {destination_path}")
            self.client.move(remote_path_from=source_path, remote_path_to=destination_path)
            logger.info(f"Moved: {source_path} -> {destination_path}")
            return True

        except WebDavException as e:
            logger.error(f"Failed to move: {e}")
            raise

    def copy_file(self, source_path: str, destination_path: str) -> bool:
        """
        Copy a file/folder in Nextcloud.

        Args:
            source_path: Source path
            destination_path: Destination path

        Returns:
            True if copied successfully

        Raises:
            WebDavException: If copy fails
        """
        try:
            logger.info(f"Copying in Nextcloud: {source_path} -> {destination_path}")
            self.client.copy(remote_path_from=source_path, remote_path_to=destination_path)
            logger.info(f"Copied: {source_path} -> {destination_path}")
            return True

        except WebDavException as e:
            logger.error(f"Failed to copy: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Test connection to Nextcloud server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to check root directory
            self.client.check("/")
            logger.info("Nextcloud connection test successful")
            return True
        except Exception as e:
            logger.error(f"Nextcloud connection test failed: {e}")
            return False
