"""
Protocol Repository

Manages protocol data access operations.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Protocol
from src.database.repositories.base import BaseRepository


class ProtocolRepository(BaseRepository[Protocol]):
    """Repository for protocol operations"""

    def __init__(self, session: AsyncSession):
        """Initialize protocol repository"""
        super().__init__(Protocol, session)

    async def get_by_nft_policy(self, policy_id: str) -> Optional[Protocol]:
        """
        Get protocol by NFT policy ID

        Args:
            policy_id: Protocol NFT policy ID

        Returns:
            Protocol instance or None
        """
        statement = select(Protocol).where(Protocol.protocol_nft_policy_id == policy_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active(self) -> List[Protocol]:
        """
        Get all active protocols

        Returns:
            List of active protocols
        """
        statement = select(Protocol).where(Protocol.is_active == True)  # noqa: E712
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_by_wallet(self, wallet_id: int) -> List[Protocol]:
        """
        Get all protocols for a wallet

        Args:
            wallet_id: Wallet ID

        Returns:
            List of protocols
        """
        statement = select(Protocol).where(Protocol.wallet_id == wallet_id)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
