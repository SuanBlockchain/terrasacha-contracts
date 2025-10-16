"""
Wallet Repository

Manages wallet data access operations.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.models import Wallet
from api.database.repositories.base import BaseRepository


class WalletRepository(BaseRepository[Wallet]):
    """Repository for wallet operations"""

    def __init__(self, session: AsyncSession):
        """Initialize wallet repository"""
        super().__init__(Wallet, session)

    async def get_by_name(self, name: str) -> Wallet | None:
        """
        Get wallet by name

        Args:
            name: Wallet name

        Returns:
            Wallet instance or None
        """
        statement = select(Wallet).where(Wallet.name == name)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_address(self, address: str) -> Wallet | None:
        """
        Get wallet by address (enterprise or staking)

        Args:
            address: Wallet address

        Returns:
            Wallet instance or None
        """
        statement = select(Wallet).where((Wallet.enterprise_address == address) | (Wallet.staking_address == address))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_default(self) -> Wallet | None:
        """
        Get default wallet

        Returns:
            Default wallet or None
        """
        statement = select(Wallet).where(Wallet.is_default == True)  # noqa: E712
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def set_default(self, wallet_id: int) -> bool:
        """
        Set wallet as default (unsets all others)

        Args:
            wallet_id: Wallet ID to set as default

        Returns:
            True if successful, False if wallet not found
        """
        # Get the wallet to set as default
        wallet = await self.get(wallet_id)
        if wallet is None:
            return False

        # Unset all other wallets
        statement = select(Wallet).where(Wallet.is_default == True)  # noqa: E712
        result = await self.session.execute(statement)
        current_defaults = result.scalars().all()

        for w in current_defaults:
            w.is_default = False
            self.session.add(w)

        # Set the new default
        wallet.is_default = True
        self.session.add(wallet)

        await self.session.commit()
        return True

    async def get_by_network(self, network: str) -> list[Wallet]:
        """
        Get all wallets for a specific network

        Args:
            network: Network type (testnet/mainnet)

        Returns:
            List of wallets
        """
        statement = select(Wallet).where(Wallet.network == network)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
