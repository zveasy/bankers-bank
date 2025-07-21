from pydantic import BaseModel


class SweepOrderRequest(BaseModel):
    order_id: str
    amount: float
    currency: str
    debtor: str
    creditor: str


class PaymentStatusResponse(BaseModel):
    status: str
