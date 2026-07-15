"""Tests for calendar date normalization in the Outlook service.

Regression coverage for the Microsoft Graph 400 caused by passing loose date
terms (e.g. the literal string "today") straight into the OData ``$filter``.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.services.outlook import OutlookService, _normalize_calendar_date


class TestNormalizeCalendarDate:
    """Unit tests for the ``_normalize_calendar_date`` helper."""

    def test_none_passes_through(self):
        assert _normalize_calendar_date(None) is None

    def test_empty_string_returns_none(self):
        assert _normalize_calendar_date("   ") is None

    def test_today_start_is_midnight(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert _normalize_calendar_date("today", "start") == f"{today}T00:00:00"

    def test_today_end_is_end_of_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert _normalize_calendar_date("today", "end") == f"{today}T23:59:59"

    def test_case_insensitive_keyword(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert _normalize_calendar_date("Today", "start") == f"{today}T00:00:00"

    def test_tomorrow(self):
        result = _normalize_calendar_date("tomorrow", "start")
        today = datetime.now(timezone.utc).date()
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S").date()
        assert (parsed - today).days == 1

    def test_yesterday(self):
        result = _normalize_calendar_date("yesterday", "end")
        today = datetime.now(timezone.utc).date()
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S")
        assert (parsed.date() - today).days == -1
        assert (parsed.hour, parsed.minute, parsed.second) == (23, 59, 59)

    def test_now_uses_current_time(self):
        result = _normalize_calendar_date("now", "start")
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S")
        assert parsed.date() == datetime.now(timezone.utc).date()

    def test_this_week_start_and_end_span_forward(self):
        start = _normalize_calendar_date("this week", "start")
        end = _normalize_calendar_date("this week", "end")
        start_dt = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
        end_dt = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S")
        assert (end_dt.date() - start_dt.date()).days == 7

    def test_bare_iso_date_start(self):
        assert _normalize_calendar_date("2026-07-15", "start") == "2026-07-15T00:00:00"

    def test_bare_iso_date_end_covers_full_day(self):
        assert _normalize_calendar_date("2026-07-15", "end") == "2026-07-15T23:59:59"

    def test_full_iso_datetime_preserved(self):
        assert _normalize_calendar_date("2026-07-15T09:30:00", "start") == "2026-07-15T09:30:00"

    def test_iso_datetime_with_z_suffix(self):
        assert _normalize_calendar_date("2026-07-15T09:30:00Z", "start") == "2026-07-15T09:30:00"

    def test_full_iso_datetime_end_not_forced_to_end_of_day(self):
        # An explicit time-of-day must be preserved, not overwritten to 23:59:59.
        assert _normalize_calendar_date("2026-07-15T09:30:00", "end") == "2026-07-15T09:30:00"

    def test_gibberish_raises_value_error(self):
        with pytest.raises(ValueError):
            _normalize_calendar_date("not a date at all", "start")


class TestListCalendarEventsNormalization:
    """The service must never forward loose date terms to the Graph client."""

    def _service_with_mock_client(self):
        service = OutlookService(
            settings_repo=MagicMock(),
            credentials_repo=MagicMock(),
        )
        mock_client = MagicMock()
        mock_client.list_events.return_value = []
        return service, mock_client

    def test_today_is_normalized_before_reaching_client(self):
        service, mock_client = self._service_with_mock_client()
        with patch.object(service, "_get_client", return_value=mock_client):
            service.list_calendar_events(start_date="today", end_date="today")

        kwargs = mock_client.list_events.call_args.kwargs
        # The literal "today" must never be forwarded — that is what Graph 400s on.
        assert kwargs["start_date"] != "today"
        assert kwargs["end_date"] != "today"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert kwargs["start_date"] == f"{today}T00:00:00"
        assert kwargs["end_date"] == f"{today}T23:59:59"

    def test_default_start_when_omitted(self):
        service, mock_client = self._service_with_mock_client()
        with patch.object(service, "_get_client", return_value=mock_client):
            service.list_calendar_events()

        kwargs = mock_client.list_events.call_args.kwargs
        assert kwargs["start_date"] is not None
        assert kwargs["end_date"] is None
        # Default start_date is a valid ISO timestamp.
        datetime.strptime(kwargs["start_date"], "%Y-%m-%dT%H:%M:%S")

    def test_iso_input_passes_through_unchanged(self):
        service, mock_client = self._service_with_mock_client()
        with patch.object(service, "_get_client", return_value=mock_client):
            service.list_calendar_events(
                start_date="2026-07-15T00:00:00", end_date="2026-07-15T23:59:59"
            )

        kwargs = mock_client.list_events.call_args.kwargs
        assert kwargs["start_date"] == "2026-07-15T00:00:00"
        assert kwargs["end_date"] == "2026-07-15T23:59:59"
