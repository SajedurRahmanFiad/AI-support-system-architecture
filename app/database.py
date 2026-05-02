from collections.abc import Generator
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

def _build_engine(database_url: str):
    engine_options = {
        "future": True,
        "pool_pre_ping": True,
    }
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}
    else:
        engine_options["pool_size"] = settings.db_pool_size
        engine_options["max_overflow"] = settings.db_max_overflow
        engine_options["pool_recycle"] = settings.db_pool_recycle
        engine_options["pool_timeout"] = settings.db_pool_timeout
    return create_engine(database_url, **engine_options)


def _resolve_engine():
    try:
        return _build_engine(settings.database_url)
    except Exception as exc:  # noqa: BLE001
        if os.environ.get("VERCEL"):
            print(
                f"[database] failed to initialize DATABASE_URL on Vercel ({exc}); falling back to sqlite",
                file=sys.stderr,
                flush=True,
            )
            return _build_engine("sqlite+pysqlite:///./local.db")
        raise


engine = _resolve_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)
