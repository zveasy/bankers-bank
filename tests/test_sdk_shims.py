# tests/test_sdk_shims.py
from pathlib import Path
import ast
import os

MAX_LOC = int(os.getenv("SHIM_MAX_LOC", "20"))

ALLOWED_ASSIGN_NAMES = {"__all__", "_mod", "__canonical_module__"}

def _is_pure_shim(p: Path) -> bool:
    src = p.read_text(encoding="utf-8")
    if len(src.splitlines()) > MAX_LOC:
        return False

    tree = ast.parse(src, filename=str(p))
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            return False

    for node in tree.body:
        if isinstance(node, ast.Assign):
            # ensure only whitelisted names on left
            for tgt in node.targets:
                if not isinstance(tgt, ast.Name) or tgt.id not in ALLOWED_ASSIGN_NAMES:
                    return False
        elif not isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)):
            return False
    return True

def test_finastra_shim_is_pure():
    p = Path("sdk/python/bankersbank/finastra.py")
    assert p.exists(), "SDK finastra shim missing"
    assert _is_pure_shim(p), "Finastra shim contains logic or exceeds size"

def test_client_shim_is_pure():
    p = Path("sdk/python/bankersbank/client.py")
    assert p.exists(), "SDK client shim missing"
    assert _is_pure_shim(p), "Client shim contains logic or exceeds size"
