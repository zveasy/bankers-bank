import os
from fastapi import Header, HTTPException, status


def require_token(authorization: str | None = Header(None)) -> None:
    """Validate Bearer token from the Authorization header.

    Token is compared against the ``API_TOKEN`` environment variable.
    Raises HTTPException on missing/invalid credentials.
    """
    expected = os.getenv("API_TOKEN", "")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return None
