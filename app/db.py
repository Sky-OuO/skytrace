from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.config import get_settings


def make_engine(url: str | None = None) -> AsyncEngine:
    database_url = url or get_settings().database_url
    if database_url.startswith("sqlite"):
        engine = create_async_engine(database_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_async_engine(database_url, pool_pre_ping=True)


async def ensure_schema(engine: AsyncEngine) -> None:
    """SQLite 演示库用模型建表。PostgreSQL 走 Alembic，不在这里建表。"""
    if not str(engine.url).startswith("sqlite"):
        return
    import app.models  # noqa: F401  注册表到 metadata

    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
