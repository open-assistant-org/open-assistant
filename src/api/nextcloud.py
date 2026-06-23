"""Nextcloud API endpoints for file operations."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from src.core.dependencies import get_credentials_repo, get_settings_repo
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.nextcloud import (
    DownloadFileRequest,
    DownloadFileResponse,
    FileContentResponse,
    FileExistsRequest,
    FileExistsResponse,
    FileInfoRequest,
    FileInfoResponse,
    FileListResponse,
    ListFilesRequest,
    NextcloudConnectionTestResponse,
    ReadFileRequest,
    SearchFilesRequest,
)
from src.services.nextcloud import NextcloudService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/nextcloud", tags=["nextcloud"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


def get_nextcloud_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> NextcloudService:
    """Get Nextcloud service with dependencies."""
    return NextcloudService(settings_repo, credentials_repo)


# ============================================================================
# FILE LISTING
# ============================================================================


@router.post("/files/list", response_model=FileListResponse)
async def list_files(
    request: ListFilesRequest, nextcloud_service: NextcloudService = Depends(get_nextcloud_service)
) -> FileListResponse:
    """
    List files in a folder.

    Args:
        request: List files request
        nextcloud_service: Nextcloud service (injected)

    Returns:
        List of files

    Raises:
        HTTPException: If listing fails
    """
    try:
        files = nextcloud_service.list_files(folder_path=request.folder_path)

        return FileListResponse(
            files=[FileInfoResponse(**f) for f in files],
            folder_path=request.folder_path,
            count=len(files),
        )

    except ValueError as e:
        logger.error(f"Invalid Nextcloud configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


# ============================================================================
# FILE READING
# ============================================================================


@router.post("/files/read", response_model=FileContentResponse)
async def read_file(
    request: ReadFileRequest, nextcloud_service: NextcloudService = Depends(get_nextcloud_service)
):
    """
    Read file content.

    Args:
        request: Read file request
        nextcloud_service: Nextcloud service (injected)

    Returns:
        File content (text or bytes)

    Raises:
        HTTPException: If reading fails
    """
    try:
        if request.as_bytes:
            # Read as bytes and return as binary response
            content = nextcloud_service.read_file_bytes(file_path=request.file_path)
            return Response(content=content, media_type="application/octet-stream")
        else:
            # Read as text
            content = nextcloud_service.read_file(file_path=request.file_path)
            return FileContentResponse(
                file_path=request.file_path, content=content, size=len(content)
            )

    except ValueError as e:
        logger.error(f"Invalid Nextcloud configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")


# ============================================================================
# FILE DOWNLOAD
# ============================================================================


@router.post("/files/download", response_model=DownloadFileResponse)
async def download_file(
    request: DownloadFileRequest,
    nextcloud_service: NextcloudService = Depends(get_nextcloud_service),
) -> DownloadFileResponse:
    """
    Download file to local storage.

    Args:
        request: Download request
        nextcloud_service: Nextcloud service (injected)

    Returns:
        Download status

    Raises:
        HTTPException: If download fails
    """
    try:
        nextcloud_service.download_file(
            remote_path=request.remote_path, local_path=request.local_path
        )

        return DownloadFileResponse(
            remote_path=request.remote_path,
            local_path=request.local_path,
            success=True,
            message="File downloaded successfully",
        )

    except ValueError as e:
        logger.error(f"Invalid Nextcloud configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


# ============================================================================
# FILE SEARCH
# ============================================================================


@router.post("/files/search")
async def search_files(
    request: SearchFilesRequest,
    nextcloud_service: NextcloudService = Depends(get_nextcloud_service),
) -> List[FileInfoResponse]:
    """
    Search for files by name.

    Args:
        request: Search request
        nextcloud_service: Nextcloud service (injected)

    Returns:
        List of matching files

    Raises:
        HTTPException: If search fails
    """
    try:
        files = nextcloud_service.search_files(query=request.query, folder_path=request.folder_path)

        return [FileInfoResponse(**f) for f in files]

    except ValueError as e:
        logger.error(f"Invalid Nextcloud configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to search files: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ============================================================================
# FILE INFO
# ============================================================================


@router.post("/files/info", response_model=FileInfoResponse)
async def get_file_info(
    request: FileInfoRequest, nextcloud_service: NextcloudService = Depends(get_nextcloud_service)
) -> FileInfoResponse:
    """
    Get file metadata.

    Args:
        request: File info request
        nextcloud_service: Nextcloud service (injected)

    Returns:
        File information

    Raises:
        HTTPException: If file not found
    """
    try:
        info = nextcloud_service.get_file_info(file_path=request.file_path)
        return FileInfoResponse(**info)

    except ValueError as e:
        logger.error(f"Invalid Nextcloud configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get file info: {e}")
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")


@router.post("/files/exists", response_model=FileExistsResponse)
async def check_file_exists(
    request: FileExistsRequest, nextcloud_service: NextcloudService = Depends(get_nextcloud_service)
) -> FileExistsResponse:
    """
    Check if file exists.

    Args:
        request: File exists request
        nextcloud_service: Nextcloud service (injected)

    Returns:
        File existence status

    Raises:
        HTTPException: If check fails
    """
    try:
        exists = nextcloud_service.file_exists(file_path=request.file_path)
        return FileExistsResponse(file_path=request.file_path, exists=exists)

    except ValueError as e:
        logger.error(f"Invalid Nextcloud configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to check file existence: {e}")
        raise HTTPException(status_code=500, detail=f"Check failed: {str(e)}")


# ============================================================================
# CONNECTION TESTING
# ============================================================================


@router.post("/test-connection", response_model=NextcloudConnectionTestResponse)
async def test_connection(
    nextcloud_service: NextcloudService = Depends(get_nextcloud_service),
) -> NextcloudConnectionTestResponse:
    """
    Test Nextcloud connection.

    Args:
        nextcloud_service: Nextcloud service (injected)

    Returns:
        Connection test result
    """
    result = nextcloud_service.test_connection()
    return NextcloudConnectionTestResponse(**result)
