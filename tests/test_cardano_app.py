import os
import json
import pathlib
import time
from typing import Dict, Optional, Any

from blockfrost import ApiError, ApiUrls, BlockFrostApi
from dotenv import load_dotenv
import pycardano as pc
import uplc.ast
from opshin.builder import build, PlutusContract
from opshin.prelude import *

from dotenv import load_dotenv
import pathlib

from terrasacha_contracts.types import PREFIX_PROTOCOL_NFT, PREFIX_USER_NFT, DatumProtocol, Mint
from terrasacha_contracts.util import unique_token_name
from menu_formatter import MenuFormatter

# Load .env from project root (parent of tests directory)
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / 'tests/.env'
load_dotenv(ENV_FILE)  # Load once with absolute path

class CardanoDApp:
    """Main dApp class that handles wallet management and smart contract interactions"""
    
    def __init__(self):
        self.network = os.getenv("network", "testnet")
        self.wallet_mnemonic = os.getenv("wallet_mnemonic")
        self.blockfrost_api_key = os.getenv("blockfrost_api_key")
        self.cardanoscan = "https://preview.cardanoscan.io" if self.network == "testnet" else "https://cardanoscan.io"
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
        self.contract_metadata = {}  # Store compilation metadata
        self.compilation_utxo = None  # Store the UTXO used for compilation
        
        # Initialize menu formatter
        self.menu = MenuFormatter()
        
        # Try to load existing contracts
        self._load_contracts()
        
        # self._compile_contracts()

#############################################
# Generic functions
#############################################
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
        
        # Check and display balances
        print(f"\nCHECKING BALANCES...")
        balances = self.check_balances()
        
        print(f"\nBALANCE SUMMARY:")
        print(f"Enterprise Address: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA")
        print(f"Staking Address: {balances['main_addresses']['staking']['balance']/1_000_000:.6f} ADA")
        
        print(f"\nTOTAL WALLET BALANCE: {balances['total_balance']/1_000_000:.6f} ADA")
        
        return balances

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
                return tx_id
            else:
                print("Failed to create transaction.")
                
        except Exception as e:
            print(f"Error in send ADA: {e}")

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

#############################################
# Contract State Management and Persistence
#############################################
    def _get_contracts_file_path(self) -> pathlib.Path:
        """Get the path for contracts storage file"""
        return pathlib.Path(f"contracts_{self.network}.json")

    def _save_contracts(self):
        """Save compiled contracts to disk with metadata"""
        if not self.contracts:
            return
            
        contracts_data = {
            'network': self.network,
            'compilation_timestamp': time.time(),
            'compilation_utxo': self.compilation_utxo,
            'contracts': {}
        }
        
        for name, contract in self.contracts.items():
            contracts_data['contracts'][name] = {
                'policy_id': contract.policy_id,
                'testnet_addr': str(contract.testnet_addr),
                'mainnet_addr': str(contract.mainnet_addr),
                'cbor_hex': contract.cbor.hex()
            }
            
        try:
            with open(self._get_contracts_file_path(), 'w') as f:
                json.dump(contracts_data, f, indent=2)
            self.menu.print_success(f"Contracts saved to {self._get_contracts_file_path()}")
        except Exception as e:
            self.menu.print_error(f"Failed to save contracts: {e}")

    def _load_contracts(self):
        """Load compiled contracts from disk if available"""
        contracts_file = self._get_contracts_file_path()
        if not contracts_file.exists():
            return
            
        try:
            with open(contracts_file, 'r') as f:
                contracts_data = json.load(f)
            
            # Validate network matches
            if contracts_data.get('network') != self.network:
                self.menu.print_warning(f"Contract network mismatch (saved: {contracts_data.get('network')}, current: {self.network})")
                return
                
            # Load compilation UTXO
            self.compilation_utxo = contracts_data.get('compilation_utxo')
            
            # Load contracts (we'll implement this when we have PlutusContract reconstruction)
            self.menu.print_info(f"Found existing contracts from {contracts_file}")
            
        except Exception as e:
            self.menu.print_error(f"Failed to load contracts: {e}")

    def _is_compilation_utxo_available(self) -> bool:
        """Check if the compilation UTXO is still available"""
        if not self.compilation_utxo:
            return False
        try:
            utxos = self.context.utxos(self.addresses[0]['enterprise_address'])
            for utxo in utxos:
                if (utxo.input.transaction_id.payload.hex() == self.compilation_utxo['tx_id'] and 
                    utxo.input.index == self.compilation_utxo['index']):
                    return True
            return False
        except Exception:
            return False

    def _get_contract_status(self) -> str:
        """Get current contract compilation status"""
        if not self.contracts:
            return "Not compiled"
        elif not self.compilation_utxo:
            return "Compiled (unknown UTXO)"
        elif self._is_compilation_utxo_available():
            return "✓ Ready"
        else:
            return "⚠ UTXO consumed"

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
            if signed_tx.id:
                print(f"Transaction submitted successfully! TX ID: {signed_tx.id}")
                print(f"Check your transaction at: {self.cardanoscan}/transaction/{signed_tx.id}")
            else:
                print("Failed to submit transaction.")
            return signed_tx.id
        except ApiError as e:
            print(f"Error submitting transaction: {e}")
            return None
