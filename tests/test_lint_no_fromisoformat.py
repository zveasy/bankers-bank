"""Fail the test suite if `datetime.fromisoformat(` is used in application code.

Allows usage inside the `tests/` tree since test helpers may validate behaviour.
"""
from __future__ import annotations

import pathlib


def _project_files():
    root = pathlib.Path(__file__).resolve().parent.parent
    for path in root.rglob("*.py"):
        if any(part in path.parts for part in ("tests", "site-packages", "dist-packages", ".venv")):
            continue  # ignore test code itself
        yield path


def test_no_fromisoformat():
    offenders: list[str] = []
    for file in _project_files():
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "fromisoformat(" in text:
            offenders.append(str(file.relative_to(file.parents[2])))
    assert not offenders, (
        "datetime.fromisoformat() is forbidden; use common.datetime.parse_iso8601 instead. "
        f"Found in: {', '.join(offenders)}"
    )
