from collections.abc import Generator, AsyncGenerator
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

def _get_async_database_url(sync_url: str) -> str:
    if sync_url.startswith("sqlite+pysqlite://"):
        return sync_url.replace("sqlite+pysqlite://", "sqlite+aiosqlite://")
    if sync_url.startswith("sqlite://"):
        return sync_url.replace("sqlite://", "sqlite+aiosqlite://")
    if sync_url.startswith("mysql+pymysql://"):
        return sync_url.replace("mysql+pymysql://", "mysql+aiomysql://")
    if sync_url.startswith("mysql://"):
        return sync_url.replace("mysql://", "mysql+aiomysql://")
    if sync_url.startswith("postgresql+psycopg2://"):
        return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    if sync_url.startswith("postgresql://"):
        return sync_url.replace("postgresql://", "postgresql+asyncpg://")
    return sync_url

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


def _build_async_engine(database_url: str):
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
    return create_async_engine(database_url, **engine_options)


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

def _resolve_async_engine():
    try:
        return _build_async_engine(_get_async_database_url(settings.database_url))
    except Exception as exc:  # noqa: BLE001
        if os.environ.get("VERCEL"):
            return _build_async_engine("sqlite+aiosqlite:///./local.db")
        raise


engine = _resolve_engine()
async_engine = _resolve_async_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as db:
        yield db


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)
