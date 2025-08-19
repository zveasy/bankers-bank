import importlib
import subprocess
import sys
from pathlib import Path


def test_sa_compat_injects_missing_types():
    """`sa_compat.apply()` should inject the expected symbols so that both
    `sqlmodel` and any user code can import them regardless of SQLAlchemy version.
    """
    from credit_facility.sa_compat import apply

    apply()

    from sqlalchemy import types as satypes  # noqa: WPS433 (import inside test)

    for name in ("DOUBLE", "Double", "UUID", "Uuid"):
        assert hasattr(satypes, name), f"Missing sqlalchemy.types.{name} after sa_compat.apply()"

    # And `sqlmodel` should import successfully once the shim is applied
    sqlmodel = importlib.import_module("sqlmodel")
    assert sqlmodel is not None


def test_audit_export_help_runs(monkeypatch):
    """Running `bin/audit-export --help` should exit 0 even under pytest."""
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", str(repo_root))

    result = subprocess.run(
        [sys.executable, str(repo_root / "bin" / "audit-export"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert ("--out" in result.stdout) or ("Usage" in result.stdout) or ("--help" in result.stdout)
