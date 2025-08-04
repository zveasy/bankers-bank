# quantengine/db.py
import os
from typing import Optional, Generator

from sqlmodel import SQLModel, Field, Session, select
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url

DB_URL = os.getenv("QUANT_DB_URL", "sqlite:////data/quant.db")

url = make_url(DB_URL)
connect_args = {}
if url.get_backend_name() == "sqlite":
    # Ensure directory exists for the SQLite file (not for :memory:)
    db_path = url.database or ""
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    connect_args = {"check_same_thread": False}

engine = create_engine(DB_URL, echo=False, connect_args=connect_args)


class CashPosition(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(index=True)  # add index
    cash: float


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that closes sessions automatically."""
    with Session(engine) as session:
        yield session


def get_cash(session: Session, bank_id: str) -> Optional[float]:
    return session.exec(
        select(CashPosition.cash).where(CashPosition.bank_id == bank_id)
    ).first()
