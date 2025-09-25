#!/usr/bin/env python3
"""CI guard: fail build if SDK shims contain logic or are too large."""
from __future__ import annotations

import ast
import sys
import os
from pathlib import Path

SHIM_DIR = Path("sdk/python/bankersbank")
MAX_LOC = int(os.getenv("SHIM_MAX_LOC", "20"))
ALLOWED_ASSIGN_NAMES = {"__all__", "_mod", "__canonical_module__"}


def is_pure_shim(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    if len(src.splitlines()) > MAX_LOC:
        print(f"[shim-guard] {path}: exceeds {MAX_LOC} LOC", file=sys.stderr)
        return False

    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        print(f"[shim-guard] {path}: syntax error {exc}", file=sys.stderr)
        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            print(f"[shim-guard] {path}: contains class/def {node.name}", file=sys.stderr)
            return False

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if not isinstance(tgt, ast.Name) or tgt.id not in ALLOWED_ASSIGN_NAMES:
                    print(f"[shim-guard] {path}: assignment to disallowed name", file=sys.stderr)
                    return False
        elif not isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)):
            print(f"[shim-guard] {path}: unexpected top-level node {type(node).__name__}", file=sys.stderr)
            return False
    return True


def main() -> int:
    if not SHIM_DIR.exists():
        print(f"[shim-guard] directory missing: {SHIM_DIR}", file=sys.stderr)
        return 1

    bad = []
    for path in SHIM_DIR.glob("*.py"):
        if not is_pure_shim(path):
            bad.append(str(path))

    if bad:
        print("[shim-guard] FAIL: non-pure shims found:\n  - " + "\n  - ".join(bad), file=sys.stderr)
        return 1

    print("[shim-guard] OK: all shims are pure and small")
    return 0


if __name__ == "__main__":
    sys.exit(main())
