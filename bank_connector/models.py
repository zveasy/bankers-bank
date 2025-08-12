from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, condecimal, constr

ISO4217 = constr(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")


class SweepOrderRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    amount: condecimal(max_digits=12, decimal_places=2, ge=Decimal("0.00"))
    currency: ISO4217
    debtor: str
    creditor: str


class SweepOrderCreated(BaseModel):
    id: int


class PaymentStatusResponse(BaseModel):
    status: Literal["SENT", "UNKNOWN", "ACCEPTED", "REJECTED", "SETTLED"]
