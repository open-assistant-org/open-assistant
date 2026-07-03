"""Artifact store API request/response models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class ArtifactResponse(BaseModel):
    """A single stored artifact (management view)."""

    artifact_id: str
    title: Optional[str] = None
    filename: str
    mime_type: Optional[str] = None
    size: Optional[int] = None
    is_public: bool
    has_secret: bool = Field(
        ..., description="Whether a passphrase gate is set (hash never exposed)"
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    permanent_link: Optional[str] = Field(
        None, description="Stable public link (present only when the artifact is public)"
    )


class ArtifactListResponse(BaseModel):
    """List of stored artifacts."""

    artifacts: List[ArtifactResponse]
    total: int


class VisibilityRequest(BaseModel):
    """Toggle an artifact's public/private visibility."""

    is_public: bool


class SecretRequest(BaseModel):
    """Set or change an artifact's passphrase."""

    passphrase: str = Field(..., min_length=1, description="The passphrase visitors must enter")


class TemporaryLinkResponse(BaseModel):
    """A signed, expiring link for a private artifact."""

    url: str
    expires_in: int = Field(..., description="Lifetime of the link in seconds")


class ArtifactActionResponse(BaseModel):
    """Generic success response for mutating actions."""

    success: bool = True
    artifact: Optional[ArtifactResponse] = None
