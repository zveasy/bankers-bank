#!/usr/bin/env python
"""Initialize local SQLite databases used in developer-mode.

This script creates fresh empty SQLite files for the services that default to
SQLite when a DATABASE_URL / *_DB_URL environment variable is not supplied.
It is safe to run multiple times (table creation is idempotent).
"""
from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Callable, Iterable

# (module, init_func_name) tuples for each service that supports local SQLite
_TARGETS: list[tuple[str, str]] = [
    ("asset_aggregator.db", "init_db"),
    ("bank_connector.db", "init_db"),
    ("quantengine.db", "init_db"),
]

def _load_callable(mod_path: str, name: str) -> Callable[[], None]:
    try:
        mod: ModuleType = importlib.import_module(mod_path)
    except ModuleNotFoundError as exc:
        raise SystemExit(f"module '{mod_path}' not found: {exc}") from exc
    try:
        fn = getattr(mod, name)
    except AttributeError as exc:
        raise SystemExit(f"{mod_path} missing callable '{name}'") from exc
    if not callable(fn):  # type: ignore[arg-type]
        raise SystemExit(f"{mod_path}.{name} is not callable")
    return fn  # type: ignore[return-value]

def _init_targets(targets: Iterable[tuple[str, str]]) -> None:
    for mod_path, fn_name in targets:
        fn = _load_callable(mod_path, fn_name)
        print(f"[init] {mod_path}.{fn_name}()")
        fn()


def main() -> None:  # pragma: no cover
    _init_targets(_TARGETS)
    print("\nSQLite databases initialised ✅")


if __name__ == "__main__":
    main()
