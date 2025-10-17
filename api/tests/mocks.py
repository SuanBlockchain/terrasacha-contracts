"""
Mock Services for API Testing

Provides mock implementations of external services for isolated testing.
"""

from unittest.mock import MagicMock


class MockBlockfrostAPI:
    """Mock Blockfrost API client for testing"""

    def __init__(self, network: str = "testnet"):
        self.network = network
        self._balances = {}
        self._transactions = {}

    def address(self, address: str):
        """Mock address query"""
        mock = MagicMock()
        balance = self._balances.get(address, 2000000)  # Default 2 ADA
        mock.amount = [{"unit": "lovelace", "quantity": str(balance)}]
        return mock

    def transaction(self, tx_hash: str):
        """Mock transaction query"""
        if tx_hash not in self._transactions:
            raise Exception(f"Transaction {tx_hash} not found")

        mock = MagicMock()
        tx_data = self._transactions[tx_hash]
        mock.block_height = tx_data.get("block_height", 1000)
        mock.block_time = tx_data.get("block_time", 1640995200)
        mock.fees = tx_data.get("fees", "200000")
        return mock

    def block_latest(self):
        """Mock latest block query"""
        mock = MagicMock()
        mock.height = 10000
        return mock

    def set_address_balance(self, address: str, balance_lovelace: int):
        """Set mock balance for testing"""
        self._balances[address] = balance_lovelace

    def set_transaction(self, tx_hash: str, tx_data: dict):
        """Set mock transaction for testing"""
        self._transactions[tx_hash] = tx_data


class MockChainContext:
    """Mock Cardano chain context for testing"""

    def __init__(self, network: str = "testnet"):
        self.network = network
        self._api = MockBlockfrostAPI(network)

    def get_api(self):
        """Get mock Blockfrost API"""
        return self._api

    def get_explorer_url(self, tx_hash: str) -> str:
        """Get mock explorer URL"""
        if self.network == "mainnet":
            return f"https://cardanoscan.io/transaction/{tx_hash}"
        return f"https://preprod.cardanoscan.io/transaction/{tx_hash}"


class MockWalletManager:
    """Mock wallet manager for testing"""

    def __init__(self, network: str = "testnet"):
        self.network = network
        self._wallets = {
            "default": MockWallet("default", network),
            "test": MockWallet("test", network),
        }

    def get_wallet_names(self) -> list[str]:
        """Get list of wallet names"""
        return list(self._wallets.keys())

    def get_default_wallet_name(self) -> str:
        """Get default wallet name"""
        return "default"

    def get_wallet(self, name: str):
        """Get wallet by name"""
        return self._wallets.get(name)

    def add_wallet(self, name: str):
        """Add a mock wallet for testing"""
        self._wallets[name] = MockWallet(name, self.network)


class MockWallet:
    """Mock wallet for testing"""

    def __init__(self, name: str, network: str = "testnet"):
        self.name = name
        self.network = network

    def get_address(self, index: int = 0):
        """Get mock address"""
        mock = MagicMock()
        if self.network == "mainnet":
            mock.__str__ = lambda: f"addr1_mock_{self.name}_{index}"
        else:
            mock.__str__ = lambda: f"addr_test1_mock_{self.name}_{index}"
        return mock

    def get_staking_address(self):
        """Get mock staking address"""
        mock = MagicMock()
        if self.network == "mainnet":
            mock.__str__ = lambda: f"stake1_mock_{self.name}"
        else:
            mock.__str__ = lambda: f"stake_test1_mock_{self.name}"
        return mock


class MockCardanoTransactions:
    """Mock transaction builder for testing"""

    def __init__(self, wallet_manager: MockWalletManager, chain_context: MockChainContext):
        self.wallet_manager = wallet_manager
        self.chain_context = chain_context
        self._submitted_txs = []

    def create_simple_transaction(
        self,
        to_address: str,
        amount_ada: float,
        from_address_index: int = 0,
        wallet_name: str = "default",
    ):
        """Mock transaction creation"""
        wallet = self.wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise ValueError(f"Wallet {wallet_name} not found")

        # Check balance
        from_address = str(wallet.get_address(from_address_index))
        api = self.chain_context.get_api()
        balance_data = api.address(from_address)
        balance = int(balance_data.amount[0]["quantity"])

        amount_lovelace = int(amount_ada * 1_000_000)
        fee = 200000  # Mock fee

        if balance < (amount_lovelace + fee):
            raise ValueError(f"Insufficient balance. Need {amount_lovelace + fee}, have {balance}")

        # Create mock signed transaction
        mock_tx = MagicMock()
        mock_tx.transaction_body.fee = fee
        return mock_tx

    def submit_transaction(self, signed_tx) -> str:
        """Mock transaction submission"""
        tx_hash = f"mock_tx_{'0' * 56}{len(self._submitted_txs):08x}"
        self._submitted_txs.append(tx_hash)

        # Register transaction in mock chain
        self.chain_context.get_api().set_transaction(
            tx_hash,
            {"block_height": 10000, "block_time": 1640995200, "fees": "200000"},
        )

        return tx_hash

    def get_transaction_info(self, tx_hash: str) -> dict:
        """Mock transaction info"""
        return {
            "tx_hash": tx_hash,
            "explorer_url": self.chain_context.get_explorer_url(tx_hash),
        }
