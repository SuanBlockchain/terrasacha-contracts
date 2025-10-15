"""
Contract Repository

Manages contract data access operations.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Contract, ContractType
from src.database.repositories.base import BaseRepository


class ContractRepository(BaseRepository[Contract]):
    """Repository for contract operations"""

    def __init__(self, session: AsyncSession):
        """Initialize contract repository"""
        super().__init__(Contract, session)

    async def get_by_policy_id(self, policy_id: str) -> Contract | None:
        """
        Get contract by policy ID

        Args:
            policy_id: Policy ID

        Returns:
            Contract instance or None
        """
        statement = select(Contract).where(Contract.policy_id == policy_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Contract | None:
        """
        Get contract by name

        Args:
            name: Contract name

        Returns:
            Contract instance or None
        """
        statement = select(Contract).where(Contract.name == name)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_type(self, contract_type: ContractType, network: str) -> list[Contract]:
        """
        Get all contracts of a specific type and network

        Args:
            contract_type: Contract type
            network: Network type

        Returns:
            List of contracts
        """
        statement = select(Contract).where(Contract.contract_type == contract_type, Contract.network == network)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
