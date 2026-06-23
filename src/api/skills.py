"""Skills management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import get_settings_service, get_skill_repo
from src.core.repositories.skill import SkillRepository
from src.models.skills import (
    SkillCreateRequest,
    SkillListResponse,
    SkillResponse,
    SkillUpdateRequest,
    SuggestKeywordsRequest,
    SuggestKeywordsResponse,
)
from src.services.settings import SettingsService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("", response_model=SkillListResponse)
async def list_skills(
    enabled_only: bool = False,
    skill_repo: SkillRepository = Depends(get_skill_repo),
) -> SkillListResponse:
    """
    List all skills, optionally filtered by enabled status.

    Args:
        enabled_only: If True, only return enabled skills
        skill_repo: Skill repository (injected)

    Returns:
        SkillListResponse with list of skills
    """
    try:
        if enabled_only:
            skills = skill_repo.get_enabled_skills()
        else:
            skills = skill_repo.get_all_skills()

        return SkillListResponse(
            skills=[SkillResponse.model_validate(skill.to_dict()) for skill in skills],
            total=len(skills),
        )
    except Exception as e:
        logger.error(f"Error listing skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list skills: {str(e)}")


@router.get("/{name}", response_model=SkillResponse)
async def get_skill(
    name: str,
    skill_repo: SkillRepository = Depends(get_skill_repo),
) -> SkillResponse:
    """
    Get a single skill by name.

    Args:
        name: Skill name
        skill_repo: Skill repository (injected)

    Returns:
        SkillResponse for the requested skill

    Raises:
        HTTPException: If skill not found
    """
    try:
        skill = skill_repo.get_skill_by_name(name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        return SkillResponse.model_validate(skill.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting skill {name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.put("/{name}", response_model=SkillResponse)
async def update_skill(
    name: str,
    request: SkillUpdateRequest,
    skill_repo: SkillRepository = Depends(get_skill_repo),
) -> SkillResponse:
    """
    Update a skill's configuration.

    Args:
        name: Skill name
        request: Update request with fields to change
        skill_repo: Skill repository (injected)

    Returns:
        SkillResponse with updated skill

    Raises:
        HTTPException: If skill not found or update fails
    """
    try:
        # Get current skill
        skill = skill_repo.get_skill_by_name(name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        # Build updates dict (only include provided fields)
        updates = {}
        if request.display_name is not None:
            updates["display_name"] = request.display_name
        if request.category is not None:
            updates["category"] = request.category
        if request.description is not None:
            updates["description"] = request.description
        if request.context_prompt is not None:
            updates["context_prompt"] = request.context_prompt
        if request.tools is not None:
            updates["tools"] = request.tools
        if request.enabled is not None:
            updates["enabled"] = request.enabled
        if request.priority is not None:
            updates["priority"] = request.priority
        if request.intent_keywords is not None:
            updates["intent_keywords"] = request.intent_keywords

        # Update skill
        skill_repo.update_skill(skill.id, updates)

        # Return updated skill
        updated_skill = skill_repo.get_skill_by_name(name)
        if not updated_skill:
            raise RuntimeError("Failed to retrieve updated skill")

        logger.info(f"Updated skill: {name}, fields: {list(updates.keys())}")
        return SkillResponse.model_validate(updated_skill.to_dict())

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating skill {name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    request: SkillCreateRequest,
    skill_repo: SkillRepository = Depends(get_skill_repo),
) -> SkillResponse:
    """
    Create a new skill.

    Args:
        request: Skill creation request
        skill_repo: Skill repository (injected)

    Returns:
        SkillResponse for the created skill

    Raises:
        HTTPException: If validation fails or name already exists
    """
    try:
        # Validate name format (alphanumeric + underscores)
        import re

        if not re.match(r"^[a-z][a-z0-9_]*$", request.name):
            raise ValueError(
                "Skill name must start with a letter and contain only lowercase letters, "
                "numbers, and underscores"
            )

        # Create skill
        skill_data = {
            "name": request.name,
            "display_name": request.display_name,
            "category": request.category,
            "description": request.description,
            "context_prompt": request.context_prompt,
            "tools": request.tools,
            "enabled": request.enabled,
            "priority": request.priority,
            "intent_keywords": request.intent_keywords,
        }

        skill = skill_repo.create_skill(skill_data)

        logger.info(f"Created skill: {request.name}")
        return SkillResponse.model_validate(skill.to_dict())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.post("/{name}/toggle", response_model=SkillResponse)
async def toggle_skill(
    name: str,
    enabled: bool,
    skill_repo: SkillRepository = Depends(get_skill_repo),
) -> SkillResponse:
    """
    Enable or disable a skill.

    Args:
        name: Skill name
        enabled: New enabled status
        skill_repo: Skill repository (injected)

    Returns:
        SkillResponse with updated skill

    Raises:
        HTTPException: If skill not found
    """
    try:
        # Get skill
        skill = skill_repo.get_skill_by_name(name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        # Toggle
        skill_repo.toggle_skill(skill.id, enabled)

        # Return updated skill
        updated_skill = skill_repo.get_skill_by_name(name)
        if not updated_skill:
            raise RuntimeError("Failed to retrieve updated skill")

        status = "enabled" if enabled else "disabled"
        logger.info(f"Skill {name} {status}")
        return SkillResponse.model_validate(updated_skill.to_dict())

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error toggling skill {name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to toggle skill: {str(e)}")


@router.post("/suggest-keywords", response_model=SuggestKeywordsResponse)
async def suggest_keywords(
    request: SuggestKeywordsRequest,
    settings_service: SettingsService = Depends(get_settings_service),
) -> SuggestKeywordsResponse:
    """
    Use LLM to suggest intent keywords for a skill.

    This endpoint helps users define good intent keywords by analyzing
    the skill's description and context prompt using an LLM.

    Args:
        request: Suggestion request with skill details
        settings_service: Settings service (injected)

    Returns:
        SuggestKeywordsResponse with suggested keywords

    Raises:
        HTTPException: If LLM not configured or suggestion fails
    """
    try:
        # Verify LLM configuration
        api_key = settings_service.get_config_with_fallback("llm.api_key")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="LLM API key not configured",
            )

        # Get LLM client
        from src.core.llm_client import LLMClient, LLMConfig

        llm_config = LLMConfig.from_settings(settings_service, temperature=0.3, max_tokens=1000)

        llm_client = LLMClient(llm_config)

        # Build prompt for keyword suggestion
        existing_str = (
            f"\n\nExisting keywords: {', '.join(request.existing_keywords)}"
            if request.existing_keywords
            else ""
        )

        prompt = f"""You are helping to define intent matching keywords for a skills-based AI assistant system.

