"""Lightweight ULID stub for tests (not full ULID spec)."""
import uuid

def new():  # type: ignore
    """Return RFC4122 UUID4 as string-compatible ULID stub."""
    return uuid.uuid4()
