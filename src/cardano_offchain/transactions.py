"""
Cardano Transaction Operations

Pure transaction functionality without console dependencies.
Handles transaction building, signing, and submission.
"""

from typing import List, Optional, Union

import pycardano as pc
from blockfrost import ApiError

from .chain_context import CardanoChainContext
from .wallet import CardanoWallet, WalletManager


class CardanoTransactions:
    """Manages Cardano transaction operations with multi-wallet support"""

    def __init__(
        self, wallet_source: Union[CardanoWallet, WalletManager], chain_context: CardanoChainContext
    ):
        """
        Initialize transaction manager

        Args:
            wallet_source: CardanoWallet instance or WalletManager instance
            chain_context: CardanoChainContext instance
        """
        if isinstance(wallet_source, CardanoWallet):
            # Backward compatibility: create single-wallet manager
            self.wallet_manager = WalletManager(wallet_source.network)
            self.wallet_manager.add_wallet("default", "", set_as_default=True)
            self.wallet_manager.wallets["default"] = wallet_source
            self.wallet = wallet_source
        elif isinstance(wallet_source, WalletManager):
            self.wallet_manager = wallet_source
            self.wallet = wallet_source.get_wallet()  # Get default wallet
        else:
            raise ValueError("wallet_source must be CardanoWallet or WalletManager")

        self.chain_context = chain_context
        self.context = chain_context.get_context()
        self.api = chain_context.get_api()

    def get_wallet(self, wallet_name: Optional[str] = None) -> Optional[CardanoWallet]:
        """
        Get wallet by name or default wallet

        Args:
            wallet_name: Name of wallet to get, None for default

        Returns:
            CardanoWallet instance or None if not found
        """
        return self.wallet_manager.get_wallet(wallet_name)

    def set_active_wallet(self, wallet_name: str) -> bool:
        """
        Set the active wallet for subsequent operations

        Args:
            wallet_name: Name of wallet to set as active

        Returns:
            True if successful, False if wallet not found
        """
        wallet = self.wallet_manager.get_wallet(wallet_name)
        if wallet:
            self.wallet = wallet
            self.wallet_manager.set_default_wallet(wallet_name)
            return True
        return False

    def get_available_wallets(self) -> List[str]:
        """Get list of available wallet names"""
        return self.wallet_manager.get_wallet_names()

    def get_active_wallet_name(self) -> Optional[str]:
        """Get name of currently active wallet"""
        return self.wallet_manager.get_default_wallet_name()

    def check_all_wallet_balances(self, limit_addresses: int = 5) -> dict:
        """
        Check balances for all managed wallets

        Args:
            limit_addresses: Number of derived addresses to check per wallet

        Returns:
            Dictionary containing balance information for all wallets
        """
        return self.wallet_manager.check_all_balances(self.api, limit_addresses)

    def create_simple_transaction(
        self,
        to_address: str,
        amount_ada: float,
        from_address_index: int = 0,
        wallet_name: Optional[str] = None,
    ) -> Optional[pc.Transaction]:
        """
        Create a simple ADA transfer transaction

        Args:
            to_address: Recipient address string
            amount_ada: Amount in ADA to send
            from_address_index: Source address index (0 = main address)
            wallet_name: Name of wallet to use (None for active wallet)

        Returns:
            Signed transaction or None if failed

        Raises:
            Exception: If transaction creation fails
        """
        try:
            # Get the wallet to use
            wallet = self.wallet_manager.get_wallet(wallet_name) if wallet_name else self.wallet
            if not wallet:
                raise Exception(f"Wallet not found: {wallet_name}")

            # Convert ADA to lovelace
            amount_lovelace = int(amount_ada * 1_000_000)

            # Get addresses and keys
            from_address = wallet.get_address(from_address_index)
            to_address_obj = pc.Address.from_primitive(to_address)
            signing_key = wallet.get_signing_key(from_address_index)

            # Check UTXOs
            utxos = self.api.address_utxos(str(from_address))
            if not utxos:
                raise Exception("No UTXOs available for transaction")

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            # Add inputs and outputs
            builder.add_input_address(from_address)
            builder.add_output(pc.TransactionOutput(to_address_obj, pc.Value(amount_lovelace)))

            # Build and sign transaction
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

            return signed_tx

        except Exception as e:
            raise Exception(f"Error creating transaction: {e}")

    def submit_transaction(self, signed_tx: pc.Transaction) -> Optional[str]:
        """
        Submit a signed transaction to the network

        Args:
            signed_tx: Signed transaction to submit

        Returns:
            Transaction ID if successful, None if failed

        Raises:
            Exception: If transaction submission fails
        """
        try:
            self.context.submit_tx(signed_tx)

            if not signed_tx.id:
                raise Exception("Transaction submission failed - no transaction ID")

            return signed_tx.id.payload.hex()

        except ApiError as e:
            raise Exception(f"Error submitting transaction: {e}")

    def get_transaction_info(self, tx_id: str) -> dict:
        """
        Get transaction information and explorer URL

        Args:
            tx_id: Transaction ID

        Returns:
            Dictionary with transaction info and explorer URL
        """
        return {
            "tx_id": tx_id,
            "explorer_url": self.chain_context.get_explorer_url(tx_id),
            "network": self.chain_context.network,
        }
    
    def sorted_utxos(self, txs: List[pc.UTxO]):
        return sorted(
            txs,
            key=lambda u: (u.input.transaction_id.payload, u.input.index),
        )

    def find_utxo_by_policy_id(self, utxos: List[pc.UTxO], policy_id: pc.ScriptHash) -> pc.UTxO:
        """Find UTXOs that contain tokens from a specific policy ID.

        Args:
            utxos: List of UTXOs to search through
            policy_id: The minting policy ID to match against

        Returns:
            List of UTXOs containing tokens from the specified policy (typically one item)
        """

        for utxo in utxos:
            # Check if the UTXO contains any tokens from the specified policy
            if utxo.output.amount.multi_asset:
                for pi, assets in utxo.output.amount.multi_asset.data.items():
                    if pi == policy_id:
                        utxo_to_spend = utxo
                        break  # Found a match, no need to check other policies in this UTXO

        return utxo_to_spend

    def extract_asset_from_utxo(self, utxo: pc.UTxO, policy_id: pc.ScriptHash) -> pc.Asset:
        """Extract the Asset from a UTXO for a specific policy ID.

        Assumes the UTXO contains exactly one token with quantity 1 for the given policy ID.

        Args:
            utxo: The UTXO to extract the asset from
            policy_id: The minting policy ID to match against

        Returns:
            The Asset object containing the asset name and quantity

        Raises:
            ValueError: If no token is found or multiple tokens are found
        """
        if not utxo.output.amount.multi_asset:
            raise ValueError("UTXO contains no multi-asset tokens")

        for pi, assets in utxo.output.amount.multi_asset.data.items():
            if pi == policy_id:
                # Should contain exactly one token with quantity 1
                asset_items = list(assets.data.items())
                if len(asset_items) != 1:
                    raise ValueError(f"Expected exactly 1 token, found {len(asset_items)}")

                asset_name, quantity = asset_items[0]
                if quantity != 1:
                    raise ValueError(f"Expected token quantity 1, found {quantity}")

                return pc.Asset({asset_name: quantity})

        raise ValueError(f"No token found for policy ID {policy_id.payload.hex()}")

    def build_contract_transaction(self, builder_config: dict) -> pc.TransactionBuilder:
        """
        Create a transaction builder for contract operations

        Args:
            builder_config: Configuration dictionary for the builder

        Returns:
            Configured transaction builder
        """
        builder = pc.TransactionBuilder(self.context)

        # Configure builder based on config
        if "inputs" in builder_config:
            for input_config in builder_config["inputs"]:
                if input_config["type"] == "address":
                    builder.add_input_address(input_config["address"])
                elif input_config["type"] == "utxo":
                    builder.add_input(input_config["utxo"])
                elif input_config["type"] == "script_input":
                    builder.add_script_input(
                        input_config["utxo"],
                        script=input_config["script"],
                        redeemer=input_config["redeemer"],
                    )

        if "outputs" in builder_config:
            for output in builder_config["outputs"]:
                builder.add_output(output)

        if "mint" in builder_config:
            builder.mint = builder_config["mint"]

        if "minting_scripts" in builder_config:
            for script_config in builder_config["minting_scripts"]:
                builder.add_minting_script(
                    script=script_config["script"], redeemer=script_config["redeemer"]
                )

        if "required_signers" in builder_config:
            builder.required_signers = builder_config["required_signers"]

        return builder

    def sign_and_submit_transaction(
        self,
        builder: pc.TransactionBuilder,
        signing_keys: List[pc.ExtendedSigningKey],
        change_address: pc.Address,
    ) -> dict:
        """
        Sign and submit a transaction from builder

        Args:
            builder: Transaction builder
            signing_keys: List of signing keys
            change_address: Address for change output

        Returns:
            Transaction result dictionary
        """
        try:
            # Build and sign
            signed_tx = builder.build_and_sign(signing_keys, change_address=change_address)

            # Submit
            tx_id = self.submit_transaction(signed_tx)

            return {
                "success": True,
                "tx_id": tx_id,
                "transaction": signed_tx,
                "explorer_url": self.chain_context.get_explorer_url(tx_id),
            }

        except Exception as e:
            return {"success": False, "error": str(e), "transaction": None}