Skill Description: {request.description}

Context/Instructions:
{request.context_prompt}{existing_str}

Task: Suggest 5-15 keywords that users might use when their message should trigger this skill. Keywords should be:
1. Single words or short phrases (1-3 words)
2. Lowercase
3. Common terms users would naturally use
4. Diverse (cover different ways users might express the same intent)

Return your response as a JSON object with this format:
{{
    "keywords": ["keyword1", "keyword2", ...],
    "reasoning": "Brief explanation of why these keywords were chosen"
}}"""

        # Get LLM response
        response = llm_client.complete_text(prompt=prompt)

        # Parse JSON response
        import json

        try:
            # Extract JSON from response (handle markdown code blocks)
            response_text = response.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            result = json.loads(response_text)
            keywords = result.get("keywords", [])
            reasoning = result.get("reasoning", "")

        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            # Fallback: try to extract keywords from text
            keywords = [
                word.strip()
                for word in response.lower().split(",")
                if word.strip() and len(word.strip()) < 30
            ][:15]
            reasoning = "Keywords extracted from LLM response (JSON parsing failed)"

        logger.info(f"Suggested {len(keywords)} keywords for skill")
        return SuggestKeywordsResponse(
            suggested_keywords=keywords,
            reasoning=reasoning,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suggesting keywords: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to suggest keywords: {str(e)}")
