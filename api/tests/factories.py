"""
Test Data Factories

Provides factory functions to generate test data for API testing.
"""

import random
from datetime import datetime, timezone


class CardanoAddressFactory:
    """Factory for generating valid-looking Cardano addresses"""

    @staticmethod
    def create_testnet_address(prefix: str = "addr_test1") -> str:
        """Generate a testnet address"""
        # Generate realistic-looking address
        chars = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        suffix = "".join(random.choice(chars) for _ in range(50))
        return f"{prefix}{suffix}"

    @staticmethod
    def create_mainnet_address() -> str:
        """Generate a mainnet address"""
        chars = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        suffix = "".join(random.choice(chars) for _ in range(50))
        return f"addr1{suffix}"

    @staticmethod
    def create_stake_address(network: str = "testnet") -> str:
        """Generate a stake address"""
        chars = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        suffix = "".join(random.choice(chars) for _ in range(50))
        if network == "mainnet":
            return f"stake1{suffix}"
        return f"stake_test1{suffix}"


class TransactionFactory:
    """Factory for generating transaction test data"""

    @staticmethod
    def create_tx_hash() -> str:
        """Generate a valid transaction hash"""
        return "".join(random.choice("0123456789abcdef") for _ in range(64))

    @staticmethod
    def create_policy_id() -> str:
        """Generate a valid policy ID"""
        return "".join(random.choice("0123456789abcdef") for _ in range(56))

    @staticmethod
    def create_transaction_data(
        tx_hash: str | None = None,
        status: str = "confirmed",
        from_address: str | None = None,
        to_address: str | None = None,
        amount_lovelace: int = 2000000,
        fee_lovelace: int = 200000,
    ) -> dict:
        """Create complete transaction test data"""
        if tx_hash is None:
            tx_hash = TransactionFactory.create_tx_hash()
        if from_address is None:
            from_address = CardanoAddressFactory.create_testnet_address()
        if to_address is None:
            to_address = CardanoAddressFactory.create_testnet_address()

        return {
            "tx_hash": tx_hash,
            "status": status,
            "operation": "send_ada",
            "from_address": from_address,
            "to_address": to_address,
            "amount_lovelace": amount_lovelace,
            "amount_ada": amount_lovelace / 1_000_000,
            "fee_lovelace": fee_lovelace,
            "fee_ada": fee_lovelace / 1_000_000,
            "submitted_at": datetime.now(timezone.utc),
            "confirmed_at": datetime.now(timezone.utc) if status == "confirmed" else None,
            "block_height": 10000 if status == "confirmed" else None,
            "confirmations": 5 if status == "confirmed" else 0,
        }


class WalletFactory:
    """Factory for generating wallet test data"""

    @staticmethod
    def create_wallet_data(
        name: str = "test_wallet",
        network: str = "testnet",
        is_default: bool = False,
    ) -> dict:
        """Create wallet test data"""
        enterprise_addr = CardanoAddressFactory.create_testnet_address()
        staking_addr = CardanoAddressFactory.create_stake_address(network)

        return {
            "name": name,
            "network": network,
            "is_default": is_default,
            "enterprise_address": enterprise_addr,
            "staking_address": staking_addr,
            "main_addresses": {
                "enterprise": enterprise_addr,
                "staking": staking_addr,
            },
            "derived_addresses": [],
        }

    @staticmethod
    def create_balance_data(
        address: str | None = None,
        balance_lovelace: int = 10000000,
        assets: list | None = None,
    ) -> dict:
        """Create balance test data"""
        if address is None:
            address = CardanoAddressFactory.create_testnet_address()
        if assets is None:
            assets = []

        return {
            "address": address,
            "balance_lovelace": balance_lovelace,
            "balance_ada": balance_lovelace / 1_000_000,
            "assets": assets,
        }


class DatabaseFactory:
    """Factory for creating database test records"""

    @staticmethod
    async def create_transaction(
        session,
        tx_hash: str | None = None,
        status: str = "submitted",
        operation: str = "send_ada",
        **kwargs,
    ):
        """Create a transaction record in the database"""
        from api.database.models import Transaction
        from api.enums import TransactionStatus

        if tx_hash is None:
            tx_hash = TransactionFactory.create_tx_hash()

        transaction = Transaction(
            tx_hash=tx_hash,
            status=TransactionStatus(status),
            operation=operation,
            description=kwargs.get("description", f"Test transaction {tx_hash[:8]}"),
            fee_lovelace=kwargs.get("fee_lovelace", 200000),
            total_output_lovelace=kwargs.get("total_output_lovelace", 2000000),
            outputs=kwargs.get("outputs", []),
            inputs=kwargs.get("inputs", []),
            submitted_at=kwargs.get("submitted_at", datetime.now(timezone.utc).replace(tzinfo=None)),
        )

        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

        return transaction

    @staticmethod
    async def create_wallet(
        session,
        name: str = "test_wallet",
        network: str = "testnet",
        **kwargs,
    ):
        """Create a wallet record in the database"""
        from api.database.models import Wallet
        from api.enums import NetworkType

        wallet = Wallet(
            name=name,
            network=NetworkType(network),
            enterprise_address=kwargs.get(
                "enterprise_address",
                CardanoAddressFactory.create_testnet_address(),
            ),
            staking_address=kwargs.get(
                "staking_address",
                CardanoAddressFactory.create_stake_address(network),
            ),
        )

        session.add(wallet)
        await session.commit()
        await session.refresh(wallet)

        return wallet
