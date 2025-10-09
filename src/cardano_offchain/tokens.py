"""
Token Operations

Pure token functionality without console dependencies.
Handles minting, burning, and token management operations.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pycardano as pc
from opshin.prelude import TxId, TxOutRef, FalseData, TrueData

from terrasacha_contracts.minting_policies.protocol_nfts import Burn, Mint
from terrasacha_contracts.minting_policies.project_nfts import BurnProject, MintProject
from terrasacha_contracts.minting_policies.grey import BurnGrey, MintGrey
from terrasacha_contracts.util import (
    PREFIX_REFERENCE_NFT,
    PREFIX_USER_NFT,
    unique_token_name,
)
from terrasacha_contracts.validators.project import (
    Certification,
    DatumProject,
    DatumProjectParams,
    EndProject,
    StakeHolderParticipation,
    TokenProject,
    UpdateProject,
    UpdateToken,
)
from terrasacha_contracts.validators.protocol import (
    DatumProtocol,
    EndProtocol,
    UpdateProtocol,
)

from .chain_context import CardanoChainContext
from .contracts import ContractManager, ReferenceScriptContract
from .transactions import CardanoTransactions
from .wallet import CardanoWallet


def convert_metadata_keys(obj):
    """
    Convert string keys to integers for metadata (CIP-25 format).
    PyCardano's Metadata class requires integer keys in the first layer.

    Args:
        obj: Object to convert (dict, list, or primitive)

    Returns:
        Converted object with integer keys where applicable
    """
    if isinstance(obj, dict):
        new_dict = {}
        for key, value in obj.items():
            # Try to convert key to int if it's a numeric string
            try:
                new_key = int(key)
            except (ValueError, TypeError):
                new_key = key
            new_dict[new_key] = convert_metadata_keys(value)
        return new_dict
    elif isinstance(obj, list):
        return [convert_metadata_keys(item) for item in obj]
    else:
        return obj


def prepare_grey_token_metadata(
    grey_minting_policy_id: pc.ScriptHash,
    grey_token_name: bytes,
    metadata_file_path: Path
) -> Optional[pc.AuxiliaryData]:
    """
    Prepare CIP-25 metadata for grey token minting with dynamic policy ID and token name.

    Args:
        grey_minting_policy_id: Policy ID for the grey token
        grey_token_name: Token name as bytes
        metadata_file_path: Path to metadata template JSON file

    Returns:
        AuxiliaryData with metadata, or None if preparation fails
    """

    def split_description_strings(description_list, max_bytes=64):
        """
        Split description strings into chunks that don't exceed max_bytes.
        PyCardano requires each metadata string to be ≤ 64 bytes.

        Args:
            description_list: List of description strings
            max_bytes: Maximum bytes per string (default 64)

        Returns:
            List of strings, each ≤ max_bytes
        """
        result = []
        for text in description_list:
            # Check if text is already within limit
            if len(text.encode('utf-8')) <= max_bytes:
                result.append(text)
            else:
                # Split text into chunks
                words = text.split()
                current_chunk = []
                current_length = 0

                for word in words:
                    word_bytes = len(word.encode('utf-8'))
                    # +1 for space between words
                    needed_length = current_length + word_bytes + (1 if current_chunk else 0)

                    if needed_length <= max_bytes:
                        current_chunk.append(word)
                        current_length = needed_length
                    else:
                        # Save current chunk and start new one
                        if current_chunk:
                            result.append(' '.join(current_chunk))
                        current_chunk = [word]
                        current_length = word_bytes

                # Add remaining chunk
                if current_chunk:
                    result.append(' '.join(current_chunk))

        return result

    try:
        # Load metadata template
        with open(metadata_file_path, 'r') as f:
            metadata_template = json.load(f)

        # Get actual policy ID and token name
        actual_policy_id = grey_minting_policy_id.to_primitive().hex()
        try:
            actual_token_name = grey_token_name.decode('utf-8')
        except:
            actual_token_name = grey_token_name.hex()

        # Extract template structure
        template_721 = metadata_template["721"]
        template_policy_id = [k for k in template_721.keys() if k != "version"][0]
        template_token_name = list(template_721[template_policy_id].keys())[0]
        token_metadata_template = template_721[template_policy_id][template_token_name]

        # Update name field to actual token name
        token_metadata_template["name"] = actual_token_name

        # Split description strings if they exceed 64 bytes
        if "description" in token_metadata_template and isinstance(token_metadata_template["description"], list):
            token_metadata_template["description"] = split_description_strings(
                token_metadata_template["description"]
            )

        # Build dynamic metadata with actual values
        dynamic_metadata = {
            "721": {
                actual_policy_id: {
                    actual_token_name: token_metadata_template
                },
                "version": template_721.get("version", "1.0")
            }
        }

        # Convert string keys to integers for PyCardano
        converted_metadata = convert_metadata_keys(dynamic_metadata)

        # Create and return auxiliary data
        metadata = pc.Metadata(converted_metadata)
        alonzo_metadata = pc.AlonzoMetadata(metadata=metadata)
        return pc.AuxiliaryData(alonzo_metadata)

    except Exception as e:
        print(f"Warning: Could not prepare metadata from {metadata_file_path}: {e}")
        return None


class TokenOperations:
    """Manages token minting, burning, and related operations"""

    def __init__(
        self,
        wallet: CardanoWallet,
        chain_context: CardanoChainContext,
        contract_manager: ContractManager,
        transactions: CardanoTransactions,
    ):
        """
        Initialize token operations

        Args:
            wallet: CardanoWallet instance
            chain_context: CardanoChainContext instance
            contract_manager: ContractManager instance
            transactions: CardanoTransactions instance
        """
        self.wallet = wallet
        self.chain_context = chain_context
        self.contract_manager = contract_manager
        self.transactions = transactions
        self.context = chain_context.get_context()
        self.api = chain_context.get_api()

    def _get_script_info_for_transaction(self, contract_name: str) -> Optional[Dict[str, Any]]:
        """
        Get script information for transaction building, handling both local and reference scripts

        Args:
            contract_name: Name of the contract to get info for

        Returns:
            Dictionary with script info and type, or None if contract not found
        """
        contract = self.contract_manager.get_contract(contract_name)
        if not contract:
            return None

        if isinstance(contract, ReferenceScriptContract):
            return {
                "type": "reference_script",
                "reference_utxo": {
                    "tx_id": contract.reference_tx_id,
                    "output_index": contract.reference_output_index,
                    "address": contract.reference_address,
                },
                "policy_id": contract.policy_id,
                "testnet_addr": contract.testnet_addr,
                "mainnet_addr": contract.mainnet_addr,
            }
        else:
            return {
                "type": "local",
                "cbor": contract.cbor,
                "policy_id": contract.policy_id,
                "testnet_addr": contract.testnet_addr,
                "mainnet_addr": contract.mainnet_addr,
            }

    def _add_script_to_builder(
        self,
        builder: pc.TransactionBuilder,
        script_info: Dict[str, Any],
        redeemer: Optional[pc.Redeemer] = None,
        is_minting: bool = False,
    ) -> bool:
        """
        Add script to transaction builder, handling both local and reference scripts

        Args:
            builder: Transaction builder to add script to
            script_info: Script information from _get_script_info_for_transaction
            redeemer: Redeemer for the script (required for spending)
            is_minting: True if this is for minting, False for spending

        Returns:
            True if script was added successfully, False otherwise
        """
        # This helper method is mainly for minting policies
        if script_info["type"] == "reference_script":
            if is_minting:
                # For minting with reference scripts, we need to handle this differently
                # The calling code should handle reference script minting policies manually
                return False  # Indicate that calling code needs to handle this
            else:
                # For spending, this helper shouldn't be used - use the direct approach in calling code
                return False
        else:
            # For local scripts, add them directly
            if is_minting:
                builder.add_minting_script(script=script_info["cbor"], redeemer=redeemer)
                return True
            else:
                # For spending, the script will be added in add_script_input call
                return True

    def create_minting_transaction(
        self, destination_address: Optional[pc.Address] = None
    ) -> Dict[str, Any]:
        """
        Create a minting transaction for protocol and user NFTs

        Args:
            destination_address: Optional destination for user token

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get protocol contract
            protocol_contract = self.contract_manager.get_contract("protocol")
            if not protocol_contract:
                return {"success": False, "error": "Protocol contract not compiled"}

            protocol_address = protocol_contract.testnet_addr

            # Get wallet info
            from_address = self.wallet.get_address(0)
            signing_key = self.wallet.get_signing_key(0)

            # Find suitable UTXO
            utxos = self.context.utxos(from_address)
            utxo_to_spend = None
            for utxo in utxos:
                if utxo.output.amount.coin > 3000000:
                    utxo_to_spend = utxo
                    break

            if not utxo_to_spend:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for minting (need >3 ADA)",
                }

            # Create UTXO reference for dynamic contract compilation
            oref = TxOutRef(
                id=TxId(utxo_to_spend.input.transaction_id.payload),
                idx=utxo_to_spend.input.index,
            )

            # Use stored protocol_nfts contract to ensure consistency
            protocol_nfts_contract = self.contract_manager.get_contract("protocol_nfts")
            if not protocol_nfts_contract:
                return {"success": False, "error": "Protocol NFTs minting contract not found. Compile contracts first."}

            # Get contract info
            minting_script = protocol_nfts_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            builder.add_input(utxo_to_spend)

            # Generate token names (using oref created above)
            protocol_token_name = unique_token_name(oref, PREFIX_REFERENCE_NFT)
            user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

            # Create assets to mint
            protocol_nft_asset = pc.MultiAsset(
                {minting_policy_id: pc.Asset({pc.AssetName(protocol_token_name): 1})}
            )
            user_nft_asset = pc.MultiAsset(
                {minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})}
            )

            total_mint = protocol_nft_asset.union(user_nft_asset)
            builder.mint = total_mint

            # Add minting script
            builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Mint()))

            # Create protocol datum
            protocol_datum = DatumProtocol(
                project_admins=[],  # Empty initially, admins added later via protocol updates
                protocol_fee=1000000,
                oracle_id=bytes.fromhex("a" * 56),  # PolicyId format
                projects=[],  # No projects initially
            )

            # Add protocol output
            protocol_value = pc.Value(0, protocol_nft_asset)
            min_val_protocol = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    protocol_address,
                    protocol_value,
                    datum=protocol_datum,
                ),
            )
            protocol_output = pc.TransactionOutput(
                address=protocol_address,
                amount=pc.Value(coin=min_val_protocol, multi_asset=protocol_nft_asset),
                datum=protocol_datum,
            )
            builder.add_output(protocol_output)

            # Add user output
            if destination_address is None:
                destination_address = from_address

            user_value = pc.Value(0, user_nft_asset)
            min_val_user = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    destination_address,
                    user_value,
                ),
            )
            user_output = pc.TransactionOutput(
                address=destination_address,
                amount=pc.Value(coin=min_val_user, multi_asset=user_nft_asset),
                datum=None,
            )
            builder.add_output(user_output)

            # Build transaction
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "protocol_token_name": protocol_token_name.hex(),
                "user_token_name": user_token_name.hex(),
                "minting_policy_id": protocol_nfts_contract.policy_id,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Minting transaction creation failed: {e}",
            }

    def create_burn_transaction(self, user_address: Optional[pc.Address] = None) -> Dict[str, Any]:
        """
        Create a burn transaction for protocol and user NFTs

        Args:
            user_address: Optional address containing user tokens to burn

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get contracts
            protocol_nfts_contract = self.contract_manager.get_contract("protocol_nfts")
            protocol_contract = self.contract_manager.get_contract("protocol")

            if not protocol_contract or not protocol_nfts_contract:
                return {"success": False, "error": "Required contracts not compiled"}

            # Get contract info
            minting_script = protocol_nfts_contract.cbor
            protocol_script = protocol_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))
            protocol_address = protocol_contract.testnet_addr

            # Find protocol UTXO
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                return {"success": False, "error": "No protocol UTXOs found"}

            protocol_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                protocol_utxos, minting_policy_id
            )
            if not protocol_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No protocol UTXO found with specified policy ID",
                }

            # Find user UTXO
            if user_address is None:
                user_address = self.wallet.get_address(0)

            user_utxos = self.context.utxos(user_address)
            if not user_utxos:
                return {"success": False, "error": "No user UTXOs found"}

            user_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                user_utxos, minting_policy_id
            )
            if not user_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No user UTXO found with specified policy ID",
                }

            payment_utxos = user_utxos
            all_inputs_utxos = self.transactions.sorted_utxos(
                payment_utxos + [protocol_utxo_to_spend]
            )
            protocol_index = all_inputs_utxos.index(protocol_utxo_to_spend)
            user_index = all_inputs_utxos.index(user_utxo_to_spend)

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            for u in payment_utxos:
                builder.add_input(u)

            # Add minting script for burning
            builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Burn()))

            # Add protocol UTXO as script input
            builder.add_script_input(
                protocol_utxo_to_spend,
                script=protocol_script,
                redeemer=pc.Redeemer(
                    EndProtocol(protocol_input_index=protocol_index, user_input_index=user_index)
                ),
            )

            # Extract assets for burning
            user_asset = self.transactions.extract_asset_from_utxo(
                user_utxo_to_spend, minting_policy_id
            )
            protocol_asset = self.transactions.extract_asset_from_utxo(
                protocol_utxo_to_spend, minting_policy_id
            )

            # Set burn amounts (negative minting)
            total_mint = pc.MultiAsset(
                {
                    minting_policy_id: pc.Asset(
                        {
                            list(protocol_asset.keys())[0]: -1,
                            list(user_asset.keys())[0]: -1,
                        }
                    )
                }
            )
            builder.mint = total_mint

            # Add user address to pay for transaction
            builder.add_input_address(user_address)

            # Add required signer
            # builder.required_signers = [self.wallet.get_payment_verification_key_hash()]

            # Build transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=user_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "burned_tokens": {
                    "protocol_token": list(protocol_asset.keys())[0].payload.hex(),
                    "user_token": list(user_asset.keys())[0].payload.hex(),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"Burn transaction creation failed: {e}"}

    def create_protocol_update_transaction(
        self, user_address: Optional[pc.Address] = None, new_datum: DatumProtocol = None
    ) -> Dict[str, Any]:
        """
        Create a transaction to update the protocol datum

        Args:
            user_address: Optional address containing user tokens

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get protocol contract
            protocol_nfts_contract = self.contract_manager.get_contract("protocol_nfts")
            protocol_contract = self.contract_manager.get_contract("protocol")

            if not protocol_contract or not protocol_nfts_contract:
                return {"success": False, "error": "Required contract not compiled"}

            # Get contract info
            protocol_script = protocol_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))
            protocol_address = protocol_contract.testnet_addr

            # Find protocol UTXO
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                return {"success": False, "error": "No protocol UTXOs found"}

            protocol_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                protocol_utxos, minting_policy_id
            )
            if not protocol_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No protocol UTXO found with specified policy ID",
                }

            # Find user UTXO
            if user_address is None:
                user_address = self.wallet.get_address(0)

            user_utxos = self.context.utxos(user_address)
            if not user_utxos:
                return {"success": False, "error": "No user UTXOs found"}

            user_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                user_utxos, minting_policy_id
            )
            if not user_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No user UTXO found with specified policy ID",
                }

            payment_utxos = user_utxos
            all_inputs_utxos = self.transactions.sorted_utxos(
                payment_utxos + [protocol_utxo_to_spend]
            )
            protocol_index = all_inputs_utxos.index(protocol_utxo_to_spend)
            user_index = all_inputs_utxos.index(user_utxo_to_spend)

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            for u in payment_utxos:
                builder.add_input(u)

            # Add protocol UTXO as script input
            builder.add_script_input(
                protocol_utxo_to_spend,
                script=protocol_script,
                redeemer=pc.Redeemer(
                    UpdateProtocol(
                        protocol_input_index=protocol_index,
                        user_input_index=user_index,
                        protocol_output_index=0,
                    )
                ),
            )

            # Update protocol datum
            old_datum = DatumProtocol.from_cbor(protocol_utxo_to_spend.output.datum.cbor)
            if not isinstance(old_datum, DatumProtocol):
                return {
                    "success": False,
                    "error": "Protocol UTXO datum is not of expected type",
                }
            if new_datum is None:
                # Create new datum with updated fee
                new_datum = DatumProtocol(
                    project_admins=["d86e773973d3786f63e79765ca79e0758f395a0cb7335d154fc18393"],
                    protocol_fee=old_datum.protocol_fee + 500000,  # Increase fee by 0.5 ADA
                    oracle_id=old_datum.oracle_id,
                    projects=old_datum.projects,
                )

            # Add protocol output
            protocol_asset = self.transactions.extract_asset_from_utxo(
                protocol_utxo_to_spend, minting_policy_id
            )
            protocol_multi_asset = pc.MultiAsset({minting_policy_id: protocol_asset})
            protocol_value = pc.Value(0, protocol_multi_asset)
            min_val_protocol = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    protocol_address,
                    protocol_value,
                    datum=new_datum,
                ),
            )
            protocol_output = pc.TransactionOutput(
                address=protocol_address,
                amount=pc.Value(coin=min_val_protocol, multi_asset=protocol_multi_asset),
                datum=new_datum,
            )
            builder.add_output(protocol_output)

            # Build transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=user_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "old_datum": old_datum,
                "new_datum": new_datum,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Protocol update transaction creation failed: {e}",
            }

    def create_project_minting_transaction(
        self,
        project_id: bytes,
        project_metadata: bytes,
        stakeholders: list,  # List of tuples: (stakeholder_name_bytes, participation_int)
        destination_address: Optional[pc.Address] = None,
        project_name: Optional[str] = None,
        wallet_override: Optional['CardanoWallet'] = None,
    ) -> Dict[str, Any]:
        """
        Create a project minting transaction for project and user NFTs

        Args:
            project_id: 32-byte project identifier
            project_metadata: Metadata URI or hash
            stakeholders: List of (stakeholder_name_bytes, participation_amount) tuples
            destination_address: Optional destination for user token
            project_name: Optional specific project contract name to use (e.g., "project_1")

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get project contract (use specified or default/first available)
            project_contract = self.contract_manager.get_project_contract(project_name)
            if not project_contract:
                return {"success": False, "error": "No project contract compiled"}

            # Find the name of the project contract being used
            project_contract_name = self.contract_manager.get_project_name_from_contract(
                project_contract
            )
            if not project_contract_name:
                return {"success": False, "error": "Could not determine project contract name"}

            project_address = project_contract.testnet_addr

            # Use the provided wallet or default to the instance wallet
            active_wallet = wallet_override if wallet_override else self.wallet

            # Get wallet info using the active wallet (default index 0)
            from_address = active_wallet.get_address(0)
            signing_key = active_wallet.get_signing_key(0)

            print(f"Using {'user-selected' if wallet_override else 'default'} wallet for project minting")

            # Get the pre-compiled project_nfts contract (compiled via CLI option 3)
            project_nfts_contract = self.contract_manager.get_project_nfts_contract(project_contract_name)
            if not project_nfts_contract:
                return {
                    "success": False,
                    "error": f"Project NFTs contract for '{project_contract_name}' not found. Please compile project contracts first using CLI option 3."
                }

            project_minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))

            # Get the compilation UTXO info for reference
            compilation_utxo_info = self.contract_manager.get_project_compilation_utxo(project_contract_name)
            # compilation_utxo_ref = self.contract_manager.get_project_compilation_utxo_as_txoutref(compilation_utxo_info)

            # if not compilation_utxo_ref:
            #     return {
            #         "success": False,
            #         "error": f"Compilation UTXO not found for project '{project_contract_name}'. Please recompile the project contracts using CLI option 3."
            #     }

            # Get UTXOs from the active wallet
            wallet_utxos = self.context.utxos(from_address)
            user_utxo_to_spend = None

            # Look for the compilation UTXO in the active wallet
            for utxo in wallet_utxos:
                if (utxo.input.transaction_id.payload.hex() == compilation_utxo_info["tx_id"]
                    and utxo.input.index == compilation_utxo_info["index"]):
                    user_utxo_to_spend = utxo
                    break

            if not user_utxo_to_spend:
                return {
                    "success": False,
                    "error": f"Compilation UTXO not found in the selected wallet. The UTXO may be in a different wallet or has been consumed. UTXO needed: {compilation_utxo_info['tx_id']}:{compilation_utxo_info['index']}"
                }
            
            oref = TxOutRef(
                id=TxId(user_utxo_to_spend.input.transaction_id.payload),
                idx=user_utxo_to_spend.input.index,
            )

            # Get contract info for script handling
            project_nfts_name = f"{project_contract_name}_nfts"
            project_nfts_info = self._get_script_info_for_transaction(project_nfts_name)
            if not project_nfts_info:
                return {"success": False, "error": "Project NFTs contract info not available"}

            # Get the protocol Policy ID for the datum
            protocol_contract = self.contract_manager.get_contract("protocol")
            if not protocol_contract:
                return {"success": False, "error": "Protocol contract not compiled"}
            protocol_address = protocol_contract.testnet_addr

            protocol_minting_script = self.contract_manager.get_contract("protocol_nfts")
            if not protocol_minting_script:
                return {"success": False, "error": "Protocol NFTs contract not compiled"}
            protocol_minting_policy_id = pc.ScriptHash(
                bytes.fromhex(protocol_minting_script.policy_id)
            )

            # Find protocol UTXO
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                return {"success": False, "error": "No protocol UTXOs found"}

            protocol_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                protocol_utxos, protocol_minting_policy_id
            )
            if not protocol_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No protocol UTXO found with specified policy ID",
                }

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            builder.add_input(user_utxo_to_spend)

            # Add minting script - handle both local and reference scripts
            mint_redeemer = pc.Redeemer(
                MintProject(
                    protocol_input_index=0,
                )
            )

            # For local scripts, use helper method
            self._add_script_to_builder(
                builder, project_nfts_info, mint_redeemer, is_minting=True
            )

            builder.reference_inputs.add(protocol_utxo_to_spend)

            # Generate token names (using oref created above)
            project_token_name = unique_token_name(oref, PREFIX_REFERENCE_NFT)
            user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

            # Create assets to mint
            project_nft_asset = pc.MultiAsset(
                {project_minting_policy_id: pc.Asset({pc.AssetName(project_token_name): 1})}
            )
            user_nft_asset = pc.MultiAsset(
                {project_minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})}
            )

            total_mint = project_nft_asset.union(user_nft_asset)
            builder.mint = total_mint

            # Create stakeholder participation list
            stakeholder_list = []
            total_supply = 0
            for stakeholder_name, participation, stakeholder_pkh in stakeholders:
                stakeholder_list.append(
                    StakeHolderParticipation(
                        stakeholder=stakeholder_name,
                        pkh=bytes.fromhex(stakeholder_pkh),
                        participation=participation,
                        claimed=FalseData(),
                    )
                )
                total_supply += participation

            # Create project parameters
            # payment_vkey = self.wallet.get_payment_verification_key_hash()
            project_params = DatumProjectParams(
                project_id=project_id,
                project_metadata=project_metadata,
                project_state=0,  # initialized
            )

            # Create project token info
            project_token_info = TokenProject(
                policy_id=b"",
                token_name=b"",
                total_supply=total_supply,
            )

            # Create initial certification (empty)
            initial_certifications = [
                Certification(
                    certification_date=0, quantity=0, real_certification_date=0, real_quantity=0
                )
            ]

            # Create project datum
            project_datum = DatumProject(
                params=project_params,
                project_token=project_token_info,
                stakeholders=stakeholder_list,
                certifications=initial_certifications,
            )

            # Add project output
            project_value = pc.Value(0, project_nft_asset)
            min_val_project = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    project_address,
                    project_value,
                    datum=project_datum,
                ),
            )
            project_output = pc.TransactionOutput(
                address=project_address,
                amount=pc.Value(coin=min_val_project, multi_asset=project_nft_asset),
                datum=project_datum,
            )
            builder.add_output(project_output)

            # Add user output
            if destination_address is None:
                destination_address = from_address

            user_value = pc.Value(0, user_nft_asset)
            min_val_user = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    destination_address,
                    user_value,
                ),
            )
            user_output = pc.TransactionOutput(
                address=destination_address,
                amount=pc.Value(coin=min_val_user, multi_asset=user_nft_asset),
                datum=None,
            )
            builder.add_output(user_output)

            # Build transaction
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "project_token_name": project_token_name.hex(),
                "user_token_name": user_token_name.hex(),
                "minting_policy_id": protocol_contract.policy_id,
                "project_id": project_id.hex(),
                "total_supply": total_supply,
                "stakeholders_count": len(stakeholder_list),
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Project minting transaction creation failed: {e}",
            }

    def create_project_burn_transaction(
        self, user_address: Optional[pc.Address] = None, project_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a burn transaction for project and user NFTs.
        Automatically detects and handles both local and reference script contracts.

        Args:
            user_address: Optional address containing user tokens to burn
            project_name: Optional specific project contract name to use

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get contracts using helper methods
            project_contract = self.contract_manager.get_project_contract(project_name)
            if not project_contract:
                return {
                    "success": False,
                    "error": f"Project contract '{project_name}' not compiled",
                }

            # Get the corresponding project NFTs minting policy
            project_nfts_contract = self.contract_manager.get_project_nfts_contract(project_name)
            if not project_nfts_contract:
                return {"success": False, "error": "Required contracts not compiled"}

            # Get project contract name for reference
            project_contract_name = (
                self.contract_manager.get_project_name_from_contract(project_contract)
                or project_name
            )
            project_nfts_name = f"{project_contract_name}_nfts"

            # Get contract info using helper methods
            project_info = self._get_script_info_for_transaction(project_contract_name)
            project_nfts_info = self._get_script_info_for_transaction(project_nfts_name)

            if not project_info or not project_nfts_info:
                return {"success": False, "error": "Contract info not available"}

            project_minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_info["policy_id"]))
            project_address = project_info["testnet_addr"]

            # Get the protocol Policy ID for the datum
            protocol_contract = self.contract_manager.get_contract("protocol")
            if not protocol_contract:
                return {"success": False, "error": "Protocol contract not compiled"}
            protocol_address = protocol_contract.testnet_addr

            protocol_minting_script = self.contract_manager.get_contract("protocol_nfts")
            if not protocol_minting_script:
                return {"success": False, "error": "Protocol NFTs contract not compiled"}
            protocol_minting_policy_id = pc.ScriptHash(
                bytes.fromhex(protocol_minting_script.policy_id)
            )

            # Find protocol UTXO
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                return {"success": False, "error": "No protocol UTXOs found"}

            protocol_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                protocol_utxos, protocol_minting_policy_id
            )
            if not protocol_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No protocol UTXO found with specified policy ID",
                }

            # Get wallet info
            signing_key = self.wallet.get_signing_key(0)

            # Find project UTXO
            project_utxos = self.context.utxos(project_address)
            if not project_utxos:
                return {"success": False, "error": "No project UTXOs found"}

            project_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                project_utxos, project_minting_policy_id
            )
            if not project_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No project UTXO found with specified policy ID",
                }

            # Find user UTXO
            if user_address is None:
                user_address = self.wallet.get_address(0)

            user_utxos = self.context.utxos(user_address)
            if not user_utxos:
                return {"success": False, "error": "No user UTXOs found"}

            user_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                user_utxos, project_minting_policy_id
            )
            if not user_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No user UTXO found with specified policy ID",
                }

            payment_utxos = user_utxos
            all_inputs_utxos = self.transactions.sorted_utxos(
                payment_utxos + [project_utxo_to_spend]
            )
            project_index = all_inputs_utxos.index(project_utxo_to_spend)
            user_index = all_inputs_utxos.index(user_utxo_to_spend)

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            for u in payment_utxos:
                builder.add_input(u)

            # Add project UTXO as script input - handle both local and reference scripts
            project_redeemer = pc.Redeemer(
                EndProject(project_input_index=project_index, user_input_index=user_index)
            )

            if project_info["type"] == "reference_script":
                # For reference scripts, we need to find the actual UTXO containing the reference script
                ref_utxo_info = project_info["reference_utxo"]
                ref_address = pc.Address.from_primitive(ref_utxo_info["address"])

                # Find the UTXO containing the reference script
                reference_script_utxo = None
                for utxo in self.context.utxos(ref_address):
                    if (
                        utxo.input.transaction_id.payload.hex() == ref_utxo_info["tx_id"]
                        and utxo.input.index == ref_utxo_info["output_index"]
                    ):
                        reference_script_utxo = utxo
                        break

                if not reference_script_utxo:
                    return {"success": False, "error": "Reference script UTXO not found"}

                builder.add_script_input(
                    project_utxo_to_spend,
                    script=reference_script_utxo,  # Pass the actual UTXO containing the script
                    redeemer=project_redeemer,
                )
            else:
                # For local scripts, include the script
                builder.add_script_input(
                    project_utxo_to_spend,
                    script=project_info["cbor"],
                    redeemer=project_redeemer,
                )

            all_reference_input_index = self.transactions.sorted_utxos(
                [reference_script_utxo, protocol_utxo_to_spend]
            )
            protocol_input_index = all_reference_input_index.index(protocol_utxo_to_spend)
            # Add minting script for burning - handle both local and reference scripts
            burn_redeemer = pc.Redeemer(
                BurnProject(
                    protocol_input_index=protocol_input_index
                )
            )

            builder.reference_inputs.add(protocol_utxo_to_spend)
            if project_nfts_info["type"] == "reference_script":
                # For reference script minting policies, we need to find the reference UTXO
                ref_utxo_info = project_nfts_info["reference_utxo"]
                ref_address = pc.Address.from_primitive(ref_utxo_info["address"])

                # Find the UTXO containing the reference script
                reference_script_utxo = None
                for utxo in self.context.utxos(ref_address):
                    if (
                        utxo.input.transaction_id.payload.hex() == ref_utxo_info["tx_id"]
                        and utxo.input.index == ref_utxo_info["output_index"]
                    ):
                        reference_script_utxo = utxo
                        break

                if not reference_script_utxo:
                    return {
                        "success": False,
                        "error": "Reference script UTXO not found for minting policy",
                    }

                # For minting policies with reference scripts, PyCardano handles this automatically
                # when we set the mint field - no need to call add_minting_script
                pass
            else:
                # For local scripts, use helper method
                self._add_script_to_builder(
                    builder, project_nfts_info, burn_redeemer, is_minting=True
                )

            # Extract assets for burning
            user_asset = self.transactions.extract_asset_from_utxo(
                user_utxo_to_spend, project_minting_policy_id
            )
            project_asset = self.transactions.extract_asset_from_utxo(
                project_utxo_to_spend, project_minting_policy_id
            )

            # Set burn amounts (negative minting)
            total_mint = pc.MultiAsset(
                {
                    project_minting_policy_id: pc.Asset(
                        {
                            list(project_asset.keys())[0]: -1,
                            list(user_asset.keys())[0]: -1,
                        }
                    )
                }
            )
            builder.mint = total_mint

            # Add user address to pay for transaction
            builder.add_input_address(user_address)

            # Build transaction
            signing_key = self.wallet.get_signing_key(0)
            print("keys", self.wallet.get_payment_verification_key_hash().hex())
            signed_tx = builder.build_and_sign([signing_key], change_address=user_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "burned_tokens": {
                    "project_token": list(project_asset.keys())[0].payload.hex(),
                    "user_token": list(user_asset.keys())[0].payload.hex(),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"Project burn transaction creation failed: {e}"}

    def create_project_update_transaction(
        self,
        user_address: Optional[pc.Address] = None,
        new_datum: DatumProject = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a transaction to update the project datum

        Args:
            user_address: Optional address containing user tokens
            new_datum: New project datum to set (optional)
            project_name: Optional specific project contract name to use

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get project contracts using helper methods
            project_contract = self.contract_manager.get_project_contract(project_name)
            if not project_contract:
                return {
                    "success": False,
                    "error": f"Project contract '{project_name}' not compiled",
                }

            # Get project contract name for reference
            project_contract_name = (
                self.contract_manager.get_project_name_from_contract(project_contract)
                or project_name
            )

            # Get contract info using helper methods
            project_info = self._get_script_info_for_transaction(project_contract_name)
            if not project_info:
                return {"success": False, "error": "Project contract info not available"}

            # Get the corresponding project NFTs minting policy
            project_nfts_contract = self.contract_manager.get_project_nfts_contract(project_name)

            # Get contract info
            minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))

            project_address = project_info["testnet_addr"]

            # Find project UTXO
            project_utxos = self.context.utxos(project_address)
            if not project_utxos:
                return {"success": False, "error": "No project UTXOs found"}

            project_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                project_utxos, minting_policy_id
            )
            if not project_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No project UTXO found with specified policy ID",
                }

            # Find user UTXO
            if user_address is None:
                user_address = self.wallet.get_address(0)

            user_utxos = self.context.utxos(user_address)
            if not user_utxos:
                return {"success": False, "error": "No user UTXOs found"}

            user_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                user_utxos, minting_policy_id
            )
            if not user_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No user UTXO found with specified policy ID",
                }

            payment_utxos = user_utxos
            all_inputs_utxos = self.transactions.sorted_utxos(
                payment_utxos + [project_utxo_to_spend]
            )
            project_index = all_inputs_utxos.index(project_utxo_to_spend)
            user_index = all_inputs_utxos.index(user_utxo_to_spend)

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            for u in payment_utxos:
                builder.add_input(u)

            # Add project UTXO as script input - handle both local and reference scripts
            project_redeemer = pc.Redeemer(
                UpdateProject(
                    project_input_index=project_index,
                    user_input_index=user_index,
                    project_output_index=0,
                )
            )

            if project_info["type"] == "reference_script":
                # For reference scripts, we need to find the actual UTXO containing the reference script
                ref_utxo_info = project_info["reference_utxo"]
                ref_address = pc.Address.from_primitive(ref_utxo_info["address"])

                # Find the UTXO containing the reference script
                reference_script_utxo = None
                for utxo in self.context.utxos(ref_address):
                    if (
                        utxo.input.transaction_id.payload.hex() == ref_utxo_info["tx_id"]
                        and utxo.input.index == ref_utxo_info["output_index"]
                    ):
                        reference_script_utxo = utxo
                        break

                if not reference_script_utxo:
                    return {"success": False, "error": "Reference script UTXO not found"}

                builder.add_script_input(
                    project_utxo_to_spend,
                    script=reference_script_utxo,  # Pass the actual UTXO containing the script
                    redeemer=project_redeemer,
                )
            else:
                # For local scripts, include the script
                builder.add_script_input(
                    project_utxo_to_spend,
                    script=project_info["cbor"],
                    redeemer=project_redeemer,
                )

            # Update project datum
            old_datum = DatumProject.from_cbor(project_utxo_to_spend.output.datum.cbor)
            if not isinstance(old_datum, DatumProject):
                return {
                    "success": False,
                    "error": "Project UTXO datum is not of expected type",
                }

            if new_datum is None:
                new_project_state = min(old_datum.params.project_state + 1, 3)
                new_datum = DatumProject(
                    params=DatumProjectParams(
                        project_id=old_datum.params.project_id,
                        project_metadata=old_datum.params.project_metadata,
                        project_state=new_project_state,
                    ),
                    project_token=old_datum.project_token,
                    stakeholders=old_datum.stakeholders,
                    certifications=old_datum.certifications,
                )

            # Add project output
            project_asset = self.transactions.extract_asset_from_utxo(
                project_utxo_to_spend, minting_policy_id
            )
            project_multi_asset = pc.MultiAsset({minting_policy_id: project_asset})
            project_value = pc.Value(0, project_multi_asset)
            min_val_project = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    project_address,
                    project_value,
                    datum=new_datum,
                ),
            )
            project_output = pc.TransactionOutput(
                address=project_address,
                amount=pc.Value(coin=min_val_project, multi_asset=project_multi_asset),
                datum=new_datum,
            )
            builder.add_output(project_output)

            # Build transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=user_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "old_datum": old_datum,
                "new_datum": new_datum,
            }

        except Exception as e:
            return {"success": False, "error": f"Project update transaction creation failed: {e}"}

    def create_grey_minting_transaction(
        self,
        project_name: Optional[str] = None,
        grey_token_quantity: int = 1,
        minting_mode: str = "free",
    ) -> Dict[str, Any]:
        """
        Create a minting transaction for grey tokens
        Purpose of this Tx is to UpdateToken datum in the project contract while minting grey tokens

        Pre-requisites: Grey token info must already exist in project datum (setup via UpdateProject first)

        Args:
            project_name: Optional specific project contract name to use
            grey_token_quantity: Number of grey tokens to mint (default: 1)
            minting_mode: Minting mode - "free" (requires authorization token) or "authorized" (any wallet, contract validates)

        Returns:
            A dictionary containing the transaction details or an error message

        Note: Grey tokens are always sent to the wallet submitting the transaction (paying fees)
        """
        try:
            project_contract = self.contract_manager.get_project_contract(project_name)
            project_nfts_contract = self.contract_manager.get_project_nfts_contract(project_name)

            if not project_contract or not project_nfts_contract:
                return {"success": False, "error": "Project contract or NFTs contract not found"}

            project_minting_policy_id = pc.ScriptHash(
                bytes.fromhex(project_nfts_contract.policy_id)
            )

            # Find the name of the project contract being used
            project_contract_name = self.contract_manager.get_project_name_from_contract(
                project_contract
            )
            if not project_contract_name:
                return {"success": False, "error": "Could not determine project contract name"}

            # Get contract info using helper method to handle both local and reference scripts
            project_info = self._get_script_info_for_transaction(project_contract_name)
            if not project_info:
                return {"success": False, "error": "Project contract info not available"}

            project_address = project_contract.testnet_addr

            # Find project UTXO
            project_utxos = self.context.utxos(project_address)
            if not project_utxos:
                return {"success": False, "error": "No project UTXOs found"}

            project_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                project_utxos, project_minting_policy_id
            )
            if not project_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No project UTXO found with specified policy ID",
                }

            # Get user info
            from_address = self.wallet.get_address(0)
            user_utxos = self.context.utxos(from_address)
            if not user_utxos:
                return {"success": False, "error": "No user UTXOs found"}

            # Mode-specific UTXO selection and index calculation
            if minting_mode == "free":
                # Free mode: Requires authorization token (project NFT)
                user_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                    user_utxos, project_minting_policy_id
                )
                if not user_utxo_to_spend:
                    return {
                        "success": False,
                        "error": "No user UTXO found with specified policy ID (authorization token required for free minting)",
                    }

                # Calculate indices including user UTXO
                payment_utxos = user_utxos
                all_inputs_utxos = self.transactions.sorted_utxos(
                    payment_utxos + [project_utxo_to_spend]
                )
                project_index = all_inputs_utxos.index(project_utxo_to_spend)
                user_index = all_inputs_utxos.index(user_utxo_to_spend)
            else:
                # Authorized mode: Any wallet can attempt, find UTXO for fees
                utxo_to_spend = None
                for utxo in user_utxos:
                    if utxo.output.amount.coin > 3000000:
                        utxo_to_spend = utxo
                        break

                if not utxo_to_spend:
                    return {
                        "success": False,
                        "error": "No suitable UTXO found for minting (need >3 ADA)",
                    }

                # Calculate indices without user token requirement
                payment_utxos = user_utxos
                all_inputs_utxos = self.transactions.sorted_utxos(
                    payment_utxos + [project_utxo_to_spend]
                )
                project_index = all_inputs_utxos.index(project_utxo_to_spend)
                user_index = None  # Not needed for authorized mode

            # Get input datum info
            try:
                project_datum = DatumProject.from_cbor(project_utxo_to_spend.output.datum.cbor)
            except Exception as e:
                return {"success": False, "error": f"Failed to get project datum: {e}"}

            # Dynamically compile grey minting contract with the project PolicyID
            grey_minting_contract = self.contract_manager.create_minting_contract(
                "grey", project_minting_policy_id
            )
            if not grey_minting_contract:
                return {"success": False, "error": "Failed to compile grey minting contract"}

            grey_minting_script = grey_minting_contract.cbor
            grey_minting_policy_id = pc.ScriptHash(bytes.fromhex(grey_minting_contract.policy_id))
            grey_token_name = project_datum.project_token.token_name

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            for u in payment_utxos:
                builder.add_input(u)

            # Select redeemer based on minting mode
            if minting_mode == "free":
                # Free mode: Use UpdateProject redeemer (requires authorization token)
                project_redeemer = pc.Redeemer(
                    UpdateProject(
                        project_input_index=project_index,
                        user_input_index=user_index,
                        project_output_index=0,
                    )
                )
            else:
                # Authorized mode: Use UpdateToken redeemer (contract validates authorization)
                project_redeemer = pc.Redeemer(
                    UpdateToken(
                        project_input_index=project_index,
                        project_output_index=0,
                    )
                )

            if project_info["type"] == "reference_script":
                # For reference scripts, we need to find the actual UTXO containing the reference script
                ref_utxo_info = project_info["reference_utxo"]
                ref_address = pc.Address.from_primitive(ref_utxo_info["address"])

                # Find the UTXO containing the reference script
                reference_script_utxo = None
                for utxo in self.context.utxos(ref_address):
                    if (
                        utxo.input.transaction_id.payload.hex() == ref_utxo_info["tx_id"]
                        and utxo.input.index == ref_utxo_info["output_index"]
                    ):
                        reference_script_utxo = utxo
                        break

                if not reference_script_utxo:
                    return {"success": False, "error": "Reference script UTXO not found"}

                builder.add_script_input(
                    project_utxo_to_spend,
                    script=reference_script_utxo,  # Pass the actual UTXO containing the script
                    redeemer=project_redeemer,
                )
            else:
                # For local scripts, include the script
                builder.add_script_input(
                    project_utxo_to_spend,
                    script=project_info["cbor"],
                    redeemer=project_redeemer,
                )

            # Add minting script for grey tokens
            builder.add_minting_script(script=grey_minting_script, redeemer=pc.Redeemer(MintGrey(project_input_index=project_index, project_output_index=0)))

            # Create grey token asset using correct token name from datum
            grey_asset = pc.Asset({pc.AssetName(grey_token_name): grey_token_quantity})
            grey_multi_asset = pc.MultiAsset({grey_minting_policy_id: grey_asset})

            builder.mint = grey_multi_asset

            # Create updated project datum based on minting mode
            if minting_mode == "free":
                # Free mode: Change project state to 1, keep stakeholders unchanged
                new_params = DatumProjectParams(
                    project_id=project_datum.params.project_id,
                    project_metadata=project_datum.params.project_metadata,
                    project_state=1,  # Move to token sale state
                )
                new_stakeholders = project_datum.stakeholders  # Keep original
            else:
                # Authorized mode: Keep state unchanged, mark stakeholder as claimed
                new_params = DatumProjectParams(
                    project_id=project_datum.params.project_id,
                    project_metadata=project_datum.params.project_metadata,
                    project_state=project_datum.params.project_state,  # Keep current state
                )

                # Get signing wallet's PKH to identify which stakeholder is claiming
                payment_vkey_hash = self.wallet.get_payment_verification_key_hash()

                # Update stakeholders: mark the authorized one as claimed
                new_stakeholders = []
                for stakeholder in project_datum.stakeholders:
                    if stakeholder.pkh == payment_vkey_hash:
                        # This is the authorized stakeholder - mark as claimed
                        new_stakeholders.append(
                            StakeHolderParticipation(
                                stakeholder=stakeholder.stakeholder,
                                pkh=stakeholder.pkh,
                                participation=stakeholder.participation,
                                claimed=TrueData(),  # Mark as claimed
                            )
                        )
                    else:
                        # Keep other stakeholders unchanged
                        new_stakeholders.append(stakeholder)

            # Create updated project datum with mode-specific changes
            new_project_datum = DatumProject(
                params=new_params,
                project_token=project_datum.project_token,
                stakeholders=new_stakeholders,
                certifications=project_datum.certifications,
            )

            # Add project output with project NFT
            project_asset = self.transactions.extract_asset_from_utxo(
                project_utxo_to_spend, project_minting_policy_id
            )
            project_multi_asset = pc.MultiAsset({project_minting_policy_id: project_asset})
            project_value = pc.Value(0, project_multi_asset)
            min_val_project = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    project_address,
                    project_value,
                    datum=new_project_datum,
                ),
            )
            project_output = pc.TransactionOutput(
                address=project_address,
                amount=pc.Value(coin=min_val_project, multi_asset=project_multi_asset),
                datum=new_project_datum,
            )
            builder.add_output(project_output)

            # Add user output with minted grey tokens
            user_value = pc.Value(0, grey_multi_asset)
            min_val_user = pc.min_lovelace(
                self.context,
                output=pc.TransactionOutput(
                    from_address,
                    user_value,
                    datum=None,
                ),
            )
            user_output = pc.TransactionOutput(
                address=from_address,
                amount=pc.Value(coin=min_val_user, multi_asset=grey_multi_asset),
                datum=None,
            )
            builder.add_output(user_output)

            # Load and attach metadata from grey_token_metadata.json
            metadata_file_path = Path(__file__).parent.parent.parent / "grey_token_metadata.json"
            auxiliary_data = prepare_grey_token_metadata(
                grey_minting_policy_id,
                grey_token_name,
                metadata_file_path
            )
            if auxiliary_data:
                builder.auxiliary_data = auxiliary_data

            # Build and sign transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "grey_token_name": grey_token_name.hex(),
                "minting_policy_id": grey_minting_contract.policy_id,
                "project_id": project_datum.params.project_id.hex(),
                "quantity": grey_token_quantity,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Grey token minting transaction creation failed: {e}",
            }

    def burn_grey_tokens(
        self,
        project_name: Optional[str] = None,
        burn_quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Create a burning transaction for grey tokens that only interacts with the grey contract.
        Bypasses project contract validation - grey contract always succeeds for burning.

        Args:
            project_name: Optional project name for grey contract compilation
            burn_quantity: Number of grey tokens to burn (default: 1)

        Returns:
            A dictionary containing the transaction details or an error message
        """
        try:
            # Get project contract and NFTs contract
            project_contract = self.contract_manager.get_project_contract(project_name)
            project_nfts_contract = self.contract_manager.get_project_nfts_contract(project_name)

            if not project_contract or not project_nfts_contract:
                return {"success": False, "error": "Project contract or NFTs contract not found"}

            project_minting_policy_id = pc.ScriptHash(
                bytes.fromhex(project_nfts_contract.policy_id)
            )

            # Find the name of the project contract being used
            project_contract_name = self.contract_manager.get_project_name_from_contract(
                project_contract
            )
            if not project_contract_name:
                return {"success": False, "error": "Could not determine project contract name"}

            project_address = project_contract.testnet_addr

            # Find project UTXO to get grey token name from datum
            project_utxos = self.context.utxos(project_address)
            if not project_utxos:
                return {"success": False, "error": "No project UTXOs found"}

            project_utxo_to_spend = self.transactions.find_utxo_by_policy_id(
                project_utxos, project_minting_policy_id
            )
            if not project_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No project UTXO found with specified policy ID",
                }

            # Get project datum to extract grey token name
            try:
                project_datum = DatumProject.from_cbor(project_utxo_to_spend.output.datum.cbor)
            except Exception as e:
                return {"success": False, "error": f"Failed to get project datum: {e}"}

            grey_token_name = project_datum.project_token.token_name

            # Dynamically compile grey minting contract with the project PolicyID
            grey_minting_contract = self.contract_manager.create_minting_contract(
                "grey", project_minting_policy_id
            )
            if not grey_minting_contract:
                return {"success": False, "error": "Failed to compile grey minting contract"}

            grey_minting_policy_id = pc.ScriptHash(bytes.fromhex(grey_minting_contract.policy_id))

            # Get user wallet address for finding UTXOs
            from_address = self.wallet.get_address(0)

            # Find UTXOs containing the grey tokens to burn
            user_utxos = self.context.utxos(from_address)
            if not user_utxos:
                return {"success": False, "error": "No UTXOs found in wallet"}

            # Find UTXOs that contain the grey tokens to burn
            grey_token_utxos = []
            total_available = 0

            for utxo in user_utxos:
                if grey_minting_policy_id in utxo.output.amount.multi_asset:
                    asset_dict = utxo.output.amount.multi_asset[grey_minting_policy_id]
                    if pc.AssetName(grey_token_name) in asset_dict:
                        token_amount = asset_dict[pc.AssetName(grey_token_name)]
                        grey_token_utxos.append(utxo)
                        total_available += token_amount

            if total_available < burn_quantity:
                return {
                    "success": False,
                    "error": f"Insufficient grey tokens. Available: {total_available}, Required: {burn_quantity}",
                }

            # Select sufficient UTXOs to cover the burn amount
            selected_utxos = []
            selected_tokens = 0
            for utxo in grey_token_utxos:
                selected_utxos.append(utxo)
                asset_dict = utxo.output.amount.multi_asset[grey_minting_policy_id]
                token_amount = asset_dict[pc.AssetName(grey_token_name)]
                selected_tokens += token_amount
                if selected_tokens >= burn_quantity:
                    break

            # Find additional UTXOs for fees (non-token UTXOs)
            fee_utxos = [
                utxo
                for utxo in user_utxos
                if utxo not in selected_utxos and utxo.output.amount.coin >= 2000000
            ]
            if not fee_utxos:
                return {"success": False, "error": "No suitable UTXO found for transaction fees"}

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            # Add selected UTXOs as inputs
            for utxo in selected_utxos:
                builder.add_input(utxo)

            # Add fee UTXO
            builder.add_input(fee_utxos[0])

            # Create negative mint value (burning)
            grey_asset = pc.Asset({pc.AssetName(grey_token_name): -burn_quantity})
            grey_multi_asset = pc.MultiAsset({grey_minting_policy_id: grey_asset})

            # Add minting script for burning with BurnGrey redeemer
            builder.add_minting_script(
                script=grey_minting_contract.cbor, redeemer=pc.Redeemer(BurnGrey())
            )

            # Set the burn amount in the transaction
            builder.mint = grey_multi_asset

            # Calculate change: return remaining tokens and ADA to user
            remaining_tokens = selected_tokens - burn_quantity

            if remaining_tokens > 0:
                # Return remaining grey tokens to user
                remaining_asset = pc.Asset({pc.AssetName(grey_token_name): remaining_tokens})
                remaining_multi_asset = pc.MultiAsset({grey_minting_policy_id: remaining_asset})

                # Calculate minimum lovelace for token output
                token_value = pc.Value(0, remaining_multi_asset)
                min_val_tokens = pc.min_lovelace(
                    self.context,
                    output=pc.TransactionOutput(from_address, token_value, datum=None),
                )

                token_output = pc.TransactionOutput(
                    address=from_address,
                    amount=pc.Value(coin=min_val_tokens, multi_asset=remaining_multi_asset),
                    datum=None,
                )
                builder.add_output(token_output)

            # Build and sign transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "grey_token_name": grey_token_name.hex(),
                "grey_policy_id": grey_minting_contract.policy_id,
                "burned_quantity": burn_quantity,
                "remaining_tokens": remaining_tokens,
                "total_burned_value": burn_quantity,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Grey token burning transaction creation failed: {e}",
            }

    def create_usda_mint_transaction(
        self,
        amount: int = 1000,
    ) -> Dict[str, Any]:
        """
        Create a minting transaction for USDA test tokens (faucet)

        Args:
            amount: Amount of USDA tokens to mint (default: 1000)

        Returns:
            A dictionary containing the transaction details or an error message
        """
        try:
            # Get myUSDFree minting policy contract (compile if not already compiled)
            usda_contract = self.contract_manager.get_contract("myUSDFree")
            if not usda_contract:
                # Compile the contract
                compile_result = self.contract_manager.compile_usda_contract()
                if not compile_result["success"]:
                    return {"success": False, "error": f"Failed to compile myUSDFree: {compile_result.get('error')}"}
                usda_contract = self.contract_manager.get_contract("myUSDFree")

            usda_policy_id = pc.ScriptHash(bytes.fromhex(usda_contract.policy_id))
            usda_token_name = b"USDATEST"

            # Get wallet address
            from_address = self.wallet.get_address(0)

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            builder.add_input_address(from_address)

            # Add minting with None redeemer (contract accepts any redeemer)
            mint_asset = pc.MultiAsset.from_primitive({
                usda_policy_id.payload: {usda_token_name: amount}
            })
            builder.mint = mint_asset
            builder.add_minting_script(script=usda_contract.cbor, redeemer=pc.Redeemer(Mint()))

            # Build and sign transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "token_name": usda_token_name.decode('utf-8'),
                "policy_id": usda_contract.policy_id,
                "amount": amount,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"USDA mint transaction creation failed: {e}",
            }

    def create_usda_burn_transaction(
        self,
        amount: int,
    ) -> Dict[str, Any]:
        """
        Create a burning transaction for USDA test tokens

        Args:
            amount: Amount of USDA tokens to burn

        Returns:
            A dictionary containing the transaction details or an error message
        """
        try:
            # Get myUSDFree minting policy contract (compile if not already compiled)
            usda_contract = self.contract_manager.get_contract("myUSDFree")
            if not usda_contract:
                # Compile the contract
                compile_result = self.contract_manager.compile_usda_contract()
                if not compile_result["success"]:
                    return {"success": False, "error": f"Failed to compile myUSDFree: {compile_result.get('error')}"}
                usda_contract = self.contract_manager.get_contract("myUSDFree")

            usda_policy_id = pc.ScriptHash(bytes.fromhex(usda_contract.policy_id))
            usda_token_name = b"USDATEST"

            # Get wallet address
            from_address = self.wallet.get_address(0)

            # Get user UTXOs and check for USDA tokens
            user_utxos = self.context.utxos(from_address)
            if not user_utxos:
                return {"success": False, "error": "No UTXOs found in wallet"}

            # Calculate available USDA tokens
            total_usda = 0
            for utxo in user_utxos:
                if usda_policy_id in utxo.output.amount.multi_asset:
                    token_dict = utxo.output.amount.multi_asset[usda_policy_id]
                    if pc.AssetName(usda_token_name) in token_dict:
                        total_usda += token_dict[pc.AssetName(usda_token_name)]

            if total_usda < amount:
                return {
                    "success": False,
                    "error": f"Insufficient USDA tokens. Have {total_usda}, need {amount}",
                }

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            builder.add_input_address(from_address)

            # Add burning (negative amount)
            burn_asset = pc.MultiAsset.from_primitive({
                usda_policy_id.payload: {usda_token_name: -amount}
            })
            builder.mint = burn_asset
            builder.add_minting_script(script=usda_contract.cbor, redeemer=pc.Redeemer(Burn()))

            # Build and sign transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

            return {
                "success": True,
                "transaction": signed_tx,
                "tx_id": signed_tx.id.payload.hex(),
                "token_name": usda_token_name.decode('utf-8'),
                "policy_id": usda_contract.policy_id,
                "burned_amount": amount,
                "remaining_tokens": total_usda - amount,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"USDA burn transaction creation failed: {e}",
            }
