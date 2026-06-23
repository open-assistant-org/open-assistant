"""Nextcloud API request and response models."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ListFilesRequest(BaseModel):
    """Request model for listing files."""

    folder_path: str = Field("/", description="Folder path to list (default: root)")


class ReadFileRequest(BaseModel):
    """Request model for reading a file."""

    file_path: str = Field(..., description="File path to read")
    as_bytes: bool = Field(False, description="Read as bytes instead of text")


class DownloadFileRequest(BaseModel):
    """Request model for downloading a file."""

    remote_path: str = Field(..., description="Remote file path")
    local_path: str = Field(..., description="Local path to save file")


class SearchFilesRequest(BaseModel):
    """Request model for searching files."""

    query: str = Field(..., description="Search query (filename pattern, case-insensitive)")
    folder_path: Optional[str] = Field(
        None, description="Optional folder to start search in (default: root '/')"
    )
    recursive: bool = Field(
        True, description="If true, search in subdirectories as well (default: true)"
    )
    max_results: int = Field(100, description="Maximum number of results to return", ge=1, le=500)


class ReadPdfRequest(BaseModel):
    """Request model for reading and extracting text from a PDF file in Nextcloud."""

    file_path: str = Field(
        ..., description="Path to the PDF file in Nextcloud (e.g. /Documents/report.pdf)"
    )


class FileInfoRequest(BaseModel):
    """Request model for getting file info."""

    file_path: str = Field(..., description="File path")


class FileExistsRequest(BaseModel):
    """Request model for checking file existence."""

    file_path: str = Field(..., description="File path to check")


class UploadFileRequest(BaseModel):
    """Request model for uploading a file."""

    remote_path: str = Field(
        ..., description="Remote file path in Nextcloud (e.g. /Documents/notes.txt)"
    )
    content: Optional[str] = Field(
        default=None,
        description="File content as a string. Use this for text files, or provide source_path for local files.",
    )
    content_encoding: Literal["text", "base64"] = Field(
        "text",
        description="Encoding of the content field. Use 'text' for plain text (default), or 'base64' for binary content.",
    )
    source_path: Optional[str] = Field(
        default=None,
        description="Local file path to upload. If provided, content is ignored and the file at source_path is read and uploaded to remote_path.",
    )


class CreateFolderRequest(BaseModel):
    """Request model for creating a folder."""

    folder_path: str = Field(..., description="Folder path to create (e.g. /Documents/NewFolder)")


class DeleteFileRequest(BaseModel):
    """Request model for deleting a file or folder."""

    file_path: str = Field(..., description="Path of file or folder to delete")


class MoveFileRequest(BaseModel):
    """Request model for moving/renaming a file."""

    source_path: str = Field(..., description="Current file/folder path")
    destination_path: str = Field(..., description="New file/folder path")


class CopyFileRequest(BaseModel):
    """Request model for copying a file."""

    source_path: str = Field(..., description="Source file/folder path")
    destination_path: str = Field(..., description="Destination file/folder path")


class FileInfoResponse(BaseModel):
    """Response model for file information."""

    name: str = Field(..., description="File name")
    path: str = Field(..., description="File path")
    type: str = Field(..., description="Type (file or directory)")
    size: Optional[int] = Field(None, description="File size in bytes")
    modified: Optional[str] = Field(None, description="Last modified timestamp")
    created: Optional[str] = Field(None, description="Creation timestamp")
    mime_type: Optional[str] = Field(None, description="MIME type")
    etag: Optional[str] = Field(None, description="ETag for caching")


class FileListResponse(BaseModel):
    """Response model for file listing."""

    files: List[FileInfoResponse] = Field(..., description="List of files")
    folder_path: str = Field(..., description="Folder that was listed")
    count: int = Field(..., description="Number of files")


class FileContentResponse(BaseModel):
    """Response model for file content."""

    file_path: str = Field(..., description="File path")
    content: str = Field(..., description="File content")
    size: int = Field(..., description="Content size")


class FileExistsResponse(BaseModel):
    """Response model for file existence check."""

    file_path: str = Field(..., description="File path")
    exists: bool = Field(..., description="Whether file exists")


class DownloadFileResponse(BaseModel):
    """Response model for file download."""

    remote_path: str = Field(..., description="Remote file path")
    local_path: str = Field(..., description="Local file path")
    success: bool = Field(..., description="Whether download was successful")
    message: str = Field(..., description="Status message")


class NextcloudConnectionTestResponse(BaseModel):
    """Response model for connection test."""

    service_name: str = Field(..., description="Service name")
    status: str = Field(..., description="Connection status (success, error, warning)")
    message: str = Field(..., description="Status message")
