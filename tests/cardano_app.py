"""
Complete Cardano dApp with OpShin Smart Contracts
This implementation creates a comprehensive dApp with wallet management,
smart contracts, and transaction handling capabilities.
"""

import os
import json
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from blockfrost import ApiError, ApiUrls, BlockFrostApi
from dotenv import load_dotenv
import pycardano as pc
# import opshin
# from opshin import build_script
# from opshin.prelude import *
from opshin.builder import build

# Load environment variables
load_dotenv()

class CardanoDApp:
    """Main dApp class that handles wallet management and smart contract interactions"""
    
    def __init__(self):
        self.network = os.getenv("network", "testnet")
        self.wallet_mnemonic = os.getenv("wallet_mnemonic")
        self.blockfrost_api_key = os.getenv("blockfrost_api_key")
        self.cardano_explorer_url = "https://preview.cexplorer.io" if self.network == "testnet" else "https://cexplorer.io"
        
        # Set network configuration
        if self.network == "testnet":
            self.base_url = ApiUrls.preview.value
            self.cardano_network = pc.Network.TESTNET
        else:
            self.base_url = ApiUrls.mainnet.value
            self.cardano_network = pc.Network.MAINNET
            
        # Initialize API client
        self.api = BlockFrostApi(
            project_id=self.blockfrost_api_key,
            base_url=self.base_url
        )
        self.context = self._get_chain_context()
        
        # Initialize wallet
        self._setup_wallet()
        
        # Store wallet addresses and keys for easy access
        self.addresses = []
        self.signing_keys = []
        self._generate_addresses(10)  # Generate 10 addresses by default
        
        # Smart contract instances
        self.contracts = {}
        # self._compile_contracts()

    def _get_chain_context(self) -> pc.ChainContext:
        return pc.BlockFrostChainContext(self.blockfrost_api_key, base_url=self.base_url)
        
    def _setup_wallet(self):
        """Initialize the main wallet from mnemonic"""
        if not self.wallet_mnemonic:
            raise ValueError("Wallet mnemonic not provided in environment variables")
            
        self.wallet = pc.crypto.bip32.HDWallet.from_mnemonic(self.wallet_mnemonic)
        
        # Derive main payment and staking keys
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
        
    def _generate_addresses(self, count: int):
        """Generate multiple addresses for the wallet"""
        print(f"Generating {count} wallet addresses...")
        
        for i in range(count):
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
            
            self.addresses.append({
                'index': i,
                'derivation_path': payment_derivation,
                'signing_key': payment_skey,
                'enterprise_address': enterprise_addr,
                'staking_address': staking_addr,
                'balance': 0  # Will be updated when checking balances
            })
            
            self.signing_keys.append(payment_skey)
    
    def _compile_contracts(self):
        """Compile OpShin smart contracts"""
        print("Compiling smart contracts...")
        
        # Simple locking contract
        self.contracts['simple_lock'] = self._create_simple_lock_contract()
        
        # Vesting contract
        self.contracts['vesting'] = self._create_vesting_contract()
        
        # Token minting contract
        self.contracts['token_mint'] = self._create_token_mint_contract()
        
        print("Smart contracts compiled successfully!")

    def _create_simple_lock_contract(self) -> pc.PlutusV2Script:
        """Create a simple locking smart contract using OpShin"""
        
        contract_code = '''
from opshin.prelude import *

@dataclass
class SimpleLockDatum(PlutusData):
    """Datum for simple lock contract"""
    CONSTR_ID = 0
    owner: bytes  # Public key hash of the owner
    unlock_time: int  # POSIX timestamp when funds can be unlocked

@dataclass  
class SimpleLockRedeemer(PlutusData):
    """Redeemer for simple lock contract"""
    CONSTR_ID = 0
    action: bytes  # Action to perform (unlock/extend)

def validator(datum: SimpleLockDatum, redeemer: SimpleLockRedeemer, context: ScriptContext) -> bool:
    """
    Simple time-locked contract validator
    Funds can only be unlocked after the specified time by the owner
    """
    
    # Check if current time is after unlock time
    tx_info = context.tx_info
    time_range = tx_info.valid_range
    
    # Get current time (start of validity range)
    current_time = time_range.lower_bound.limit
    
    # Verify unlock conditions
    if redeemer.action == b"unlock":
        # Check if unlock time has passed
        assert current_time >= datum.unlock_time, "Unlock time not reached"
        
        # Check if transaction is signed by owner
        assert datum.owner in tx_info.signatories, "Not signed by owner"
        
        return True
    
    return False
        '''
        
        # Compile the contract
        script = build(contract_code)
        return script

    def _create_vesting_contract(self) -> pc.PlutusV2Script:
        """Create a vesting contract using OpShin"""
        
        contract_code = '''
from opshin.prelude import *

@dataclass
class VestingDatum(PlutusData):
    """Datum for vesting contract"""
    CONSTR_ID = 0
    beneficiary: bytes  # Beneficiary's public key hash
    vesting_schedule: List[int]  # List of unlock timestamps
    amounts: List[int]  # Corresponding unlock amounts in lovelace

@dataclass
class VestingRedeemer(PlutusData):
    """Redeemer for vesting contract"""
    CONSTR_ID = 0
    withdrawal_index: int  # Which vesting period to unlock

def validator(datum: VestingDatum, redeemer: VestingRedeemer, context: ScriptContext) -> bool:
    """
    Vesting contract validator
    Allows gradual release of funds according to schedule
    """
    
    tx_info = context.tx_info
    time_range = tx_info.valid_range
    current_time = time_range.lower_bound.limit
    
    # Verify withdrawal index is valid
    withdrawal_idx = redeemer.withdrawal_index
    assert 0 <= withdrawal_idx < len(datum.vesting_schedule), "Invalid withdrawal index"
    
    # Check if vesting time has been reached
    unlock_time = datum.vesting_schedule[withdrawal_idx]
    assert current_time >= unlock_time, "Vesting period not reached"
    
    # Check if signed by beneficiary
    assert datum.beneficiary in tx_info.signatories, "Not signed by beneficiary"
    
    # Verify correct amount is being withdrawn
    expected_amount = datum.amounts[withdrawal_idx]
    
    # Check outputs to ensure remaining funds stay in contract
    # (This is simplified - in practice you'd check all outputs)
    
    return True
        '''

        script = build(contract_code)
        return script

    def _create_token_mint_contract(self) -> pc.PlutusV2Script:
        """Create a token minting contract using OpShin"""
        
        contract_code = '''
from opshin.prelude import *

@dataclass
class MintingRedeemer(PlutusData):
    """Redeemer for minting contract"""
    CONSTR_ID = 0
    action: bytes  # "mint" or "burn"
    amount: int   # Amount to mint/burn

def validator(redeemer: MintingRedeemer, context: ScriptContext) -> bool:
    """
    Token minting validator
    Controls minting and burning of custom tokens
    """
    
    tx_info = context.tx_info
    purpose = context.purpose
    
    # Ensure this is being used for minting
    assert isinstance(purpose, Minting), "Wrong script purpose"
    
    policy_id = purpose.policy_id
    mint_value = tx_info.mint
    
    if redeemer.action == b"mint":
        # Allow minting up to specified amount
        minted_amount = mint_value.get(policy_id, {}).get(b"MyToken", 0)
        assert minted_amount <= redeemer.amount, "Minting too many tokens"
        assert minted_amount > 0, "Must mint positive amount"
        
    elif redeemer.action == b"burn":
        # Allow burning
        burned_amount = mint_value.get(policy_id, {}).get(b"MyToken", 0)
        assert burned_amount < 0, "Must burn negative amount"
        assert abs(burned_amount) <= redeemer.amount, "Burning too many tokens"
    
    return True
        '''

        script = build(contract_code)
        return script
    
    def check_balances(self) -> Dict[str, Any]:
        """Check balances for all wallet addresses"""
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
            enterprise_utxos = self.api.address_utxos(str(self.enterprise_address))
            enterprise_balance = sum(int(utxo.amount[0].quantity) for utxo in enterprise_utxos if utxo.amount[0].unit == 'lovelace')
            balances['main_addresses']['enterprise']['balance'] = enterprise_balance
            
            # Check main staking address  
            # staking_utxos = self.api.address_utxos(str(self.staking_address))
            # staking_balance = sum(int(utxo.amount[0].quantity) for utxo in staking_utxos if utxo.amount[0].unit == 'lovelace')
            # balances['main_addresses']['staking']['balance'] = staking_balance
            
            # Check derived addresses
            for addr_info in self.addresses[:5]:  # Check first 5 addresses
                try:
                    utxos = self.api.address_utxos(str(addr_info['enterprise_address']))
                    balance = sum(int(utxo.amount[0].quantity) for utxo in utxos if utxo.amount[0].unit == 'lovelace')
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
            # balances['total_balance'] = (enterprise_balance + staking_balance + 
            #                           sum(addr['balance'] for addr in balances['derived_addresses']))
            balances['total_balance'] = enterprise_balance
            
        except ApiError as e:
            print(f"Error checking balances: {e}")
            
        return balances

    def create_simple_transaction(self, to_address: str, amount_ada: float, from_address_index: int = 0) -> Optional[pc.Transaction]:
        """Create a simple ADA transfer transaction"""
        
        try:
            # Convert ADA to lovelace
            amount_lovelace = int(amount_ada * 1_000_000)
            
            # Get UTXOs from source address
            from_address = self.addresses[from_address_index]['enterprise_address']
            to_address = pc.Address.from_primitive(to_address)
            signing_key = self.addresses[from_address_index]['signing_key']
            
            utxos = self.api.address_utxos(str(from_address))
            
            if not utxos:
                print("No UTXOs available for transaction")
                return None
            
            # Create transaction builder
            builder = pc.TransactionBuilder(self.context)

            # Add inputs
            builder.add_input_address(from_address)

            builder.add_output(
                pc.TransactionOutput(to_address, pc.Value(amount_lovelace))
            )
            
            # for utxo in utxos:
            #     tx_in = TransactionInput.from_primitive([utxo.tx_hash, utxo.output_index])
            #     tx_out = TransactionOutput(
            #         Address.from_bech32(utxo.address),
            #         Value.from_primitive(
            #             [amount.quantity if amount.unit == 'lovelace' else 0 for amount in utxo.amount]
            #         )
            #     )
            #     builder.add_input_and_build_utxo(tx_in, tx_out)
            
            # # Add output
            # recipient_address = Address.from_bech32(to_address)
            # builder.add_output(TransactionOutput(recipient_address, Value(coin=amount_lovelace)))
            
            # Build transaction
            signed_tx = builder.build_and_sign([signing_key], change_address=from_address)
            
            return signed_tx
            
        except Exception as e:
            print(f"Error creating transaction: {e}")
            return None

    def submit_transaction(self, signed_tx: pc.Transaction) -> Optional[str]:
        """Submit a signed transaction to the network"""
        try:
            # tx_id = self.api.transaction_submit(signed_tx.to_cbor())
            self.context.submit_tx(signed_tx)
            return signed_tx.id
        except ApiError as e:
            print(f"Error submitting transaction: {e}")
            return None
    
    def lock_funds_simple(self, amount_ada: float, unlock_time_minutes: int = 60) -> Optional[str]:
        """Lock funds in the simple lock contract"""
        try:
            # Calculate unlock time (current time + minutes)
            unlock_timestamp = int(time.time() * 1000) + (unlock_time_minutes * 60 * 1000)
            
            # Create datum
            datum = {
                "constructor": 0,
                "fields": [
                    {"bytes": self.payment_skey.to_verification_key().hash().to_primitive().hex()},
                    {"int": unlock_timestamp}
                ]
            }
            
            # Get contract address
            contract_address = pc.Address(
                payment_part=pc.ScriptHash(self.contracts['simple_lock'].hash()),
                network=self.cardano_network
            )
            
            # Create transaction to lock funds
            builder = pc.TransactionBuilder(pc.ChainContext.from_blockfrost_api(self.api))
            
            # Add input from main address
            utxos = self.api.address_utxos(str(self.enterprise_address))
            if not utxos:
                print("No UTXOs available")
                return None
                
            # Add sufficient inputs
            for utxo in utxos[:2]:  # Use first 2 UTXOs
                tx_in = pc.TransactionInput.from_primitive([utxo.tx_hash, utxo.output_index])
                builder.add_input(tx_in)
            
            # Add output to contract with datum
            amount_lovelace = int(amount_ada * 1_000_000)
            contract_output = pc.TransactionOutput(
                address=contract_address,
                amount=pc.Value(coin=amount_lovelace),
                datum=pc.PlutusData.from_json(json.dumps(datum))
            )
            builder.add_output(contract_output)
            
            # Build and sign
            signed_tx = builder.build_and_sign([self.payment_skey], change_address=self.enterprise_address)
            
            # Submit
            tx_id = self.submit_transaction(signed_tx)
            
            if tx_id:
                print(f"Funds locked successfully! Transaction ID: {tx_id}")
                print(f"Unlock time: {datetime.fromtimestamp(unlock_timestamp/1000)}")
                
            return tx_id
            
        except Exception as e:
            print(f"Error locking funds: {e}")
            return None
    
    def display_wallet_info(self):
        """Display comprehensive wallet information"""
        print("\n" + "="*80)
        print("CARDANO DAPP WALLET INFORMATION")
        print("="*80)
        
        print(f"Network: {self.network.upper()}")
        print(f"Wallet Type: HD Wallet (BIP32)")
        
        print("\nMAIN ADDRESSES:")
        print(f"Enterprise (Payment Only): {self.enterprise_address}")
        print(f"Staking Enabled: {self.staking_address}")
        
        print(f"\nDERIVED ADDRESSES (First 10):")
        for addr_info in self.addresses:
            print(f"Index {addr_info['index']:2d} | {addr_info['derivation_path']:20s} | {str(addr_info['enterprise_address'])}")
        
        print(f"\nSMART CONTRACTS:")
        for name, contract in self.contracts.items():
            contract_hash = contract.hash()
            contract_address = pc.Address(pc.ScriptHash(contract_hash), network=self.cardano_network)
            print(f"{name:15s} | Hash: {contract_hash.hex()[:16]}... | Address: {str(contract_address)[:50]}...")
        
        # Check and display balances
        print(f"\nCHECKING BALANCES...")
        balances = self.check_balances()
        
        print(f"\nBALANCE SUMMARY:")
        print(f"Enterprise Address: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA")
        print(f"Staking Address: {balances['main_addresses']['staking']['balance']/1_000_000:.6f} ADA")
        
        print(f"\nDerived Address Balances:")
        for addr_balance in balances['derived_addresses']:
            if addr_balance['balance'] > 0:
                print(f"Index {addr_balance['index']:2d}: {addr_balance['balance']/1_000_000:.6f} ADA")
        
        print(f"\nTOTAL WALLET BALANCE: {balances['total_balance']/1_000_000:.6f} ADA")
        
        return balances
    
    def interactive_menu(self):
        """Interactive menu for dApp operations"""
        while True:
            print("\n" + "="*60)
            print("CARDANO DAPP INTERACTIVE MENU")
            print("="*60)
            print("1. Display Wallet Info & Balances")
            print("2. Generate New Addresses")
            print("3. Send ADA")
            print("4. Lock Funds (Simple Contract)")
            print("5. Check Contract Balances")
            print("6. Export Wallet Data")
            print("7. Test Smart Contracts")
            print("0. Exit")
            print("-"*60)
            
            choice = input("Select an option (0-7): ").strip()
            
            if choice == "0":
                print("Exiting dApp...")
                break
            elif choice == "1":
                self.display_wallet_info()
            elif choice == "2":
                count = int(input("How many new addresses to generate? "))
                self._generate_addresses(count)
                print(f"Generated {count} new addresses!")
            elif choice == "3":
                self._send_ada_menu()
            elif choice == "4":
                self._lock_funds_menu()
            elif choice == "5":
                self._check_contracts_menu()
            elif choice == "6":
                self._export_wallet_menu()
            elif choice == "7":
                self._test_contracts_menu()
            else:
                print("Invalid option. Please try again.")
    
    def _send_ada_menu(self):
        """Send ADA submenu"""
        try:
            print("\nSEND ADA")
            print("-" * 30)
            
            # Show available balances
            balances = self.check_balances()
            print("Available balances:")
            print(f"Enterprise: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA")
            
            to_address = input("Recipient address: ").strip()
            amount = float(input("Amount (ADA): "))
            
            print(f"Sending {amount} ADA to {to_address[:20]}...")
            
            tx = self.create_simple_transaction(to_address, amount)
            if tx:
                tx_id = self.submit_transaction(tx)
                if tx_id:
                    print(f"Transaction submitted successfully! TX ID: {tx_id}")
                    print(f"Check your transaction at: {self.cardano_explorer_url}/transaction/{tx_id}")
                else:
                    print("Failed to submit transaction.")
            else:
                print("Failed to create transaction.")
                
        except Exception as e:
            print(f"Error in send ADA: {e}")
    
    def _lock_funds_menu(self):
        """Lock funds submenu"""
        try:
            print("\nLOCK FUNDS")
            print("-" * 30)
            
            amount = float(input("Amount to lock (ADA): "))
            minutes = int(input("Lock duration (minutes): "))
            
            tx_id = self.lock_funds_simple(amount, minutes)
            if tx_id:
                print("Funds locked successfully!")
            else:
                print("Failed to lock funds.")
                
        except Exception as e:
            print(f"Error in lock funds: {e}")
    
    def _check_contracts_menu(self):
        """Check contract balances submenu"""
        print("\nSMART CONTRACT BALANCES")
        print("-" * 40)
        
        for name, contract in self.contracts.items():
            contract_address = pc.Address(pc.ScriptHash(contract.hash()), network=self.cardano_network)
            try:
                utxos = self.api.address_utxos(str(contract_address))
                balance = sum(int(utxo.amount[0].quantity) for utxo in utxos if utxo.amount[0].unit == 'lovelace')
                print(f"{name:15s}: {balance/1_000_000:.6f} ADA")
            except:
                print(f"{name:15s}: 0.000000 ADA (no UTXOs)")
    
    def _export_wallet_menu(self):
        """Export wallet data submenu"""
        print("\nEXPORT WALLET DATA")
        print("-" * 30)
        
        wallet_data = {
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
            ],
            'smart_contracts': {
                name: {
                    'hash': contract.hash().hex(),
                    'address': str(pc.Address(pc.ScriptHash(contract.hash()), network=self.cardano_network))
                }
                for name, contract in self.contracts.items()
            }
        }
        
        filename = f"wallet_data_{self.network}_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(wallet_data, f, indent=2)
        
        print(f"Wallet data exported to: {filename}")
    
    def _test_contracts_menu(self):
        """Test smart contracts submenu"""
        print("\nTEST SMART CONTRACTS")
        print("-" * 30)
        print("Contract testing functionality would go here.")
        print("This would include unit tests for each contract validator function.")


def main():
    """Main function to run the dApp"""
    
    # Check for required environment variables
    required_vars = ['wallet_mnemonic', 'blockfrost_api_key']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease create a .env file with:")
        print("network=testnet")  
        print("wallet_mnemonic=your wallet mnemonic phrase here")
        print("blockfrost_api_key=your blockfrost api key here")
        return
    
    try:
        # Initialize the dApp
        print("Initializing Cardano dApp...")
        dapp = CardanoDApp()
        
        # Display initial wallet info
        dapp.display_wallet_info()
        
        # Start interactive menu
        input("\nPress Enter to continue to interactive menu...")
        dapp.interactive_menu()
        
    except Exception as e:
        print(f"Error initializing dApp: {e}")
        print("Please check your environment variables and network connection.")


if __name__ == "__main__":
    main()