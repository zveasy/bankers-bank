import os
import pytest


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

    skip_marker = pytest.mark.skip(reason="external integration tests disabled (set BANKERSBANK_INTEGRATION=1 to run)")
    for item in items:
        path_str = str(item.fspath)
        if "integration-client" in path_str or "integration_client" in path_str:
            item.add_marker(skip_marker)
