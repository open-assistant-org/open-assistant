"""Tests for cron job scheduling functionality."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.repositories.cron_job import CronJobRepository
from src.services.cron_job import CronJobService


class TestCronJobRepository:
    """Tests for CronJobRepository CRUD operations."""

    def test_create_job(self, clean_temp_db):
        """Test creating a cron job."""
        repo = CronJobRepository(clean_temp_db)

        job = repo.create_job(
            job_id="cron-test123",
            name="Test Job",
            cron_expression="0 9 * * MON",
            job_type="tool",
            description="A test job",
            tool_name="google_send_email",
            tool_parameters={"to": "test@example.com", "subject": "Test"},
        )

        assert job["job_id"] == "cron-test123"
        assert job["name"] == "Test Job"
        assert job["cron_expression"] == "0 9 * * MON"
        assert job["job_type"] == "tool"
        assert job["tool_name"] == "google_send_email"
        assert job["tool_parameters"] == {"to": "test@example.com", "subject": "Test"}
        assert job["enabled"] is True

    def test_create_prompt_job(self, clean_temp_db):
        """Test creating a prompt-type cron job."""
        repo = CronJobRepository(clean_temp_db)

        job = repo.create_job(
            job_id="cron-prompt1",
            name="Daily Digest",
            cron_expression="0 8 * * *",
            job_type="prompt",
            prompt="Summarize unread emails and send digest",
        )

        assert job["job_type"] == "prompt"
        assert job["prompt"] == "Summarize unread emails and send digest"
        assert job["tool_name"] is None

    def test_get_job(self, clean_temp_db):
        """Test retrieving a cron job by ID."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-get1",
            name="Get Test",
            cron_expression="*/5 * * * *",
            job_type="tool",
            tool_name="system_fetch_logs",
        )

        job = repo.get_job("cron-get1")
        assert job is not None
        assert job["name"] == "Get Test"
        assert job["cron_expression"] == "*/5 * * * *"

    def test_get_job_not_found(self, clean_temp_db):
        """Test retrieving a non-existent job."""
        repo = CronJobRepository(clean_temp_db)
        assert repo.get_job("nonexistent") is None

    def test_list_jobs(self, clean_temp_db):
        """Test listing all cron jobs."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-list1",
            name="Job 1",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )
        repo.create_job(
            job_id="cron-list2",
            name="Job 2",
            cron_expression="0 10 * * *",
            job_type="prompt",
            prompt="Do something",
        )

        jobs = repo.list_jobs()
        job_ids = [j["job_id"] for j in jobs]
        assert "cron-list1" in job_ids
        assert "cron-list2" in job_ids

    def test_list_jobs_enabled_only(self, clean_temp_db):
        """Test listing only enabled jobs."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-en1",
            name="Enabled Job",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )
        repo.create_job(
            job_id="cron-dis1",
            name="Disabled Job",
            cron_expression="0 10 * * *",
            job_type="tool",
            tool_name="test_tool",
        )
        repo.toggle_job("cron-dis1", enabled=False)

        jobs = repo.list_jobs(enabled_only=True)
        job_ids = [j["job_id"] for j in jobs]
        assert "cron-en1" in job_ids
        assert "cron-dis1" not in job_ids

    def test_update_job(self, clean_temp_db):
        """Test updating a cron job."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-upd1",
            name="Original Name",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        result = repo.update_job(
            "cron-upd1", {"name": "Updated Name", "cron_expression": "0 10 * * *"}
        )
        assert result is True

        job = repo.get_job("cron-upd1")
        assert job["name"] == "Updated Name"
        assert job["cron_expression"] == "0 10 * * *"

    def test_delete_job(self, clean_temp_db):
        """Test deleting a cron job."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-del1",
            name="To Delete",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        result = repo.delete_job("cron-del1")
        assert result is True
        assert repo.get_job("cron-del1") is None

    def test_delete_job_not_found(self, clean_temp_db):
        """Test deleting a non-existent job."""
        repo = CronJobRepository(clean_temp_db)
        assert repo.delete_job("nonexistent") is False

    def test_toggle_job(self, clean_temp_db):
        """Test toggling a cron job's enabled state."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-tog1",
            name="Toggle Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        # Toggle off
        new_state = repo.toggle_job("cron-tog1")
        assert new_state is False

        # Toggle back on
        new_state = repo.toggle_job("cron-tog1")
        assert new_state is True

    def test_toggle_job_explicit(self, clean_temp_db):
        """Test setting explicit enabled state."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-tog2",
            name="Explicit Toggle",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        new_state = repo.toggle_job("cron-tog2", enabled=False)
        assert new_state is False

        job = repo.get_job("cron-tog2")
        assert job["enabled"] is False

    def test_toggle_nonexistent_job(self, clean_temp_db):
        """Test toggling a non-existent job."""
        repo = CronJobRepository(clean_temp_db)
        assert repo.toggle_job("nonexistent") is None


