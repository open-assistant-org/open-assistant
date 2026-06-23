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
