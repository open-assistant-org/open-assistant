"""Pydantic models for Skills API."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SkillResponse(BaseModel):
    """Response model for a single skill."""

    id: int = Field(..., description="Skill database ID")
    name: str = Field(..., description="Unique skill name")
    display_name: str = Field(..., description="Human-readable name")
    category: str = Field(..., description="Skill category")
    description: str = Field(..., description="Brief description of the skill")
    context_prompt: str = Field(..., description="Detailed LLM instructions for this skill")
    tools: List[str] = Field(default_factory=list, description="List of tool names")
    enabled: bool = Field(default=True, description="Whether skill is active")
    priority: int = Field(default=5, description="Selection priority (higher = selected first)")
    intent_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords for intent matching",
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class SkillListResponse(BaseModel):
    """Response model for listing skills."""

    skills: List[SkillResponse] = Field(..., description="List of skills")
    total: int = Field(..., description="Total number of skills")


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    display_name: Optional[str] = Field(None, description="Human-readable name")
    category: Optional[str] = Field(None, description="Skill category")
    description: Optional[str] = Field(None, description="Brief description")
    context_prompt: Optional[str] = Field(None, description="LLM instructions")
    tools: Optional[List[str]] = Field(None, description="List of tool names")
    enabled: Optional[bool] = Field(None, description="Whether skill is active")
    priority: Optional[int] = Field(None, ge=0, le=100, description="Selection priority")
    intent_keywords: Optional[List[str]] = Field(None, description="Intent matching keywords")


class SkillCreateRequest(BaseModel):
    """Request model for creating a new skill."""

    name: str = Field(..., description="Unique skill name (alphanumeric + underscores)")
    display_name: str = Field(..., description="Human-readable name")
    category: str = Field(..., description="Skill category")
    description: str = Field(..., description="Brief description")
    context_prompt: str = Field(..., description="Detailed LLM instructions")
    tools: List[str] = Field(default_factory=list, description="List of tool names")
    enabled: bool = Field(default=True, description="Whether skill is active")
    priority: int = Field(default=5, ge=0, le=100, description="Selection priority")
    intent_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords for intent matching",
    )


class SuggestKeywordsRequest(BaseModel):
    """Request model for keyword suggestions."""

    description: str = Field(..., description="Skill description")
    context_prompt: str = Field(..., description="Skill context/instructions")
    existing_keywords: List[str] = Field(
        default_factory=list,
        description="Already defined keywords",
    )


class SuggestKeywordsResponse(BaseModel):
    """Response model for keyword suggestions."""

    suggested_keywords: List[str] = Field(..., description="LLM-suggested keywords")
    reasoning: str = Field(..., description="Explanation of why these keywords were chosen")
