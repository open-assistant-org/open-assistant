"""Centralized logging configuration with rotation."""

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# Timezone used to render log timestamps. None => system local time.
# Updated at runtime via set_log_timezone() once the user's configured
# timezone is known (and again whenever it changes).
_log_tz: Optional[ZoneInfo] = None


def set_log_timezone(tz_name: Optional[str]) -> None:
    """Set the timezone used to render log timestamps.

    Args:
        tz_name: IANA timezone name (e.g. "Europe/Brussels"). Falsy values or
            an invalid name fall back to the system local time.
    """
    global _log_tz
    if not tz_name:
        _log_tz = None
        return
    try:
        _log_tz = ZoneInfo(tz_name)
    except Exception:
        # Keep whatever was previously configured rather than crashing logging
        logging.getLogger(__name__).warning(
            "Invalid log timezone '%s', keeping previous setting", tz_name
        )


class _TimezoneFormatter(logging.Formatter):
    """Formatter that renders asctime in the configured user timezone."""

    def formatTime(self, record, datefmt=None):  # noqa: N802 (stdlib signature)
        dt = datetime.fromtimestamp(record.created, _log_tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_file: str = "assistant.log",
    when: str = "midnight",
    interval: int = 1,
    backup_count: int = 30,
) -> None:
    """
    Configure root logger with daily file rotation.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        log_file: Name of the log file
        when: When to rotate ('midnight', 'S', 'M', 'H', 'D', 'W0'-'W6')
        interval: Interval between rotations (1 = every day at midnight)
        backup_count: Number of backup files to keep (30 = 30 days)
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatters with timestamps and context support.
    # _TimezoneFormatter renders asctime in the user's configured timezone
    # (set via set_log_timezone); falls back to system local time until then.
    file_formatter = _TimezoneFormatter(
        "%(asctime)s - %(name)s - [%(job_id)s/%(execution_id)s] - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        defaults={"job_id": "-", "execution_id": "-", "job_name": "-"},
    )
    console_formatter = _TimezoneFormatter(
        "%(asctime)s - [%(job_id)s] - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
        defaults={"job_id": "-", "execution_id": "-"},
    )

    # File handler with daily rotation
    # Rotates at midnight, keeps last 30 days
    # Files will be named: assistant.log, assistant.log.2026-01-29, assistant.log.2026-01-28, etc.
    file_handler = TimedRotatingFileHandler(
        log_path / log_file,
        when=when,
        interval=interval,
        backupCount=backup_count,
        encoding="utf-8",
        utc=False,  # Use local time
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Set the suffix for rotated files to include date
    file_handler.suffix = "%Y-%m-%d"

    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logger.info(
        f"Logging initialized at level {log_level}, rotating daily, keeping {backup_count} days"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Name of the module (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
