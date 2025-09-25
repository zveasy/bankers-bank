import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Prefer canonical package over SDK copy
# ---------------------------------------------------------------------------
_SDK_DIR = Path(__file__).resolve().parents[1] / "sdk" / "python"
if str(_SDK_DIR) in sys.path:
    sys.path.remove(str(_SDK_DIR))

import pytest

from common import secrets as secrets_module


def pytest_configure(config):
    """If pytest-socket is installed, disable sockets and allow localhost if supported."""
    try:
        import pytest_socket

        pytest_socket.disable_socket()
        if hasattr(pytest_socket, "allow_hosts"):
            pytest_socket.allow_hosts("127.0.0.1", "localhost")
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Default auth token for API tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _secrets() -> None:
    """Provide default secrets for tests via the secrets manager."""

    secrets_module.secrets.set_override(
        {"API_TOKENS": {"tester": "testtoken"}, "JWT_SECRET": "testsecret"}
    )
    yield
    secrets_module.secrets.set_override({})


# ---------------------------------------------------------------------------
# Fake Redis for offline unit tests
# ---------------------------------------------------------------------------

try:
    import fakeredis  # type: ignore

    from quantengine import main as _qmain

    _qmain.redis_client = fakeredis.FakeRedis()
except Exception:
    # If fakeredis not installed or quantengine absent, ignore – tests will skip
    pass

# ---------------------------------------------------------------------------
# Automatically skip external integration tests unless opt-in
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    """Skip tests that require a running HTTP server unless opt-in via env."""
    if os.getenv("BANKERSBANK_INTEGRATION") == "1":
        return  # run normally

    skip_marker = pytest.mark.skip(
        reason="external integration tests disabled (set BANKERSBANK_INTEGRATION=1 to run)"
    )
    for item in items:
        path_str = str(item.fspath)
        if "integration_client" in path_str:
            item.add_marker(skip_marker)
