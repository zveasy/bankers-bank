"""Helpers to build and parse ISO20022 messages using pydantic_xsd."""

from pydantic_xsd import BaseModel


class Pain001(BaseModel, xsd_path="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09.xsd"):
    pass  # actual fields provided by schema


class Pain002(BaseModel, xsd_path="urn:iso:std:iso:20022:tech:xsd:pain.002.001.10.xsd"):
    pass


def create_pain_001(order_id: str, amount: float, currency: str, debtor: str, creditor: str) -> str:
    """Return XML string for pain.001 message."""
    msg = Pain001.parse_obj({})  # placeholder since schema models provide defaults
    # In real implementation you'd populate fields accordingly
    return msg.to_xml()


def parse_pain_002(xml: str) -> str:
    """Parse pain.002 XML and return payment status."""
    msg = Pain002.from_xml(xml)
    # In real implementation you'd access proper status field
    return getattr(msg, "status", "UNKNOWN")
