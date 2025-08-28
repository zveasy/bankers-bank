"""Datetime helpers common to multiple services.

Currently provides:
    parse_iso8601(s): robust ISO-8601 parser that always returns an *aware* UTC
    datetime instance. The function accepts strings with:
        • trailing "Z"
        • explicit offsets like "+00:00" or "-05:00"
        • fractional seconds
    and normalises them to UTC.

This avoids scattered direct calls to dateutil.parser.isoparse or
datetime.fromisoformat, giving us a single spot to patch if behavior changes.
"""
from __future__ import annotations

import datetime as _dt
from typing import Union

from dateutil.parser import isoparse as _isoparse

__all__ = ["parse_iso8601"]


def _ensure_utc(dt: _dt.datetime) -> _dt.datetime:
    """Return *dt* converted to UTC and TZ-aware."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        # naive → assume already UTC
        return dt.replace(tzinfo=_dt.timezone.utc)
    # convert
    return dt.astimezone(_dt.timezone.utc)


def parse_iso8601(value: Union[str, _dt.datetime]) -> _dt.datetime:
    """Parse *value* into a timezone-aware UTC datetime.

    Accepts ISO-8601 strings or datetime objects. If *value* is already a
    datetime, it will be normalised to UTC.
    """
    if isinstance(value, _dt.datetime):
        return _ensure_utc(value)

    if not isinstance(value, str):
        raise TypeError("parse_iso8601 expects str or datetime, got " + type(value).__name__)

    try:
        dt = _isoparse(value)
    except Exception as exc:  # pragma: no cover – caller will decide
        raise ValueError(f"invalid ISO-8601 datetime: {value}") from exc

    return _ensure_utc(dt)
