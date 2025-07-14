import types

try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False
    stub = types.ModuleType("requests")
    def _stub(*args, **kwargs):
        raise RuntimeError("requests library not available")
    stub.get = stub.post = _stub
    import sys
    sys.modules["requests"] = stub
