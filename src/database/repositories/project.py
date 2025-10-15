"""
Project Repository

Manages project data access operations.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Project, ProjectState
from src.database.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for project operations"""

    def __init__(self, session: AsyncSession):
        """Initialize project repository"""
        super().__init__(Project, session)

    async def get_by_name(self, name: str) -> Project | None:
        """
        Get project by name

        Args:
            name: Project name

        Returns:
            Project instance or None
        """
        statement = select(Project).where(Project.name == name)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_project_id(self, project_id: str) -> Project | None:
        """
        Get project by on-chain project ID

        Args:
            project_id: On-chain project ID hash

        Returns:
            Project instance or None
        """
        statement = select(Project).where(Project.project_id == project_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_protocol(self, protocol_id: int) -> list[Project]:
        """
        Get all projects for a protocol

        Args:
            protocol_id: Protocol ID

        Returns:
            List of projects
        """
        statement = select(Project).where(Project.protocol_id == protocol_id)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_by_state(self, state: ProjectState) -> list[Project]:
        """
        Get all projects in a specific state

        Args:
            state: Project state

        Returns:
            List of projects
        """
        statement = select(Project).where(Project.project_state == state)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_active(self) -> list[Project]:
        """
        Get all active projects

        Returns:
            List of active projects
        """
        statement = select(Project).where(Project.is_active == True)  # noqa: E712
        result = await self.session.execute(statement)
        return list(result.scalars().all())