#############################################
# Functions specific to contracts
#############################################
    def _display_contracts_info(self):
        """Display comprehensive contract information with professional formatting"""
        self.menu.print_header("CONTRACT INFORMATION", "Addresses, Balances & Status")
        
        if not self.contracts:
            self.menu.print_error("No contracts compiled yet. Please compile contracts first.")
            input("\nPress Enter to continue...")
            return
        
        # Display compilation info
        if self.compilation_utxo:
            utxo_status = "✓ Available" if self._is_compilation_utxo_available() else "✗ Consumed"
            self.menu.print_section("COMPILATION INFORMATION")
            print(f"│ Compilation UTXO: {self.compilation_utxo['tx_id'][:16]}...:{self.compilation_utxo['index']}")
            print(f"│ UTXO Amount: {self.compilation_utxo['amount']/1_000_000:.6f} ADA")
            print(f"│ UTXO Status: {utxo_status}")
            print()
        
        # Display contract details
        self.menu.print_section("CONTRACT DETAILS")
        
        for name, contract in self.contracts.items():
            try:
                contract_address = contract.testnet_addr if self.cardano_network == pc.Network.TESTNET else contract.mainnet_addr
                network_label = "Testnet" if self.cardano_network == pc.Network.TESTNET else "Mainnet"
                
                # Check balance
                try:
                    utxos = self.api.address_utxos(str(contract_address))
                    balance = sum(int(utxo.amount[0].quantity) for utxo in utxos if utxo.amount[0].unit == 'lovelace')
                    balance_ada = balance / 1_000_000
                    status = "✓" if balance > 0 else "○"
                except:
                    balance_ada = 0.0
                    status = "○"
                
                self.menu.print_contract_info(
                    name=name.upper(),
                    policy_id=contract.policy_id,
                    address=str(contract_address),
                    balance=balance_ada,
                    status=status
                )
                
            except Exception as e:
                self.menu.print_error(f"Error getting info for {name}: {e}")
        
        self.menu.print_footer()
        input("\nPress Enter to continue...")

    def _compile_contracts(self, force: bool = False):
        """Compile OpShin smart contracts with smart recompilation logic"""
        
        # Check if we need to compile
        if not force and self.contracts and self.compilation_utxo and self._is_compilation_utxo_available():
            self.menu.print_info("Contracts already compiled and UTXO available - skipping compilation")
            return
        
        self.menu.print_info("Compiling smart contracts...")

        ##############################################
        # Find and validate UTXO for compilation
        ##############################################
        utxos = self.context.utxos(self.addresses[0]['enterprise_address'])

        utxo_to_spend = None
        for utxo in utxos:
            if utxo.output.amount.coin > 3000000:
                utxo_to_spend = utxo
                break
        assert utxo_to_spend is not None, "No suitable UTXO found for compilation (need >3 ADA)"
        
        # Store compilation UTXO metadata
        self.compilation_utxo = {
            'tx_id': utxo_to_spend.input.transaction_id.payload.hex(),
            'index': utxo_to_spend.input.index,
            'amount': utxo_to_spend.output.amount.coin
        }

        oref = TxOutRef(
            id=TxId(utxo_to_spend.input.transaction_id.payload),
            idx=utxo_to_spend.input.index
        )
        
        self.menu.print_info(f"Using UTXO: {self.compilation_utxo['tx_id'][:16]}...:{self.compilation_utxo['index']} ({self.compilation_utxo['amount']/1_000_000:.2f} ADA)")

        ##############################################
        # Section to build the protocol_nfts
        ##############################################
        protocol_nfts_path = self.minting_contracts_path.joinpath("protocol_nfts.py")
        protocol_nft_contract = build(protocol_nfts_path, oref)
        self.contracts["protocol_nfts"] = PlutusContract(protocol_nft_contract)

        ##############################################
        # Section to build the protocol
        ##############################################
        protocol_path = self.spending_contracts_path.joinpath("protocol.py")
        protocol_contract = build(protocol_path, oref)
        self.contracts["protocol"] = PlutusContract(protocol_contract)

        self.menu.print_success("Smart contracts compiled successfully!")
        
        # Save contracts to disk
        self._save_contracts()