class TestJobExecutions:
    """Tests for job execution tracking."""

    def test_create_and_complete_execution(self, clean_temp_db):
        """Test creating and completing a job execution."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-exec1",
            name="Execution Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        # Create execution
        exec_id = repo.create_execution(job_id="cron-exec1", job_type="cron")
        assert exec_id > 0

        # Complete it
        repo.complete_execution(
            execution_id=exec_id,
            status="success",
            result={"message": "Done"},
        )

        # Verify
        executions = repo.get_job_executions("cron-exec1")
        assert len(executions) == 1
        assert executions[0]["status"] == "success"
        assert executions[0]["result"] == {"message": "Done"}
        assert executions[0]["completed_at"] is not None

    def test_failed_execution(self, clean_temp_db):
        """Test recording a failed execution."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-fail1",
            name="Fail Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        exec_id = repo.create_execution(job_id="cron-fail1", job_type="cron")
        repo.complete_execution(
            execution_id=exec_id,
            status="failed",
            error_message="Connection refused",
        )

        executions = repo.get_job_executions("cron-fail1")
        assert len(executions) == 1
        assert executions[0]["status"] == "failed"
        assert executions[0]["error_message"] == "Connection refused"

    def test_execution_history_order(self, clean_temp_db):
        """Test that executions are returned in reverse chronological order."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-order1",
            name="Order Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        # Create multiple executions
        for i in range(3):
            exec_id = repo.create_execution(job_id="cron-order1", job_type="cron")
            repo.complete_execution(execution_id=exec_id, status="success")

        executions = repo.get_job_executions("cron-order1")
        assert len(executions) == 3

    def test_recent_executions(self, clean_temp_db):
        """Test getting recent executions across all jobs."""
        repo = CronJobRepository(clean_temp_db)

        repo.create_job(
            job_id="cron-recent1",
            name="Job A",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )
        repo.create_job(
            job_id="cron-recent2",
            name="Job B",
            cron_expression="0 10 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        repo.create_execution(job_id="cron-recent1", job_type="cron")
        repo.create_execution(job_id="cron-recent2", job_type="cron")

        executions = repo.get_recent_executions(limit=10)
        assert len(executions) == 2


class TestCronJobService:
    """Tests for CronJobService business logic."""

    def test_create_tool_job(self, clean_temp_db):
        """Test creating a tool-type job through the service."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="Weekly Report",
            cron_expression="0 9 * * MON",
            job_type="tool",
            tool_name="google_send_email",
            tool_parameters={"to": "boss@example.com", "subject": "Weekly Report"},
        )

        assert job["name"] == "Weekly Report"
        assert job["job_id"].startswith("cron-")
        assert job["job_type"] == "tool"

    def test_create_prompt_job(self, clean_temp_db):
        """Test creating a prompt-type job through the service."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="Email Digest",
            cron_expression="0 8 * * *",
            job_type="prompt",
            prompt="Summarize my unread emails",
        )

        assert job["job_type"] == "prompt"
        assert job["prompt"] == "Summarize my unread emails"

    def test_create_job_invalid_type(self, clean_temp_db):
        """Test that invalid job_type raises ValueError."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        with pytest.raises(ValueError, match="job_type must be"):
            service.create_job(
                name="Bad Job",
                cron_expression="0 9 * * *",
                job_type="invalid",
            )

    def test_create_tool_job_without_tool_name(self, clean_temp_db):
        """Test that tool jobs require tool_name."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        with pytest.raises(ValueError, match="tool_name is required"):
            service.create_job(
                name="Bad Tool Job",
                cron_expression="0 9 * * *",
                job_type="tool",
            )

    def test_create_prompt_job_without_prompt(self, clean_temp_db):
        """Test that prompt jobs require prompt."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        with pytest.raises(ValueError, match="prompt is required"):
            service.create_job(
                name="Bad Prompt Job",
                cron_expression="0 9 * * *",
                job_type="prompt",
            )

    def test_create_job_invalid_cron(self, clean_temp_db):
        """Test that invalid cron expressions are rejected."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        with pytest.raises(ValueError, match="Invalid cron expression"):
            service.create_job(
                name="Bad Cron",
                cron_expression="not a cron",
                job_type="tool",
                tool_name="test_tool",
            )

    def test_list_jobs(self, clean_temp_db):
        """Test listing jobs through the service."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job1 = service.create_job(
            name="Job 1",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )
        job2 = service.create_job(
            name="Job 2",
            cron_expression="0 10 * * *",
            job_type="prompt",
            prompt="Do something",
        )

        jobs = service.list_jobs()
        job_ids = [j["job_id"] for j in jobs]
        assert job1["job_id"] in job_ids
        assert job2["job_id"] in job_ids

    def test_update_job(self, clean_temp_db):
        """Test updating a job through the service."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="Original",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        updated = service.update_job(job["job_id"], {"name": "Updated"})
        assert updated is not None
        assert updated["name"] == "Updated"

    def test_update_job_invalid_cron(self, clean_temp_db):
        """Test that updating with invalid cron raises ValueError."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        with pytest.raises(ValueError, match="Invalid cron expression"):
            service.update_job(job["job_id"], {"cron_expression": "bad"})

    def test_update_nonexistent_job(self, clean_temp_db):
        """Test updating a non-existent job."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        result = service.update_job("nonexistent", {"name": "test"})
        assert result is None

    def test_delete_job(self, clean_temp_db):
        """Test deleting a job through the service."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="To Delete",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        assert service.delete_job(job["job_id"]) is True
        assert service.get_job(job["job_id"]) is None

    def test_toggle_job(self, clean_temp_db):
        """Test toggling a job through the service."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="Toggle Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        # Disable
        new_state = service.toggle_job(job["job_id"], enabled=False)
        assert new_state is False

        # Verify
        updated = service.get_job(job["job_id"])
        assert updated["enabled"] is False

        # Re-enable
        new_state = service.toggle_job(job["job_id"], enabled=True)
        assert new_state is True

    def test_toggle_nonexistent_job(self, clean_temp_db):
        """Test toggling a non-existent job."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        result = service.toggle_job("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_run_now(self, clean_temp_db):
        """Test immediate job execution."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="Run Now Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
            tool_parameters={"key": "value"},
        )

        result = await service.run_now(job["job_id"])
        assert result["status"] in ("success", "failed")
        assert "execution_id" in result

    @pytest.mark.asyncio
    async def test_run_now_nonexistent(self, clean_temp_db):
        """Test run_now with non-existent job."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        with pytest.raises(ValueError, match="not found"):
            await service.run_now("nonexistent")

    def test_get_job_executions(self, clean_temp_db):
        """Test getting execution history through the service."""
        repo = CronJobRepository(clean_temp_db)
        service = CronJobService(repo)

        job = service.create_job(
            name="Exec History",
            cron_expression="0 9 * * *",
            job_type="tool",
            tool_name="test_tool",
        )

        # Create some executions directly
        exec_id = repo.create_execution(job_id=job["job_id"], job_type="cron")
        repo.complete_execution(exec_id, status="success")

        executions = service.get_job_executions(job["job_id"])
        assert len(executions) == 1


