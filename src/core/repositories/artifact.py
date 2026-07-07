"""Repository for artifact store operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.repositories.base import BaseRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ArtifactRepository(BaseRepository):
    """Repository for managing stored artifacts."""

    def create(
        self,
        artifact_id: str,
        filename: str,
        rel_path: str,
        title: Optional[str] = None,
        mime_type: Optional[str] = None,
        size: Optional[int] = None,
        is_public: bool = False,
    ) -> Dict[str, Any]:
        """Create a new artifact record.

        Args:
            artifact_id: Unique artifact ID (uuid4)
            filename: Original filename
            rel_path: Path relative to the artifacts directory
            title: Optional human-readable title
            mime_type: Detected MIME type
            size: File size in bytes
            is_public: Whether the artifact is publicly viewable

        Returns:
            Created artifact dictionary
        """
        now = datetime.utcnow().isoformat()
        data = {
            "artifact_id": artifact_id,
            "title": title,
            "filename": filename,
            "rel_path": rel_path,
            "mime_type": mime_type,
            "size": size,
            "is_public": 1 if is_public else 0,
            "secret_hash": None,
            "created_at": now,
            "updated_at": now,
        }

        self.insert("artifacts", data)
        logger.info(f"Created artifact: {artifact_id}")

        return self.get_by_id(artifact_id)

    def get_by_id(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Get an artifact by its ID."""
        return self.fetch_one("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,))

    def list_all(self) -> List[Dict[str, Any]]:
        """List all artifacts, newest first."""
        return self.fetch_all("SELECT * FROM artifacts ORDER BY created_at DESC")

    def set_public(self, artifact_id: str, is_public: bool) -> bool:
        """Set the public/private visibility of an artifact."""
        data = {
            "is_public": 1 if is_public else 0,
            "updated_at": datetime.utcnow().isoformat(),
        }
        affected = self.update("artifacts", data, "artifact_id = ?", (artifact_id,))
        return affected > 0

    def set_secret(self, artifact_id: str, secret_hash: Optional[str]) -> bool:
        """Set or clear the passphrase hash for an artifact.

        Args:
            artifact_id: Artifact ID
            secret_hash: Salted hash to store, or None to disable the passphrase gate
        """
        data = {
            "secret_hash": secret_hash,
            "updated_at": datetime.utcnow().isoformat(),
        }
        affected = self.update("artifacts", data, "artifact_id = ?", (artifact_id,))
        return affected > 0

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact record."""
        affected = self.delete("artifacts", "artifact_id = ?", (artifact_id,))
        if affected > 0:
            logger.info(f"Deleted artifact: {artifact_id}")
        return affected > 0
