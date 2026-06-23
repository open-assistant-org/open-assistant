"""Request models for LLM-powered analysis."""

from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeContentRequest(BaseModel):
    """Request model for AI-powered content analysis."""

    content: str = Field(..., description="The text content to be analyzed.")
    question: str = Field(
        ...,
        description="The question to answer or goal for the analysis (e.g., 'What are the key themes?', 'Summarize the main points', 'Identify action items').",
    )
    format: Optional[str] = Field(
        "brief summary",
        description="Desired output format (e.g., 'brief summary', 'bullet points', 'detailed report', 'json').",
    )
