import os
from typing import Optional
from decimal import Decimal

from sqlalchemy import Column, Numeric
from sqlmodel import Field, SQLModel, create_engine, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bank_connector.db")

# Engine options: sqlite needs check_same_thread, Postgres can use pool_pre_ping
engine_kwargs = {"echo": False, "pool_pre_ping": True}
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine_kwargs.pop("pool_pre_ping", None)

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)


class SweepOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True, unique=True)
    # store money as Decimal with scale 2
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    currency: str
    debtor: str
    creditor: str
    status: Optional[str] = None


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


# FastAPI dependency: ensures the session is closed after each request
def get_session():
    with Session(engine) as session:
        yield session
