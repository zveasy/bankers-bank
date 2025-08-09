from pathlib import Path

TREASURY_DOC = Path("docs/treasury-orchestrator.md")


def test_treasury_doc_contains_sweep_order():
    text = TREASURY_DOC.read_text(encoding="utf-8")
    assert "SweepOrder" in text
