"""
Token Operations

Pure token functionality without console dependencies.
Handles minting, burning, and token management operations.
"""

from typing import Optional, Dict, Any
from opshin.prelude import TxOutRef, TxId
import pycardano as pc
from terrasacha_contracts.types import (
    PREFIX_PROTOCOL_NFT, PREFIX_USER_NFT, Burn, DatumProtocol, Mint, EndProtocol, UpdateProtocol
)
from terrasacha_contracts.util import unique_token_name
from .wallet import CardanoWallet
from .chain_context import CardanoChainContext
from .contracts import ContractManager
from .transactions import CardanoTransactions


class TokenOperations:
    """Manages token minting, burning, and related operations"""
    
    def __init__(
        self, 
        wallet: CardanoWallet, 
        chain_context: CardanoChainContext,
        contract_manager: ContractManager,
        transactions: CardanoTransactions
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
    
    def create_minting_transaction(self, destination_address: Optional[pc.Address] = None) -> Dict[str, Any]:
        """
        Create a minting transaction for protocol and user NFTs
        
        Args:
            destination_address: Optional destination for user token
            
        Returns:
            Transaction creation result dictionary
        """
        try:
            # Get contracts
            protocol_nfts_contract = self.contract_manager.get_contract("protocol_nfts")
            protocol_contract = self.contract_manager.get_contract("protocol")
            
            if not protocol_nfts_contract or not protocol_contract:
                return {
                    'success': False,
                    'error': 'Required contracts not compiled'
                }
            
            # Get contract info
            minting_script = protocol_nfts_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))
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
                    'success': False,
                    'error': 'No suitable UTXO found for minting (need >3 ADA)'
                }
            
            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            builder.add_input(utxo_to_spend)
            
            # Create UTXO reference for token naming
            oref = TxOutRef(
                id=TxId(utxo_to_spend.input.transaction_id.payload),
                idx=utxo_to_spend.input.index,
            )
            
            # Generate token names
            protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
            user_token_name = unique_token_name(oref, PREFIX_USER_NFT)
            
            # Create assets to mint
            protocol_nft_asset = pc.MultiAsset({
                minting_policy_id: pc.Asset({pc.AssetName(protocol_token_name): 1})
            })
            user_nft_asset = pc.MultiAsset({
                minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})
            })
            
            total_mint = protocol_nft_asset.union(user_nft_asset)
            builder.mint = total_mint
            
            # Add minting script
            builder.add_minting_script(
                script=minting_script,
                redeemer=pc.Redeemer(Mint())
            )
            
            # Create protocol datum
            payment_vkey = self.wallet.get_payment_verification_key_hash()
            protocol_datum = DatumProtocol(
                protocol_admin=[payment_vkey],
                protocol_fee=1000000,
                oracle_id=b"oracle_integration_test"
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
                'success': True,
                'transaction': signed_tx,
                'tx_id': signed_tx.id.payload.hex(),
                'protocol_token_name': protocol_token_name.hex(),
                'user_token_name': user_token_name.hex(),
                'minting_policy_id': protocol_nfts_contract.policy_id
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Minting transaction creation failed: {e}'
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
            
            if not protocol_nfts_contract or not protocol_contract:
                return {
                    'success': False,
                    'error': 'Required contracts not compiled'
                }
            
            # Get contract info
            minting_script = protocol_nfts_contract.cbor
            protocol_script = protocol_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))
            protocol_address = protocol_contract.testnet_addr
            
            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            
            # Add minting script for burning
            builder.add_minting_script(
                script=minting_script,
                redeemer=pc.Redeemer(Burn())
            )
            
            # Find protocol UTXO
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                return {
                    'success': False,
                    'error': 'No protocol UTXOs found'
                }
            
            protocol_utxo_to_spend = self.transactions.find_utxo_by_policy_id(protocol_utxos, minting_policy_id)
            if not protocol_utxo_to_spend:
                return {
                    'success': False,
                    'error': 'No protocol UTXO found with specified policy ID'
                }
            
            # Add protocol UTXO as script input
            builder.add_script_input(
                protocol_utxo_to_spend,
                script=protocol_script,
                redeemer=pc.Redeemer(EndProtocol(protocol_input_index=0))
            )
            
            # Find user UTXO
            if user_address is None:
                user_address = self.wallet.get_address(0)
            
            user_utxos = self.context.utxos(user_address)
            if not user_utxos:
                return {
                    'success': False,
                    'error': 'No user UTXOs found'
                }
            
            user_utxo_to_spend = self.transactions.find_utxo_by_policy_id(user_utxos, minting_policy_id)
            if not user_utxo_to_spend:
                return {
                    'success': False,
                    'error': 'No user UTXO found with specified policy ID'
                }
            
            # Add user UTXO as input
            builder.add_input(user_utxo_to_spend)
            
            # Extract assets for burning
            user_asset = self.transactions.extract_asset_from_utxo(user_utxo_to_spend, minting_policy_id)
            protocol_asset = self.transactions.extract_asset_from_utxo(protocol_utxo_to_spend, minting_policy_id)
            
            # Set burn amounts (negative minting)
            total_mint = pc.MultiAsset({minting_policy_id: pc.Asset({
                list(protocol_asset.keys())[0]: -1,
                list(user_asset.keys())[0]: -1,
            })})
            builder.mint = total_mint
            
            # Add user address to pay for transaction
            builder.add_input_address(user_address)
            
            # Add required signer
            builder.required_signers = [self.wallet.get_payment_verification_key_hash()]
            
            # Build transaction
            signing_key = self.wallet.get_signing_key(0)
            signed_tx = builder.build_and_sign([signing_key], change_address=user_address)
            
            return {
                'success': True,
                'transaction': signed_tx,
                'tx_id': signed_tx.id.payload.hex(),
                'burned_tokens': {
                    'protocol_token': list(protocol_asset.keys())[0].payload.hex(),
                    'user_token': list(user_asset.keys())[0].payload.hex()
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Burn transaction creation failed: {e}'
            }

    def create_protocol_update_transaction(self, user_address: Optional[pc.Address] = None, new_datum: DatumProtocol = None) -> Dict[str, Any]:
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
                return {
                    'success': False,
                    'error': 'Required contract not compiled'
                }
            
            # Get contract info
            minting_script = protocol_nfts_contract.cbor
            protocol_script = protocol_contract.cbor
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))
            protocol_address = protocol_contract.testnet_addr
            
            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            
            # Find protocol UTXO
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                return {
                    'success': False,
                    'error': 'No protocol UTXOs found'
                }
            
            protocol_utxo_to_spend = self.transactions.find_utxo_by_policy_id(protocol_utxos, minting_policy_id)
            if not protocol_utxo_to_spend:
                return {
                    'success': False,
                    'error': 'No protocol UTXO found with specified policy ID'
                }
            
            # Add protocol UTXO as script input
            builder.add_script_input(
                protocol_utxo_to_spend,
                script=protocol_script,
                redeemer=pc.Redeemer(UpdateProtocol(
                    protocol_input_index=0,
                    user_input_index=1,
                    protocol_output_index=0
                ))
            )
            # Find user UTXO
            if user_address is None:
                user_address = self.wallet.get_address(0)

            user_utxos = self.context.utxos(user_address)
            if not user_utxos:
                return {
                    'success': False,
                    'error': 'No user UTXOs found'
                }
            
            user_utxo_to_spend = self.transactions.find_utxo_by_policy_id(user_utxos, minting_policy_id)
            if not user_utxo_to_spend:
                return {
                    'success': False,
                    'error': 'No user UTXO found with specified policy ID'
                }
            
            # Add user UTXO as input
            builder.add_input(user_utxo_to_spend)

            # Add user address to pay for transaction
            builder.add_input_address(user_address)
            

            # Update protocol datum
            old_datum = DatumProtocol.from_cbor(protocol_utxo_to_spend.output.datum.cbor)
            if not isinstance(old_datum, DatumProtocol):
                return {
                    'success': False,
                    'error': 'Protocol UTXO datum is not of expected type'
                }
            if new_datum is None:
                # Create new datum with updated fee
                new_datum = DatumProtocol(
                    protocol_admin=old_datum.protocol_admin,
                    protocol_fee=old_datum.protocol_fee + 500000,  # Increase fee by 0.5 ADA
                    oracle_id=old_datum.oracle_id
                )
            
            # Validate datum update
            # self.validate_datum_update(old_datum, new_datum)

            # Add protocol output
            protocol_asset = self.transactions.extract_asset_from_utxo(protocol_utxo_to_spend, minting_policy_id)
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
                'success': True,
                'transaction': signed_tx,
                'tx_id': signed_tx.id.payload.hex(),
                'old_datum': old_datum,
                'new_datum': new_datum
            }
            
            # Add protocol
        except Exception as e:
            return {
                'success': False,
                'error': f'Protocol update transaction creation failed: {e}'
            }