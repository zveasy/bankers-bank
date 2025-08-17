"""SQLAlchemy compatibility shims for sqlmodel.

Provides missing type symbols (`DOUBLE`, `DOUBLE_PRECISION`, `Double`, `UUID`, `Uuid`) when using
`sqlmodel` with newer versions of SQLAlchemy that dropped / renamed them.

This is intentionally minimal and side-effect free beyond touching `sqlalchemy.types`.
Call `apply()` once, ideally **before** any sqlmodel import.
"""
from __future__ import annotations

from typing import Any


def _ensure(name: str, value: Any) -> None:  # pragma: no cover
    """Set `sqlalchemy.types.<name>` to *value* if it is currently missing."""
    from sqlalchemy import types as satypes  # local import to avoid hard dep at module import

    if not hasattr(satypes, name):
        setattr(satypes, name, value)


def apply() -> None:
    """Inject missing symbols onto ``sqlalchemy.types``.

    Safe to call multiple times.
    """
    from sqlalchemy import types as satypes

    # Try real DOUBLE from MySQL dialect; else fall back to Float.
    try:
        from sqlalchemy.dialects.mysql import DOUBLE as _MYSQL_DOUBLE  # type: ignore
    except Exception:  # pragma: no cover
        from sqlalchemy import Float as _MYSQL_DOUBLE  # type: ignore

    for _alias in ("DOUBLE", "DOUBLE_PRECISION", "Double"):
        _ensure(_alias, _MYSQL_DOUBLE)

    # UUID – use dialect type if present, else a simple decorator around String(36).
    try:
        from sqlalchemy.dialects.postgresql import UUID as _PG_UUID  # type: ignore
        _UUID_FALLBACK = _PG_UUID
    except Exception:  # pragma: no cover
        from sqlalchemy import String, TypeDecorator  # type: ignore

        class _UUID_FALLBACK(TypeDecorator):
            impl = String(36)
            cache_ok = True

    for _alias in ("UUID", "Uuid"):
        _ensure(_alias, _UUID_FALLBACK)


__all__ = ["apply"]
