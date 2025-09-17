"""
Token Operations

Pure token functionality without console dependencies.
Handles minting, burning, and token management operations.
"""

from typing import Any, Dict, Optional

import pycardano as pc
from opshin.prelude import TxId, TxOutRef

from terrasacha_contracts.minting_policies.protocol_nfts import Burn, Mint
from terrasacha_contracts.minting_policies.project_nfts import BurnProject, MintProject
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

            # Dynamically compile authentication_nfts contract with this UTXO
            protocol_nfts_contract = self.contract_manager.create_minting_contract("protocol", oref)
            if not protocol_nfts_contract:
                return {"success": False, "error": "Failed to compile authentication_nfts contract"}

            # Store the compiled contract in ContractManager for later use (burn/update operations)
            self.contract_manager.contracts["protocol_nfts"] = protocol_nfts_contract

            # Persist the dynamically compiled contract to disk
            try:
                if not self.contract_manager._save_contracts():
                    print(
                        "Warning: Failed to save dynamically compiled protocol_nfts contract to disk"
                    )
            except Exception as e:
                print(f"Warning: Error saving contracts to disk: {e}")

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

            # Get wallet info
            from_address = self.wallet.get_address(0)
            signing_key = self.wallet.get_signing_key(0)

            print("keys", self.wallet.get_payment_verification_key_hash().hex())

            # Find suitable UTXO
            user_utxos = self.context.utxos(from_address)
            user_utxo_to_spend = None
            for utxo in user_utxos:
                if utxo.output.amount.coin > 3000000:
                    user_utxo_to_spend = utxo
                    break

            if not user_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for minting (need >5 ADA)",
                }

            # Create UTXO reference for dynamic contract compilation
            oref = TxOutRef(
                id=TxId(user_utxo_to_spend.input.transaction_id.payload),
                idx=user_utxo_to_spend.input.index,
            )

            # Dynamically compile project_nfts contract with this UTXO
            project_nfts_contract = self.contract_manager.create_minting_contract("project", oref)
            if not project_nfts_contract:
                return {"success": False, "error": "Failed to compile project_nfts contract"}

            project_nfts_name = f"{project_contract_name}_nfts"
            self.contract_manager.contracts[project_nfts_name] = project_nfts_contract

            # Get contract info using helper method
            project_nfts_info = self._get_script_info_for_transaction(project_nfts_name)
            if not project_nfts_info:
                return {"success": False, "error": "Project NFTs contract info not available"}

            project_minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_info["policy_id"]))

            # Get the protocol Policy ID for the datum
            protocol_contract = self.contract_manager.get_contract("protocol")
            if not protocol_contract:
                return {"success": False, "error": "Protocol contract not compiled"}
            protocol_policy_id = bytes.fromhex(protocol_contract.policy_id)
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
                    protocol_policy_id=bytes.fromhex(protocol_minting_script.policy_id),
                )
            )

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
                        pkh=stakeholder_pkh,
                        participation=participation,
                        amount_claimed=0,
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
                current_supply=0,  # Initially no tokens minted
            )

            # Create initial certification (empty)
            initial_certifications = [
                Certification(
                    certification_date=0, quantity=0, real_certification_date=0, real_quantity=0
                )
            ]

            # Create project datum
            project_datum = DatumProject(
                protocol_policy_id=protocol_policy_id,
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
            protocol_policy_id = bytes.fromhex(protocol_contract.policy_id)
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
                    protocol_input_index=protocol_input_index,
                    protocol_policy_id=bytes.fromhex(protocol_minting_script.policy_id),
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
                    protocol_policy_id=old_datum.protocol_policy_id,
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
        destination_address: Optional[pc.Address] = None,
        project_name: Optional[str] = None,
        grey_token_quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Create a minting transaction for grey tokens
        Purpose of this Tx is to UpdateToken datum in the project contract while minting grey tokens

        Pre-requisites: Grey token info must already exist in project datum (setup via UpdateProject first)

        Args:
            destination_address: Optional destination for grey token
            project_name: Optional specific project contract name to use
            grey_token_quantity: Number of grey tokens to mint (default: 1)

        Returns:
            A dictionary containing the transaction details or an error message
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

            # Get input datum info
            try:
                project_datum = DatumProject.from_cbor(project_utxo_to_spend.output.datum.cbor)
            except Exception as e:
                return {"success": False, "error": f"Failed to get project datum: {e}"}

            # Validate project state - UpdateToken can only be used when project_state > 0
            if project_datum.params.project_state <= 0:
                return {
                    "success": False,
                    "error": "UpdateToken can only be used when project_state > 0. Project must be active for grey token minting.",
                }

            # Check if grey token info exists in project datum
            # For now, we assume it uses the same policy_id and token_name as project token
            # In future, this should be separate grey token info in the datum
            if (
                not project_datum.project_token.policy_id
                or not project_datum.project_token.token_name
            ):
                return {
                    "success": False,
                    "error": "Grey token info not found in project datum. Setup grey tokens first via Update Project menu.",
                }

            # Get wallet info
            from_address = self.wallet.get_address(0)
            if destination_address is None:
                destination_address = from_address

            # Find suitable UTXO
            user_utxos = self.context.utxos(from_address)
            user_utxo_to_spend = None
            for utxo in user_utxos:
                if utxo.output.amount.coin > 3000000:
                    user_utxo_to_spend = utxo
                    break

            if not user_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for minting (need >3 ADA)",
                }

            # Dynamically compile grey minting contract with the project PolicyID
            grey_minting_contract = self.contract_manager.create_minting_contract(
                "grey", bytes.fromhex(project_contract.policy_id)
            )
            if not grey_minting_contract:
                return {"success": False, "error": "Failed to compile grey minting contract"}

            grey_minting_script = grey_minting_contract.cbor
            grey_minting_policy_id = pc.ScriptHash(bytes.fromhex(grey_minting_contract.policy_id))

            # Read grey token info from project datum (policy_id should match grey contract policy_id)
            grey_token_policy_id = bytes.fromhex(grey_minting_contract.policy_id)
            grey_token_name = project_datum.project_token.token_name

            # Update project datum - increment current_supply by minted quantity
            new_current_supply = project_datum.project_token.current_supply + grey_token_quantity

            # Validate supply constraints
            if new_current_supply > project_datum.project_token.total_supply:
                return {
                    "success": False,
                    "error": f"Cannot mint {grey_token_quantity} tokens. Would exceed total supply ({project_datum.project_token.total_supply})",
                }

            new_token_project = TokenProject(
                policy_id=project_datum.project_token.policy_id,
                token_name=grey_token_name,
                total_supply=project_datum.project_token.total_supply,
                current_supply=new_current_supply,
            )

            # Update stakeholders datum - preserve all stakeholders, only update amount_claimed for the minting user
            new_stakeholders = []
            user_pkh = self.wallet.get_payment_verification_key_hash().hex()

            for stakeholder in project_datum.stakeholders:
                # Create a copy of the stakeholder
                updated_stakeholder = StakeHolderParticipation(
                    stakeholder=stakeholder.stakeholder,
                    pkh=stakeholder.pkh,
                    participation=stakeholder.participation,
                    amount_claimed=stakeholder.amount_claimed,
                )

                # Update amount_claimed if this stakeholder matches the current user
                if stakeholder.pkh == user_pkh:
                    new_amount_claimed = stakeholder.amount_claimed + grey_token_quantity
                    # Validate that amount_claimed doesn't exceed participation
                    if new_amount_claimed > stakeholder.participation:
                        return {
                            "success": False,
                            "error": f"Cannot mint {grey_token_quantity} tokens. Would exceed your participation limit ({stakeholder.participation})",
                        }
                    updated_stakeholder.amount_claimed = new_amount_claimed
                elif stakeholder.stakeholder == b"investor" and stakeholder.pkh == b"":
                    # Handle investor stakeholder with empty PKH
                    new_amount_claimed = stakeholder.amount_claimed + grey_token_quantity
                    if new_amount_claimed > stakeholder.participation:
                        return {
                            "success": False,
                            "error": f"Cannot mint {grey_token_quantity} tokens. Would exceed investor participation limit ({stakeholder.participation})",
                        }
                    updated_stakeholder.amount_claimed = new_amount_claimed

                # Always append the stakeholder (either updated or unchanged)
                new_stakeholders.append(updated_stakeholder)

            # Calculate transaction input indices for UpdateToken redeemer
            payment_utxos = user_utxos
            all_inputs_utxos = self.transactions.sorted_utxos(
                payment_utxos + [project_utxo_to_spend]
            )
            project_index = all_inputs_utxos.index(project_utxo_to_spend)
            user_index = all_inputs_utxos.index(user_utxo_to_spend)

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            builder.add_input(user_utxo_to_spend)

            # Add minting script for grey tokens
            builder.add_minting_script(script=grey_minting_script, redeemer=pc.Redeemer(Mint()))

            # Add project UTXO as script input with UpdateToken redeemer - handle both local and reference scripts
            project_redeemer = pc.Redeemer(
                UpdateToken(
                    project_input_index=project_index,
                    user_input_index=user_index,
                    project_output_index=0,
                    new_supply=new_current_supply,  # Pass the new total current_supply, not just the minted quantity
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

            # Create grey token asset using correct token name from datum
            grey_asset = pc.Asset({pc.AssetName(grey_token_name): grey_token_quantity})
            grey_multi_asset = pc.MultiAsset({grey_minting_policy_id: grey_asset})

            builder.mint = grey_multi_asset

            # Create updated project datum
            new_project_datum = DatumProject(
                protocol_policy_id=project_datum.protocol_policy_id,
                params=project_datum.params,
                project_token=new_token_project,
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
                    destination_address,
                    user_value,
                    datum=None,
                ),
            )
            user_output = pc.TransactionOutput(
                address=destination_address,
                amount=pc.Value(coin=min_val_user, multi_asset=grey_multi_asset),
                datum=None,
            )
            builder.add_output(user_output)

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
                "new_current_supply": new_current_supply,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Grey token minting transaction creation failed: {e}",
            }

    def burn_grey_tokens(
        self,
        grey_token_policy_id: str,
        grey_token_name: str,
        burn_quantity: int = 1,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a burning transaction for grey tokens that only interacts with the grey contract.
        Bypasses project contract validation - grey contract always succeeds for burning.

        Args:
            grey_token_policy_id: Policy ID of the grey tokens to burn
            grey_token_name: Token name of the grey tokens to burn (hex string)
            burn_quantity: Number of grey tokens to burn (default: 1)
            project_name: Optional project name for grey contract compilation

        Returns:
            A dictionary containing the transaction details or an error message
        """
        try:
            # Get user wallet address for finding UTXOs
            from_address = self.wallet.get_address()

            # Find UTXOs containing the grey tokens to burn
            user_utxos = self.context.utxos(from_address)
            if not user_utxos:
                return {"success": False, "error": "No UTXOs found in wallet"}

            # Convert policy ID and token name for UTXO searching
            grey_policy_id_bytes = pc.ScriptHash(bytes.fromhex(grey_token_policy_id))
            grey_token_name_bytes = bytes.fromhex(grey_token_name)

            # Find UTXOs that contain the grey tokens to burn
            grey_token_utxos = []
            total_available = 0

            for utxo in user_utxos:
                if grey_policy_id_bytes in utxo.output.amount.multi_asset:
                    asset_dict = utxo.output.amount.multi_asset[grey_policy_id_bytes]
                    if pc.AssetName(grey_token_name_bytes) in asset_dict:
                        token_amount = asset_dict[pc.AssetName(grey_token_name_bytes)]
                        grey_token_utxos.append(utxo)
                        total_available += token_amount

            if total_available < burn_quantity:
                return {
                    "success": False,
                    "error": f"Insufficient grey tokens. Available: {total_available}, Required: {burn_quantity}",
                }

            # Get or compile the grey minting contract for burning
            # We need a project contract to get the policy_id parameter for grey contract compilation
            project_contract = self.contract_manager.get_project_contract(project_name)
            if not project_contract:
                return {
                    "success": False,
                    "error": "Project contract not found - needed for grey contract compilation",
                }

            # Compile grey contract with project policy_id as parameter
            grey_minting_contract = self.contract_manager.create_minting_contract(
                "grey", bytes.fromhex(project_contract.policy_id)
            )
            if not grey_minting_contract:
                return {"success": False, "error": "Failed to compile grey minting contract"}

            # Verify the policy ID matches
            if grey_minting_contract.policy_id != grey_token_policy_id:
                return {
                    "success": False,
                    "error": f"Policy ID mismatch. Expected: {grey_token_policy_id}, Got: {grey_minting_contract.policy_id}",
                }

            # Select sufficient UTXOs to cover the burn amount
            selected_utxos = []
            selected_tokens = 0
            for utxo in grey_token_utxos:
                selected_utxos.append(utxo)
                asset_dict = utxo.output.amount.multi_asset[grey_policy_id_bytes]
                token_amount = asset_dict[pc.AssetName(grey_token_name_bytes)]
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
            grey_asset = pc.Asset({pc.AssetName(grey_token_name_bytes): -burn_quantity})
            grey_multi_asset = pc.MultiAsset({grey_policy_id_bytes: grey_asset})

            # Add minting script for burning with Burn redeemer
            builder.add_minting_script(
                script=grey_minting_contract.cbor, redeemer=pc.Redeemer(Burn())
            )

            # Set the burn amount in the transaction
            builder.mint = grey_multi_asset

            # Calculate change: return remaining tokens and ADA to user
            remaining_tokens = selected_tokens - burn_quantity

            if remaining_tokens > 0:
                # Return remaining grey tokens to user
                remaining_asset = pc.Asset({pc.AssetName(grey_token_name_bytes): remaining_tokens})
                remaining_multi_asset = pc.MultiAsset({grey_policy_id_bytes: remaining_asset})

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
                "grey_token_name": grey_token_name,
                "grey_policy_id": grey_token_policy_id,
                "burned_quantity": burn_quantity,
                "remaining_tokens": remaining_tokens,
                "total_burned_value": burn_quantity,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Grey token burning transaction creation failed: {e}",
            }
