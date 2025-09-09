"""
Cardano CLI Interface

Console interface that uses the core Cardano library.
Handles user interactions, menus, and display formatting.
"""

import json
import os
import pathlib
import time

import pycardano as pc
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / "menu/.env"
load_dotenv(ENV_FILE)

# Import core Cardano functionality
from src.cardano_offchain import (
    CardanoChainContext,
    CardanoTransactions,
    CardanoWallet,
    ContractManager,
    TokenOperations,
    WalletManager,
)
from terrasacha_contracts.validators.protocol import DatumProtocol
from tests.menu.menu_formatter import MenuFormatter


class CardanoCLI:
    """Console interface for Cardano dApp operations"""

    def switch_to_wallet(self, wallet_name: str) -> bool:
        """
        Switch the active wallet and update all necessary references
        
        Args:
            wallet_name: Name of the wallet to switch to
            
        Returns:
            True if switch was successful, False otherwise
        """
        if wallet_name not in self.wallet_manager.get_wallet_names():
            return False
            
        try:
            if self.transactions.set_active_wallet(wallet_name):
                # Update the wallet manager's default wallet
                self.wallet_manager.set_default_wallet(wallet_name)
                # Update the CLI's wallet reference
                self.wallet = self.wallet_manager.get_wallet(wallet_name)
                # Recreate TokenOperations with the new wallet
                self.token_operations = TokenOperations(
                    self.wallet, self.chain_context, self.contract_manager, self.transactions
                )
                return True
        except Exception:
            pass
            
        return False

    def resolve_address_input(self, input_str: str, switch_wallet: bool = False) -> Optional[str]:
        """
        Resolve address input - if it's a wallet name, return the main address
        Optionally switch to that wallet if it's a wallet name

        Args:
            input_str: Address string or wallet name
            switch_wallet: If True, switch active wallet when wallet name is provided

        Returns:
            Valid Cardano address string or None if invalid
        """
        input_str = input_str.strip()

        # Check if it's a wallet name
        if input_str in self.wallet_manager.get_wallet_names():
            if switch_wallet:
                if self.switch_to_wallet(input_str):
                    print(f"ℹ Switched to wallet: {input_str}")
                else:
                    print(f"⚠ Failed to switch to wallet: {input_str}")
                    return None
            
            wallet = self.wallet_manager.get_wallet(input_str)
            return str(wallet.enterprise_address)

        # Try to validate as a regular Cardano address
        try:
            pc.Address.from_primitive(input_str)
            return input_str
        except Exception:
            return None

    def __init__(self):
        """Initialize the CLI interface"""
        # Get environment variables
        self.network = os.getenv("network", "testnet")
        blockfrost_api_key = os.getenv("blockfrost_api_key")

        if not blockfrost_api_key:
            raise ValueError("Missing required environment variable: blockfrost_api_key")

        # Initialize core components
        self.chain_context = CardanoChainContext(self.network, blockfrost_api_key)

        # Initialize wallet manager from environment
        self.wallet_manager = WalletManager.from_environment(self.network)
        if not self.wallet_manager.get_wallet_names():
            raise ValueError(
                "No wallets configured. Set wallet_mnemonic or wallet_mnemonic_<role> environment variables"
            )

        # For backward compatibility
        self.wallet = self.wallet_manager.get_wallet()  # Get default wallet

        self.transactions = CardanoTransactions(self.wallet_manager, self.chain_context)
        self.contract_manager = ContractManager(self.chain_context)
        self.token_operations = TokenOperations(
            self.wallet, self.chain_context, self.contract_manager, self.transactions
        )

        # Initialize menu formatter
        self.menu = MenuFormatter()

        # Add context property for convenience
        self.context = self.chain_context.get_context()

        # Generate initial addresses for all wallets
        for wallet in self.wallet_manager.wallets.values():
            wallet.generate_addresses(10)

    def display_wallet_info(self, show_all_wallets: bool = False):
        """Display wallet information for active wallet or all wallets"""
        active_wallet_name = self.wallet_manager.get_default_wallet_name()

        if show_all_wallets:
            print("\n" + "=" * 80)
            print("CARDANO DAPP MULTI-WALLET INFORMATION")
            print("=" * 80)
            wallets_to_show = self.wallet_manager.get_wallet_names()
        else:
            print("\n" + "=" * 80)
            print("ACTIVE WALLET INFORMATION")
            print("=" * 80)
            wallets_to_show = [active_wallet_name] if active_wallet_name else []

        print(f"Network: {self.network.upper()}")
        print(f"Wallet Type: HD Wallet (BIP32)")
        print(f"Active Wallet: {active_wallet_name}")
        if show_all_wallets:
            print(f"Total Wallets: {len(self.wallet_manager.get_wallet_names())}")

        # Display selected wallet(s)
        for wallet_name in wallets_to_show:
            wallet = self.wallet_manager.get_wallet(wallet_name)
            wallet_info = wallet.get_wallet_info()
            is_active = wallet_name == active_wallet_name
            status = " (ACTIVE)" if is_active else ""

            print(f"\n{'='*20} WALLET: {wallet_name.upper()}{status} {'='*20}")

            print("MAIN ADDRESSES:")
            print(f"  Enterprise: {wallet_info['main_addresses']['enterprise']}")
            print(f"  Staking:    {wallet_info['main_addresses']['staking']}")

            print(f"DERIVED ADDRESSES (First 5):")
            for addr_info in wallet_info["derived_addresses"][:5]:
                print(
                    f"  {addr_info['index']:2d} | {addr_info['path']:20s} | {addr_info['enterprise_address']}"
                )

        # Check and display balances for selected wallet(s)
        print(f"\n{'='*20} CHECKING BALANCES {'='*20}")

        if show_all_wallets:
            all_balances = self.transactions.check_all_wallet_balances()
            balances_to_show = {
                k: v for k, v in all_balances.items() if k != "total_across_all_wallets"
            }
        else:
            # Only check balance for active wallet
            active_wallet = self.wallet_manager.get_wallet(active_wallet_name)
            if active_wallet:
                balances = active_wallet.check_balances(self.chain_context.get_api())
                balances_to_show = {active_wallet_name: balances}
            else:
                balances_to_show = {}

        for wallet_name, balances in balances_to_show.items():
            if "error" in balances:
                print(f"\n{wallet_name.upper()}: ERROR - {balances['error']}")
                continue

            is_active = wallet_name == active_wallet_name
            status = " (ACTIVE)" if is_active else ""
            print(f"\n{wallet_name.upper()}{status}:")
            print(
                f"  Enterprise: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA"
            )

            for addr in balances["derived_addresses"]:
                if addr["balance"] > 0:
                    print(f"  Address {addr['index']}: {addr['balance']/1_000_000:.6f} ADA")

            print(f"  Wallet Total: {balances['total_balance']/1_000_000:.6f} ADA")

        print(
            f"\nGRAND TOTAL ACROSS ALL WALLETS: {all_balances['total_across_all_wallets']/1_000_000:.6f} ADA"
        )

        return all_balances

    def wallet_management_menu(self):
        """Wallet management submenu"""
        while True:
            print("\n" + "=" * 60)
            print("WALLET MANAGEMENT MENU")
            print("=" * 60)
            print(f"Active Wallet: {self.wallet_manager.get_default_wallet_name()}")
            print(f"Available Wallets: {', '.join(self.wallet_manager.get_wallet_names())}")
            print()
            print("1. Switch Active Wallet")
            print("2. List All Wallets")
            print("3. Show Wallet Details")
            print("4. Check All Wallet Balances")
            print("0. Back to Main Menu")

            choice = input("\nEnter your choice (0-4): ").strip()

            if choice == "0":
                break
            elif choice == "1":
                self.switch_active_wallet()
            elif choice == "2":
                self.list_all_wallets()
            elif choice == "3":
                self.show_wallet_details()
            elif choice == "4":
                self.display_wallet_info(show_all_wallets=True)
            else:
                print("Invalid choice. Please try again.")

    def switch_active_wallet(self):
        """Switch the active wallet"""
        wallets = self.wallet_manager.get_wallet_names()
        if len(wallets) <= 1:
            print("Only one wallet available. No switching needed.")
            return

        print("\nAvailable wallets:")
        for i, wallet_name in enumerate(wallets, 1):
            is_active = wallet_name == self.wallet_manager.get_default_wallet_name()
            status = " (CURRENT)" if is_active else ""
            print(f"{i}. {wallet_name}{status}")

        try:
            choice = int(input(f"\nSelect wallet (1-{len(wallets)}): ")) - 1
            if 0 <= choice < len(wallets):
                wallet_name = wallets[choice]
                if self.switch_to_wallet(wallet_name):
                    print(f"\nActive wallet switched to: {wallet_name}")
                else:
                    print("Failed to switch wallet.")
            else:
                print("Invalid choice.")
        except (ValueError, IndexError):
            print("Invalid input.")

    def list_all_wallets(self):
        """List all available wallets with basic info"""
        print("\n" + "=" * 60)
        print("ALL WALLETS")
        print("=" * 60)

        for wallet_name in self.wallet_manager.get_wallet_names():
            wallet = self.wallet_manager.get_wallet(wallet_name)
            is_active = wallet_name == self.wallet_manager.get_default_wallet_name()
            status = " (ACTIVE)" if is_active else ""

            print(f"\nWallet: {wallet_name.upper()}{status}")
            print(f"  Enterprise Address: {wallet.enterprise_address}")
            print(f"  Staking Address: {wallet.staking_address}")

    def show_wallet_details(self):
        """Show detailed information for a specific wallet"""
        wallets = self.wallet_manager.get_wallet_names()
        print("\nAvailable wallets:")
        for i, wallet_name in enumerate(wallets, 1):
            is_active = wallet_name == self.wallet_manager.get_default_wallet_name()
            status = " (ACTIVE)" if is_active else ""
            print(f"{i}. {wallet_name}{status}")

        try:
            choice = int(input(f"\nSelect wallet to view details (1-{len(wallets)}): ")) - 1
            if 0 <= choice < len(wallets):
                wallet_name = wallets[choice]
                wallet = self.wallet_manager.get_wallet(wallet_name)
                wallet_info = wallet.get_wallet_info()

                print(f"\n{'='*60}")
                print(f"WALLET DETAILS: {wallet_name.upper()}")
                print(f"{'='*60}")
                print(f"Network: {wallet_info['network'].upper()}")
                print(f"Main Enterprise Address: {wallet_info['main_addresses']['enterprise']}")
                print(f"Main Staking Address: {wallet_info['main_addresses']['staking']}")

                print(f"\nDerived Addresses:")
                for addr_info in wallet_info["derived_addresses"]:
                    print(f"  {addr_info['index']:2d} | {addr_info['enterprise_address']}")

                # Check balance for this specific wallet
                try:
                    balances = wallet.check_balances(self.chain_context.get_api())
                    print(f"\nBalance Summary:")
                    print(
                        f"  Enterprise: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA"
                    )
                    for addr in balances["derived_addresses"]:
                        if addr["balance"] > 0:
                            print(f"  Address {addr['index']}: {addr['balance']/1_000_000:.6f} ADA")
                    print(f"  Total: {balances['total_balance']/1_000_000:.6f} ADA")
                except Exception as e:
                    print(f"\nError checking balance: {e}")
            else:
                print("Invalid choice.")
        except (ValueError, IndexError):
            print("Invalid input.")

    def send_ada_menu(self):
        """Send ADA submenu"""
        try:
            active_wallet_name = self.wallet_manager.get_default_wallet_name()
            print(f"\nSEND ADA (From: {active_wallet_name})")
            print("-" * 40)

            # Show available balances
            balances = self.wallet.check_balances(self.chain_context.get_api())
            print("Available balances:")
            print(
                f"Enterprise: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA"
            )
            print("ℹ Available wallets: default, project, investor")

            to_address_input = input("Recipient address (or wallet name): ").strip()

            # Resolve address input (could be wallet name or address)
            to_address = self.resolve_address_input(to_address_input)
            if not to_address:
                print(f"Invalid address or wallet name: {to_address_input}")
                return

            # Show resolved address if it was a wallet name
            if to_address_input != to_address:
                print(f"Resolved wallet '{to_address_input}' to address: {to_address[:20]}...")

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
            "network": self.network,
            "main_addresses": wallet_info["main_addresses"],
            "derived_addresses": wallet_info["derived_addresses"],
            "smart_contracts": {
                name: {"policy_id": info["policy_id"], "address": info["address"]}
                for name, info in contracts_info["contracts"].items()
            },
        }

        filename = f"wallet_data_{self.network}_{int(time.time())}.json"
        with open(filename, "w") as f:
            json.dump(wallet_data, f, indent=2)

        print(f"Wallet data exported to: {filename}")

    def display_contracts_info(self):
        """Display comprehensive contract information"""
        self.menu.print_header("CONTRACT INFORMATION", "Addresses, Balances & Status")

        contracts_info = self.contract_manager.get_contracts_info()

        if not contracts_info["contracts"]:
            self.menu.print_error("No contracts compiled yet. Please compile contracts first.")
            input("\nPress Enter to continue...")
            return

        # Display compilation info
        if contracts_info["compilation_utxo"]:
            utxo = contracts_info["compilation_utxo"]
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

        for name, info in contracts_info["contracts"].items():
            if info.get("type") == "minting_policy":
                # For minting policies, only show policy ID
                self.menu.print_minting_policy_info(
                    name=name.upper(),
                    policy_id=info["policy_id"]
                )
            else:
                # For spending validators, show balance info
                status = "✓" if info["balance"] > 0 else "○"
                self.menu.print_contract_info(
                    name=name.upper(),
                    policy_id=info["policy_id"],
                    address=info["address"],
                    balance=info["balance_ada"],
                    status=status,
                )

        # Display available project contracts
        project_contracts = self.contract_manager.list_project_contracts()
        if len(project_contracts) > 1:
            self.menu.print_section("AVAILABLE PROJECT CONTRACTS")
            for i, contract_name in enumerate(project_contracts, 1):
                is_default = contract_name == "project" or (contract_name == project_contracts[0] and "project" not in project_contracts)
                status = " (default)" if is_default else ""
                print(f"│ {i}. {contract_name.upper()}{status}")
            print()

        self.menu.print_footer()
        input("\nPress Enter to continue...")

    def mint_protocol_token(self):
        """Test smart contracts submenu"""
        self.menu.print_header("CONTRACT TESTING", "Mint Protocol & User NFTs")

        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for testing")
            return

        # Check UTXO availability
        main_address = self.wallet.get_address(0)
        compilation_info = self.contract_manager.get_contracts_info()

        if compilation_info[
            "compilation_utxo"
        ] and not self.contract_manager._is_compilation_utxo_available(main_address):
            self.menu.print_warning(
                "⚠ WARNING: The UTXO used for compilation has been consumed!\n"
                "Testing will use a different UTXO and may produce different token names."
            )
            if not self.menu.confirm_action("Continue with testing?"):
                return

        self.menu.print_info("This will mint two NFTs: one protocol token and one user token")
        
        # Show available wallets for user convenience
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        
        destin_address_str = self.menu.get_input(
            "Enter destination address or wallet name (or press Enter for default)"
        )

        destination_address = None
        if destin_address_str.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # Switch to the wallet if a wallet name is provided so transaction uses correct signing keys
            resolved_address = self.resolve_address_input(destin_address_str.strip(), switch_wallet=True)
            if resolved_address:
                try:
                    destination_address = pc.Address.from_primitive(resolved_address)
                    # Show resolved address if it was a wallet name
                    if destin_address_str.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(f"Resolved wallet '{destin_address_str.strip()}' to: {resolved_address}")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(f"Invalid address or wallet name: {destin_address_str.strip()}")
                return
        else:
            self.menu.print_info("Using default address (wallet address)")

        try:
            self.menu.print_info("Creating minting transaction...")
            result = self.token_operations.create_minting_transaction(destination_address)

            if not result["success"]:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                return

            self.menu.print_success("Transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")
            print(f"Protocol Token: {result['protocol_token_name']}")
            print(f"User Token: {result['user_token_name']}")

            if self.menu.confirm_action("Submit transaction to network?"):
                self.menu.print_info("Submitting transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])

                if tx_id:
                    self.menu.print_success("Transaction submitted successfully!")
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Explorer: {tx_info['explorer_url']}")
                    
                    # Mark contracts as deployed and save them to disk
                    deployed_contracts = ["protocol", "protocol_nfts"]
                    if self.contract_manager.mark_contract_as_deployed(deployed_contracts):
                        self.menu.print_success("✓ Contracts saved to disk (deployment confirmed)")
                    else:
                        self.menu.print_warning("⚠ Contracts deployed but failed to save to disk")
                else:
                    self.menu.print_error("Failed to submit transaction")
            else:
                self.menu.print_info("Transaction cancelled by user")

        except Exception as e:
            self.menu.print_error(f"Testing failed: {e}")

        input("\nPress Enter to continue...")

    def create_project_menu(self):
        """Create project submenu"""
        self.menu.print_header("PROJECT CREATION", "Create Project NFTs and Smart Contract")

        # First, check if protocol and project contracts are deployed
        contracts = self.contract_manager.list_contracts()
        
        # Check for project contract availability and allow selection
        project_contracts = self.contract_manager.list_project_contracts()
        selected_project_name = None
        if not project_contracts:
            project_contract = None
        elif len(project_contracts) == 1:
            # Only one project contract available
            selected_project_name = project_contracts[0]
            project_contract = self.contract_manager.get_project_contract(selected_project_name)
            self.menu.print_info(f"Using project contract: {selected_project_name.upper()}")
        else:
            # Multiple project contracts - let user choose
            self.menu.print_section("PROJECT CONTRACT SELECTION")
            self.menu.print_info("Multiple project contracts available:")
            for i, contract_name in enumerate(project_contracts, 1):
                print(f"│ {i}. {contract_name.upper()}")
            
            try:
                choice = int(self.menu.get_input(f"Select project contract (1-{len(project_contracts)})")) - 1
                if 0 <= choice < len(project_contracts):
                    selected_project_name = project_contracts[choice]
                    project_contract = self.contract_manager.get_project_contract(selected_project_name)
                    self.menu.print_info(f"Selected project contract: {selected_project_name.upper()}")
                else:
                    self.menu.print_error("Invalid project selection")
                    return
            except (ValueError, IndexError):
                self.menu.print_error("Invalid input for project selection")
                return
        
        if not contracts or "protocol" not in contracts or not project_contract:
            self.menu.print_error("❌ Protocol or Project contracts not available")
            self.menu.print_info("Please compile contracts first (Option 2 in Contract Menu)")
            input("\nPress Enter to continue...")
            return

        # Check if protocol has been deployed (has UTXOs at protocol address)
        protocol_contract = self.contract_manager.get_contract("protocol")
        try:    
            if protocol_contract:
                self.menu.print_success("✓ Protocol deployed and ready")
            # try:
            #     protocol_utxos = self.context.utxos(protocol_contract.testnet_addr)
            #     if not protocol_utxos:
            #         self.menu.print_error("❌ Protocol not deployed yet")
            #         self.menu.print_info("Please deploy protocol first (Option 3: Mint Tokens)")
            #         input("\nPress Enter to continue...")
            #         return
            #     else:
            #         self.menu.print_success("✓ Protocol deployed and ready")
        except Exception as e:
            self.menu.print_warning(f"⚠ Could not verify protocol deployment: {e}")

        self.menu.print_info("This will create a new project with associated NFTs")

        # Get project information
        self.menu.print_section("PROJECT INFORMATION")

        # Project ID (32 bytes)
        project_id_str = self.menu.get_input(
            "Enter project ID (64 hex chars, or press Enter for auto-generated)"
        )
        if project_id_str.strip():
            try:
                if len(project_id_str) != 64:
                    raise ValueError("Project ID must be exactly 64 hex characters")
                project_id = bytes.fromhex(project_id_str)
            except ValueError as e:
                self.menu.print_error(f"Invalid project ID: {e}")
                return
        else:
            # Auto-generate project ID
            import secrets

            project_id = secrets.token_bytes(32)
            self.menu.print_info(f"Auto-generated project ID: {project_id.hex()}")

        # Project metadata
        metadata_uri = self.menu.get_input(
            "Enter project metadata URI (or press Enter for default)"
        )
        if not metadata_uri.strip():
            metadata_uri = f"https://terrasacha.com/project/{project_id.hex()[:16]}"
            self.menu.print_info(f"Using default metadata URI: {metadata_uri}")
        project_metadata = metadata_uri.encode("utf-8")

        # Stakeholders
        self.menu.print_section("STAKEHOLDERS SETUP")
        stakeholders = []
        total_participation = 0

        self.menu.print_info("Enter stakeholder information (minimum 1 stakeholder required)")

        while True:
            stakeholder_name = self.menu.get_input(
                f"Stakeholder {len(stakeholders) + 1} name (or 'done' to finish)"
            )
            if stakeholder_name.lower() == "done":
                if len(stakeholders) == 0:
                    self.menu.print_error("At least one stakeholder is required")
                    continue
                break

            if not stakeholder_name.strip():
                self.menu.print_error("Stakeholder name cannot be empty")
                continue

            participation_str = self.menu.get_input(
                f"Participation amount for '{stakeholder_name}' (in lovelace)"
            )
            try:
                participation = int(participation_str)
                if participation <= 0:
                    raise ValueError("Participation must be positive")
            except ValueError as e:
                self.menu.print_error(f"Invalid participation amount: {e}")
                continue

            stakeholders.append((stakeholder_name.encode("utf-8"), participation))
            total_participation += participation

            self.menu.print_success(f"✓ Added {stakeholder_name}: {participation:,} lovelace")

            if len(stakeholders) >= 10:
                self.menu.print_warning("Maximum 10 stakeholders reached")
                break

        # Display summary
        self.menu.print_section("PROJECT SUMMARY")
        print(f"Project ID: {project_id.hex()}")
        print(f"Metadata: {metadata_uri}")
        print(f"Total Supply: {total_participation:,} lovelace")
        print(f"Stakeholders ({len(stakeholders)}):")
        for i, (name, participation) in enumerate(stakeholders, 1):
            percentage = (participation / total_participation) * 100
            print(f"  {i}. {name.decode('utf-8')}: {participation:,} ({percentage:.2f}%)")

        # Destination address
        self.menu.print_section("DESTINATION SETUP")
        
        # Show available wallets for user convenience
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        
        destin_address_str = self.menu.get_input(
            "Enter destination address or wallet name (or press Enter for default)"
        )

        destination_address = None
        if destin_address_str.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # Switch to the wallet if a wallet name is provided so transaction uses correct signing keys
            resolved_address = self.resolve_address_input(destin_address_str.strip(), switch_wallet=True)
            if resolved_address:
                try:
                    destination_address = pc.Address.from_primitive(resolved_address)
                    # Show resolved address if it was a wallet name
                    if destin_address_str.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(f"Resolved wallet '{destin_address_str.strip()}' to: {resolved_address}")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(f"Invalid address or wallet name: {destin_address_str.strip()}")
                return
        else:
            self.menu.print_info("Using default address (wallet address)")

        # Confirm creation
        if not self.menu.confirm_action(
            f"Create project with {len(stakeholders)} stakeholders and {total_participation:,} total supply?"
        ):
            self.menu.print_info("Project creation cancelled")
            return

        try:
            self.menu.print_info("Creating project minting transaction...")
            result = self.token_operations.create_project_minting_transaction(
                project_id=project_id,
                project_metadata=project_metadata,
                stakeholders=stakeholders,
                destination_address=destination_address,
                project_name=selected_project_name,
            )

            if not result["success"]:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                return

            self.menu.print_success("Transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")
            print(f"Project Token: {result['project_token_name']}")
            print(f"User Token: {result['user_token_name']}")
            print(f"Project ID: {result['project_id']}")
            print(f"Total Supply: {result['total_supply']:,}")
            print(f"Stakeholders: {result['stakeholders_count']}")

            if self.menu.confirm_action("Submit transaction to network?"):
                self.menu.print_info("Submitting transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])

                if tx_id:
                    self.menu.print_success("Project created successfully!")
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Explorer: {tx_info['explorer_url']}")
                    
                    # Mark project contracts as deployed and save them to disk
                    # Find which project contract was used and its corresponding NFTs contract
                    project_contracts = [name for name in self.contract_manager.contracts.keys() if name == "project" or name.startswith("project_")]
                    # For each project, add its corresponding NFTs contract
                    deployed_contracts = project_contracts.copy()
                    for project_name in project_contracts:
                        project_nfts_name = f"{project_name}_nfts"
                        if project_nfts_name in self.contract_manager.contracts:
                            deployed_contracts.append(project_nfts_name)
                    if self.contract_manager.mark_contract_as_deployed(deployed_contracts):
                        self.menu.print_success("✓ Project contracts saved to disk (deployment confirmed)")
                    else:
                        self.menu.print_warning("⚠ Project contracts deployed but failed to save to disk")
                else:
                    self.menu.print_error("Failed to submit transaction")
            else:
                self.menu.print_info("Transaction cancelled by user")

        except Exception as e:
            self.menu.print_error(f"Project creation failed: {e}")

        input("\nPress Enter to continue...")

    def burn_tokens_menu(self):
        """Burn tokens submenu"""
        self.menu.print_header("TOKEN BURNING", "Burn Protocol & User NFTs")

        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for burning")
            return

        self.menu.print_info(
            "This will burn protocol and user NFTs (tokens will be permanently destroyed)"
        )
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        user_address_input = self.menu.get_input(
            "Enter address or wallet name containing tokens to burn (or press Enter for default wallet address)"
        )

        user_address = None
        if user_address_input.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # For burn operations, switch to the wallet if a wallet name is provided
            resolved_address = self.resolve_address_input(user_address_input.strip(), switch_wallet=True)
            if resolved_address:
                try:
                    user_address = pc.Address.from_primitive(resolved_address)
                    if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}...")
                    else:
                        self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(f"Invalid address or wallet name: {user_address_input.strip()}")
                return
        else:
            self.menu.print_info("Using default wallet address")

        try:
            self.menu.print_info("Creating burn transaction...")
            result = self.token_operations.create_burn_transaction(user_address)

            if not result["success"]:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                return

            self.menu.print_success("Burn transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")

            if self.menu.confirm_action("Submit burn transaction to network?"):
                self.menu.print_info("Submitting burn transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])

                if tx_id:
                    self.menu.print_success("Burn transaction submitted successfully!")
                    self.menu.print_info(
                        "Tokens have been permanently destroyed and removed from circulation."
                    )
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Explorer: {tx_info['explorer_url']}")
                else:
                    self.menu.print_error("Failed to submit burn transaction")
            else:
                self.menu.print_info("Burn transaction cancelled by user")

        except Exception as e:
            self.menu.print_error(f"Token burning failed: {e}")

        input("\nPress Enter to continue...")

    def update_protocol_menu(self):
        """Update protocol datum submenu"""
        self.menu.print_header("PROTOCOL UPDATE", "Update Protocol Parameters")

        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for protocol update")
            return

        # Display current protocol information
        try:
            # Get protocol contract address
            protocol_contract = self.contract_manager.get_contract("protocol")
            protocol_nfts_contract = self.contract_manager.get_contract("protocol_nfts")

            if not protocol_contract or not protocol_nfts_contract:
                self.menu.print_error("Required contracts not found")
                return

            protocol_address = protocol_contract.testnet_addr
            minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))

            # Find current protocol UTXO and datum
            protocol_utxos = self.context.utxos(protocol_address)
            if not protocol_utxos:
                self.menu.print_error("No protocol UTXOs found")
                return

            protocol_utxo = None
            for utxo in protocol_utxos:
                if utxo.output.amount.multi_asset:
                    for (
                        policy_id,
                        assets,
                    ) in utxo.output.amount.multi_asset.data.items():
                        if policy_id == minting_policy_id:
                            protocol_utxo = utxo
                            break
                    if protocol_utxo:
                        break

            if not protocol_utxo:
                self.menu.print_error("No protocol UTXO found with expected policy ID")
                return

            # Extract current datum
            current_datum = DatumProtocol.from_cbor(protocol_utxo.output.datum.cbor)
            if not current_datum:
                self.menu.print_error("Protocol UTXO has no datum or invalid datum")
                return

            # Display current protocol state
            self.menu.print_section("CURRENT PROTOCOL STATE")
            print(f"│ Protocol Fee: {current_datum.protocol_fee / 1_000_000:.6f} ADA")
            print(f"│ Oracle ID: {current_datum.oracle_id.hex()[:16]}...")
            print(f"│ Project Count: {len(current_datum.projects)}")
            if current_datum.projects:
                print(
                    f"│ Projects: {[project.hex()[:16] + '...' for project in current_datum.projects[:3]]}"
                )
                if len(current_datum.projects) > 3:
                    print(f"│           ... and {len(current_datum.projects) - 3} more")
            else:
                print(f"│ Projects: None (empty)")
            print()

        except Exception as e:
            self.menu.print_error(f"Failed to retrieve current protocol state: {e}")
            return

        # Get user input for updates
        self.menu.print_info("Protocol Update Options:")

        # Initialize new values with current values
        new_fee_lovelace = current_datum.protocol_fee
        new_oracle_id = current_datum.oracle_id
        new_projects_list = current_datum.projects.copy()

        # Option to specify custom fee or use default increment
        fee_input = self.menu.get_input(
            "Enter new protocol fee in ADA (or press Enter for +0.5 ADA increment)"
        )

        if fee_input.strip():
            try:
                new_fee_ada = float(fee_input.strip())
                new_fee_lovelace = int(new_fee_ada * 1_000_000)
                self.menu.print_info(f"New protocol fee will be: {new_fee_ada:.6f} ADA")
            except ValueError:
                self.menu.print_error("Invalid fee amount entered")
                return
        else:
            new_fee_lovelace = current_datum.protocol_fee + 500_000  # +0.5 ADA
            self.menu.print_info(f"Using default increment: {new_fee_lovelace / 1_000_000:.6f} ADA")

        # Option to update Oracle ID
        oracle_input = self.menu.get_input("Enter new Oracle ID (or press Enter to keep current)")
        if oracle_input.strip():
            try:
                new_oracle_id = oracle_input.strip().encode("utf-8")
                self.menu.print_info(f"New Oracle ID: {oracle_input.strip()}")
            except Exception as e:
                self.menu.print_error(f"Invalid Oracle ID: {e}")
                return


        # Option to update Projects list
        project_input = self.menu.get_input("Update projects? (add/remove/keep) [keep]")
        if project_input.strip().lower() in ["add", "remove"]:
            if project_input.strip().lower() == "add":
                self.menu.print_info("Adding projects (type 'done' when finished)")
                while True:
                    new_project_hex = self.menu.get_input("Enter project ID (hex) or 'done'")
                    if new_project_hex.strip().lower() == 'done':
                        break
                    
                    try:
                        new_project_bytes = bytes.fromhex(new_project_hex.strip())
                        
                        # Check length
                        if len(new_project_bytes) > 32:  # Reasonable limit for project ID
                            self.menu.print_error(
                                "Project ID should not exceed 32 bytes (64 hex chars)"
                            )
                            continue
                            
                        # Check capacity
                        if len(new_projects_list) >= 10:  # Protocol validation limit
                            self.menu.print_error(
                                "Cannot add more projects - maximum limit of 10 reached"
                            )
                            break
                            
                        # Check for duplicates within the transaction
                        if new_project_bytes in new_projects_list:
                            self.menu.print_error("Project already being added in this transaction")
                            continue
                            
                        new_projects_list.append(new_project_bytes)
                        self.menu.print_success(f"✓ Added project: {new_project_hex.strip()}")
                        
                    except ValueError:
                        self.menu.print_error("Invalid hex format for project ID")
                        continue
                
                if len(new_projects_list) > len(current_datum.projects):
                    added_count = len(new_projects_list) - len(current_datum.projects)
                    self.menu.print_info(f"Will add {added_count} new project(s) in this transaction")

            elif project_input.strip().lower() == "remove":
                if len(current_datum.projects) == 0:
                    self.menu.print_error("No projects to remove")
                    return
                self.menu.print_info("Current projects:")
                for i, project in enumerate(current_datum.projects):
                    print(f"  {i}: {project.hex()}")
                try:
                    project_index = int(self.menu.get_input("Enter index of project to remove"))
                    if 0 <= project_index < len(current_datum.projects):
                        removed_project = new_projects_list.pop(project_index)
                        self.menu.print_info(f"Removed project: {removed_project.hex()}")
                    else:
                        self.menu.print_error("Invalid project index")
                        return
                except ValueError:
                    self.menu.print_error("Invalid project index")
                    return

        # Create new datum with all updates
        new_datum = DatumProtocol(
            protocol_fee=new_fee_lovelace,
            oracle_id=new_oracle_id,
            projects=new_projects_list,  # Use updated projects list
        )

        # Option to specify user address
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        user_address_input = self.menu.get_input(
            "Enter address or wallet name containing user tokens (or press Enter for default wallet address)"
        )

        user_address = None
        if user_address_input.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # For protocol update operations, switch to the wallet if a wallet name is provided
            resolved_address = self.resolve_address_input(user_address_input.strip(), switch_wallet=True)
            if resolved_address:
                try:
                    user_address = pc.Address.from_primitive(resolved_address)
                    if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}...")
                    else:
                        self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(f"Invalid address or wallet name: {user_address_input.strip()}")
                return
        else:
            self.menu.print_info("Using default wallet address")

        # Create and submit transaction
        try:
            self.menu.print_info("Creating protocol update transaction...")
            result = self.token_operations.create_protocol_update_transaction(
                user_address, new_datum
            )

            if not result["success"]:
                self.menu.print_error(f"Failed to create update transaction: {result['error']}")
                return

            self.menu.print_success("Protocol update transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")

            # Show datum changes
            self.menu.print_section("PROTOCOL CHANGES")
            old_datum = result["old_datum"]
            new_datum_result = result["new_datum"]

            # Compare fee changes
            fee_changed = old_datum.protocol_fee != new_datum_result.protocol_fee
            fee_status = "changed" if fee_changed else "unchanged"
            print(
                f"│ Protocol Fee: {old_datum.protocol_fee / 1_000_000:.6f} ADA → {new_datum_result.protocol_fee / 1_000_000:.6f} ADA ({fee_status})"
            )

            # Compare Oracle ID changes
            oracle_changed = old_datum.oracle_id != new_datum_result.oracle_id
            oracle_status = "changed" if oracle_changed else "unchanged"
            old_oracle_str = old_datum.oracle_id.hex()[:16] + "..."
            new_oracle_str = new_datum_result.oracle_id.hex()[:16] + "..."
            print(f"│ Oracle ID: {old_oracle_str} → {new_oracle_str} ({oracle_status})")

            # Compare Project changes
            old_project_set = set(old_datum.projects)
            new_project_set = set(new_datum_result.projects)
            project_changed = old_project_set != new_project_set
            project_status = "changed" if project_changed else "unchanged"
            print(
                f"│ Project Count: {len(old_datum.projects)} → {len(new_datum_result.projects)} ({project_status})"
            )

            if project_changed:
                added_projects = new_project_set - old_project_set
                removed_projects = old_project_set - new_project_set
                if added_projects:
                    print(
                        f"│   Added: {[project.hex()[:16] + '...' for project in added_projects]}"
                    )
                if removed_projects:
                    print(
                        f"│   Removed: {[project.hex()[:16] + '...' for project in removed_projects]}"
                    )

            print()

            if self.menu.confirm_action("Submit protocol update transaction to network?"):
                self.menu.print_info("Submitting protocol update transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])

                if tx_id:
                    self.menu.print_success("Protocol update transaction submitted successfully!")
                    self.menu.print_info("Protocol parameters have been updated.")
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Explorer: {tx_info['explorer_url']}")
                else:
                    self.menu.print_error("Failed to submit protocol update transaction")
            else:
                self.menu.print_info("Protocol update transaction cancelled by user")

        except Exception as e:
            self.menu.print_error(f"Protocol update failed: {e}")

        input("\nPress Enter to continue...")

    def burn_project_tokens_menu(self):
        """Burn project tokens submenu"""
        self.menu.print_header("PROJECT TOKEN BURNING", "Burn Project & User NFTs")

        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for burning")
            return

        # Project contract selection
        project_contracts = self.contract_manager.list_project_contracts()
        if not project_contracts:
            self.menu.print_error("No project contracts found")
            return
        elif len(project_contracts) == 1:
            # Only one project contract available
            selected_project = project_contracts[0]
            self.menu.print_info(f"Using project contract: {selected_project.upper()}")
        else:
            # Multiple project contracts - let user choose
            self.menu.print_section("PROJECT CONTRACT SELECTION")
            self.menu.print_info("Multiple project contracts available:")
            for i, contract_name in enumerate(project_contracts, 1):
                print(f"│ {i}. {contract_name.upper()}")
            
            try:
                choice = int(self.menu.get_input(f"Select project contract to burn tokens from (1-{len(project_contracts)})")) - 1
                if 0 <= choice < len(project_contracts):
                    selected_project = project_contracts[choice]
                    self.menu.print_info(f"Selected project contract: {selected_project.upper()}")
                else:
                    self.menu.print_error("Invalid project selection")
                    return
            except (ValueError, IndexError):
                self.menu.print_error("Invalid input for project selection")
                return

        self.menu.print_info(
            "This will burn project and user NFTs (tokens will be permanently destroyed)"
        )
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        user_address_input = self.menu.get_input(
            "Enter address or wallet name containing tokens to burn (or press Enter for default wallet address)"
        )

        user_address = None
        if user_address_input.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # For project burn operations, switch to the wallet if a wallet name is provided
            resolved_address = self.resolve_address_input(user_address_input.strip(), switch_wallet=True)
            if resolved_address:
                try:
                    user_address = pc.Address.from_primitive(resolved_address)
                    if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}...")
                    else:
                        self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(f"Invalid address or wallet name: {user_address_input.strip()}")
                return
        else:
            self.menu.print_info("Using default wallet address")

        try:
            self.menu.print_info("Creating project burn transaction...")
            result = self.token_operations.create_project_burn_transaction(user_address, selected_project)

            if not result["success"]:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                return

            self.menu.print_success("Project burn transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")
            print(f"Burned project token: {result['burned_tokens']['project_token']}")
            print(f"Burned user token: {result['burned_tokens']['user_token']}")

            if self.menu.confirm_action("Submit project burn transaction to network?"):
                self.menu.print_info("Submitting project burn transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])
                self.menu.print_success(f"Project burn transaction submitted! TX ID: {tx_id}")
            else:
                self.menu.print_info("Transaction not submitted")

        except Exception as e:
            self.menu.print_error(f"Project burn transaction creation failed: {e}")

        input("\nPress Enter to continue...")

    def update_project_menu(self):
        """Update project datum submenu"""
        self.menu.print_header("PROJECT UPDATE", "Update Project Parameters")

        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for project update")
            return

        # Display current project information
        try:
            # Get project contracts with selection
            project_contracts = self.contract_manager.list_project_contracts()
            if not project_contracts:
                self.menu.print_error("No project contracts found")
                return
            elif len(project_contracts) == 1:
                # Only one project contract available
                selected_project = project_contracts[0]
                project_contract = self.contract_manager.get_project_contract(selected_project)
                self.menu.print_info(f"Using project contract: {selected_project.upper()}")
            else:
                # Multiple project contracts - let user choose
                self.menu.print_section("PROJECT CONTRACT SELECTION")
                self.menu.print_info("Multiple project contracts available:")
                for i, contract_name in enumerate(project_contracts, 1):
                    print(f"│ {i}. {contract_name.upper()}")
                
                try:
                    choice = int(self.menu.get_input(f"Select project contract to update (1-{len(project_contracts)})")) - 1
                    if 0 <= choice < len(project_contracts):
                        selected_project = project_contracts[choice]
                        project_contract = self.contract_manager.get_project_contract(selected_project)
                        self.menu.print_info(f"Selected project contract: {selected_project.upper()}")
                    else:
                        self.menu.print_error("Invalid project selection")
                        return
                except (ValueError, IndexError):
                    self.menu.print_error("Invalid input for project selection")
                    return
            
            project_nfts_contract = self.contract_manager.get_project_nfts_contract(selected_project)

            if not project_contract or not project_nfts_contract:
                self.menu.print_error("Required project contracts not found")
                return

            project_address = project_contract.testnet_addr
            minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))

            # Find current project UTXO and datum
            project_utxos = self.context.utxos(project_address)
            if not project_utxos:
                self.menu.print_error("No project UTXOs found")
                return

            project_utxo = None
            for utxo in project_utxos:
                if utxo.output.amount.multi_asset:
                    for (
                        policy_id,
                        assets,
                    ) in utxo.output.amount.multi_asset.data.items():
                        if policy_id == minting_policy_id:
                            project_utxo = utxo
                            break
                    if project_utxo:
                        break

            if not project_utxo:
                self.menu.print_error("No project UTXO with required token found")
                return

            # Parse current datum
            from terrasacha_contracts.validators.project import DatumProject

            current_datum = DatumProject.from_cbor(project_utxo.output.datum.cbor)

            # Display current project state
            self.menu.print_section("CURRENT PROJECT STATUS")
            print(f"│ Owner: {current_datum.params.owner.hex()[:20]}...")
            print(f"│ Project ID: {current_datum.params.project_id.hex()[:20]}...")
            print(f"│ Project State: {current_datum.params.project_state}")
            print(f"│ Current Supply: {current_datum.project_token.current_supply:,}")
            print(f"│ Total Supply: {current_datum.project_token.total_supply:,}")
            print(f"│ Stakeholder Count: {len(current_datum.stakeholders)}")
            print(f"│ Certification Count: {len(current_datum.certifications)}")

            # Ask for user address
            self.menu.print_info("ℹ Available wallets: default, project, investor")
            user_address_input = self.menu.get_input(
                "Enter address or wallet name containing user tokens (or press Enter for default wallet address)"
            )

            user_address = None
            if user_address_input.strip():
                # Use the existing resolve_address_input method that supports wallet names
                # For project update operations, switch to the wallet if a wallet name is provided
                resolved_address = self.resolve_address_input(user_address_input.strip(), switch_wallet=True)
                if resolved_address:
                    try:
                        user_address = pc.Address.from_primitive(resolved_address)
                        if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                            self.menu.print_info(f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}...")
                        else:
                            self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                    except Exception as e:
                        self.menu.print_error(f"Invalid address format: {e}")
                        return
                else:
                    self.menu.print_error(f"Invalid address or wallet name: {user_address_input.strip()}")
                    return
            else:
                self.menu.print_info("Using default wallet address")

            # Confirm update (default behavior will advance project state)
            if not self.menu.confirm_action("Update project datum (advance project state)?"):
                self.menu.print_info("Project update cancelled")
                return

            self.menu.print_info("Creating project update transaction...")
            result = self.token_operations.create_project_update_transaction(user_address, None, selected_project)

            if not result["success"]:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                return

            self.menu.print_success("Project update transaction created successfully!")
            print(f"TX ID: {result['tx_id']}")

            # Display changes
            old_datum = result["old_datum"]
            new_datum = result["new_datum"]
            print("\n│ CHANGES MADE:")
            print(
                f"│ Project State: {old_datum.params.project_state} → {new_datum.params.project_state}"
            )

            if self.menu.confirm_action("Submit project update transaction to network?"):
                self.menu.print_info("Submitting project update transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])
                self.menu.print_success(f"Project update transaction submitted! TX ID: {tx_id}")
            else:
                self.menu.print_info("Transaction not submitted")

        except Exception as e:
            self.menu.print_error(f"Project update failed: {e}")

        input("\nPress Enter to continue...")

    def select_wallet_for_compilation(self, purpose: str) -> Optional[pc.Address]:
        """
        Ask user to select a wallet for compilation and return its address
        
        Args:
            purpose: Description of what the wallet will be used for
            
        Returns:
            Address of selected wallet or None if cancelled
        """
        wallets = self.wallet_manager.get_wallet_names()
        
        self.menu.print_section(f"WALLET SELECTION FOR {purpose.upper()}")
        self.menu.print_info(f"Select wallet to use for {purpose}:")
        
        for i, wallet_name in enumerate(wallets, 1):
            is_active = wallet_name == self.wallet_manager.get_default_wallet_name()
            status = " (CURRENT)" if is_active else ""
            print(f"│ {i}. {wallet_name}{status}")
        
        try:
            choice = int(self.menu.get_input(f"Select wallet (1-{len(wallets)}, or 0 to cancel)"))
            if choice == 0:
                return None
            elif 1 <= choice <= len(wallets):
                wallet_name = wallets[choice - 1]
                wallet = self.wallet_manager.get_wallet(wallet_name)
                self.menu.print_info(f"Selected wallet: {wallet_name}")
                return wallet.get_address(0)
            else:
                self.menu.print_error("Invalid choice")
                return None
        except (ValueError, IndexError):
            self.menu.print_error("Invalid input")
            return None

    def contract_submenu(self):
        """Interactive menu for contract operations"""

        # Check if we need to compile contracts initially
        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_info("No contracts found - compiling now...")
            try:
                # For automatic compilation, use default wallet for both (backward compatibility)
                main_address = self.wallet.get_address(0) 
                result = self.contract_manager.compile_contracts(main_address, main_address)
                if result["success"]:
                    self.menu.print_success(result["message"])
                else:
                    self.menu.print_error(result["error"])
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
            self.menu.print_menu_option("2", "Compile/Recompile All Contracts", "✓")
            self.menu.print_menu_option("3", "Compile New Project Contract Only", "✓")
            self.menu.print_menu_option("4", "Mint Protocol Tokens", "✓")
            self.menu.print_menu_option("5", "Burn Tokens", "✓")
            self.menu.print_menu_option("6", "Update Protocol Datum", "✓")
            self.menu.print_menu_option("7", "Create Project", "✓")
            self.menu.print_menu_option("8", "Burn Project Tokens", "✓")
            self.menu.print_menu_option("9", "Update Project Datum", "✓")
            self.menu.print_separator()
            self.menu.print_menu_option("10", "Delete Empty Contract", "🗑")
            self.menu.print_menu_option("0", "Back to Main Menu")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-10)")

            if choice == "0":
                self.menu.print_info("Returning to main menu...")
                break
            elif choice == "1":
                self.display_contracts_info()
            elif choice == "2":
                try:
                    # Ask for protocol wallet selection
                    protocol_address = self.select_wallet_for_compilation("protocol contract")
                    if not protocol_address:
                        self.menu.print_info("Compilation cancelled")
                        continue
                    
                    # Ask for project wallet selection  
                    project_address = self.select_wallet_for_compilation("project contract")
                    if not project_address:
                        self.menu.print_info("Compilation cancelled")
                        continue
                    
                    self.menu.print_info("Starting contract compilation...")
                    result = self.contract_manager.compile_contracts(protocol_address, project_address, force=True)
                    if result["success"]:
                        self.menu.print_success(result["message"])
                        if result.get("contracts"):
                            print(f"Compiled contracts: {', '.join(result['contracts'])}")
                    else:
                        self.menu.print_error(result["error"])
                except Exception as e:
                    self.menu.print_error(f"Compilation failed: {e}")
            elif choice == "3":
                self.compile_project_only_menu()
            elif choice == "4":
                self.mint_protocol_token()
            elif choice == "5":
                self.burn_tokens_menu()
            elif choice == "6":
                self.update_protocol_menu()
            elif choice == "7":
                self.create_project_menu()
            elif choice == "8":
                self.burn_project_tokens_menu()
            elif choice == "9":
                self.update_project_menu()
            elif choice == "10":
                self.delete_empty_contract_menu()
            else:
                self.menu.print_error("Invalid option. Please try again.")

    def compile_project_only_menu(self):
        """Compile only a new project contract using existing protocol"""
        self.menu.print_header("PROJECT CONTRACT COMPILATION", "Compile New Project Only")
        
        # Check if protocol contract exists
        if "protocol" not in self.contract_manager.list_contracts():
            self.menu.print_error("❌ Protocol contract not found!")
            self.menu.print_info("You must compile the full contract suite first (Option 2)")
            input("\nPress Enter to continue...")
            return
        
        # Show current project contracts
        project_contracts = self.contract_manager.list_project_contracts()
        if project_contracts:
            self.menu.print_section("EXISTING PROJECT CONTRACTS")
            for i, contract_name in enumerate(project_contracts, 1):
                print(f"│ {i}. {contract_name.upper()}")
            print()
        
        self.menu.print_info("This will compile a new project contract using the existing protocol contract.")
        self.menu.print_info("The new project contract will be automatically assigned the next available index.")
        
        if not self.menu.confirm_action("Proceed with project contract compilation?"):
            self.menu.print_info("Compilation cancelled")
            input("\nPress Enter to continue...")
            return
        
        # Compile project contract
        try:
            # Ask for project wallet selection
            project_address = self.select_wallet_for_compilation("new project contract")
            if not project_address:
                self.menu.print_info("Compilation cancelled")
                input("\nPress Enter to continue...")
                return
            
            self.menu.print_info("Compiling project contract...")
            result = self.contract_manager.compile_project_contract_only(project_address)
            
            if result["success"]:
                self.menu.print_success("✅ Project contract compiled successfully!")
                self.menu.print_section("COMPILATION RESULTS")
                print(f"│ Contract Name: {result['project_name'].upper()}")
                print(f"│ Policy ID: {result['policy_id']}")
                print(f"│ Used UTXO: {result.get('used_utxo', 'N/A')}")
                print(f"│ Saved to Disk: {'✓' if result['saved'] else '✗'}")
                print()
                
                if result["saved"]:
                    self.menu.print_info("Contract files saved to artifacts/ directory")
                else:
                    self.menu.print_warning("⚠ Contract compiled but not saved to disk")
            else:
                self.menu.print_error(f"❌ Compilation failed: {result['error']}")
                
        except Exception as e:
            self.menu.print_error(f"❌ Compilation error: {e}")
            
        input("\nPress Enter to continue...")

    def delete_empty_contract_menu(self):
        """Delete contracts that have zero balance"""
        self.menu.print_header("DELETE EMPTY CONTRACTS", "Remove Contracts with Zero Balance")
        
        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available")
            input("\nPress Enter to continue...")
            return
        
        # Filter out minting policies (they can't be deleted)
        deletable_contracts = [name for name in contracts if not name.endswith("_nfts")]
        
        if not deletable_contracts:
            self.menu.print_error("No deletable contracts found (only minting policies exist)")
            input("\nPress Enter to continue...")
            return
        
        self.menu.print_section("AVAILABLE CONTRACTS FOR DELETION")
        self.menu.print_info("Only spending validator contracts with zero balance can be deleted:")
        
        # Show contract info with balances
        contracts_info = self.contract_manager.get_contracts_info()
        for i, contract_name in enumerate(deletable_contracts, 1):
            contract_info = contracts_info["contracts"].get(contract_name, {})
            balance_ada = contract_info.get("balance_ada", 0)
            status = "✗ Has Balance" if balance_ada > 0 else "✓ Empty"
            print(f"│ {i}. {contract_name.upper()}: {balance_ada:.6f} ADA ({status})")
        
        print()
        
        try:
            choice = int(self.menu.get_input(f"Select contract to delete (1-{len(deletable_contracts)}, or 0 to cancel)"))
            if choice == 0:
                self.menu.print_info("Operation cancelled")
                input("\nPress Enter to continue...")
                return
            elif 1 <= choice <= len(deletable_contracts):
                contract_name = deletable_contracts[choice - 1]
                
                self.menu.print_warning(f"⚠ This will permanently delete contract '{contract_name}' if it has zero balance")
                if not self.menu.confirm_action("Proceed with deletion?"):
                    self.menu.print_info("Deletion cancelled")
                    input("\nPress Enter to continue...")
                    return
                
                # Attempt deletion
                result = self.contract_manager.delete_contract_if_empty(contract_name)
                
                if result["success"]:
                    self.menu.print_success(result["message"])
                    if result.get("saved"):
                        self.menu.print_success("✓ Updated contracts file saved to disk")
                    # Show different messages based on deletion reason
                    if "unused address" in result["message"]:
                        self.menu.print_info("ℹ This contract was never deployed/used, so it was safe to delete")
                    else:
                        self.menu.print_info("ℹ Contract had zero balance and no tokens, so it was safe to delete")
                else:
                    self.menu.print_error(result["error"])
                    if "balance" in result:
                        balance_ada = result["balance"] / 1_000_000
                        print(f"Contract still has {balance_ada:.6f} ADA")
                        if result.get("has_tokens"):
                            print("Contract also contains tokens")
                        print("You must burn all tokens before deleting the contract")
                        
            else:
                self.menu.print_error("Invalid choice")
                
        except (ValueError, IndexError):
            self.menu.print_error("Invalid input")
            
        input("\nPress Enter to continue...")

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
                balance=balances["total_balance"] / 1_000_000,
                contracts_status=contract_status,
                wallet_name=self.wallet_manager.get_default_wallet_name(),
            )

            # Display menu options
            self.menu.print_section("MAIN MENU")
            self.menu.print_menu_option("1", "Display Wallet Info & Balances")
            self.menu.print_menu_option("2", "Generate New Addresses")
            self.menu.print_menu_option("3", "Send ADA")
            self.menu.print_menu_option("4", "Enter Contract Menu", "💼" if contracts else "")
            self.menu.print_menu_option("5", "Export Wallet Data")
            self.menu.print_menu_option("6", "Wallet Management")
            self.menu.print_separator()
            self.menu.print_menu_option("0", "Exit Application")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-6)")

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
            elif choice == "6":
                self.wallet_management_menu()
            else:
                self.menu.print_error("Invalid option. Please try again.")


def main():
    """Main function to run the CLI"""

    # Check for required environment variables
    required_vars = ["wallet_mnemonic", "blockfrost_api_key"]
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
        # cli.display_wallet_info()

        # Start interactive menu
        cli.interactive_menu()

    except Exception as e:
        print(f"Error initializing dApp: {e}")


if __name__ == "__main__":
    main()
