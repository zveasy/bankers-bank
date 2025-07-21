from __future__ import annotations

import os
from typing import Optional

from sqlmodel import Field, SQLModel, create_engine, Session, select

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bank_connector.db")
engine = create_engine(DATABASE_URL, echo=False)


class SweepOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str
    amount: float
    currency: str
    debtor: str
    creditor: str
    status: Optional[str] = None


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
