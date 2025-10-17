"""
Database Connection Management

Handles async database connections, session management, and engine configuration.
All schema changes should be managed through Alembic migrations.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import create_engine


# Get the project root directory (two levels up from api/database/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


class DatabaseSettings(BaseSettings):
    """Database configuration from environment variables"""

    # PostgreSQL connection - loaded from .env file with sensible defaults
    postgres_host: str = "localhost"  # Default to localhost for local development
    postgres_port: int = 5432  # Standard PostgreSQL port
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

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

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

    def __init__(self, settings: DatabaseSettings | None = None):
        """
        Initialize database manager

        Args:
            settings: Database settings (loads from environment if not provided)
        """
        self.settings = settings or DatabaseSettings()
        self._engine: AsyncEngine | None = None
        self._sync_engine: Engine | None = None
        self._async_session_factory: async_sessionmaker[AsyncSession] | None = None

    def get_sync_engine(self) -> Engine:
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

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """
        Get async session factory

        Returns:
            SQLAlchemy async session factory
        """
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                bind=self.get_async_engine(), class_=AsyncSession, expire_on_commit=False
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
_db_manager: DatabaseManager | None = None


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
