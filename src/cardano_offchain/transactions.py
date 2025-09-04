"""
Cardano Transaction Operations

Pure transaction functionality without console dependencies.
Handles transaction building, signing, and submission.
"""

from typing import Optional, List
from blockfrost import ApiError
import pycardano as pc
from .chain_context import CardanoChainContext
from .wallet import CardanoWallet


class CardanoTransactions:
    """Manages Cardano transaction operations"""
    
    def __init__(self, wallet: CardanoWallet, chain_context: CardanoChainContext):
        """
        Initialize transaction manager
        
        Args:
            wallet: CardanoWallet instance
            chain_context: CardanoChainContext instance
        """
        self.wallet = wallet
        self.chain_context = chain_context
        self.context = chain_context.get_context()
        self.api = chain_context.get_api()
    
    def create_simple_transaction(
        self, 
        to_address: str, 
        amount_ada: float, 
        from_address_index: int = 0
    ) -> Optional[pc.Transaction]:
        """
        Create a simple ADA transfer transaction
        
        Args:
            to_address: Recipient address string
            amount_ada: Amount in ADA to send
            from_address_index: Source address index (0 = main address)
            
        Returns:
            Signed transaction or None if failed
            
        Raises:
            Exception: If transaction creation fails
        """
        try:
            # Convert ADA to lovelace
            amount_lovelace = int(amount_ada * 1_000_000)
            
            # Get addresses and keys
            from_address = self.wallet.get_address(from_address_index)
            to_address_obj = pc.Address.from_primitive(to_address)
            signing_key = self.wallet.get_signing_key(from_address_index)
            
            # Check UTXOs
            utxos = self.api.address_utxos(str(from_address))
            if not utxos:
                raise Exception("No UTXOs available for transaction")
            
            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)
            
            # Add inputs and outputs
            builder.add_input_address(from_address)
            builder.add_output(
                pc.TransactionOutput(to_address_obj, pc.Value(amount_lovelace))
            )
            
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
            'tx_id': tx_id,
            'explorer_url': self.chain_context.get_explorer_url(tx_id),
            'network': self.chain_context.network
        }
    
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
        if 'inputs' in builder_config:
            for input_config in builder_config['inputs']:
                if input_config['type'] == 'address':
                    builder.add_input_address(input_config['address'])
                elif input_config['type'] == 'utxo':
                    builder.add_input(input_config['utxo'])
                elif input_config['type'] == 'script_input':
                    builder.add_script_input(
                        input_config['utxo'],
                        script=input_config['script'],
                        redeemer=input_config['redeemer']
                    )
        
        if 'outputs' in builder_config:
            for output in builder_config['outputs']:
                builder.add_output(output)
        
        if 'mint' in builder_config:
            builder.mint = builder_config['mint']
        
        if 'minting_scripts' in builder_config:
            for script_config in builder_config['minting_scripts']:
                builder.add_minting_script(
                    script=script_config['script'],
                    redeemer=script_config['redeemer']
                )
        
        if 'required_signers' in builder_config:
            builder.required_signers = builder_config['required_signers']
        
        return builder
    
    def sign_and_submit_transaction(
        self, 
        builder: pc.TransactionBuilder, 
        signing_keys: List[pc.ExtendedSigningKey],
        change_address: pc.Address
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
                'success': True,
                'tx_id': tx_id,
                'transaction': signed_tx,
                'explorer_url': self.chain_context.get_explorer_url(tx_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'transaction': None
            }