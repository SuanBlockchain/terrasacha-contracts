"""
Cardano CLI Interface

Console interface that uses the core Cardano library.
Handles user interactions, menus, and display formatting.
"""

import os
import json
import time
from dotenv import load_dotenv
import pathlib
import pycardano as pc

# Load environment variables
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / 'menu/.env'
load_dotenv(ENV_FILE)

# Import core Cardano functionality
from src.cardano_offchain import (
    CardanoWallet,
    CardanoChainContext, 
    CardanoTransactions,
    ContractManager,
    TokenOperations
)
from menu_formatter import MenuFormatter


class CardanoCLI:
    """Console interface for Cardano dApp operations"""
    
    def __init__(self):
        """Initialize the CLI interface"""
        # Get environment variables
        self.network = os.getenv("network", "testnet")
        wallet_mnemonic = os.getenv("wallet_mnemonic")
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        
        if not wallet_mnemonic or not blockfrost_api_key:
            raise ValueError("Missing required environment variables: wallet_mnemonic, blockfrost_api_key")
        
        # Initialize core components
        self.chain_context = CardanoChainContext(self.network, blockfrost_api_key)
        self.wallet = CardanoWallet(wallet_mnemonic, self.network)
        self.transactions = CardanoTransactions(self.wallet, self.chain_context)
        self.contract_manager = ContractManager(self.chain_context)
        self.token_operations = TokenOperations(
            self.wallet, self.chain_context, self.contract_manager, self.transactions
        )
        
        # Initialize menu formatter
        self.menu = MenuFormatter()
        
        # Generate initial addresses
        self.wallet.generate_addresses(10)
    
    def display_wallet_info(self):
        """Display comprehensive wallet information"""
        print("\n" + "="*80)
        print("CARDANO DAPP WALLET INFORMATION")
        print("="*80)
        
        wallet_info = self.wallet.get_wallet_info()
        
        print(f"Network: {self.network.upper()}")
        print(f"Wallet Type: HD Wallet (BIP32)")
        
        print("\nMAIN ADDRESSES:")
        print(f"Enterprise (Payment Only): {wallet_info['main_addresses']['enterprise']}")
        print(f"Staking Enabled: {wallet_info['main_addresses']['staking']}")
        
        print(f"\nDERIVED ADDRESSES (First 10):")
        for addr_info in wallet_info['derived_addresses']:
            print(f"Index {addr_info['index']:2d} | {addr_info['path']:20s} | {addr_info['enterprise_address']}")
        
        # Check and display balances
        print(f"\nCHECKING BALANCES...")
        balances = self.wallet.check_balances(self.chain_context.get_api())
        
        print(f"\nBALANCE SUMMARY:")
        print(f"Enterprise Address: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA")
        
        for addr in balances['derived_addresses']:
            if addr['balance'] > 0:
                print(f"Address {addr['index']}: {addr['balance']/1_000_000:.6f} ADA")
        
        print(f"\nTOTAL WALLET BALANCE: {balances['total_balance']/1_000_000:.6f} ADA")
        
        return balances
    
    def send_ada_menu(self):
        """Send ADA submenu"""
        try:
            print("\nSEND ADA")
            print("-" * 30)
            
            # Show available balances
            balances = self.wallet.check_balances(self.chain_context.get_api())
            print("Available balances:")
            print(f"Enterprise: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA")
            
            to_address = input("Recipient address: ").strip()
            amount = float(input("Amount (ADA): "))
            
            print(f"Sending {amount} ADA to {to_address[:20]}...")
            
            tx = self.transactions.create_simple_transaction(to_address, amount)
            if tx:
                tx_id = self.transactions.submit_transaction(tx)
                if tx_id:
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Transaction submitted successfully! TX ID: {tx_info['tx_id']}")
                    print(f"Check your transaction at: {tx_info['explorer_url']}")
                    return tx_id
            else:
                print("Failed to create transaction.")
                
        except Exception as e:
            print(f"Error in send ADA: {e}")
    
    def export_wallet_menu(self):
        """Export wallet data submenu"""
        print("\nEXPORT WALLET DATA")
        print("-" * 30)
        
        # Get wallet info
        wallet_info = self.wallet.get_wallet_info()
        contracts_info = self.contract_manager.get_contracts_info()
        
        wallet_data = {
            'network': self.network,
            'main_addresses': wallet_info['main_addresses'],
            'derived_addresses': wallet_info['derived_addresses'],
            'smart_contracts': {
                name: {
                    'policy_id': info['policy_id'],
                    'address': info['address']
                }
                for name, info in contracts_info['contracts'].items()
            }
        }
        
        filename = f"wallet_data_{self.network}_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(wallet_data, f, indent=2)
        
        print(f"Wallet data exported to: {filename}")
    
    def display_contracts_info(self):
        """Display comprehensive contract information"""
        self.menu.print_header("CONTRACT INFORMATION", "Addresses, Balances & Status")
        
        contracts_info = self.contract_manager.get_contracts_info()
        
        if not contracts_info['contracts']:
            self.menu.print_error("No contracts compiled yet. Please compile contracts first.")
            input("\nPress Enter to continue...")
            return
        
        # Display compilation info
        if contracts_info['compilation_utxo']:
            utxo = contracts_info['compilation_utxo']
            main_address = self.wallet.get_address(0)
            utxo_available = self.contract_manager._is_compilation_utxo_available(main_address)
            utxo_status = "✓ Available" if utxo_available else "✗ Consumed"
            
            self.menu.print_section("COMPILATION INFORMATION")
            print(f"│ Compilation UTXO: {utxo['tx_id'][:16]}...:{utxo['index']}")
            print(f"│ UTXO Amount: {utxo['amount']/1_000_000:.6f} ADA")
            print(f"│ UTXO Status: {utxo_status}")
            print()
        
        # Display contract details
        self.menu.print_section("CONTRACT DETAILS")
        
        for name, info in contracts_info['contracts'].items():
            status = "✓" if info['balance'] > 0 else "○"
            self.menu.print_contract_info(
                name=name.upper(),
                policy_id=info['policy_id'],
                address=info['address'],
                balance=info['balance_ada'],
                status=status
            )
        
        self.menu.print_footer()
        input("\nPress Enter to continue...")
    
    def test_contracts_menu(self):
        """Test smart contracts submenu"""
        self.menu.print_header("CONTRACT TESTING", "Mint Protocol & User NFTs")
        
        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for testing")
            return
        
        # Check UTXO availability
        main_address = self.wallet.get_address(0)
        compilation_info = self.contract_manager.get_contracts_info()
        
        if (compilation_info['compilation_utxo'] and 
            not self.contract_manager._is_compilation_utxo_available(main_address)):
            self.menu.print_warning(
                "⚠ WARNING: The UTXO used for compilation has been consumed!\n"
                "Testing will use a different UTXO and may produce different token names."
            )
            if not self.menu.confirm_action("Continue with testing?"):
                return
        
        self.menu.print_info("This will mint two NFTs: one protocol token and one user token")
        destin_address_str = self.menu.get_input("Enter destination address for user token (or press Enter for default)")
        
        destination_address = None
        if destin_address_str.strip():
            try:
                destination_address = pc.Address.from_primitive(destin_address_str.strip())
            except Exception as e:
                self.menu.print_error(f"Invalid address format: {e}")
                return
        else:
            self.menu.print_info("Using default address (wallet address)")
        
        try:
            self.menu.print_info("Creating minting transaction...")
            result = self.token_operations.create_minting_transaction(destination_address)
            
            if not result['success']:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                return
            
            self.menu.print_success("Transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")
            print(f"Protocol Token: {result['protocol_token_name']}")
            print(f"User Token: {result['user_token_name']}")
            
            if self.menu.confirm_action("Submit transaction to network?"):
                self.menu.print_info("Submitting transaction...")
                tx_id = self.transactions.submit_transaction(result['transaction'])
                
                if tx_id:
                    self.menu.print_success("Transaction submitted successfully!")
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Explorer: {tx_info['explorer_url']}")
                else:
                    self.menu.print_error("Failed to submit transaction")
            else:
                self.menu.print_info("Transaction cancelled by user")
                
        except Exception as e:
            self.menu.print_error(f"Testing failed: {e}")
        
        input("\nPress Enter to continue...")
    
    def burn_tokens_menu(self):
        """Burn tokens submenu"""
        self.menu.print_header("TOKEN BURNING", "Burn Protocol & User NFTs")
        
        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for burning")
            return
        
        self.menu.print_info("This will burn protocol and user NFTs (tokens will be permanently destroyed)")
        user_address_input = self.menu.get_input("Enter address containing tokens to burn (or press Enter for default wallet address)")
        
        user_address = None
        if user_address_input.strip():
            try:
                user_address = pc.Address.from_primitive(user_address_input.strip())
                self.menu.print_info(f"Using specified address: {str(user_address)[:50]}...")
            except Exception as e:
                self.menu.print_error(f"Invalid address format: {e}")
                return
        else:
            self.menu.print_info("Using default wallet address")
        
        try:
            self.menu.print_info("Creating burn transaction...")
            result = self.token_operations.create_burn_transaction(user_address)
            
            if not result['success']:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                return
            
            self.menu.print_success("Burn transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")
            
            if self.menu.confirm_action("Submit burn transaction to network?"):
                self.menu.print_info("Submitting burn transaction...")
                tx_id = self.transactions.submit_transaction(result['transaction'])
                
                if tx_id:
                    self.menu.print_success("Burn transaction submitted successfully!")
                    self.menu.print_info("Tokens have been permanently destroyed and removed from circulation.")
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Explorer: {tx_info['explorer_url']}")
                else:
                    self.menu.print_error("Failed to submit burn transaction")
            else:
                self.menu.print_info("Burn transaction cancelled by user")
                
        except Exception as e:
            self.menu.print_error(f"Token burning failed: {e}")
        
        input("\nPress Enter to continue...")
    
    def contract_submenu(self):
        """Interactive menu for contract operations"""
        
        # Check if we need to compile contracts initially
        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_info("No contracts found - compiling now...")
            try:
                main_address = self.wallet.get_address(0)
                result = self.contract_manager.compile_contracts(main_address)
                if result['success']:
                    self.menu.print_success(result['message'])
                else:
                    self.menu.print_error(result['error'])
                    return
            except Exception as e:
                self.menu.print_error(f"Failed to compile contracts: {e}")
                return
        
        while True:
            # Get current status
            main_address = self.wallet.get_address(0)
            contract_status = self.contract_manager.get_contract_status(main_address)
            
            # Display header
            self.menu.print_header("SMART CONTRACT MANAGEMENT", f"Status: {contract_status}")
            self.menu.print_breadcrumb(["Main Menu", "Contract Menu"])
            
            # Display menu options
            self.menu.print_section("CONTRACT OPERATIONS")
            self.menu.print_menu_option("1", "Display Contracts Info", "✓")
            self.menu.print_menu_option("2", "Compile/Recompile Contracts", "✓")
            self.menu.print_menu_option("3", "Mint Tokens", "✓")
            self.menu.print_menu_option("4", "Burn Tokens", "✓")
            self.menu.print_separator()
            self.menu.print_menu_option("0", "Back to Main Menu")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-4)")

            if choice == "0":
                self.menu.print_info("Returning to main menu...")
                break
            elif choice == "1":
                self.display_contracts_info()
            elif choice == "2":
                try:
                    main_address = self.wallet.get_address(0)
                    result = self.contract_manager.compile_contracts(main_address, force=True)
                    if result['success']:
                        self.menu.print_success(result['message'])
                    else:
                        self.menu.print_error(result['error'])
                except Exception as e:
                    self.menu.print_error(f"Compilation failed: {e}")
            elif choice == "3":
                self.test_contracts_menu()
            elif choice == "4":
                self.burn_tokens_menu()
            else:
                self.menu.print_error("Invalid option. Please try again.")
    
    def interactive_menu(self):
        """Main interactive menu for dApp operations"""
        while True:
            # Get current status
            balances = self.wallet.check_balances(self.chain_context.get_api())
            main_address = self.wallet.get_address(0)
            contract_status = self.contract_manager.get_contract_status(main_address)
            contracts = self.contract_manager.list_contracts()
            
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
            self.menu.print_menu_option("4", "Enter Contract Menu", "💼" if contracts else "")
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
                    self.wallet.generate_addresses(count)
                    self.menu.print_success(f"Generated {count} new addresses!")
                except ValueError:
                    self.menu.print_error("Please enter a valid number")
            elif choice == "3":
                self.send_ada_menu()
            elif choice == "4":
                self.contract_submenu()
            elif choice == "5":
                self.export_wallet_menu()
            else:
                self.menu.print_error("Invalid option. Please try again.")


def main():
    """Main function to run the CLI"""
    
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
        # Initialize the CLI
        print("Initializing Cardano dApp...")
        cli = CardanoCLI()
        
        # Display initial wallet info
        cli.display_wallet_info()
        
        # Start interactive menu
        cli.interactive_menu()
        
    except Exception as e:
        print(f"Error initializing dApp: {e}")


if __name__ == "__main__":
    main()