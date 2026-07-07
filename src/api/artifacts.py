"""API endpoints for the artifact store.

Owner/management endpoints (list, delete, visibility, temporary-link, secret) are
called by the Artifacts tab and are gated the same way as the rest of the app UI
(by the surrounding proxy in managed deployments). The visitor endpoints
(``GET /artifact/{id}`` and ``POST /artifact/{id}/unlock``) implement the public
sharing + passphrase gate and must remain reachable without the owner's auth for
external sharing to work.
"""

from pathlib import Path, PurePosixPath
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from src.core.dependencies import get_artifact_repo
from src.core.jwt import (
    create_artifact_token,
    create_artifact_unlock_token,
    verify_artifact_token,
    verify_artifact_unlock_token,
)
from src.core.repositories.artifact import ArtifactRepository
from src.models.artifacts import (
    ArtifactActionResponse,
    ArtifactListResponse,
    ArtifactResponse,
    SecretRequest,
    TemporaryLinkResponse,
    VisibilityRequest,
)
from src.services.artifacts import (
    delete_artifact_files,
    hash_secret,
    permanent_link,
    resolve_artifact_path,
    temporary_link,
    verify_secret,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
visitor_router = APIRouter(prefix="/artifact", tags=["artifacts"])

_TEMP_LINK_TTL_SECONDS = 300
_UNLOCK_COOKIE_MAX_AGE = 3600

_GATE_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "ui" / "static" / "artifact-unlock.html"
)


def _to_response(art: dict) -> ArtifactResponse:
    """Convert a DB artifact row to the API response model."""
    is_public = bool(art["is_public"])
    return ArtifactResponse(
        artifact_id=art["artifact_id"],
        title=art.get("title"),
        filename=art["filename"],
        mime_type=art.get("mime_type"),
        size=art.get("size"),
        is_public=is_public,
        has_secret=bool(art.get("secret_hash")),
        created_at=art.get("created_at"),
        updated_at=art.get("updated_at"),
        permanent_link=permanent_link(art["artifact_id"]) if is_public else None,
    )


def _get_or_404(repo: ArtifactRepository, artifact_id: str) -> dict:
    art = repo.get_by_id(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return art


def _cookie_name(artifact_id: str) -> str:
    return f"oa_artifact_{artifact_id}"


# ---------------------------------------------------------------------------
# Owner / management endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    repo: ArtifactRepository = Depends(get_artifact_repo),
) -> ArtifactListResponse:
    """List all stored artifacts, newest first."""
    artifacts = [_to_response(a) for a in repo.list_all()]
    return ArtifactListResponse(artifacts=artifacts, total=len(artifacts))


@router.delete("/{artifact_id}", response_model=ArtifactActionResponse)
async def delete_artifact(
    artifact_id: str,
    repo: ArtifactRepository = Depends(get_artifact_repo),
) -> ArtifactActionResponse:
    """Delete an artifact: remove its files and DB record."""
    art = _get_or_404(repo, artifact_id)
    delete_artifact_files(art)
    repo.delete_artifact(artifact_id)
    return ArtifactActionResponse(success=True)


@router.patch("/{artifact_id}/visibility", response_model=ArtifactActionResponse)
async def set_visibility(
    artifact_id: str,
    request: VisibilityRequest,
    repo: ArtifactRepository = Depends(get_artifact_repo),
) -> ArtifactActionResponse:
    """Toggle an artifact's public/private visibility."""
    _get_or_404(repo, artifact_id)
    repo.set_public(artifact_id, request.is_public)
    art = repo.get_by_id(artifact_id)
    return ArtifactActionResponse(success=True, artifact=_to_response(art))


@router.post("/{artifact_id}/temporary-link", response_model=TemporaryLinkResponse)
async def create_temporary_link(
    artifact_id: str,
    repo: ArtifactRepository = Depends(get_artifact_repo),
) -> TemporaryLinkResponse:
    """Mint a signed link valid for 300 seconds (for sharing a private artifact)."""
    _get_or_404(repo, artifact_id)
    token = create_artifact_token(artifact_id)
    return TemporaryLinkResponse(
        url=temporary_link(artifact_id, token),
        expires_in=_TEMP_LINK_TTL_SECONDS,
    )


