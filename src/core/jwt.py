"""JWT helpers for signed, expiring tokens (OAuth state and artifact links)."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

ALGORITHM = "HS256"
_STATE_TTL_SECONDS = 300  # 5 minutes


def get_jwt_secret() -> str:
    """Get the JWT signing secret from the ENCRYPTION_KEY env var.

    ENCRYPTION_KEY is a secure random key required by the app for encryption,
    so it is reused here to sign JWTs. It must be set before any token is
    issued or verified.
    """
    import os

    secret = os.getenv("ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError("ENCRYPTION_KEY not set - required for signing JWTs")
    return secret


def create_oauth_state(instance_id: Optional[str] = None) -> str:
    """Create a signed, expiring state token for OAuth CSRF check.

    Args:
        instance_id: Optional instance slug to embed for relay routing

    Returns:
        Signed JWT state token
    """
    payload = {
        "nonce": secrets.token_hex(16),
        "exp": datetime.now(UTC) + timedelta(seconds=_STATE_TTL_SECONDS),
        "purpose": "oauth_state",
    }
    if instance_id:
        payload["instance_id"] = instance_id

    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def verify_oauth_state(state: str) -> bool:
    """Verify state token signature and expiry.

    Args:
        state: JWT state token to verify

    Returns:
        True if valid and unexpired
    """
    try:
        payload = jwt.decode(state, get_jwt_secret(), algorithms=[ALGORITHM])
        return payload.get("purpose") == "oauth_state"
    except JWTError:
        return False


def create_artifact_token(artifact_id: str) -> str:
    """Create a signed, expiring link token for sharing a private artifact.

    Valid for 300 seconds (``_STATE_TTL_SECONDS``). Anyone holding the token can
    reach the artifact's ``/view`` route until it expires.

    Args:
        artifact_id: The artifact this token grants access to

    Returns:
        Signed JWT link token
    """
    payload = {
        "artifact_id": artifact_id,
        "nonce": secrets.token_hex(16),
        "exp": datetime.now(UTC) + timedelta(seconds=_STATE_TTL_SECONDS),
        "purpose": "artifact_link",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def verify_artifact_token(token: str) -> Optional[str]:
    """Verify a temporary artifact link token.

    Args:
        token: JWT link token to verify

    Returns:
        The ``artifact_id`` if the token is valid, unexpired, and of the right
        purpose; otherwise ``None``.
    """
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        if payload.get("purpose") != "artifact_link":
            return None
        return payload.get("artifact_id")
    except JWTError:
        return None


def create_artifact_unlock_token(artifact_id: str, ttl: int = 3600) -> str:
    """Create a token proving the passphrase for a secret-gated artifact was entered.

    Minted after a correct passphrase and carried back as an httpOnly cookie so
    the visitor is not re-prompted on every view. Defaults to a 1-hour lifetime.

    Args:
        artifact_id: The artifact this unlock token applies to
        ttl: Lifetime in seconds

    Returns:
        Signed JWT unlock token
    """
    payload = {
        "artifact_id": artifact_id,
        "exp": datetime.now(UTC) + timedelta(seconds=ttl),
        "purpose": "artifact_unlock",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def verify_artifact_unlock_token(token: str, artifact_id: str) -> bool:
    """Verify an artifact unlock token matches the given artifact and is unexpired.

    Args:
        token: JWT unlock token to verify
        artifact_id: The artifact the token must be scoped to

    Returns:
        True if valid, unexpired, correct purpose, and matching artifact_id.
    """
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        return (
            payload.get("purpose") == "artifact_unlock"
            and payload.get("artifact_id") == artifact_id
        )
    except JWTError:
        return False
