from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from fireguard.config import settings

engine = create_engine(settings.database_url, echo=False)


def get_session() -> Session:
    return Session(engine)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
