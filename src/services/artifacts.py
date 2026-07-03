"""Artifact store service: passphrase hashing, filesystem persistence, and link helpers.

Artifacts are files (HTML, PDF, DOCX, images, ...) copied out of ephemeral temp
storage into the durable artifacts directory and tracked in the ``artifacts``
table. This module holds the stateless helpers shared by ``SystemService`` (the
``store_artifact`` tool) and the ``/api/artifacts`` router.
"""

import hashlib
import hmac
import mimetypes
import os
import secrets
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from src.core.config import get_app_config
from src.core.repositories.artifact import ArtifactRepository
from src.utils.logger import get_logger
from src.utils.tmp import get_artifacts_dir

logger = get_logger(__name__)

# PBKDF2 parameters for passphrase hashing.
_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 200_000
_PBKDF2_PREFIX = "pbkdf2_sha256"


# ---------------------------------------------------------------------------
# Passphrase (secret) hashing
# ---------------------------------------------------------------------------


def hash_secret(passphrase: str) -> str:
    """Hash a passphrase with a random per-artifact salt.

    Returns an encoded string ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.
    The plaintext passphrase is never stored.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, passphrase.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_PREFIX}${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_secret(passphrase: str, stored: str) -> bool:
    """Verify a passphrase against a stored hash in constant time."""
    if not stored:
        return False
    try:
        prefix, iterations_s, salt_hex, hash_hex = stored.split("$")
        if prefix != _PBKDF2_PREFIX:
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, passphrase.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


# ---------------------------------------------------------------------------
# Filesystem persistence
# ---------------------------------------------------------------------------


def store_artifact(
    source_path: str,
    repo: ArtifactRepository,
    title: Optional[str] = None,
    make_public: bool = False,
) -> Dict[str, Any]:
    """Copy a file into the durable artifact store and record it.

    Args:
        source_path: Path to the file to persist (e.g. a create_html output)
        repo: ArtifactRepository for the DB record
        title: Optional human-readable title
        make_public: Whether the artifact is publicly viewable

    Returns:
        The created artifact record (as stored in the DB).

    Raises:
        ValueError: If ``source_path`` does not point to an existing file.
    """
    src = Path(source_path).expanduser()
    if not src.exists() or not src.is_file():
        raise ValueError(f"source_path does not point to an existing file: {source_path}")

    artifact_id = str(uuid4())
    dest_dir = get_artifacts_dir() / artifact_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = src.name
    dest = dest_dir / filename
    shutil.copy2(src, dest)

    mime_type = mimetypes.guess_type(filename)[0]
    size = dest.stat().st_size
    rel_path = f"{artifact_id}/{filename}"

    record = repo.create(
        artifact_id=artifact_id,
        filename=filename,
        rel_path=rel_path,
        title=title,
        mime_type=mime_type,
        size=size,
        is_public=make_public,
    )
    logger.info(f"Stored artifact {artifact_id} ({size} bytes) from {source_path}")
    return record


def resolve_artifact_path(artifact: Dict[str, Any]) -> Path:
    """Return the absolute path to a stored artifact's file."""
    return get_artifacts_dir() / artifact["rel_path"]


def delete_artifact_files(artifact: Dict[str, Any]) -> None:
    """Remove an artifact's on-disk directory (best effort)."""
    artifact_dir = get_artifacts_dir() / str(artifact.get("artifact_id", ""))
    if artifact_dir.exists() and artifact_dir.is_dir():
        shutil.rmtree(artifact_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Link helpers
# ---------------------------------------------------------------------------


def _app_url() -> str:
    """Base application URL, without a trailing slash.

    Prefers the initialized global config; falls back to the APP_URL env var (or
    the local default) when config has not been initialized yet.
    """
    try:
        base = get_app_config().general.app_url
    except RuntimeError:
        base = os.getenv("APP_URL", "http://localhost:8080")
    return base.rstrip("/")


def permanent_link(artifact_id: str) -> str:
    """The stable public view URL for an artifact (usable when public)."""
    return f"{_app_url()}/api/artifacts/{artifact_id}/view"


def temporary_link(artifact_id: str, token: str) -> str:
    """A 300s signed view URL for a private artifact."""
    return f"{_app_url()}/api/artifacts/{artifact_id}/view?token={token}"


def management_url() -> str:
    """URL of the Artifacts management tab."""
    return f"{_app_url()}/artifacts"
