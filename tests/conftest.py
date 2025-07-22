

def pytest_configure(config):
    """If pytest-socket is installed, disable sockets and allow localhost if supported."""
    try:
        import pytest_socket
        pytest_socket.disable_socket()
        if hasattr(pytest_socket, "allow_hosts"):
            pytest_socket.allow_hosts("127.0.0.1", "localhost")
    except ImportError:
        pass
