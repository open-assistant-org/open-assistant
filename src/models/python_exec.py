"""Python execution request models."""

from typing import Optional

from pydantic import BaseModel, Field


class PythonExecuteRequest(BaseModel):
    """Request model for executing Python code."""

    code: str = Field(
        ...,
        description=(
            "Python code to execute. Can be any valid Python — use standard library modules, "
            "make HTTP requests with 'requests' or 'urllib', parse data, run calculations, etc. "
            "Print output to stdout to return results. "
            "Examples: 'import requests; r = requests.get(\"https://api.example.com\"); print(r.json())' "
            'or \'import json; data = {"key": "value"}; print(json.dumps(data, indent=2))\'.'
        ),
    )
    timeout: Optional[int] = Field(
        default=60,
        ge=1,
        le=120,
        description="Maximum execution time in seconds (default 60, max 120).",
    )


class PythonAgentRequest(BaseModel):
    """Request model for delegating a multi-step Python task to a sub-agent."""

    goal: str = Field(
        ...,
        description=(
            "Natural-language description of what to accomplish with Python. "
            "Be specific about inputs, transformations, and desired output (e.g. file paths, format). "
            "Examples: 'Fetch https://api.github.com/repos/python/cpython and save the description "
            "to /app/tmp/desc.txt', or 'Download the last 30 daily closes of AAPL via yfinance and "
            "save an interactive plotly HTML chart to /app/tmp/aapl.html'."
        ),
    )
    context: Optional[str] = Field(
        default=None,
        description=(
            "Optional extra facts the sub-agent needs: file paths produced by earlier steps, URLs, "
            "API keys the user already provided in the conversation, data schemas, parameter values, "
            "or constraints. Keep concise — only what the sub-agent needs to succeed. "
            "The sub-agent works in a persistent workspace directory and can inspect inputs and "
            "verify its own outputs with built-in read_file/list_files/write_file tools."
        ),
    )
    max_iterations: int = Field(
        default=8,
        ge=1,
        le=20,
        description=(
            "Maximum number of inner LLM↔python_execute turns before the sub-agent must stop. "
            "Defaults to 8, hard-capped at 20. Increase only for genuinely complex multi-stage tasks."
        ),
    )
