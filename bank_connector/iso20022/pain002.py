"""Parse minimal ISO 20022 pain.002 status report."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from enum import Enum
from typing import Final

NS: Final = "urn:iso:std:iso:20022:tech:xsd:pain.002.001.03"
ALT_NS: Final = "urn:iso:std:iso:20022:tech:xsd:pain.002.001.02"  # accept either


class PaymentStatus(Enum):
    ACCP = "ACCP"  # Accepted technical validation
    ACSC = "ACSC"  # Accepted settlement completed
    RJCT = "RJCT"  # Rejected
    UNKNOWN = "UNKNOWN"


def _find_status(root: ET.Element) -> str | None:
    # pain.002 variants may nest GrpSts under \GrpHdr\GrpSts or \CstmrPmtStsRpt\OrgnlGrpInfAndSts
    # We'll look for first occurrence of element ending with 'GrpSts' or 'TxSts'.
    for tag in ("GrpSts", "TxSts"):
        elem = root.find(f".//{{*}}{tag}")
        if elem is not None and elem.text:
            return elem.text.strip().upper()
    return None


def parse_pain002(xml_text: str) -> PaymentStatus:
    """Extract status code from pain.002 XML and map to PaymentStatus."""

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return PaymentStatus.UNKNOWN

    code = _find_status(root)
    if code in (
        PaymentStatus.ACCP.value,
        PaymentStatus.ACSC.value,
        PaymentStatus.RJCT.value,
    ):
        return PaymentStatus(code)  # type: ignore[arg-type]
    return PaymentStatus.UNKNOWN
