import os
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quantengine.db")
engine = create_engine(DATABASE_URL, echo=False)

class CashPosition(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str
    cash: float


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def get_cash(session: Session, bank_id: str) -> Optional[float]:
    result = session.exec(select(CashPosition.cash).where(CashPosition.bank_id == bank_id)).first()
    return result