#############################################
# Interactive main menu
#############################################

    def interactive_menu(self):
        """Interactive menu for dApp operations"""
        while True:
            # Get current status
            balances = self.check_balances()
            contract_status = self._get_contract_status()
            
            # Display header and status
            self.menu.print_header("TERRASACHA CARDANO DAPP", "Smart Contract Management Interface")
            self.menu.print_status_bar(
                network=self.network.upper(),
                balance=balances['total_balance'] / 1_000_000,
                contracts_status=contract_status
            )
            
            # Display menu options
            self.menu.print_section("MAIN MENU")
            self.menu.print_menu_option("1", "Display Wallet Info & Balances")
            self.menu.print_menu_option("2", "Generate New Addresses")
            self.menu.print_menu_option("3", "Send ADA")
            self.menu.print_menu_option("4", "Enter Contract Menu", "💼" if self.contracts else "")
            self.menu.print_menu_option("5", "Export Wallet Data")
            self.menu.print_separator()
            self.menu.print_menu_option("0", "Exit Application")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-5)")

            if choice == "0":
                self.menu.print_info("Goodbye! Thanks for using Terrasacha dApp")
                break
            elif choice == "1":
                self.display_wallet_info()
            elif choice == "2":
                try:
                    count = int(self.menu.get_input("How many new addresses to generate"))
                    self._generate_addresses(count)
                    self.menu.print_success(f"Generated {count} new addresses!")
                except ValueError:
                    self.menu.print_error("Please enter a valid number")
            elif choice == "3":
                self._send_ada_menu()
            elif choice == "4":
                self.contract_submenu()
            elif choice == "5":
                self._export_wallet_menu()
            else:
                self.menu.print_error("Invalid option. Please try again.")
    
    def _test_contracts(self):
        """Test smart contracts submenu with enhanced validation"""
        self.menu.print_header("CONTRACT TESTING", "Mint Protocol & User NFTs")
        
        if not self.contracts:
            self.menu.print_error("No contracts available for testing")
            return
        
        # Validate UTXO availability
        if self.compilation_utxo and not self._is_compilation_utxo_available():
            self.menu.print_warning(
                "⚠ WARNING: The UTXO used for compilation has been consumed!\n"
                "Testing will use a different UTXO and may produce different token names."
            )
            if not self.menu.confirm_action("Continue with testing?"):
                return
        
        self.menu.print_info("This will mint two NFTs: one protocol token and one user token")
        destin_address = self.menu.get_input("Enter destination address for user token (or press Enter for default)")
        
        if not destin_address.strip():
            destin_address = None
            self.menu.print_info("Using default address (wallet address)")
        
        try:
            self.menu.print_info("Building transaction...")
            signed_tx = self.test_minting_contract(destin_address)
            self.menu.print_success(f"Transaction built successfully!")
            print(f"TX ID: {signed_tx.id.payload.hex()}")
            
            if self.menu.confirm_action("Submit transaction to network?"):
                self.menu.print_info("Submitting transaction...")
                tx_id = self.submit_transaction(signed_tx)
                
                if tx_id:
                    self.menu.print_success("Transaction submitted successfully!")
                    
                    # Update UTXO status since it will be consumed
                    if self.compilation_utxo and self._is_compilation_utxo_available():
                        self.menu.print_warning(
                            "Note: The compilation UTXO will be consumed after this transaction.\n"
                            "Future contract operations will require recompilation with a new UTXO."
                        )
                else:
                    self.menu.print_error("Failed to submit transaction")
            else:
                self.menu.print_info("Transaction cancelled by user")
                
        except Exception as e:
            self.menu.print_error(f"Testing failed: {e}")
        
        input("\nPress Enter to continue...")

    def test_minting_contract(self, destin_address: pc.Address = None):
        """Test the minting functionality of the contract"""
        # Create transaction builder
        builder = pc.TransactionBuilder(self.context)

        # Get contract info
        protocol_nfts_contract = self.contracts["protocol_nfts"]
        minting_script: pc.PlutusV2Script = protocol_nfts_contract.cbor
        minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))

        protocol_contract = self.contracts["protocol"]
        protocol_address = protocol_contract.testnet_addr

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

        # Generate token names using the actual utility function
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)
        
        # Create assets to mint
        protocol_nft_asset = pc.MultiAsset({minting_policy_id: pc.Asset({pc.AssetName(protocol_token_name): 1})})
        user_nft_asset = pc.MultiAsset({minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})})

        total_mint = protocol_nft_asset.union(user_nft_asset)
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
                protocol_address,
                protocol_value,
                datum=protocol_datum,
            ),
        )
        protocol_output = pc.TransactionOutput(
            address=protocol_address,
            amount=pc.Value(coin=min_val, multi_asset=protocol_nft_asset),
            datum=protocol_datum,
        )
        builder.add_output(protocol_output)

        user_value = pc.Value(0, user_nft_asset)

        if destin_address is None:
            destin_address = from_address

        min_val = pc.min_lovelace(
            self.context,
            output=pc.TransactionOutput(
                destin_address,
                user_value,
                datum=protocol_datum,
            ),
        )
        # Add user output (send user NFT to user address)
        user_output = pc.TransactionOutput(
            address=destin_address,
            amount=pc.Value(coin=min_val, multi_asset=user_nft_asset),
            datum=None,
        )
        builder.add_output(user_output)

        # Build transaction
        signed_tx = builder.build_and_sign([signing_key], change_address=from_address)

        return signed_tx


    def test_burn_tokens(self):
        """Test burning tokens"""
        builder = pc.TransactionBuilder(self.context)

         # Get contract info
        protocol_nfts_contract = self.contracts["protocol_nfts"]
        minting_script: pc.PlutusV2Script = protocol_nfts_contract.cbor
        minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))

        protocol_contract = self.contracts["protocol"]
        protocol_address = protocol_contract.testnet_addr


