from typing import Any, Dict

import jwt
from fastapi import Header, HTTPException, status

from .secrets import get_secret


def require_token(authorization: str | None = Header(None)) -> Dict[str, Any] | None:
    """Validate Bearer token via per-user tokens or JWT."""

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Check for JWT (three segments separated by '.')
    if token.count(".") == 2:
        secret = get_secret("JWT_SECRET")
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            ) from exc
        return payload

    # Fallback to static per-user tokens
    tokens: Dict[str, str] = get_secret("API_TOKENS", {})
    for user, expected in tokens.items():
        if token == expected:
            return {"sub": user}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
