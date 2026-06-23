"""JWT helpers for managed mode OAuth state."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

ALGORITHM = "HS256"
_STATE_TTL_SECONDS = 300  # 5 minutes


def get_jwt_secret() -> str:
    """Get JWT secret from ENCRYPTION_KEY env var.

    The ENCRYPTION_KEY is already a secure random key pushed from the platform
    during provisioning, making it suitable for JWT signing.
    """
    import os

    secret = os.getenv("ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError("ENCRYPTION_KEY not set - required for managed mode OAuth")
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
