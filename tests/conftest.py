import sys
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[1]
SDK_PATH = ROOT / "sdk" / "python"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

try:
    import requests  # type: ignore
    REQUESTS_AVAILABLE = True
except Exception:  # pragma: no cover - missing dependency
    REQUESTS_AVAILABLE = False
    stub = types.ModuleType("requests")
    def _stub(*args, **kwargs):
        raise RuntimeError("requests library not available")
    stub.get = stub.post = _stub
    sys.modules["requests"] = stub