#############################################
# Interactive contract submenu
#############################################
    def contract_submenu(self):
        """Interactive menu for contract operations"""
        
        # Check if we need to compile contracts initially
        if not self.contracts:
            self.menu.print_info("No contracts found - compiling now...")
            try:
                self._compile_contracts()
            except Exception as e:
                self.menu.print_error(f"Failed to compile contracts: {e}")
                return
        
        while True:
            # Get current status
            contract_status = self._get_contract_status()
            utxo_available = self._is_compilation_utxo_available() if self.compilation_utxo else False
            
            # Display header
            self.menu.print_header("SMART CONTRACT MANAGEMENT", f"Status: {contract_status}")
            self.menu.print_breadcrumb(["Main Menu", "Contract Menu"])
            
            # Show UTXO warning if needed
            if self.compilation_utxo and not utxo_available:
                self.menu.print_warning(
                    f"Compilation UTXO consumed! Current contracts are preserved but new "
                    f"compilation will use different UTXO and create new contract addresses."
                )
            
            # Display menu options with status
            self.menu.print_section("CONTRACT OPERATIONS")
            
            # Status indicators for each option
            info_status = "✓" if self.contracts else "✗"
            compile_status = "⚠" if self.compilation_utxo and not utxo_available else "✓" if self.contracts else ""
            test_status = "✓" if self.contracts and utxo_available else "⚠" if self.contracts else "✗"
            
            self.menu.print_menu_option("1", "Display Contracts Info", info_status)
            self.menu.print_menu_option("2", "Compile/Recompile Contracts", compile_status)
            self.menu.print_menu_option("3", "Test Contracts (Mint NFTs)", test_status)
            self.menu.print_separator()
            self.menu.print_menu_option("0", "Back to Main Menu")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-3)")

            if choice == "0":
                self.menu.print_info("Returning to main menu...")
                break
            elif choice == "1":
                self._display_contracts_info()
            elif choice == "2":
                if self.contracts and self.compilation_utxo and self._is_compilation_utxo_available():
                    if not self.menu.confirm_action("Contracts already compiled and ready. Force recompile?"):
                        continue
                
                try:
                    self._compile_contracts(force=True)
                except Exception as e:
                    self.menu.print_error(f"Compilation failed: {e}")
                    
            elif choice == "3":
                if not self.contracts:
                    self.menu.print_error("No contracts compiled. Please compile contracts first.")
                elif self.compilation_utxo and not self._is_compilation_utxo_available():
                    self.menu.print_warning("Compilation UTXO consumed - testing may fail or create different tokens")
                    if not self.menu.confirm_action("Continue with testing anyway?"):
                        continue
                
                self._test_contracts()
            else:
                self.menu.print_error("Invalid option. Please try again.")

class TestCardanoDApp:

    def setup_method(self):
        self.dapp = CardanoDApp()

    def test_compile_contracts(self):
        self.dapp.compile_contracts()

    def test_contracts_menu(self):

        for name, contract in self.dapp.contracts.items():
            print(f"Testing contract: {name}")
            signed_tx = self.dapp.test_minting_contract(contract)

            # Submit
            tx_id = self.dapp.submit_transaction(signed_tx)
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

    dapp.interactive_menu()

if __name__ == "__main__":
    main()