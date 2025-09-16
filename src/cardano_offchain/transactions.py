"""
Cardano Transaction Operations

Pure transaction functionality without console dependencies.
Handles transaction building, signing, and submission.
"""

from typing import Any, Dict, List, Optional, Union

import pycardano as pc
from blockfrost import ApiError

from .chain_context import CardanoChainContext
from .wallet import CardanoWallet, WalletManager


class TransactionBuilderHelper:
    """Helper class for building transactions with both local and reference scripts"""
    
    def __init__(self, context: pc.ChainContext, contract_manager):
        self.context = context
        self.contract_manager = contract_manager
    
    def add_script_to_transaction(self, builder: pc.TransactionBuilder, contract_name: str, redeemer: pc.Redeemer = None) -> bool:
        """
        Add a script to a transaction, handling both local and reference scripts
        
        Args:
            builder: Transaction builder
            contract_name: Name of the contract to add
            redeemer: Optional redeemer for spending scripts
            
        Returns:
            True if script was added successfully, False otherwise
        """
        script_info = self.contract_manager.get_contract_script_info(contract_name)
        if not script_info:
            return False
            
        if script_info["type"] == "reference_script":
            # For reference scripts, add as reference input
            ref_utxo_info = script_info["reference_utxo"]
            ref_tx_id = pc.TransactionId(bytes.fromhex(ref_utxo_info["tx_id"]))
            ref_input = pc.TransactionInput(ref_tx_id, ref_utxo_info["output_index"])
            builder.reference_inputs.add(ref_input)
            return True
        else:
            # For local scripts, the script will be included directly when needed
            return True
    
    def get_script_for_minting(self, contract_name: str) -> Optional[pc.NativeScript]:
        """
        Get script for minting operations
        
        Args:
            contract_name: Name of the minting policy contract
            
        Returns:
            Script object or None if not available or is reference script
        """
        script_info = self.contract_manager.get_contract_script_info(contract_name)
        if not script_info or script_info["type"] == "reference_script":
            return None
        return script_info["cbor"]
    
    def get_script_for_spending(self, contract_name: str) -> Optional[pc.NativeScript]:
        """
        Get script for spending operations
        
        Args:
            contract_name: Name of the spending validator contract
            
        Returns:
            Script object or None if not available or is reference script
        """
        script_info = self.contract_manager.get_contract_script_info(contract_name)
        if not script_info or script_info["type"] == "reference_script":
            return None
        return script_info["cbor"]


