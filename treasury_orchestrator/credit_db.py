import os
from datetime import datetime
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine

DATABASE_URL = os.getenv("CREDIT_DB_URL", "sqlite:///./credit_facility.db")
engine = create_engine(DATABASE_URL, echo=False)


class CreditFacility(SQLModel, table=True):
    """Credit facility master record."""

    id: str = Field(primary_key=True)
    limit: float
    drawn: float = 0.0
    ltv_limit: float


class CreditTxn(SQLModel, table=True):
    """Individual credit facility transactions."""

    id: Optional[int] = Field(default=None, primary_key=True)
    facility_id: str = Field(foreign_key="creditfacility.id")
    amount: float
    txn_type: str
    ts: datetime = Field(default_factory=datetime.utcnow)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)

