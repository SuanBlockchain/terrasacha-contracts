"""
Transaction Repository

Manages transaction data access operations.
"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.models import Transaction, TransactionStatus
from api.database.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    """Repository for transaction operations"""

    def __init__(self, session: AsyncSession):
        """Initialize transaction repository"""
        super().__init__(Transaction, session)

    async def get_by_tx_hash(self, tx_hash: str) -> Transaction | None:
        """
        Get transaction by tx_hash

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction instance or None
        """
        statement = select(Transaction).where(Transaction.tx_hash == tx_hash)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_wallet(self, wallet_id: int, limit: int = 50) -> list[Transaction]:
        """
        Get transactions for a wallet

        Args:
            wallet_id: Wallet ID
            limit: Maximum number of transactions

        Returns:
            List of transactions (most recent first)
        """
        statement = (
            select(Transaction)
            .where(Transaction.wallet_id == wallet_id)
            .order_by(desc(Transaction.created_at))
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_by_status(self, status: TransactionStatus) -> list[Transaction]:
        """
        Get transactions by status

        Args:
            status: Transaction status

        Returns:
            List of transactions
        """
        statement = select(Transaction).where(Transaction.status == status).order_by(desc(Transaction.created_at))
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_pending(self) -> list[Transaction]:
        """
        Get all pending transactions

        Returns:
            List of pending transactions
        """
        return await self.get_by_status(TransactionStatus.PENDING)

    async def get_recent(self, limit: int = 50) -> list[Transaction]:
        """
        Get recent transactions

        Args:
            limit: Maximum number of transactions

        Returns:
            List of recent transactions
        """
        statement = select(Transaction).order_by(desc(Transaction.created_at)).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
