"""LLM-powered content analysis service."""

from typing import Any, Dict, Optional

from src.utils.logger import get_logger
from src.core.llm_client import LLMClient, LLMConfig

logger = get_logger(__name__)


async def analyze_content(
    content: str,
    question: str,
    format: Optional[str] = "brief summary",
    settings_service=None,
) -> Dict[str, Any]:
    """
    Analyze provided content using an LLM.

    Args:
        content: The text content to be analyzed.
        question: The question to answer or goal for the analysis.
        format: Desired output format.
        settings_service: SettingsService instance for LLM configuration.

    Returns:
        Dict with keys: analysis_result (str), format (str).
    """
    if not settings_service:
        raise ValueError("settings_service is required for analyze_content")

    # Build LLM client from settings
    llm_config = LLMConfig.from_settings(settings_service)
    llm_client = LLMClient(llm_config)

    system_message = (
        "You are an expert analytical AI. Your task is to analyze the provided content "
        f"based on the user's question and deliver the result in the specified format. "
        "Be precise, thorough, and directly address the question. "
        "Do NOT add any conversational pleasantries or meta-commentary; just the analysis."
    )

    prompt = (
        f"Content to analyze:\n\n{content}\n\n"
        f"Question: {question}\n\n"
        f"Desired Output Format: {format}\n\n"
        "Please provide the analysis now, strictly following the desired output format."
    )

    logger.info(f"analyze_content: processing analysis for question '{question[:100]}'")
    analysis_result = llm_client.complete_text(
        prompt=prompt,
        system_message=system_message,
        temperature=0.3,
        max_tokens=4096,
    )
    logger.info("analyze_content: analysis complete")

    return {"analysis_result": analysis_result, "format": format}
