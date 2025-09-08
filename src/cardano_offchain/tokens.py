"""
Token Operations

Pure token functionality without console dependencies.
Handles minting, burning, and token management operations.
"""

from typing import Any, Dict, Optional

import pycardano as pc
from opshin.prelude import TxId, TxOutRef

from terrasacha_contracts.minting_policies.authentication_nfts import Burn, Mint
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
)
from terrasacha_contracts.validators.protocol import (
    DatumProtocol,
    EndProtocol,
    UpdateProtocol,
)

from .chain_context import CardanoChainContext
from .contracts import ContractManager
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
            protocol_nfts_contract = self.contract_manager.create_minting_contract(oref)
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
            payment_vkey = self.wallet.get_payment_verification_key_hash()
            protocol_datum = DatumProtocol(
                protocol_admin=[payment_vkey],
                protocol_fee=1000000,
                oracle_id=bytes.fromhex("a" * 56),  # PolicyId format
                projects=[],  # Empty initially, projects added later via protocol updates
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

            if not protocol_contract:
                return {"success": False, "error": "Required contracts not compiled"}

            # Get contract info
            minting_script = protocol_nfts_contract.cbor
            protocol_script = protocol_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))
            protocol_address = protocol_contract.testnet_addr

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            # Add minting script for burning
            builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Burn()))

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

            # Add protocol UTXO as script input
            builder.add_script_input(
                protocol_utxo_to_spend,
                script=protocol_script,
                redeemer=pc.Redeemer(EndProtocol(protocol_input_index=0)),
            )

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

            # Add user UTXO as input
            builder.add_input(user_utxo_to_spend)

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
            builder.required_signers = [self.wallet.get_payment_verification_key_hash()]

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
            all_inputs_utxos = self.transactions.sorted_utxos(payment_utxos + [protocol_utxo_to_spend, user_utxo_to_spend])
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
                    protocol_admin=old_datum.protocol_admin,
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
    ) -> Dict[str, Any]:
        """
        Create a project minting transaction for project and user NFTs

        Args:
            project_id: 32-byte project identifier
            project_metadata: Metadata URI or hash
            stakeholders: List of (stakeholder_name_bytes, participation_amount) tuples
            destination_address: Optional destination for user token

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get project contract
            project_contract = self.contract_manager.get_contract("project")
            if not project_contract:
                return {"success": False, "error": "Project contract not compiled"}

            project_address = project_contract.testnet_addr

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
                    "error": "No suitable UTXO found for minting (need >5 ADA)",
                }

            # Create UTXO reference for dynamic contract compilation
            oref = TxOutRef(
                id=TxId(utxo_to_spend.input.transaction_id.payload),
                idx=utxo_to_spend.input.index,
            )

            # Dynamically compile project_nfts contract with this UTXO
            project_nfts_contract = self.contract_manager.create_minting_contract(oref)
            if not project_nfts_contract:
                return {"success": False, "error": "Failed to compile project_nfts contract"}

            # Store the compiled contract in ContractManager for later use (burn/update operations)
            self.contract_manager.contracts["project_nfts"] = project_nfts_contract

            # Persist the dynamically compiled contract to disk
            try:
                if not self.contract_manager._save_contracts():
                    print(
                        "Warning: Failed to save dynamically compiled project_nfts contract to disk"
                    )
            except Exception as e:
                print(f"Warning: Error saving contracts to disk: {e}")

            # Get contract info
            minting_script = project_nfts_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            builder.add_input(utxo_to_spend)

            # Generate token names (using oref created above)
            project_token_name = unique_token_name(oref, PREFIX_REFERENCE_NFT)
            user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

            # Create assets to mint
            project_nft_asset = pc.MultiAsset(
                {minting_policy_id: pc.Asset({pc.AssetName(project_token_name): 1})}
            )
            user_nft_asset = pc.MultiAsset(
                {minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})}
            )

            total_mint = project_nft_asset.union(user_nft_asset)
            builder.mint = total_mint

            # Add minting script
            builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Mint()))

            # Create stakeholder participation list
            stakeholder_list = []
            total_supply = 0
            for stakeholder_name, participation in stakeholders:
                stakeholder_list.append(
                    StakeHolderParticipation(
                        stakeholder=stakeholder_name, participation=participation
                    )
                )
                total_supply += participation

            # Create project parameters
            payment_vkey = self.wallet.get_payment_verification_key_hash()
            project_params = DatumProjectParams(
                owner=payment_vkey,
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
            # Get the protocol Policy ID for the datum
            protocol_contract = self.contract_manager.get_contract("protocol")
            if not protocol_contract:
                return {"success": False, "error": "Protocol contract not compiled"}
            # protocol_script = protocol_contract.cbor
            protocol_policy_id = bytes.fromhex(protocol_contract.policy_id)
            # protocol_policy_id = protocol_contract.policy_id

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
        self, user_address: Optional[pc.Address] = None
    ) -> Dict[str, Any]:
        """
        Create a burn transaction for project and user NFTs

        Args:
            user_address: Optional address containing user tokens to burn

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get contracts
            project_nfts_contract = self.contract_manager.get_contract("project_nfts")
            project_contract = self.contract_manager.get_contract("project")

            if not project_nfts_contract or not project_contract:
                return {"success": False, "error": "Required contracts not compiled"}

            # Get contract info
            minting_script = project_nfts_contract.cbor
            project_script = project_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))
            project_address = project_contract.testnet_addr

            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            # Add minting script for burning
            builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Burn()))

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

            # Add project UTXO as script input
            builder.add_script_input(
                project_utxo_to_spend,
                script=project_script,
                redeemer=pc.Redeemer(EndProject(project_input_index=0)),
            )

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

            # Add user UTXO as input
            builder.add_input(user_utxo_to_spend)

            # Extract assets for burning
            user_asset = self.transactions.extract_asset_from_utxo(
                user_utxo_to_spend, minting_policy_id
            )
            project_asset = self.transactions.extract_asset_from_utxo(
                project_utxo_to_spend, minting_policy_id
            )

            # Set burn amounts (negative minting)
            total_mint = pc.MultiAsset(
                {
                    minting_policy_id: pc.Asset(
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

            # Add required signer
            builder.required_signers = [self.wallet.get_payment_verification_key_hash()]

            # Build transaction
            signing_key = self.wallet.get_signing_key(0)
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
        self, user_address: Optional[pc.Address] = None, new_datum: DatumProject = None
    ) -> Dict[str, Any]:
        """
        Create a transaction to update the project datum

        Args:
            user_address: Optional address containing user tokens
            new_datum: New project datum to set (optional)

        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get project contracts
            project_nfts_contract = self.contract_manager.get_contract("project_nfts")
            project_contract = self.contract_manager.get_contract("project")

            protocol_nfts_contract = self.contract_manager.get_contract("protocol_nfts")
            protocol_contract = self.contract_manager.get_contract("protocol")

            if not project_contract or not project_nfts_contract or not protocol_contract:
                return {"success": False, "error": "Required contract not compiled"}

            # Get contract info
            project_script = project_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))
            protocol_minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))

            project_address = project_contract.testnet_addr
            protocol_address = protocol_contract.testnet_addr

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
            all_inputs_utxos = self.transactions.sorted_utxos(payment_utxos + [project_utxo_to_spend, user_utxo_to_spend])
            project_index = all_inputs_utxos.index(project_utxo_to_spend)
            user_index = all_inputs_utxos.index(user_utxo_to_spend)


            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            for u in payment_utxos:
                builder.add_input(u)

            # Add project UTXO as script input
            builder.add_script_input(
                project_utxo_to_spend,
                script=project_script,
                redeemer=pc.Redeemer(
                    UpdateProject(
                        project_input_index=project_index,
                        user_input_index=user_index,
                        project_output_index=0,
                    )
                ),
            )

            # Add protocol UTXO as input
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                return {"success": False, "error": "No protocol UTXOs found"}
            
            protocol_utxo = self.transactions.find_utxo_by_policy_id(
                protocol_utxos, protocol_minting_policy_id
            )
            if not protocol_utxo:
                return {
                    "success": False,
                    "error": "No protocol UTXO found with specified policy ID",
                }
            # # builder.add_input(protocol_utxo)
            builder.reference_inputs.add(protocol_utxo)

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
                        owner=old_datum.params.owner,
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
