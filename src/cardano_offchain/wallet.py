"""
Cardano Wallet Management

Pure wallet functionality without console dependencies.
Handles wallet creation, address generation, and key management.
"""

import os
from typing import Any, Dict, List, Optional

import pycardano as pc
from blockfrost import ApiError, BlockFrostApi


class CardanoWallet:
    """Manages Cardano wallet operations without console dependencies"""

    def __init__(self, wallet_mnemonic: str, network: str = "testnet"):
        """
        Initialize wallet from mnemonic

        Args:
            wallet_mnemonic: BIP39 mnemonic phrase
            network: Network type ("testnet" or "mainnet")
        """
        self.network = network
        self.cardano_network = pc.Network.TESTNET if network == "testnet" else pc.Network.MAINNET

        # Initialize wallet
        self.wallet = pc.crypto.bip32.HDWallet.from_mnemonic(wallet_mnemonic)

        # Derive main keys
        self.payment_key = self.wallet.derive_from_path("m/1852'/1815'/0'/0/0")
        self.staking_key = self.wallet.derive_from_path("m/1852'/1815'/0'/2/0")

        # Get signing keys
        self.payment_skey = pc.ExtendedSigningKey.from_hdwallet(self.payment_key)
        self.staking_skey = pc.ExtendedSigningKey.from_hdwallet(self.staking_key)

        # Create main addresses
        self.enterprise_address = pc.Address(
            payment_part=self.payment_skey.to_verification_key().hash(),
            network=self.cardano_network,
        )

        self.staking_address = pc.Address(
            payment_part=self.payment_skey.to_verification_key().hash(),
            staking_part=self.staking_skey.to_verification_key().hash(),
            network=self.cardano_network,
        )

        # Derived addresses storage
        self.addresses = []
        self.signing_keys = []

    def generate_addresses(self, count: int) -> List[Dict[str, Any]]:
        """
        Generate multiple addresses for the wallet

        Args:
            count: Number of addresses to generate

        Returns:
            List of generated address information
        """
        generated_addresses = []

        for i in range(len(self.addresses), len(self.addresses) + count):
            # Payment addresses
            payment_derivation = f"m/1852'/1815'/0'/0/{i}"
            payment_key = self.wallet.derive_from_path(payment_derivation)
            payment_skey = pc.ExtendedSigningKey.from_hdwallet(payment_key)

            # Enterprise address (payment only)
            enterprise_addr = pc.Address(
                payment_part=payment_skey.to_verification_key().hash(), network=self.cardano_network
            )

            # Staking enabled address
            staking_addr = pc.Address(
                payment_part=payment_skey.to_verification_key().hash(),
                staking_part=self.staking_skey.to_verification_key().hash(),
                network=self.cardano_network,
            )

            addr_info = {
                "index": i,
                "derivation_path": payment_derivation,
                "signing_key": payment_skey,
                "enterprise_address": enterprise_addr,
                "staking_address": staking_addr,
                "balance": 0,
            }

            self.addresses.append(addr_info)
            self.signing_keys.append(payment_skey)
            generated_addresses.append(addr_info)

        return generated_addresses

    def get_wallet_info(self) -> Dict[str, Any]:
        """
        Get comprehensive wallet information

        Returns:
            Dictionary containing wallet information
        """
        return {
            "network": self.network,
            "main_addresses": {
                "enterprise": str(self.enterprise_address),
                "staking": str(self.staking_address),
            },
            "derived_addresses": [
                {
                    "index": addr["index"],
                    "path": addr["derivation_path"],
                    "enterprise_address": str(addr["enterprise_address"]),
                    "staking_address": str(addr["staking_address"]),
                }
                for addr in self.addresses
            ],
        }

    def check_balances(self, api: BlockFrostApi, limit_addresses: int = 5) -> Dict[str, Any]:
        """
        Check balances for wallet addresses

        Args:
            api: BlockFrost API instance for balance queries
            limit_addresses: Number of derived addresses to check

        Returns:
            Dictionary containing balance information
        """
        balances = {
            "main_addresses": {
                "enterprise": {"address": str(self.enterprise_address), "balance": 0},
                "staking": {"address": str(self.staking_address), "balance": 0},
            },
            "derived_addresses": [],
            "total_balance": 0,
        }

        try:
            # Check main enterprise address
            enterprise_utxos = api.address_utxos(str(self.enterprise_address))
            enterprise_balance = sum(
                int(utxo.amount[0].quantity)
                for utxo in enterprise_utxos
                if utxo.amount[0].unit == "lovelace"
            )
            balances["main_addresses"]["enterprise"]["balance"] = enterprise_balance

            # Check derived addresses
            for addr_info in self.addresses[:limit_addresses]:
                try:
                    utxos = api.address_utxos(str(addr_info["enterprise_address"]))
                    balance = sum(
                        int(utxo.amount[0].quantity)
                        for utxo in utxos
                        if utxo.amount[0].unit == "lovelace"
                    )
                    addr_info["balance"] = balance

                    balances["derived_addresses"].append(
                        {
                            "index": addr_info["index"],
                            "address": str(addr_info["enterprise_address"]),
                            "balance": balance,
                        }
                    )

                except ApiError:
                    # Address might not exist on chain yet
                    balances["derived_addresses"].append(
                        {
                            "index": addr_info["index"],
                            "address": str(addr_info["enterprise_address"]),
                            "balance": 0,
                        }
                    )

            # Calculate total
            balances["total_balance"] = enterprise_balance + sum(
                addr["balance"] for addr in balances["derived_addresses"]
            )

        except ApiError as e:
            raise Exception(f"Error checking balances: {e}")

        return balances

    def get_payment_verification_key_hash(self) -> bytes:
        """Get the payment verification key hash"""
        return self.payment_skey.to_verification_key().hash().payload

    def get_address(self, index: int = 0, use_staking: bool = False) -> pc.Address:
        """
        Get address by index

        Args:
            index: Address index (0 = main address)
            use_staking: Whether to use staking address

        Returns:
            Cardano address
        """
        if index == 0:
            return self.staking_address if use_staking else self.enterprise_address

        if index - 1 >= len(self.addresses):
            self.generate_addresses(index - len(self.addresses))

        addr_info = self.addresses[index - 1]
        return addr_info["staking_address"] if use_staking else addr_info["enterprise_address"]

    def find_wallet_index_by_address(self, target_address: pc.Address, max_search: int = 20) -> Optional[int]:
        """
        Find the wallet index that corresponds to a given address within this wallet

        Args:
            target_address: The address to search for
            max_search: Maximum number of wallet indices to search (default: 20)

        Returns:
            Wallet index if found, None otherwise
        """
        target_primitive = target_address.to_primitive()

        # Check main addresses first (index 0)
        if self.enterprise_address.to_primitive() == target_primitive:
            return 0
        if self.staking_address.to_primitive() == target_primitive:
            return 0

        # Search through generated addresses by actually generating them and comparing
        # Use the exact same logic as generate_addresses method
        for i in range(1, max_search + 1):
            try:
                # Use the exact same derivation logic as generate_addresses
                payment_derivation = f"m/1852'/1815'/0'/0/{i}"
                payment_key = self.wallet.derive_from_path(payment_derivation)
                payment_skey = pc.ExtendedSigningKey.from_hdwallet(payment_key)

                # Create enterprise address (payment only)
                enterprise_addr = pc.Address(
                    payment_part=payment_skey.to_verification_key().hash(),
                    network=self.cardano_network
                )

                # Create staking address (payment + staking)
                staking_addr = pc.Address(
                    payment_part=payment_skey.to_verification_key().hash(),
                    staking_part=self.staking_skey.to_verification_key().hash(),
                    network=self.cardano_network,
                )

                if (enterprise_addr.to_primitive() == target_primitive or
                    staking_addr.to_primitive() == target_primitive):
                    return i

            except Exception as e:
                # Skip this index if derivation fails
                continue
        return None

    def get_signing_key(self, index: int = 0) -> pc.ExtendedSigningKey:
        """
        Get signing key by index

        Args:
            index: Address index (0 = main address)

        Returns:
            Extended signing key
        """
        if index == 0:
            return self.payment_skey

        if index - 1 >= len(self.addresses):
            self.generate_addresses(index - len(self.addresses))

        return self.addresses[index - 1]["signing_key"]


