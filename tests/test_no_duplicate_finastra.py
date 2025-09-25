# tests/test_no_duplicate_finastra.py
from pathlib import Path

def test_sdk_finastra_is_shim():
    root = Path(__file__).resolve().parents[1]
    sdk_file = root / "sdk" / "python" / "bankersbank" / "finastra.py"
    text = sdk_file.read_text(encoding="utf-8")
    assert "from bankersbank.finastra import *" in text and len(text.splitlines()) < 15, \
        "SDK finastra.py must stay a tiny forwarding shim."
