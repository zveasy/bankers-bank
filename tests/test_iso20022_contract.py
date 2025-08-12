"""Contract tests for ISO20022 builders/parsers (Sprint-8 PR-1)."""
from __future__ import annotations

import pathlib
import re

import pytest

from bank_connector.iso20022 import PaymentStatus, build_pain001, parse_pain002

BASE_DIR = (
    pathlib.Path(__file__).parent.parent / "bank_connector" / "iso20022" / "fixtures"
)


class FixedClock:
    def now_iso(self) -> str:  # type: ignore[override]
        return "2025-08-06T10:37:01Z"


class FixedUUID:
    def __init__(self) -> None:
        self.i = 0

    def new(self) -> str:  # type: ignore[override]
        self.i += 1
        return f"00000000-0000-0000-0000-{self.i:012d}"


def normalize_xml(s: str) -> str:
    """Collapse whitespace outside of tags for robust comparison."""
    # remove line breaks & multiple spaces between tags
    collapsed = re.sub(r">\s+<", "><", s.strip())
    return collapsed


def test_pain001_matches_golden():
    clock = FixedClock()
    uuidf = FixedUUID()
    xml_generated = build_pain001(
        order_id="ORD-123",
        debtor="ACCT-1",
        creditor="MMF-ABC",
        amount=100_000.00,
        currency="USD",
        execution_ts="2025-08-06T10:37:01Z",
        clock=clock,
        uuidf=uuidf,
    )

    golden_path = BASE_DIR / "pain001_happy.xml"
    xml_expected = golden_path.read_text()

    assert normalize_xml(xml_generated) == normalize_xml(xml_expected)


@pytest.mark.parametrize(
    "fixture_name,status",
    [
        ("pain002_accp.xml", PaymentStatus.ACCP),
        ("pain002_acsc.xml", PaymentStatus.ACSC),
        ("pain002_rjct.xml", PaymentStatus.RJCT),
    ],
)
def test_pain002_status_codes(fixture_name: str, status: PaymentStatus):
    xml_text = (BASE_DIR / fixture_name).read_text()
    assert parse_pain002(xml_text) == status


def test_pain002_unknown_is_safe():
    unknown_xml = "<Document><Foo>Bar</Foo></Document>"
    assert parse_pain002(unknown_xml) == PaymentStatus.UNKNOWN
