import datetime as _dt

import pytest

from common.datetime import parse_iso8601


@pytest.mark.parametrize(
    "s,expected",
    [
        ("2025-08-27T12:00:00Z", _dt.datetime(2025, 8, 27, 12, 0, 0, tzinfo=_dt.timezone.utc)),
        ("2025-08-27T12:00:00+00:00", _dt.datetime(2025, 8, 27, 12, 0, 0, tzinfo=_dt.timezone.utc)),
        ("2025-08-27T07:00:00-05:00", _dt.datetime(2025, 8, 27, 12, 0, 0, tzinfo=_dt.timezone.utc)),
        ("2025-08-27T12:00:00.123456Z", _dt.datetime(2025, 8, 27, 12, 0, 0, 123456, tzinfo=_dt.timezone.utc)),
    ],
)
def test_parse_iso8601(s, expected):
    assert parse_iso8601(s) == expected


def test_parse_datetime_roundtrip():
    dt = _dt.datetime(2025, 1, 1, 0, 0, tzinfo=_dt.timezone.utc)
    assert parse_iso8601(dt) is dt  # same object when already UTC-aware
