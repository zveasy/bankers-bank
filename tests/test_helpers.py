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
    requests = stub

try:
    import jsonschema  # type: ignore
    JSONSCHEMA_AVAILABLE = True
except Exception:
    JSONSCHEMA_AVAILABLE = False
    js_stub = types.ModuleType("jsonschema")
    def _js_stub(*args, **kwargs):
        raise RuntimeError("jsonschema library not available")
    js_stub.validate = _js_stub
    import sys
    sys.modules["jsonschema"] = js_stub

__all__ = ["REQUESTS_AVAILABLE", "requests", "JSONSCHEMA_AVAILABLE"]
