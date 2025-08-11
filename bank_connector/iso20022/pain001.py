"""Build minimal ISO 20022 pain.001.001.03 XML.

Subset sufficient for Sweep Order use-case. No external deps; uses stdlib ElementTree.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Protocol

NS = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
ET.register_namespace("", NS)  # default NS


class Clock(Protocol):
    """Abstract clock used for deterministic testing."""

    def now_iso(self) -> str:  # pragma: no cover – protocol stub
        """Return current timestamp in ISO-8601 (UTC) format."""


class UUIDFactory(Protocol):
    """Abstract UUID factory for deterministic testing."""

    def new(self) -> str:  # pragma: no cover – protocol stub
        """Return a new RFC-4122 string."""


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _indent(elem: ET.Element, level: int = 0) -> None:  # pragma: no cover
    """Pretty-print helper (in-place)."""

    pad = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + "  "
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():  # type: ignore[name-defined]
            child.tail = pad
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = pad


def build_pain001(
    *,
    order_id: str,
    debtor: str,
    creditor: str,
    amount: float,
    currency: str,
    execution_ts: str,
    clock: Clock,
    uuidf: UUIDFactory,
) -> str:
    """Return pain.001.001.03 XML string for single credit transfer.

    Arguments:
        order_id: client order reference (EndToEndId)
        debtor: debtor name (simple string)
        creditor: creditor name (simple string)
        amount: decimal amount (2dp)
        currency: currency code (e.g. "USD")
        execution_ts: ISO timestamp – we derive date part for ReqdExctnDt
        clock: injectable clock for `CreDtTm`
        uuidf: injectable uuid factory for MsgId / PmtInfId
    """

    # Root
    doc = ET.Element(ET.QName(NS, "Document"))
    ccti = ET.SubElement(doc, ET.QName(NS, "CstmrCdtTrfInitn"))

    # ------------------- Group Header -------------------
    grp_hdr = ET.SubElement(ccti, ET.QName(NS, "GrpHdr"))
    ET.SubElement(grp_hdr, ET.QName(NS, "MsgId")).text = uuidf.new()
    ET.SubElement(grp_hdr, ET.QName(NS, "CreDtTm")).text = clock.now_iso()
    ET.SubElement(grp_hdr, ET.QName(NS, "NbOfTxs")).text = "1"

    # ------------------- Payment Information -------------
    pmt_inf = ET.SubElement(ccti, ET.QName(NS, "PmtInf"))
    ET.SubElement(pmt_inf, ET.QName(NS, "PmtInfId")).text = uuidf.new()
    ET.SubElement(pmt_inf, ET.QName(NS, "PmtMtd")).text = "TRF"

    # ReqdExctnDt requires date only (YYYY-MM-DD)
    exec_date = execution_ts.split("T", 1)[0]
    ET.SubElement(pmt_inf, ET.QName(NS, "ReqdExctnDt")).text = exec_date

    dbtr = ET.SubElement(pmt_inf, ET.QName(NS, "Dbtr"))
    ET.SubElement(dbtr, ET.QName(NS, "Nm")).text = debtor

    # Transaction
    ctti = ET.SubElement(pmt_inf, ET.QName(NS, "CdtTrfTxInf"))
    pmt_id = ET.SubElement(ctti, ET.QName(NS, "PmtId"))
    ET.SubElement(pmt_id, ET.QName(NS, "EndToEndId")).text = order_id

    amt_elt = ET.SubElement(ctti, ET.QName(NS, "Amt"))
    instd = ET.SubElement(amt_elt, ET.QName(NS, "InstdAmt"), Ccy=currency)
    instd.text = f"{amount:.2f}"

    cdtr = ET.SubElement(ctti, ET.QName(NS, "Cdtr"))
    ET.SubElement(cdtr, ET.QName(NS, "Nm")).text = creditor

    # Pretty print to string
    _indent(doc)
    xml_bytes = ET.tostring(doc, encoding="utf-8")
    return xml_bytes.decode("utf-8")
