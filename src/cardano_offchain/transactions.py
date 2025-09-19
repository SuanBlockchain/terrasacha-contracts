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

            # Check UTXOs
            utxos = self.context.utxos(from_address)

            # for utxo in utxos:
            #     if utxo.output.script == pc.PlutusV2Script(bytes.fromhex("590c410100003323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232222323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323374a90001bb1498c8c8c8ccccccccccccd40100140180300280240200cc04c01c054400c4008400411411411448888888888888c8c8c8c8c8c8c8c8c8c8c94ccd5cd1918440088009918358800a8068a999ab9a3230880110013232333501501110021001500f500c153335734646110022002660ec6460ec2002a00490020991919192999ab9a32308c0110013307a323233306c50081002100148001400d2002153335734646118022002660f464646660d8a0102004200290002800a40042666600a08a006076002264c66ae7124011e4d757374206d696e742065786163746c792031207573657220746f6b656e004984c98cd5ce2481224d757374206d696e742065786163746c7920312070726f746f636f6c20746f6b656e004984004c8c8cccccccd40500a40a005809809c04c40084005406140404004c8c8cccccccd404809c09805009009404440084005405d40384c98cd5ce24811a4d757374206d696e742065786163746c79203220746f6b656e73004984c98cd5ce2481115554784f206e6f7420636f6e73756d6564004984c94ccd5cd191844808800991841008800a8070a999ab9a3230890110013307732307710015003480104c8c8cccc004004c18940241100e888894ccd55cf801899980280100100089919192999ab9a3230910110013307f5001480004cccc01c01cd5d1003001800899319ab9c4912a43616e6e6f742073656e6420746f6b656e7320746f206f757470757473207768656e206275726e696e67004984004c8d40644004cc1bcc8c8ccc1c0c1a9400c40084004cd5d019bb0375291100375090001bb2499403c52613574200644466008004002264c66ae71241314d757374206275726e2065786163746c79203220746f6b656e73202870726f746f636f6c202b20757365722070616972290049854ccd5cd191844808800a501330010420381326335738920115496e76616c69642072656465656d657220747970650049888cccc00c0081000040d48889261001323233306650031002100133574066ec0dd4a44100375090001bb249940144004c16140044004c19540144004c18940044004c8ccd40280700144005400441a441a4488888888c8c8c8c8c8c8c8c8c94ccd5cd19183f08009983699183d8800a801240802646464666a020200620042002a00890202400026002293128010800991919a80808010800a80128038800991a8050800a8008800991919a80608010800a801182d182da8020800991919a80488010800a4500305150021222323232323330010013054500303422253335573e00426600800200226464a666ae68c8c1dc4004cc19cc16d40094024528898008a4c466600a00a6ae880100084d5d08011125010013053500212223232533357346460e020026460a62002a0022a002264c9308009825a8008800a44105555345525f0010014881045245465f00123726a0022444666e31400d40094004488cdc5a801280089119b8a500250011065100123233305900170090002800899319ab9c4901104e616d654572726f723a207e626f6f6c004984c98cd5ce24810c4e616d654572726f723a207a004984c98cd5ce24810c4e616d654572726f723a2079004984c98cd5ce24810c4e616d654572726f723a2079004984c98cd5ce24810c4e616d654572726f723a2079004984c98cd5ce24810c4e616d654572726f723a2078004984c98cd5ce24810c4e616d654572726f723a2078004984c98cd5ce24810c4e616d654572726f723a2078004984c98cd5ce24810c4e616d654572726f723a2078004984c98cd5ce2481144e616d654572726f723a2076616c696461746f72004984c98cd5ce24811a4e616d654572726f723a20757365725f746f6b656e5f6e616d65004984c98cd5ce24811c4e616d654572726f723a20756e697175655f746f6b656e5f6e616d65004984c98cd5ce2481124e616d654572726f723a2074785f696e666f004984c98cd5ce2481124e616d654572726f723a2074785f696e666f004984c98cd5ce2481174e616d654572726f723a20746f6b656e5f616d6f756e74004984c98cd5ce24810e4e616d654572726f723a2073756d004984c98cd5ce24811c4e616d654572726f723a20736c6963655f627974655f737472696e67004984c98cd5ce2481134e616d654572726f723a20736861335f323536004984c98cd5ce2481134e616d654572726f723a2072656465656d6572004984c98cd5ce2481124e616d654572726f723a20707572706f7365004984c98cd5ce2481124e616d654572726f723a20707572706f7365004984c98cd5ce24811e4e616d654572726f723a2070726f746f636f6c5f746f6b656e5f6e616d65004984c98cd5ce2481114e616d654572726f723a20707265666978004984c98cd5ce2481184e616d654572726f723a206f776e5f706f6c6963795f6964004984c98cd5ce2481114e616d654572726f723a206f7574707574004984c98cd5ce2481154e616d654572726f723a206f75725f6d696e746564004984c98cd5ce24810f4e616d654572726f723a206f726566004984c98cd5ce24810f4e616d654572726f723a206f726566004984c98cd5ce24810f4e616d654572726f723a206f726566004984c98cd5ce2481154e616d654572726f723a206d696e745f76616c7565004984c98cd5ce24810e4e616d654572726f723a206c656e004984c98cd5ce2481154e616d654572726f723a206973696e7374616e6365004984c98cd5ce2481154e616d654572726f723a20696e7075745f7574786f004984c98cd5ce2481164e616d654572726f723a20696e6465785f6279746573004984c98cd5ce2481134e616d654572726f723a206861735f7574786f004984c98cd5ce24811e4e616d654572726f723a206765745f6d696e74696e675f707572706f7365004984c98cd5ce2481154e616d654572726f723a2066756c6c5f746f6b656e004984c98cd5ce2481124e616d654572726f723a20636f6e74657874004984c98cd5ce2481124e616d654572726f723a20636f6e74657874004984c98cd5ce2481124e616d654572726f723a20636f6e74657874004984c98cd5ce24811b4e616d654572726f723a20636f6e735f627974655f737472696e67004984c98cd5ce2481184e616d654572726f723a20636f6d62696e65645f68617368004984c98cd5ce2481184e616d654572726f723a20636f6d62696e65645f64617461004984c98cd5ce24811d4e616d654572726f723a20617070656e645f627974655f737472696e67004984c98cd5ce24811a4e616d654572726f723a205052454649585f555345525f4e4654004984c98cd5ce24811f4e616d654572726f723a205052454649585f5245464552454e43455f4e4654004984c98cd5ce2481124e616d654572726f723a204d696e74696e67004984c98cd5ce24810f4e616d654572726f723a204d696e74004984c98cd5ce24810f4e616d654572726f723a204275726e004980048dd598019816000801918021aba200100c233301d3758601a6050002400226ec5262300c3574400201601601601601601646466e1cc0440052000500100f00f237566020603a0024601e6ae880048dd69807180d80091806980d0009111bad3235573c666020008466ebc008d55ce800899bb00013750a0046ea54008888dd5991aab9e33300f00423375e0046aae740044cdd80009ba650023752a0044466601a00446eb4d55cf0008a5eb008ccc02cdd6180b980b000900089bb14988c8ccc03000488cdc000124004900028008058070071180800091bae3011301000123010300f0012300f35744002444664602644a666aae7c0045401054ccd5cd18019aba10011357420022660040046ae8800400800c888cc8c048894ccd55cf8008a802099aba0300335742002660040046ae8800400800c888ccc8c0448894ccd55cf801080089998018019aba200233004001357420040040060024649454005c3919ba548008dd8a4c466e9520003762931191b8d00150012233710002004ebc8c800540048d55ce9baa001235573c6ea80048d5d0800919ba548000cd5d01ba950013762931191800800800a612bd8799fd8799f5820be08700c9a6c373844b8c21e61a3b693b4563510d961f3e8c74c0e154cd94285ff00ff0001")):
            #         reference_utxo = utxo
            #         break

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            # builder.add_script_input(reference_utxo)
            for u in utxos:
                builder.add_input(u)

            builder.add_output(pc.TransactionOutput(to_address_obj, pc.Value(amount_lovelace)))

            builder.fee_buffer = 1_000_000

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