"""
Cardano Wallet Management

Pure wallet functionality without console dependencies.
Handles wallet creation, address generation, and key management.
"""

import os
from typing import Dict, List, Any, Optional
from blockfrost import ApiError, BlockFrostApi
import pycardano as pc


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
            network=self.cardano_network
        )
        
        self.staking_address = pc.Address(
            payment_part=self.payment_skey.to_verification_key().hash(),
            staking_part=self.staking_skey.to_verification_key().hash(),
            network=self.cardano_network
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
                payment_part=payment_skey.to_verification_key().hash(),
                network=self.cardano_network
            )
            
            # Staking enabled address
            staking_addr = pc.Address(
                payment_part=payment_skey.to_verification_key().hash(),
                staking_part=self.staking_skey.to_verification_key().hash(),
                network=self.cardano_network
            )
            
            addr_info = {
                'index': i,
                'derivation_path': payment_derivation,
                'signing_key': payment_skey,
                'enterprise_address': enterprise_addr,
                'staking_address': staking_addr,
                'balance': 0
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
            'network': self.network,
            'main_addresses': {
                'enterprise': str(self.enterprise_address),
                'staking': str(self.staking_address)
            },
            'derived_addresses': [
                {
                    'index': addr['index'],
                    'path': addr['derivation_path'],
                    'enterprise_address': str(addr['enterprise_address']),
                    'staking_address': str(addr['staking_address'])
                }
                for addr in self.addresses
            ]
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
            'main_addresses': {
                'enterprise': {'address': str(self.enterprise_address), 'balance': 0},
                'staking': {'address': str(self.staking_address), 'balance': 0}
            },
            'derived_addresses': [],
            'total_balance': 0
        }
        
        try:
            # Check main enterprise address
            enterprise_utxos = api.address_utxos(str(self.enterprise_address))
            enterprise_balance = sum(
                int(utxo.amount[0].quantity) 
                for utxo in enterprise_utxos 
                if utxo.amount[0].unit == 'lovelace'
            )
            balances['main_addresses']['enterprise']['balance'] = enterprise_balance
            
            # Check derived addresses
            for addr_info in self.addresses[:limit_addresses]:
                try:
                    utxos = api.address_utxos(str(addr_info['enterprise_address']))
                    balance = sum(
                        int(utxo.amount[0].quantity) 
                        for utxo in utxos 
                        if utxo.amount[0].unit == 'lovelace'
                    )
                    addr_info['balance'] = balance
                    
                    balances['derived_addresses'].append({
                        'index': addr_info['index'],
                        'address': str(addr_info['enterprise_address']),
                        'balance': balance
                    })
                    
                except ApiError:
                    # Address might not exist on chain yet
                    balances['derived_addresses'].append({
                        'index': addr_info['index'],
                        'address': str(addr_info['enterprise_address']),
                        'balance': 0
                    })
            
            # Calculate total
            balances['total_balance'] = enterprise_balance + sum(
                addr['balance'] for addr in balances['derived_addresses']
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
        return addr_info['staking_address'] if use_staking else addr_info['enterprise_address']
    
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
            
        return self.addresses[index - 1]['signing_key']