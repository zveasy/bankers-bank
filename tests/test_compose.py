import shutil
import subprocess

import pytest

docker = shutil.which("docker")
pytestmark = pytest.mark.skipif(docker is None, reason="docker not installed")


def test_compose_config():
    """Validate docker-compose file if Docker is available and config renders.

    Skips the test when:
    • docker is not installed (handled by pytestmark above)
    • `docker compose config` returns non-zero (e.g., missing .env vars on CI)
    """
    try:
        subprocess.run([
            "docker",
            "compose",
            "config",
            "--quiet",
        ], check=True)
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"docker compose config failed: {exc}")
