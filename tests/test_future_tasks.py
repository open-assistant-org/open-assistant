"""Tests for future task scheduling functionality."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.repositories.future_task import FutureTaskRepository
from src.services.future_task import FutureTaskService


class TestFutureTaskRepository:
    """Tests for FutureTaskRepository CRUD operations."""

    def test_create_task(self, clean_temp_db):
        """Test creating a future task."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        task = repo.create_task(
            task_id="future-test123",
            name="Test Task",
            scheduled_time=scheduled_time,
            job_type="tool",
            description="A test task",
            tool_name="google_send_email",
            tool_parameters={"to": "test@example.com", "subject": "Test"},
        )

        assert task["task_id"] == "future-test123"
        assert task["name"] == "Test Task"
        assert task["scheduled_time"] == scheduled_time
        assert task["job_type"] == "tool"
        assert task["tool_name"] == "google_send_email"
        assert task["tool_parameters"] == {"to": "test@example.com", "subject": "Test"}
        assert task["status"] == "pending"

    def test_create_prompt_task(self, clean_temp_db):
        """Test creating a prompt-type future task."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(days=1)).isoformat()
        task = repo.create_task(
            task_id="future-prompt1",
            name="Reminder Task",
            scheduled_time=scheduled_time,
            job_type="prompt",
            prompt="Remind the user to call John",
        )

        assert task["job_type"] == "prompt"
        assert task["prompt"] == "Remind the user to call John"
        assert task["tool_name"] is None

    def test_get_task(self, clean_temp_db):
        """Test retrieving a future task by ID."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(hours=5)).isoformat()
        repo.create_task(
            task_id="future-get1",
            name="Get Test",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="system_fetch_logs",
        )

        task = repo.get_task("future-get1")
        assert task is not None
        assert task["name"] == "Get Test"
        assert task["scheduled_time"] == scheduled_time

    def test_get_task_not_found(self, clean_temp_db):
        """Test retrieving a non-existent task."""
        repo = FutureTaskRepository(clean_temp_db)
        assert repo.get_task("nonexistent") is None

    def test_list_tasks(self, clean_temp_db):
        """Test listing all future tasks."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time1 = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        scheduled_time2 = (datetime.utcnow() + timedelta(hours=2)).isoformat()

        repo.create_task(
            task_id="future-list1",
            name="Task 1",
            scheduled_time=scheduled_time1,
            job_type="tool",
            tool_name="test_tool",
        )
        repo.create_task(
            task_id="future-list2",
            name="Task 2",
            scheduled_time=scheduled_time2,
            job_type="prompt",
            prompt="Do something",
        )

        tasks = repo.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_by_status(self, clean_temp_db):
        """Test filtering tasks by status."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        # Create pending task
        repo.create_task(
            task_id="future-pending1",
            name="Pending Task",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )

        # Create and complete another task
        repo.create_task(
            task_id="future-completed1",
            name="Completed Task",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )
        repo.update_status(
            task_id="future-completed1",
            status="completed",
            completed_at=datetime.utcnow().isoformat(),
        )

        pending_tasks = repo.list_tasks(status="pending")
        assert len(pending_tasks) == 1
        assert pending_tasks[0]["status"] == "pending"

        completed_tasks = repo.list_tasks(status="completed")
        assert len(completed_tasks) == 1
        assert completed_tasks[0]["status"] == "completed"

    def test_list_tasks_hides_old_completed(self, clean_temp_db):
        """Completed/failed/cancelled tasks older than 24h are hidden."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        old_completed_at = (datetime.utcnow() - timedelta(hours=25)).isoformat()
        recent_completed_at = (datetime.utcnow() - timedelta(hours=1)).isoformat()

        repo.create_task(
            task_id="future-old-done",
            name="Old Done",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )
        repo.update_status(
            task_id="future-old-done",
            status="completed",
            completed_at=old_completed_at,
        )

        repo.create_task(
            task_id="future-recent-done",
            name="Recent Done",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )
        repo.update_status(
            task_id="future-recent-done",
            status="completed",
            completed_at=recent_completed_at,
        )

        repo.create_task(
            task_id="future-still-pending",
            name="Pending",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )

        all_tasks = repo.list_tasks()
        task_ids = {t["task_id"] for t in all_tasks}
        assert "future-still-pending" in task_ids
        assert "future-recent-done" in task_ids
        assert "future-old-done" not in task_ids

        completed = repo.list_tasks(status="completed")
        completed_ids = {t["task_id"] for t in completed}
        assert completed_ids == {"future-recent-done"}

    def test_update_status(self, clean_temp_db):
        """Test updating task status."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        repo.create_task(
            task_id="future-update1",
            name="Update Test",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )

        # Update to completed
        completed_at = datetime.utcnow().isoformat()
        success = repo.update_status(
            task_id="future-update1",
            status="completed",
            completed_at=completed_at,
            result={"message": "Success"},
        )

        assert success is True

        task = repo.get_task("future-update1")
        assert task["status"] == "completed"
        assert task["completed_at"] == completed_at
        assert task["result"] == {"message": "Success"}

    def test_delete_task(self, clean_temp_db):
        """Test deleting a future task."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        repo.create_task(
            task_id="future-delete1",
            name="Delete Test",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )

        success = repo.delete_task("future-delete1")
        assert success is True

        task = repo.get_task("future-delete1")
        assert task is None

    def test_get_pending_tasks(self, clean_temp_db):
        """Test retrieving pending tasks."""
        repo = FutureTaskRepository(clean_temp_db)

        scheduled_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        # Create pending task
        repo.create_task(
            task_id="future-pending2",
            name="Pending Task",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )

        # Create completed task
        repo.create_task(
            task_id="future-completed2",
            name="Completed Task",
            scheduled_time=scheduled_time,
            job_type="tool",
            tool_name="test_tool",
        )
        repo.update_status(
            task_id="future-completed2",
            status="completed",
            completed_at=datetime.utcnow().isoformat(),
        )

        pending = repo.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0]["task_id"] == "future-pending2"

    def test_get_missed_tasks(self, clean_temp_db):
        """Test retrieving missed tasks."""
        repo = FutureTaskRepository(clean_temp_db)

        # Create missed task (scheduled in the past)
        past_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        repo.create_task(
            task_id="future-missed1",
            name="Missed Task",
            scheduled_time=past_time,
            job_type="tool",
            tool_name="test_tool",
        )

        # Create future task
        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        repo.create_task(
            task_id="future-future1",
            name="Future Task",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
        )

        missed = repo.get_missed_tasks()
        assert len(missed) == 1
        assert missed[0]["task_id"] == "future-missed1"


class TestFutureTaskService:
    """Tests for FutureTaskService business logic."""

    def test_create_task_with_iso_time(self, clean_temp_db):
        """Test creating task with ISO 8601 time."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=2)).isoformat()

        task = service.create_task(
            name="Test Task",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
            tool_parameters={"key": "value"},
        )

        assert task["name"] == "Test Task"
        assert task["status"] == "pending"
        assert "future-" in task["task_id"]

    def test_create_task_with_relative_time(self, clean_temp_db):
        """Test creating task with relative time."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        task = service.create_task(
            name="Test Task",
            scheduled_time="in 2 hours",
            job_type="prompt",
            prompt="Remind me",
        )

        assert task["name"] == "Test Task"
        assert task["status"] == "pending"

        # Verify time is approximately 2 hours in future
        scheduled = datetime.fromisoformat(task["scheduled_time"])
        expected = datetime.utcnow() + timedelta(hours=2)
        diff = abs((scheduled - expected).total_seconds())
        assert diff < 60  # Within 1 minute tolerance

    def test_create_task_past_time_fails(self, clean_temp_db):
        """Test that creating task with past time raises error."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        past_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()

        with pytest.raises(ValueError, match="must be in the future"):
            service.create_task(
                name="Past Task",
                scheduled_time=past_time,
                job_type="tool",
                tool_name="test_tool",
            )

    def test_create_task_invalid_job_type(self, clean_temp_db):
        """Test that invalid job_type raises error."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with pytest.raises(ValueError, match="must be 'tool' or 'prompt'"):
            service.create_task(
                name="Invalid Task",
                scheduled_time=future_time,
                job_type="invalid",
            )

    def test_create_task_tool_without_tool_name(self, clean_temp_db):
        """Test that tool job without tool_name raises error."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with pytest.raises(ValueError, match="tool_name is required"):
            service.create_task(
                name="Tool Task",
                scheduled_time=future_time,
                job_type="tool",
            )

    def test_create_task_prompt_without_prompt(self, clean_temp_db):
        """Test that prompt job without prompt raises error."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with pytest.raises(ValueError, match="prompt is required"):
            service.create_task(
                name="Prompt Task",
                scheduled_time=future_time,
                job_type="prompt",
            )

    def test_get_task(self, clean_temp_db):
        """Test retrieving task with execution history."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        created_task = service.create_task(
            name="Get Test",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
        )

        task = service.get_task(created_task["task_id"])
        assert task is not None
        assert task["name"] == "Get Test"
        assert "recent_executions" in task

    def test_list_tasks(self, clean_temp_db):
        """Test listing tasks."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        service.create_task(
            name="Task 1",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
        )
        service.create_task(
            name="Task 2",
            scheduled_time=future_time,
            job_type="prompt",
            prompt="Do something",
        )

        tasks = service.list_tasks()
        assert len(tasks) >= 2

    def test_list_tasks_filtered(self, clean_temp_db):
        """Test listing tasks with status filter."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        task1 = service.create_task(
            name="Pending Task",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
        )

        task2 = service.create_task(
            name="Task to Cancel",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
        )

        # Cancel one task
        service.cancel_task(task2["task_id"])

        pending = service.list_tasks(status="pending")
        assert len(pending) == 1
        assert pending[0]["task_id"] == task1["task_id"]

        cancelled = service.list_tasks(status="cancelled")
        assert len(cancelled) == 1
        assert cancelled[0]["task_id"] == task2["task_id"]

    def test_cancel_task(self, clean_temp_db):
        """Test cancelling a pending task."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        task = service.create_task(
            name="Cancel Test",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
        )

        success = service.cancel_task(task["task_id"])
        assert success is True

        # Verify status updated
        updated_task = repo.get_task(task["task_id"])
        assert updated_task["status"] == "cancelled"

    def test_cancel_nonexistent_task(self, clean_temp_db):
        """Test cancelling non-existent task."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        success = service.cancel_task("nonexistent")
        assert success is False

    def test_cancel_completed_task_fails(self, clean_temp_db):
        """Test that cancelling completed task raises error."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        task = service.create_task(
            name="Completed Task",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
        )

        # Mark as completed
        repo.update_status(
            task_id=task["task_id"],
            status="completed",
            completed_at=datetime.utcnow().isoformat(),
        )

        with pytest.raises(ValueError, match="only pending tasks can be cancelled"):
            service.cancel_task(task["task_id"])

    def test_parse_scheduled_time_iso(self, clean_temp_db):
        """Test parsing ISO 8601 time."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        iso_time = "2025-12-25T15:00:00"
        parsed = service._parse_scheduled_time(iso_time)
        assert parsed.year == 2025
        assert parsed.month == 12
        assert parsed.day == 25
        assert parsed.hour == 15

    def test_parse_scheduled_time_relative(self, clean_temp_db):
        """Test parsing relative time expressions."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        now = datetime.utcnow()

        # Test "in X hours"
        parsed = service._parse_scheduled_time("in 3 hours")
        expected = now + timedelta(hours=3)
        diff = abs((parsed - expected).total_seconds())
        assert diff < 1  # Within 1 second

        # Test "in X minutes"
        parsed = service._parse_scheduled_time("in 30 minutes")
        expected = now + timedelta(minutes=30)
        diff = abs((parsed - expected).total_seconds())
        assert diff < 1

        # Test "in X days"
        parsed = service._parse_scheduled_time("in 2 days")
        expected = now + timedelta(days=2)
        diff = abs((parsed - expected).total_seconds())
        assert diff < 1

    def test_parse_scheduled_time_invalid(self, clean_temp_db):
        """Test parsing invalid time string."""
        repo = FutureTaskRepository(clean_temp_db)
        service = FutureTaskService(repo)

        with pytest.raises(ValueError, match="Could not parse"):
            service._parse_scheduled_time("invalid time string")

    @pytest.mark.asyncio
    async def test_execute_tool_task(self, clean_temp_db):
        """Test executing a tool task."""
        repo = FutureTaskRepository(clean_temp_db)

        # Mock tool executor
        mock_executor = AsyncMock()
        mock_executor.execute_tool = AsyncMock(
            return_value={"success": True, "result": "Tool executed"}
        )

        # Mock scheduler to initialize semaphore
        mock_scheduler = MagicMock()

        service = FutureTaskService(repo, tool_executor=mock_executor, scheduler=mock_scheduler)

        # Initialize semaphore (normally done by load_pending_tasks)
        service._job_semaphore = asyncio.Semaphore(5)

        # Create task
        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        task = service.create_task(
            name="Tool Task",
            scheduled_time=future_time,
            job_type="tool",
            tool_name="test_tool",
            tool_parameters={"key": "value"},
        )

        # Execute task directly (bypass scheduler)
        await service._execute_task(task["task_id"])

        # Verify tool was called
        mock_executor.execute_tool.assert_called_once()

        # Verify task status updated
        updated_task = repo.get_task(task["task_id"])
        assert updated_task["status"] == "completed"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Test needs update for new MessageHandler-based execution")
    async def test_execute_prompt_task(self, clean_temp_db):
        """Test executing a prompt task."""
        repo = FutureTaskRepository(clean_temp_db)

        # Mock message_handler
        mock_message_handler = AsyncMock()
        mock_message_handler.process_message = AsyncMock(
            return_value={"status": "success", "message": "Task completed"}
        )

        # Mock scheduler to initialize semaphore
        mock_scheduler = MagicMock()

        service = FutureTaskService(
            repo, message_handler=mock_message_handler, scheduler=mock_scheduler
        )

        # Initialize semaphore (normally done by load_pending_tasks)
        service._job_semaphore = asyncio.Semaphore(5)

        # Create task
        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        task = service.create_task(
            name="Prompt Task",
            scheduled_time=future_time,
            job_type="prompt",
            prompt="Do something",
        )

        # Execute task directly (bypass scheduler)
        await service._execute_task(task["task_id"])

        # Verify message_handler was called
        mock_message_handler.process_message.assert_called_once()

        # Verify task status updated
        updated_task = repo.get_task(task["task_id"])
        assert updated_task["status"] == "completed"


class TestFutureTaskModels:
    """Tests for Pydantic models."""

    def test_schedule_task_request(self):
        """Test ScheduleTaskRequest model validation."""
        from src.models.future_tasks import ScheduleTaskRequest

        request = ScheduleTaskRequest(
            name="Test Task",
            scheduled_time="2025-12-25T15:00:00",
            job_type="tool",
            tool_name="test_tool",
            tool_parameters={"key": "value"},
        )

        assert request.name == "Test Task"
        assert request.job_type == "tool"
        assert request.tool_name == "test_tool"

    def test_future_task_response(self):
        """Test FutureTaskResponse model."""
        from src.models.future_tasks import FutureTaskResponse

        response = FutureTaskResponse(
            task_id="future-123",
            name="Test Task",
            scheduled_time="2025-12-25T15:00:00",
            job_type="tool",
            status="pending",
        )

        assert response.task_id == "future-123"
        assert response.status == "pending"