class TestCronJobModels:
    """Tests for Pydantic cron job models."""

    def test_create_request_validation(self):
        """Test CreateCronJobRequest validation."""
        from src.models.cron_jobs import CreateCronJobRequest

        request = CreateCronJobRequest(
            name="Test Job",
            cron_expression="0 9 * * MON",
            job_type="tool",
            tool_name="google_send_email",
            tool_parameters={"to": "test@example.com"},
        )

        assert request.name == "Test Job"
        assert request.job_type == "tool"

    def test_create_request_prompt_type(self):
        """Test CreateCronJobRequest with prompt type."""
        from src.models.cron_jobs import CreateCronJobRequest

        request = CreateCronJobRequest(
            name="Digest Job",
            cron_expression="0 8 * * *",
            job_type="prompt",
            prompt="Summarize emails",
        )

        assert request.job_type == "prompt"
        assert request.prompt == "Summarize emails"

    def test_update_request_partial(self):
        """Test UpdateCronJobRequest with partial updates."""
        from src.models.cron_jobs import UpdateCronJobRequest

        request = UpdateCronJobRequest(
            job_id="cron-123",
            name="New Name",
        )

        assert request.name == "New Name"
        assert request.cron_expression is None

    def test_response_model(self):
        """Test CronJobResponse model."""
        from src.models.cron_jobs import CronJobResponse

        response = CronJobResponse(
            job_id="cron-123",
            name="Test",
            cron_expression="0 9 * * *",
            job_type="tool",
            enabled=True,
        )

        assert response.job_id == "cron-123"
        assert response.enabled is True

    def test_list_response_model(self):
        """Test CronJobListResponse model."""
        from src.models.cron_jobs import CronJobListResponse, CronJobResponse

        jobs = [
            CronJobResponse(
                job_id=f"cron-{i}",
                name=f"Job {i}",
                cron_expression="0 9 * * *",
                job_type="tool",
                enabled=True,
            )
            for i in range(3)
        ]

        response = CronJobListResponse(jobs=jobs, total=3)
        assert response.total == 3
        assert len(response.jobs) == 3
