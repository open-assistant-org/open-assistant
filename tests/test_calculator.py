"""Tests for the calculator service."""

import logging

import pytest

from src.services.calculator import calculate


def test_valid_expression():
    assert calculate("2 + 3 * 4")["result"] == 14


@pytest.mark.parametrize("expression", ["2h30", "3,5 * 2", "1 +"])
def test_unparseable_expression_returns_error_without_error_log(expression, caplog):
    with caplog.at_level(logging.ERROR):
        result = calculate(expression)
    assert result["error"].startswith("Invalid expression")
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
