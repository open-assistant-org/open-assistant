"""Shared pytest fixtures and configuration."""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from cryptography.fernet import Fernet

from src.core.database import DatabaseManager
from src.core.encryption import EncryptionService


@pytest.fixture(scope="session")
def test_encryption_key() -> str:
    """Generate a test encryption key for the session."""
    return Fernet.generate_key().decode()


@pytest.fixture
def temp_env(test_encryption_key) -> Generator[dict, None, None]:
    """Create temporary environment with test values."""
    original_env = os.environ.copy()

    test_vars = {
        "ENCRYPTION_KEY": test_encryption_key,
        "DATABASE_URL": "sqlite:///test.db",
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "DEBUG",
    }

    os.environ.update(test_vars)

    try:
        yield test_vars
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
def clean_temp_db() -> Generator[DatabaseManager, None, None]:
    """Create a clean temporary database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_manager = DatabaseManager(str(db_path))
        db_manager.init_database()

        try:
            yield db_manager
        finally:
            # Cleanup is handled by TemporaryDirectory context manager
            pass


@pytest.fixture
def test_db_path() -> Generator[Path, None, None]:
    """Provide a path to a test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    # Add custom markers
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "migration: mark test as related to settings migration")
