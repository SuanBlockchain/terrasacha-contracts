"""
Complete Cardano dApp with OpShin Smart Contracts
This implementation creates a comprehensive dApp with wallet management,
smart contracts, and transaction handling capabilities.
"""

import os
import json
import pathlib
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
from opshin.builder import build, PlutusContract
from opshin.prelude import *

from dotenv import load_dotenv
import pathlib

from terrasacha_contracts.types import PREFIX_PROTOCOL_NFT, PREFIX_USER_NFT, DatumProtocol, Mint
from terrasacha_contracts.util import unique_token_name

# Load .env from project root (parent of tests directory)
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / 'tests/.env'
load_dotenv(ENV_FILE)  # Load once with absolute path

# Load environment variables
# load_dotenv()

class CardanoDApp:
    """Main dApp class that handles wallet management and smart contract interactions"""
    
    def __init__(self):
        self.network = os.getenv("network", "testnet")
        self.wallet_mnemonic = os.getenv("wallet_mnemonic")
        self.blockfrost_api_key = os.getenv("blockfrost_api_key")
        self.cardano_explorer_url = "https://preview.cexplorer.io" if self.network == "testnet" else "https://cexplorer.io"
        self.contracts_dir ="./src/terrasacha_contracts"
        
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

        self.minting_contracts_path = pathlib.Path(self.contracts_dir) / "minting_policies"
        self.spending_contracts_path = pathlib.Path(self.contracts_dir) / "validators"

        # Initialize wallet
        self._setup_wallet()
        
        # Store wallet addresses and keys for easy access
        self.addresses = []
        self.signing_keys = []
        self._generate_addresses(10)  # Generate 10 addresses by default
        
        # Smart contract instances
        self.contracts = {}
        self._compile_contracts()

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

        protocol_nfts_path = self.minting_contracts_path.joinpath("protocol_nfts.py")

        protocol_nft_contract = build(protocol_nfts_path)


        self.contracts["protocol_nfts"] = PlutusContract(protocol_nft_contract)
        
        print("Smart contracts compiled successfully!")

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
            policy_id = contract.policy_id
            # contract_address = pc.Address(pc.ScriptHash(policy_id), network=self.cardano_network)
            if self.cardano_network == "mainnet":
                contract_address = contract.mainnet_addr
            else:
                contract_address = contract.testnet_addr
            print(f"{name:15s} | PolicyId: {policy_id} | Address: {contract_address.encode()}")
        
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
            try:
                if self.cardano_network == "mainnet":
                    contract_address = contract.mainnet_addr
                else:
                    contract_address = contract.testnet_addr
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

    def _test_contracts_menu(self):
        """Test smart contracts submenu"""
        print("\nTEST SMART CONTRACTS")
        print("-" * 30)
        print("Contract testing functionality would go here.")
        print("This would include unit tests for each contract validator function.")

        for name, contract in self.contracts.items():
            print(f"Testing contract: {name}")
            # Here you would call the test functions for each contract
            # For example: test_contract(contract)
            # test_minting_contract(contract)
            self.test_minting_contract(contract)

    def test_minting_contract(self, contract: PlutusContract):
        """Test the minting functionality of the contract"""
        # print(f"Testing minting contract: {self.contracts['protocol_nfts'].blueprint}")
        # Here you would call the actual test functions for the contract
        # For example: assert contract.mint() == expected_result
        
        # Create transaction builder
        builder = pc.TransactionBuilder(self.context)

        # Get contract info
        minting_script: pc.PlutusV2Script = contract.cbor
        minting_policy_id = pc.ScriptHash(bytes.fromhex(contract.policy_id))
        contract_address = contract.testnet_addr
        

        from_address = self.addresses[0]['enterprise_address']
        utxos = self.context.utxos(from_address)
        signing_key = self.addresses[0]['signing_key']

        utxo_to_spend = None
        for utxo in utxos:
            if utxo.output.amount.coin > 3000000:
                utxo_to_spend = utxo
                break
        assert utxo_to_spend is not None, "No suitable UTXO found for minting test"

        builder.add_input(utxo_to_spend)
        oref = TxOutRef(
            id=TxId(utxo_to_spend.input.transaction_id.payload),
            idx=utxo_to_spend.input.index,
        )

        # Create the tokens
        # Generate token names using the actual utility function
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)
        
        # Create assets to mint
        # protocol_nft_asset = pc.Asset({pc.AssetName(protocol_token_name): 1})
        # user_nft_asset = pc.Asset({pc.AssetName(user_token_name): 1})

        protocol_nft_asset = pc.MultiAsset({minting_policy_id: pc.Asset({pc.AssetName(protocol_token_name): 1})})
        user_nft_asset = pc.MultiAsset({minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})})

        # protocol_nft_asset = pc.MultiAsset.from_primitive({bytes(minting_policy_id): { protocol_token_name: 1 }})
        # user_nft_asset = pc.MultiAsset.from_primitive({bytes(minting_policy_id): { user_token_name: 1 }})

        total_mint = protocol_nft_asset.union(user_nft_asset)

        # total_mint = pc.MultiAsset({
        #     minting_policy_id: { protocol_nft_asset, user_nft_asset }
        # })
        builder.mint = total_mint
        
        # Create contract output
        builder.add_minting_script(
            script=minting_script,
            redeemer=pc.Redeemer(Mint())  # Mint redeemer
        )

        # Add protocol output (send protocol NFT to protocol address)
        payment_vkey = self.payment_skey.to_verification_key().hash()
        protocol_datum = DatumProtocol(
            protocol_admin=[payment_vkey.payload],
            protocol_fee=1000000,
            oracle_id=b"oracle_integration_test",
            project_id=b"project_integration_test",
        )

        protocol_value = pc.Value(0, protocol_nft_asset)

        min_val = pc.min_lovelace(
            self.context,
            output=pc.TransactionOutput(
                contract_address,
                protocol_value,
                datum=protocol_datum,
            ),
        )
        protocol_output = pc.TransactionOutput(
            address=contract_address,
            amount=pc.Value(coin=min_val, multi_asset=protocol_nft_asset),
            datum=protocol_datum,
        )
        builder.add_output(protocol_output)

        user_value = pc.Value(0, user_nft_asset)

        min_val = pc.min_lovelace(
            self.context,
            output=pc.TransactionOutput(
                from_address,
                user_value,
                datum=protocol_datum,
            ),
        )
        # Add user output (send user NFT to user address)
        user_output = pc.TransactionOutput(
            address=from_address,
            amount=pc.Value(coin=min_val, multi_asset=user_nft_asset),
            datum=None,
        )
        builder.add_output(user_output)

        # Build transaction
        signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

        return signed_tx


class TestCardanoDApp:

    def setup_method(self):
        self.dapp = CardanoDApp()

    def test_contracts_menu(self):

        for name, contract in self.dapp.contracts.items():
            print(f"Testing contract: {name}")
            signed_tx = self.dapp.test_minting_contract(contract)

            # Submit
            tx_id = self.dapp.submit_transaction(signed_tx)
            
            if tx_id:
                print(f"Funds locked successfully! Transaction ID: {tx_id}")
                # print(f"Unlock time: {datetime.fromtimestamp(unlock_timestamp/1000)}")
                
            return tx_id

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
    
    # try:
    # Initialize the dApp
    print("Initializing Cardano dApp...")
    dapp = CardanoDApp()
    
    # Display initial wallet info
    dapp.display_wallet_info()
    
    # Start interactive menu
    input("\nPress Enter to continue to interactive menu...")

    dapp.interactive_menu()

    # except Exception as e:
    #     print(f"Error initializing dApp: {e}")
    #     print("Please check your environment variables and network connection.")


if __name__ == "__main__":
    main()