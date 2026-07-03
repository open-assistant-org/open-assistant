import os
import tempfile
from pathlib import Path


def get_tmp_dir() -> Path:
    """Return the directory for temporary/offloaded files.

    Resolution order:
      1. TMP_DIR env var
      2. System temp directory (tempfile.gettempdir())

    The path is created on first call if it doesn't exist.
    """
    path = Path(os.getenv("TMP_DIR") or tempfile.gettempdir())
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_artifacts_dir() -> Path:
    """Return the directory for durably stored artifacts.

    Unlike ``get_tmp_dir()`` (which is purged nightly by the tmp cleanup cron),
    this lives under the persistent data directory so stored artifacts survive
    until the user deletes them.

    Resolution order:
      1. ARTIFACTS_DIR env var
      2. <DATA_DIR>/artifacts (DATA_DIR defaults to "data")

    The path is created on first call if it doesn't exist.
    """
    base = os.getenv("ARTIFACTS_DIR") or str(Path(os.getenv("DATA_DIR") or "data") / "artifacts")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path