@router.put("/{artifact_id}/secret", response_model=ArtifactActionResponse)
async def set_secret(
    artifact_id: str,
    request: SecretRequest,
    repo: ArtifactRepository = Depends(get_artifact_repo),
) -> ArtifactActionResponse:
    """Enable or change the passphrase gate for an artifact."""
    _get_or_404(repo, artifact_id)
    repo.set_secret(artifact_id, hash_secret(request.passphrase))
    art = repo.get_by_id(artifact_id)
    return ArtifactActionResponse(success=True, artifact=_to_response(art))


@router.delete("/{artifact_id}/secret", response_model=ArtifactActionResponse)
async def clear_secret(
    artifact_id: str,
    repo: ArtifactRepository = Depends(get_artifact_repo),
) -> ArtifactActionResponse:
    """Disable the passphrase gate for an artifact."""
    _get_or_404(repo, artifact_id)
    repo.set_secret(artifact_id, None)
    art = repo.get_by_id(artifact_id)
    return ArtifactActionResponse(success=True, artifact=_to_response(art))


# ---------------------------------------------------------------------------
# Public / visitor endpoints
# ---------------------------------------------------------------------------


def _render_gate(status_code: int = 200) -> HTMLResponse:
    """Render the passphrase gate page (self-contained; unlocks via fetch)."""
    try:
        html = _GATE_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        html = (
            '<!DOCTYPE html><html><body><form onsubmit="event.preventDefault();'
            "fetch(location.pathname+'/unlock'+location.search,"
            "{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({passphrase:this.p.value})}).then(r=>r.ok?location.reload():"
            "alert('Incorrect passphrase'))\">"
            "<input name='p' type='password' placeholder='Passphrase'><button>Unlock</button>"
            "</form></body></html>"
        )
    return HTMLResponse(html, status_code=status_code)


def _serve_file(art: dict) -> FileResponse:
    path = resolve_artifact_path(art)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file is missing")
    media_type = art.get("mime_type") or "application/octet-stream"
    # HTML renders inline in the browser; everything else downloads.
    if media_type == "text/html":
        return FileResponse(path, media_type="text/html")
    return FileResponse(path, media_type=media_type, filename=art["filename"])


@visitor_router.get("/{artifact_id}", name="view_artifact")
async def view_artifact(
    artifact_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    repo: ArtifactRepository = Depends(get_artifact_repo),
):
    """Serve an artifact at the clean public URL ``/artifact/{id}``.

    Access is checked in two layers: (1) the artifact must be public, or a valid
    300s ``token`` must be supplied; (2) if a passphrase is set, a valid unlock
    cookie must be present, otherwise the passphrase gate page is returned.
    """
    art = _get_or_404(repo, artifact_id)

    # Layer 1: link-level access
    if not bool(art["is_public"]):
        if not token or verify_artifact_token(token) != artifact_id:
            raise HTTPException(status_code=401, detail="This artifact is private.")

    # Layer 2: passphrase gate
    if art.get("secret_hash"):
        cookie = request.cookies.get(_cookie_name(artifact_id))
        if not cookie or not verify_artifact_unlock_token(cookie, artifact_id):
            return _render_gate()

    return _serve_file(art)


@visitor_router.post("/{artifact_id}/unlock")
async def unlock_artifact(
    artifact_id: str,
    body: SecretRequest,
    request: Request,
    repo: ArtifactRepository = Depends(get_artifact_repo),
):
    """Verify a passphrase and, on success, set the unlock cookie.

    Called by the gate page via fetch. On success returns 200 with a Set-Cookie
    header; the page then reloads ``/artifact/{id}`` and the file is served.
    """
    art = _get_or_404(repo, artifact_id)

    stored = art.get("secret_hash")
    if not stored:
        # No passphrase configured — nothing to unlock.
        return JSONResponse({"success": True})

    if not verify_secret(body.passphrase, stored):
        return JSONResponse({"success": False}, status_code=401)

    cookie_path = str(PurePosixPath(request.url.path).parent) + "/"

    response = JSONResponse({"success": True})
    response.set_cookie(
        key=_cookie_name(artifact_id),
        value=create_artifact_unlock_token(artifact_id),
        max_age=_UNLOCK_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path=cookie_path,
    )
    return response
