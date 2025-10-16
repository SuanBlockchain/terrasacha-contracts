"""
Base Repository

Provides common CRUD operations for all repositories.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel


ModelType = TypeVar("ModelType", bound=SQLModel)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations"""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        """
        Initialize repository

        Args:
            model: SQLModel class
            session: Async database session
        """
        self.model = model
        self.session = session

    async def create(self, obj: ModelType) -> ModelType:
        """
        Create a new record

        Args:
            obj: Model instance to create

        Returns:
            Created model instance
        """
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def get(self, id: int) -> ModelType | None:
        """
        Get record by ID

        Args:
            id: Record ID

        Returns:
            Model instance or None
        """
        return await self.session.get(self.model, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """
        Get all records with pagination

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances
        """
        statement = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def update(self, id: int, **kwargs: Any) -> ModelType | None:
        """
        Update record by ID

        Args:
            id: Record ID
            **kwargs: Fields to update

        Returns:
            Updated model instance or None
        """
        obj = await self.get(id)
        if obj is None:
            return None

        for key, value in kwargs.items():
            setattr(obj, key, value)

        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete(self, id: int) -> bool:
        """
        Delete record by ID

        Args:
            id: Record ID

        Returns:
            True if deleted, False if not found
        """
        obj = await self.get(id)
        if obj is None:
            return False

        await self.session.delete(obj)
        await self.session.commit()
        return True

    async def count(self) -> int:
        """
        Count total records

        Returns:
            Total count
        """
        statement = select(self.model)
        result = await self.session.execute(statement)
        return len(list(result.scalars().all()))