class WalletManager:
    """Manages multiple named Cardano wallets for different roles"""

    def __init__(self, network: str = "testnet"):
        """
        Initialize wallet manager

        Args:
            network: Network type ("testnet" or "mainnet")
        """
        self.network = network
        self.wallets: Dict[str, CardanoWallet] = {}
        self.default_wallet: Optional[str] = None

    def add_wallet(self, name: str, mnemonic: str, set_as_default: bool = False) -> CardanoWallet:
        """
        Add a new wallet with a given name

        Args:
            name: Wallet name/role (e.g., "administrator", "investor", "project")
            mnemonic: BIP39 mnemonic phrase
            set_as_default: Whether to set this as the default wallet

        Returns:
            Created CardanoWallet instance
        """
        wallet = CardanoWallet(mnemonic, self.network)
        self.wallets[name] = wallet

        if set_as_default or self.default_wallet is None:
            self.default_wallet = name

        return wallet

    def get_wallet(self, name: Optional[str] = None) -> Optional[CardanoWallet]:
        """
        Get wallet by name or default wallet

        Args:
            name: Wallet name, or None for default wallet

        Returns:
            CardanoWallet instance or None if not found
        """
        if name is None:
            name = self.default_wallet

        return self.wallets.get(name) if name else None

    def get_wallet_names(self) -> List[str]:
        """Get list of all wallet names"""
        return list(self.wallets.keys())

    def set_default_wallet(self, name: str) -> bool:
        """
        Set default wallet by name

        Args:
            name: Wallet name

        Returns:
            True if successful, False if wallet doesn't exist
        """
        if name in self.wallets:
            self.default_wallet = name
            return True
        return False

    def get_default_wallet_name(self) -> Optional[str]:
        """Get name of default wallet"""
        return self.default_wallet

    def remove_wallet(self, name: str) -> bool:
        """
        Remove wallet by name

        Args:
            name: Wallet name

        Returns:
            True if removed, False if not found
        """
        if name in self.wallets:
            del self.wallets[name]
            if self.default_wallet == name:
                self.default_wallet = next(iter(self.wallets.keys()), None)
            return True
        return False

    def check_all_balances(self, api: BlockFrostApi, limit_addresses: int = 5) -> Dict[str, Any]:
        """
        Check balances for all wallets

        Args:
            api: BlockFrost API instance
            limit_addresses: Number of derived addresses to check per wallet

        Returns:
            Dictionary containing balance information for all wallets
        """
        all_balances = {}
        total_across_wallets = 0

        for name, wallet in self.wallets.items():
            try:
                balances = wallet.check_balances(api, limit_addresses)
                all_balances[name] = balances
                total_across_wallets += balances["total_balance"]
            except Exception as e:
                all_balances[name] = {"error": str(e), "total_balance": 0}

        all_balances["total_across_all_wallets"] = total_across_wallets
        return all_balances

    @classmethod
    def from_environment(cls, network: str = "testnet") -> "WalletManager":
        """
        Create WalletManager from environment variables

        Supports both single wallet (wallet_mnemonic) and multiple wallets
        (wallet_mnemonic_<role>) configurations

        Args:
            network: Network type

        Returns:
            WalletManager instance with wallets loaded from environment
        """
        manager = cls(network)

        # Check for single wallet configuration (backward compatibility)
        single_mnemonic = os.getenv("wallet_mnemonic")
        if single_mnemonic:
            manager.add_wallet("default", single_mnemonic, set_as_default=True)

        # Check for multi-wallet configuration
        env_vars = os.environ
        wallet_prefixes = [key for key in env_vars.keys() if key.startswith("wallet_mnemonic_")]

        for key in wallet_prefixes:
            role = key.replace("wallet_mnemonic_", "")
            mnemonic = env_vars[key]
            if mnemonic and role:
                # Set first multi-wallet as default if no single wallet exists
                set_default = len(manager.wallets) == 0
                manager.add_wallet(role, mnemonic, set_as_default=set_default)

        return manager

    def get_wallet_info_all(self) -> Dict[str, Any]:
        """
        Get comprehensive information for all wallets

        Returns:
            Dictionary containing information for all wallets
        """
        return {
            "network": self.network,
            "default_wallet": self.default_wallet,
            "wallets": {name: wallet.get_wallet_info() for name, wallet in self.wallets.items()},
        }
