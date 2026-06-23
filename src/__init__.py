"""Open Assistant - AI-powered task automation and integration."""

import tomllib
from pathlib import Path

# Read version from pyproject.toml
try:
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)
        __version__ = pyproject["project"]["version"]
except (FileNotFoundError, KeyError):
    __version__ = "unknown"
