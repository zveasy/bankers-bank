import shutil
import subprocess
import pytest

docker = shutil.which("docker")
pytestmark = pytest.mark.skipif(docker is None, reason="docker not installed")

def test_compose_config():
    subprocess.run(["docker", "compose", "config", "--quiet"], check=True)
