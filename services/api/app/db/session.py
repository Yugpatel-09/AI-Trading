from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from services.api.app.core.config import settings


class Base(AsyncAttrs, DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2 models."""
    pass


def get_engine(db_url: str = None):
    url = db_url or settings.DATABASE_URL
    # For SQLite, ensure timeout and connect_args are handled appropriately
    connect_args = {}
    if "sqlite" in url:
        connect_args = {"check_same_thread": False}
    return create_async_engine(
        url,
        echo=settings.DEBUG,
        connect_args=connect_args,
        future=True,
    )


engine = get_engine()
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding an isolated database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(engine_override=None, drop_all: bool = False):
    """Initialize database tables."""
    eng = engine_override or engine
    async with eng.begin() as conn:
        if drop_all:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
