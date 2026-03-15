"""
Async SQLAlchemy database configuration with connection pooling.
"""
from typing import AsyncGenerator
import structlog
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

logger = structlog.get_logger()

_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker | None = None


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.DEBUG,
            connect_args={
                "server_settings": {"application_name": settings.APP_NAME},
                "command_timeout": 60,
            },
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory


async def init_db() -> None:
    """Initialize database and create all tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        # Import all models to register them with Base
        from app.models import order, inventory, supplier, shipment, user  # noqa
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully")


async def close_db() -> None:
    """Close database connections."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connections closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """Check database connectivity."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return False