class CardanoTransactions:
    """Manages Cardano transaction operations with multi-wallet support"""

    def __init__(
        self, wallet_source: Union[CardanoWallet, WalletManager], chain_context: CardanoChainContext, contract_manager=None
    ):
        """
        Initialize transaction manager

        Args:
            wallet_source: CardanoWallet instance or WalletManager instance
            chain_context: CardanoChainContext instance
            contract_manager: Optional ContractManager for reference script support
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
        
        # Initialize transaction builder helper for reference script support
        self.contract_manager = contract_manager
        if contract_manager:
            self.builder_helper = TransactionBuilderHelper(self.context, contract_manager)
        else:
            self.builder_helper = None

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

            # project_contract = self.contract_manager.get_project_contract("project")
            # Check UTXOs
            utxos = self.context.utxos(from_address)
            # reference_script_utxo = None
            # for utxo in utxos:
            #     if utxo.output.script and utxo.output.script == project_contract.cbor:
            #         reference_script_utxo = utxo
            #         break

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            for u in utxos:
                builder.add_input(u)


            builder.fee = 5000000
            # Add inputs and outputs
            # builder.add_input_address(from_address)
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


    def create_reference_script(self, project_name: Optional[str] = None, 
                              source_address: Optional[pc.Address] = None,
                              destination_address: Optional[pc.Address] = None,
                              source_wallet: Optional[CardanoWallet] = None) -> Dict[str, Any]:
        """
        Create a reference script for the specified project
        
        Args:
            project_name: Optional specific project contract name to use
            source_address: Address to fund the transaction (defaults to wallet address)
            destination_address: Address to send the reference script UTXO (defaults to source_address)
            source_wallet: Wallet instance to use for signing (required if source_address differs from default)
            
        Returns:
            Reference script creation result dictionary
        """
        try:
            # Get project contract
            project_contract = self.contract_manager.get_project_contract(project_name)
            if not project_contract:
                return {"success": False, "error": f"Project contract '{project_name}' not compiled"}
            
            # Handle reference script contracts
            if hasattr(project_contract, 'storage_type') and project_contract.storage_type == 'reference_script':
                return {"success": False, "error": "Contract is already stored as a reference script"}
            
            # Use provided addresses or defaults
            if source_address is None:
                source_address = self.wallet.get_address(0)
            if destination_address is None:
                destination_address = source_address
                
            # Use provided wallet or default wallet for signing
            signing_wallet = source_wallet if source_wallet else self.wallet
            signing_key = signing_wallet.get_signing_key(0)
            
            print(f"Using source address: {str(source_address)}")
            print(f"Using signing wallet: {signing_wallet.get_payment_verification_key_hash().hex()}")
            # Find suitable UTXO from source address
            source_utxos = self.context.utxos(source_address)
            suitable_utxo = None
            for utxo in source_utxos:
                if utxo.output.amount.coin > 5000000:  # Need >5 ADA for reference script
                    suitable_utxo = utxo
                    break

            if not suitable_utxo:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for reference script creation (need >5 ADA)",
                }
                
            # Calculate minimum lovelace for reference script output
            min_val_ref_script = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    destination_address,
                    pc.Value(0),
                    datum=None,
                    script=project_contract.cbor,
                ),
            )
            
            # Build transaction
            builder = pc.TransactionBuilder(self.context)
            builder.add_input_address(source_address)
            
            # Add reference script output
            ref_script_output = pc.TransactionOutput(
                destination_address, 
                min_val_ref_script, 
                script=project_contract.cbor
            )
            builder.add_output(ref_script_output)

            # Build and sign transaction
            signed_tx = builder.build_and_sign([signing_key], change_address=source_address)
            tx_id = signed_tx.id.payload.hex()
            
            # Find the output index of the reference script
            ref_output_index = None
            for i, output in enumerate(signed_tx.transaction_body.outputs):
                if output.script is not None:
                    ref_output_index = i
                    break
                    
            if ref_output_index is None:
                return {"success": False, "error": "Reference script output not found in transaction"}
            
            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": tx_id,
                "reference_utxo": {
                    "tx_id": tx_id,
                    "output_index": ref_output_index,
                    "address": str(destination_address)
                },
                "explorer_url": self.chain_context.get_explorer_url(tx_id),
            }

        except Exception as e:
            return {"success": False, "error": f"Reference script creation failed: {e}"}
        
    def create_project_nfts_reference_script(self, project_name: Optional[str] = None,
                                           source_address: Optional[pc.Address] = None,
                                           destination_address: Optional[pc.Address] = None,
                                           source_wallet: Optional[CardanoWallet] = None) -> Dict[str, Any]:
        """
        Create a reference script for the project NFTs minting policy
        
        Args:
            project_name: Optional specific project contract name to use  
            source_address: Address to fund the transaction (defaults to wallet address)
            destination_address: Address to send the reference script UTXO (defaults to source_address)
            source_wallet: Wallet instance to use for signing (required if source_address differs from default)
            
        Returns:
            Reference script creation result dictionary
        """
        try:
            # Get project NFTs contract
            project_nfts_contract = self.contract_manager.get_project_nfts_contract(project_name)
            if not project_nfts_contract:
                return {"success": False, "error": f"Project NFTs contract for '{project_name}' not compiled"}
                
            # Handle reference script contracts
            if hasattr(project_nfts_contract, 'storage_type') and project_nfts_contract.storage_type == 'reference_script':
                return {"success": False, "error": "Project NFTs contract is already stored as a reference script"}
            
            # Use provided addresses or defaults
            if source_address is None:
                source_address = self.wallet.get_address(0)
            if destination_address is None:
                destination_address = source_address
                
            # Use provided wallet or default wallet for signing
            signing_wallet = source_wallet if source_wallet else self.wallet
            signing_key = signing_wallet.get_signing_key(0)

            # Find suitable UTXO from source address
            source_utxos = self.context.utxos(source_address)
            suitable_utxo = None
            for utxo in source_utxos:
                if utxo.output.amount.coin > 5000000:  # Need >5 ADA for reference script
                    suitable_utxo = utxo
                    break

            if not suitable_utxo:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for reference script creation (need >5 ADA)",
                }
                
            # Calculate minimum lovelace for reference script output
            min_val_ref_script = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    destination_address,
                    pc.Value(0),
                    datum=None,
                    script=project_nfts_contract.cbor,
                ),
            )
            
            # Build transaction
            builder = pc.TransactionBuilder(self.context)
            builder.add_input_address(source_address)
            
            # Add reference script output
            ref_script_output = pc.TransactionOutput(
                destination_address, 
                min_val_ref_script, 
                script=project_nfts_contract.cbor
            )
            builder.add_output(ref_script_output)

            # Build and sign transaction
            signed_tx = builder.build_and_sign([signing_key], change_address=source_address)
            tx_id = signed_tx.id.payload.hex()
            
            # Find the output index of the reference script
            ref_output_index = None
            for i, output in enumerate(signed_tx.transaction_body.outputs):
                if output.script is not None:
                    ref_output_index = i
                    break
                    
            if ref_output_index is None:
                return {"success": False, "error": "Reference script output not found in transaction"}
            
            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": tx_id,
                "reference_utxo": {
                    "tx_id": tx_id,
                    "output_index": ref_output_index,
                    "address": str(destination_address)
                },
                "explorer_url": self.chain_context.get_explorer_url(tx_id),
            }

        except Exception as e:
            return {"success": False, "error": f"Project NFTs reference script creation failed: {e}"}