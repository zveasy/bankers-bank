#!/usr/bin/env python3
"""Report duplicate basenames and duplicate symbol definitions.
Run in CI after lint/tests to surface potential drift.
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(".").resolve()
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", "tests"}
SYMBOLS = {
    "FinastraAPIClient",
    "ClientCredentialsTokenProvider",
    "fetch_token",
    "BankersBankClient",
}

def iter_py_files() -> list[Path]:
    files: list[Path] = []
    for p in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    return files


def dup_basenames(files: list[Path]):
    by_name: defaultdict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_name[f.name].append(f)
    return {n: paths for n, paths in by_name.items() if len(paths) > 1}


def symbol_definitions(files: list[Path]):
    defs: defaultdict[str, list[Path]] = defaultdict(list)
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in SYMBOLS:
                defs[node.name].append(f)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in SYMBOLS:
                defs[node.name].append(f)
    return defs


def main() -> int:
    files = iter_py_files()

    print("=== Duplicate basenames ===")
    dups = dup_basenames(files)
    if not dups:
        print("None")
    else:
        for name, paths in sorted(dups.items()):
            print(f"{name}:")
            for p in paths:
                print(f"  - {p.relative_to(ROOT)}")

    print("\n=== Symbol definitions ===")
    defs = symbol_definitions(files)
    for sym in sorted(SYMBOLS):
        paths = defs.get(sym, [])
        if paths:
            print(f"{sym}:")
            for p in paths:
                print(f"  - {p.relative_to(ROOT)}")
        else:
            print(f"{sym}: None")

    return 0


if __name__ == "__main__":
    sys.exit(main())
