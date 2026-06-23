"""Calculator request models."""

from pydantic import BaseModel, Field


class CalculateRequest(BaseModel):
    """Request model for evaluating mathematical expressions."""

    expression: str = Field(
        ...,
        description="Mathematical expression to evaluate. Supports: +, -, *, /, **, "
        "%, //, parentheses, and common math functions (sqrt, sin, cos, tan, log, "
        "abs, round, min, max, pi, e). Examples: '2 + 3 * 4', 'sqrt(144)', "
        "'round(3.14159, 2)', '15% of 200' (converted to 200 * 0.15).",
    )
