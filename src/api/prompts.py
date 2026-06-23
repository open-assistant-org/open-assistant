"""Prompts API for managing system prompt, memory, and soul configuration."""

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import get_prompts_repo
from src.core.repositories.prompts import PromptsRepository
from src.models.settings import (
    PromptResponse,
    PromptsListResponse,
    PromptUpdateRequest,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

VALID_PROMPT_KEYS = {"system_prompt_default", "system_prompt_custom", "memory", "soul"}


@router.get("", response_model=PromptsListResponse)
async def list_prompts(
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
) -> PromptsListResponse:
    """
    List all prompts.

    Returns:
        PromptsListResponse with all prompts
    """
    prompts = prompts_repo.list_all()
    prompt_responses = [PromptResponse(**p) for p in prompts]
    return PromptsListResponse(prompts=prompt_responses)


@router.get("/{key}", response_model=PromptResponse)
async def get_prompt(
    key: str,
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
) -> PromptResponse:
    """
    Get a specific prompt by key.

    Args:
        key: Prompt key (system_prompt_default, system_prompt_custom, memory, soul)

    Returns:
        PromptResponse with prompt details

    Raises:
        HTTPException: If prompt not found
    """
    if key not in VALID_PROMPT_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {key}")

    prompt = prompts_repo.get(key)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    return PromptResponse(**prompt)


@router.put("/{key}", response_model=PromptResponse)
async def update_prompt(
    key: str,
    request: PromptUpdateRequest,
    prompts_repo: PromptsRepository = Depends(get_prompts_repo),
) -> PromptResponse:
    """
    Update a prompt value.

    Args:
        key: Prompt key (system_prompt_default, system_prompt_custom, memory, soul)
        request: Prompt update request with new value

    Returns:
        PromptResponse with updated prompt

    Raises:
        HTTPException: If prompt not found or update fails
    """
    if key not in VALID_PROMPT_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {key}")

    success = prompts_repo.set(key, request.value)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update prompt")

    prompt = prompts_repo.get(key)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found after update")

    return PromptResponse(**prompt)
