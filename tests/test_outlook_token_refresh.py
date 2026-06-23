"""Tests for proactive Outlook token refresh functionality."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.core.repositories.cron_job import CronJobRepository
from src.integrations.outlook.auth import refresh_outlook_token_proactively


class TestRefreshOutlookTokenProactively:
    """Tests for the proactive token refresh function in auth.py."""

    @patch("src.integrations.outlook.auth.PublicClientApplication")
    @patch("src.integrations.outlook.auth._load_token_cache")
    @patch("src.integrations.outlook.auth._save_token_cache")
    def test_successful_refresh(self, mock_save, mock_load_cache, mock_app_cls):
        """Token is refreshed successfully when cached account exists."""
        mock_cache = MagicMock()
        mock_load_cache.return_value = mock_cache

        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "new_token"}

        result = refresh_outlook_token_proactively(
            client_id="test-client-id",
            token_cache_path="/tmp/test_cache.json",
        )

        assert result is True
        mock_app.acquire_token_silent.assert_called_once()
        mock_save.assert_called_once_with(mock_app, "/tmp/test_cache.json")

    @patch("src.integrations.outlook.auth.PublicClientApplication")
    @patch("src.integrations.outlook.auth._load_token_cache")
    def test_no_cached_accounts(self, mock_load_cache, mock_app_cls):
        """Returns False when no cached accounts exist."""
        mock_cache = MagicMock()
        mock_load_cache.return_value = mock_cache

        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []

        result = refresh_outlook_token_proactively(
            client_id="test-client-id",
            token_cache_path="/tmp/test_cache.json",
        )

        assert result is False
        mock_app.acquire_token_silent.assert_not_called()

    @patch("src.integrations.outlook.auth.PublicClientApplication")
    @patch("src.integrations.outlook.auth._load_token_cache")
    def test_silent_acquisition_fails(self, mock_load_cache, mock_app_cls):
        """Returns False when silent token acquisition fails (expired refresh token)."""
        mock_cache = MagicMock()
        mock_load_cache.return_value = mock_cache

        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = None

        result = refresh_outlook_token_proactively(
            client_id="test-client-id",
            token_cache_path="/tmp/test_cache.json",
        )

        assert result is False

    @patch("src.integrations.outlook.auth.ConfidentialClientApplication")
    @patch("src.integrations.outlook.auth._load_token_cache")
    @patch("src.integrations.outlook.auth._save_token_cache")
    def test_confidential_client_refresh(self, mock_save, mock_load_cache, mock_app_cls):
        """Uses ConfidentialClientApplication when client_secret is provided."""
        mock_cache = MagicMock()
        mock_load_cache.return_value = mock_cache

        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "new_token"}

        result = refresh_outlook_token_proactively(
            client_id="test-client-id",
            client_secret="test-secret",
            tenant_id="test-tenant",
            token_cache_path="/tmp/test_cache.json",
        )

        assert result is True
        mock_app_cls.assert_called_once_with(
            "test-client-id",
            authority="https://login.microsoftonline.com/test-tenant",
            client_credential="test-secret",
            token_cache=mock_cache,
        )

    @patch("src.integrations.outlook.auth.PublicClientApplication")
    @patch("src.integrations.outlook.auth._load_token_cache")
    def test_no_token_cache_path(self, mock_load_cache, mock_app_cls):
        """Works without a token cache path (cache is None)."""
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []

        result = refresh_outlook_token_proactively(
            client_id="test-client-id",
        )

        assert result is False
        mock_load_cache.assert_not_called()


class TestOutlookServiceRefreshCredentials:
    """Tests for OutlookService.refresh_credentials method."""

    def _make_service(self, settings=None, creds=None):
        """Helper to create an OutlookService with mocked dependencies."""
        from src.services.outlook import OutlookService

        settings_repo = MagicMock()
        credentials_repo = MagicMock()

        settings_map = settings or {}
        settings_repo.get.side_effect = lambda key: settings_map.get(key)
        credentials_repo.get.return_value = creds

        return OutlookService(settings_repo, credentials_repo)

    def test_refresh_skipped_when_disabled(self):
        """Returns skipped status when Outlook is not enabled."""
        service = self._make_service(settings={"outlook.enabled": False})
        result = service.refresh_credentials()

        assert result["status"] == "skipped"
        assert "not enabled" in result["message"]

    def test_refresh_skipped_when_no_client_id(self):
        """Returns skipped status when client_id is not configured."""
        service = self._make_service(settings={"outlook.enabled": True, "outlook.client_id": None})
        result = service.refresh_credentials()

        assert result["status"] == "skipped"
        assert "client ID" in result["message"]

    @patch("src.services.outlook.refresh_outlook_token_proactively")
    def test_refresh_success(self, mock_refresh):
        """Returns success when token refresh succeeds."""
        mock_refresh.return_value = True

        service = self._make_service(
            settings={
                "outlook.enabled": True,
                "outlook.client_id": "test-id",
                "outlook.tenant_id": "test-tenant",
            }
        )
        result = service.refresh_credentials()

        assert result["status"] == "success"
        mock_refresh.assert_called_once_with(
            client_id="test-id",
            client_secret=None,
            tenant_id="test-tenant",
            token_cache_path="data/outlook_token_cache.json",
        )

    @patch("src.services.outlook.refresh_outlook_token_proactively")
    def test_refresh_warning_on_failure(self, mock_refresh):
        """Returns warning when silent acquisition fails."""
        mock_refresh.return_value = False

        service = self._make_service(
            settings={
                "outlook.enabled": True,
                "outlook.client_id": "test-id",
                "outlook.tenant_id": "test-tenant",
            }
        )
        result = service.refresh_credentials()

        assert result["status"] == "warning"
        assert "Re-authentication" in result["message"]

    @patch("src.services.outlook.refresh_outlook_token_proactively")
    def test_refresh_error_on_exception(self, mock_refresh):
        """Returns error when refresh raises an exception."""
        mock_refresh.side_effect = Exception("Network error")

        service = self._make_service(
            settings={
                "outlook.enabled": True,
                "outlook.client_id": "test-id",
                "outlook.tenant_id": "test-tenant",
            }
        )
        result = service.refresh_credentials()

        assert result["status"] == "error"
        assert "Network error" in result["message"]

    @patch("src.services.outlook.refresh_outlook_token_proactively")
    def test_refresh_with_client_secret(self, mock_refresh):
        """Passes client_secret from settings to refresh function."""
        mock_refresh.return_value = True

        service = self._make_service(
            settings={
                "outlook.enabled": True,
                "outlook.client_id": "test-id",
                "outlook.tenant_id": "test-tenant",
                "outlook.client_secret": "my-secret",
            },
        )
        result = service.refresh_credentials()

        assert result["status"] == "success"
        mock_refresh.assert_called_once_with(
            client_id="test-id",
            client_secret="my-secret",
            tenant_id="test-tenant",
            token_cache_path="data/outlook_token_cache.json",
        )


class TestSystemTokenRefreshJob:
    """Tests for the persisted system cron job that refreshes Outlook tokens."""

    JOB_ID = "__system_outlook_token_refresh"

    def test_system_job_created_in_database(self, clean_temp_db):
        """The system refresh job is created in the DB when it doesn't exist."""
        repo = CronJobRepository(clean_temp_db)

        # Job should not exist yet
        assert repo.get_job(self.JOB_ID) is None

        # Simulate what main.py startup does
        repo.create_job(
            job_id=self.JOB_ID,
            name="Outlook Token Refresh",
            cron_expression="0 */6 * * *",
            job_type="tool",
            description="System job: proactively refreshes Outlook OAuth tokens.",
            tool_name="outlook_refresh_credentials",
        )

        job = repo.get_job(self.JOB_ID)
        assert job is not None
        assert job["job_id"] == self.JOB_ID
        assert job["tool_name"] == "outlook_refresh_credentials"
        assert job["job_type"] == "tool"
        assert job["cron_expression"] == "0 */6 * * *"
        assert job["enabled"] is True

    def test_system_job_not_duplicated_on_restart(self, clean_temp_db):
        """The system refresh job is not recreated if it already exists."""
        repo = CronJobRepository(clean_temp_db)

        # Create the job (first startup)
        repo.create_job(
            job_id=self.JOB_ID,
            name="Outlook Token Refresh",
            cron_expression="0 */6 * * *",
            job_type="tool",
            tool_name="outlook_refresh_credentials",
        )

        # Simulate second startup: check before creating
        existing = repo.get_job(self.JOB_ID)
        assert existing is not None

        # Should not attempt to create again — verify only one exists
        jobs = [j for j in repo.list_jobs() if j["job_id"] == self.JOB_ID]
        assert len(jobs) == 1

    def test_system_job_can_be_toggled(self, clean_temp_db):
        """Users can disable/enable the system refresh job like any other job."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id=self.JOB_ID,
            name="Outlook Token Refresh",
            cron_expression="0 */6 * * *",
            job_type="tool",
            tool_name="outlook_refresh_credentials",
        )

        # Disable
        new_state = repo.toggle_job(self.JOB_ID, enabled=False)
        assert new_state is False

        job = repo.get_job(self.JOB_ID)
        assert job["enabled"] is False

        # Re-enable
        new_state = repo.toggle_job(self.JOB_ID, enabled=True)
        assert new_state is True
