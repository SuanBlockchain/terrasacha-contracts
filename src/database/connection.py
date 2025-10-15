"""
Database Connection Management

Handles async database connections, session management, and engine configuration.
All schema changes should be managed through Alembic migrations.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine


class DatabaseSettings(BaseSettings):
    """Database configuration from environment variables"""

    # PostgreSQL connection - all values loaded from .env file
    postgres_host: str = "localhost"  # Safe default, typically localhost for development
    postgres_port: int  # No default - must be set in .env
    postgres_user: str  # No default - must be set in .env
    postgres_password: str  # No default - must be set in .env
    postgres_db: str  # No default - must be set in .env

    # Connection pool settings
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600

    # SSL settings
    postgres_ssl: bool = False

    class Config:
        env_file = "src/cardano_offchain/menu/.env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env file

    @property
    def database_url(self) -> str:
        """Construct synchronous database URL"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Construct async database URL"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


class DatabaseManager:
    """
    Database connection and session management

    Provides both sync and async database connections with proper lifecycle management.
    All schema changes must be managed through Alembic migrations.
    """

    def __init__(self, settings: Optional[DatabaseSettings] = None):
        """
        Initialize database manager

        Args:
            settings: Database settings (loads from environment if not provided)
        """
        self.settings = settings or DatabaseSettings()
        self._engine: Optional[AsyncEngine] = None
        self._sync_engine = None
        self._async_session_factory: Optional[sessionmaker] = None

    def get_sync_engine(self):
        """
        Get synchronous database engine

        Returns:
            SQLAlchemy sync engine
        """
        if self._sync_engine is None:
            self._sync_engine = create_engine(
                self.settings.database_url,
                echo=False,
                pool_size=self.settings.pool_size,
                max_overflow=self.settings.max_overflow,
                pool_timeout=self.settings.pool_timeout,
                pool_recycle=self.settings.pool_recycle,
            )
        return self._sync_engine

    def get_async_engine(self) -> AsyncEngine:
        """
        Get async database engine

        Returns:
            SQLAlchemy async engine
        """
        if self._engine is None:
            self._engine = create_async_engine(
                self.settings.async_database_url,
                echo=False,
                pool_size=self.settings.pool_size,
                max_overflow=self.settings.max_overflow,
                pool_timeout=self.settings.pool_timeout,
                pool_recycle=self.settings.pool_recycle,
            )
        return self._engine

    def get_session_factory(self) -> sessionmaker:
        """
        Get async session factory

        Returns:
            SQLAlchemy async session factory
        """
        if self._async_session_factory is None:
            self._async_session_factory = sessionmaker(
                bind=self.get_async_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
        return self._async_session_factory

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get async database session with automatic cleanup

        Usage:
            async with db_manager.get_session() as session:
                # Use session here
                result = await session.execute(query)

        Yields:
            AsyncSession instance
        """
        session_factory = self.get_session_factory()
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Close database connections"""
        if self._engine:
            await self._engine.dispose()
        if self._sync_engine:
            self._sync_engine.dispose()


# ============================================================================
# Global database manager instance
# ============================================================================

# Singleton instance for application-wide use
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    Get global database manager instance

    Returns:
        DatabaseManager singleton
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to inject database sessions

    Usage in FastAPI:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Item))
            return result.scalars().all()

    Yields:
        AsyncSession instance
    """
    db_manager = get_db_manager()
    async with db_manager.get_session() as session:
        yield session
