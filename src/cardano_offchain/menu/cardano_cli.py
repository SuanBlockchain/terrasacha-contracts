"""
Cardano CLI Interface

Console interface that uses the core Cardano library.
Handles user interactions, menus, and display formatting.
"""

import copy
import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional

import pycardano as pc
from dotenv import load_dotenv

# Load environment variables
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / "menu/.env"
load_dotenv(ENV_FILE)

# Import core Cardano functionality
from src.cardano_offchain import (
    CardanoChainContext,
    CardanoTransactions,
    ContractManager,
    TokenOperations,
    WalletManager,
)
from terrasacha_contracts.validators.protocol import DatumProtocol
from src.cardano_offchain.menu.menu_formatter import MenuFormatter
from terrasacha_contracts.validators.project import (
    DatumProject,
    DatumProjectParams,
    TokenProject,
    StakeHolderParticipation,
    Certification,
)
from opshin.prelude import TrueData


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

    def get_available_wallets_info(self) -> str:
        """Get formatted string of available wallets for user information"""
        wallet_names = self.wallet_manager.get_wallet_names()
        return f"ℹ Available wallets: {', '.join(wallet_names)}"

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

        self.contract_manager = ContractManager(self.chain_context)
        self.transactions = CardanoTransactions(
            self.wallet_manager, self.chain_context, self.contract_manager
        )
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
            # Select source wallet (where to send ADA from)
            source_selection = self.select_wallet_or_address_for_source("sending ADA from")
            if not source_selection:
                self.menu.print_info("Send ADA cancelled")
                return

            source_address, source_wallet_name, should_switch = source_selection

            # Switch to source wallet if a wallet was selected
            if should_switch and source_wallet_name:
                if self.switch_to_wallet(source_wallet_name):
                    self.menu.print_info(f"Switched to wallet: {source_wallet_name}")
                else:
                    self.menu.print_error(f"Failed to switch to wallet: {source_wallet_name}")
                    return

            # Show available balances
            balances = self.wallet.check_balances(self.chain_context.get_api())
            print("\nAvailable balances:")
            print(
                f"Enterprise: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA"
            )

            # Select destination address
            destination_selection = self.select_wallet_or_address_for_destination("sending ADA to")
            if not destination_selection:
                self.menu.print_info("Send ADA cancelled")
                return

            to_address, destination_wallet_name = destination_selection

            amount = float(input("Amount (ADA): "))

            print(f"Sending {amount} ADA to {to_address}")

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
            # Check storage type from actual contract
            contract = self.contract_manager.get_contract(name)
            storage_type = getattr(contract, "storage_type", "local") if contract else "local"

            if info.get("type") == "minting_policy":
                # For minting policies, show policy ID and storage type
                print(f"│ 📝 {name.upper()}")
                print(f"│   Policy ID: {info['policy_id']}")
                print(f"│   Type: Minting Policy")
                print(
                    f"│   Storage: {'📍 Reference Script' if storage_type == 'reference_script' else '💾 Local'}"
                )

                if storage_type == "reference_script" and hasattr(contract, "reference_tx_id"):
                    print(
                        f"│   Reference UTXO: {contract.reference_tx_id}#{contract.reference_output_index}"
                    )
                    print(f"│   Reference Address: {contract.reference_address}")
                print()
            else:
                # For spending validators, show balance info and storage type
                status = "✓" if info["balance"] > 0 else "○"
                print(f"│ {status} {name.upper()}")
                print(f"│   Policy ID: {info['policy_id']}")
                print(f"│   Address: {info['address']}")
                print(f"│   Balance: {info['balance_ada']:.6f} ADA")
                print(f"│   Type: Spending Validator")
                print(
                    f"│   Storage: {'📍 Reference Script' if storage_type == 'reference_script' else '💾 Local'}"
                )

                if storage_type == "reference_script" and hasattr(contract, "reference_tx_id"):
                    print(
                        f"│   Reference UTXO: {contract.reference_tx_id}#{contract.reference_output_index}"
                    )
                    print(f"│   Reference Address: {contract.reference_address}")
                print()

        # Display available project contracts
        project_contracts = self.contract_manager.list_project_contracts()
        if len(project_contracts) > 1:
            self.menu.print_section("AVAILABLE PROJECT CONTRACTS")
            for i, contract_name in enumerate(project_contracts, 1):
                is_default = contract_name == "project" or (
                    contract_name == project_contracts[0] and "project" not in project_contracts
                )
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

        # Select destination for the user token
        destination_selection = self.select_wallet_or_address_for_destination("user token delivery")
        if not destination_selection:
            self.menu.print_info("Protocol token minting cancelled")
            return

        destination_address, destination_wallet_name = destination_selection

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
                    if self.contract_manager.mark_contract_as_deployed(deployed_contracts, main_address):
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

        # Check for project contract availability and allow selection
        project_contracts = self.contract_manager.list_project_contracts()
        selected_project_name = None
        if not project_contracts:
            project_contract = None
        elif len(project_contracts) == 1:
            # Only one project contract available
            selected_project_name = project_contracts[0]
            self.menu.print_info(f"Using project contract: {selected_project_name.upper()}")
        else:
            # Multiple project contracts - let user choose
            self.menu.print_section("PROJECT CONTRACT SELECTION")
            self.menu.print_info("Multiple project contracts available:")
            for i, contract_name in enumerate(project_contracts, 1):
                print(f"│ {i}. {contract_name.upper()}")

            try:
                choice = (
                    int(
                        self.menu.get_input(f"Select project contract (1-{len(project_contracts)})")
                    )
                    - 1
                )
                if 0 <= choice < len(project_contracts):
                    selected_project_name = project_contracts[choice]
                    project_contract = self.contract_manager.get_project_contract(
                        selected_project_name
                    )
                    self.menu.print_info(
                        f"Selected project contract: {selected_project_name.upper()}"
                    )
                else:
                    self.menu.print_error("Invalid project selection")
                    return
            except (ValueError, IndexError):
                self.menu.print_error("Invalid input for project selection")
                return

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

            stakeholder_pkh = self.menu.get_input(
                f"Public Key Hash (pkh) for '{stakeholder_name}' or press Enter to skip"
            )
            try:
                if stakeholder_pkh and len(stakeholder_pkh) != 56:
                    raise ValueError("Public Key Hash must be exactly 56 hex characters")
                else:
                    # Validate pkh format
                    bytes.fromhex(stakeholder_pkh)
            except ValueError as e:
                self.menu.print_error(f"Invalid Public Key Hash: {e}")
                continue

            stakeholders.append((stakeholder_name.encode("utf-8"), participation, stakeholder_pkh))
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
        for i, (name, participation, stakeholder_pkh) in enumerate(stakeholders, 1):
            percentage = (participation / total_participation) * 100
            print(f"  {i}. {name.decode('utf-8')}: {participation:,} ({percentage:.2f}%)")

        # Destination address selection
        destination_selection = self.select_wallet_or_address_for_destination("user token delivery")
        if not destination_selection:
            self.menu.print_info("Project creation cancelled")
            return

        destination_address, destination_wallet_name = destination_selection

        # Ask which wallet to use for the transaction (important for compilation UTXO)
        self.menu.print_section("WALLET SELECTION FOR MINTING")
        self.menu.print_info("Project minting requires the wallet that contains the compilation UTXO.")

        # Get available wallets
        available_wallets = self.wallet_manager.get_wallet_names()
        current_wallet = self.wallet_manager.get_default_wallet_name()

        print(f"\nAvailable wallets:")
        for i, wallet_name in enumerate(available_wallets, 1):
            is_active = wallet_name == current_wallet
            status = " (CURRENT)" if is_active else ""
            print(f"│  {i}. {wallet_name}{status}")

        wallet_choice = self.menu.get_input(f"Select wallet (1-{len(available_wallets)}, default: use current wallet)")

        wallet_override = None
        if wallet_choice.strip():
            try:
                wallet_index = int(wallet_choice) - 1
                if 0 <= wallet_index < len(available_wallets):
                    selected_wallet_name = available_wallets[wallet_index]
                    if selected_wallet_name != current_wallet:
                        wallet_override = self.wallet_manager.get_wallet(selected_wallet_name)
                        self.menu.print_success(f"Using wallet: {selected_wallet_name}")
                    else:
                        self.menu.print_info("Using current wallet")
                else:
                    self.menu.print_error("Invalid wallet selection")
                    return
            except ValueError:
                self.menu.print_error("Invalid input. Please enter a number.")
                return

        try:
            self.menu.print_info("Creating project minting transaction...")
            result = self.token_operations.create_project_minting_transaction(
                project_id=project_id,
                project_metadata=project_metadata,
                stakeholders=stakeholders,
                destination_address=destination_address,
                project_name=selected_project_name,
                wallet_override=wallet_override,
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
                    # Get project contracts (excluding NFT minting policies for user display)
                    project_contracts = self.contract_manager.list_project_contracts()

                    # For deployment marking, we need to include both project contracts and their NFTs
                    deployed_contracts = project_contracts.copy()
                    for project_name in project_contracts:
                        project_nfts_name = f"{project_name}_nfts"
                        if project_nfts_name in self.contract_manager.contracts:
                            deployed_contracts.append(project_nfts_name)

                    if self.contract_manager.mark_contract_as_deployed(deployed_contracts, destination_address):
                        self.menu.print_success(
                            "✓ Project contracts saved to disk (deployment confirmed)"
                        )
                    else:
                        self.menu.print_warning(
                            "⚠ Project contracts deployed but failed to save to disk"
                        )
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

        # Select source wallet containing tokens to burn
        source_selection = self.select_wallet_or_address_for_source("token burning")
        if not source_selection:
            self.menu.print_info("Token burning cancelled")
            return

        user_address, source_wallet_name, should_switch = source_selection

        # Switch to source wallet if a wallet was selected
        if should_switch and source_wallet_name:
            if self.switch_to_wallet(source_wallet_name):
                self.menu.print_info(f"Switched to wallet: {source_wallet_name}")
            else:
                self.menu.print_error(f"Failed to switch to wallet: {source_wallet_name}")
                return

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
            print(f"│ Admins Count: {len(current_datum.project_admins)}")
            print(f"│ Projects Count: {len(current_datum.projects)}")
            if current_datum.project_admins:
                print(
                    f"│ Admins: {[admin.hex()[:16] + '...' for admin in current_datum.project_admins[:3]]}"
                )
                if len(current_datum.project_admins) > 3:
                    print(f"│           ... and {len(current_datum.project_admins) - 3} more")
            else:
                print(f"│ Admins: None (empty)")
            print()
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
        new_admin_list = current_datum.project_admins.copy()
        projects_name = current_datum.projects.copy()
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

        # Option to update Admins list
        admin_input = self.menu.get_input("Update admins? (add/remove/keep) [keep]")
        if admin_input.strip().lower() in ["add", "remove"]:
            if admin_input.strip().lower() == "add":
                self.menu.print_info("Adding admins (type 'done' when finished)")
                while True:
                    new_admin_hex = self.menu.get_input("Enter admin ID (hex) or 'done'")
                    if new_admin_hex.strip().lower() == "done":
                        break

                    try:
                        new_admin_bytes = bytes.fromhex(new_admin_hex.strip())

                        # Check length
                        if len(new_admin_bytes) > 32:  # Reasonable limit for admin ID
                            self.menu.print_error(
                                "Admin ID should not exceed 32 bytes (64 hex chars)"
                            )
                            continue

                        # Check capacity
                        if len(new_admin_list) >= 10:  # Protocol validation limit
                            self.menu.print_error(
                                "Cannot add more admins - maximum limit of 10 reached"
                            )
                            break

                        # Check for duplicates within the transaction
                        if new_admin_bytes in new_admin_list:
                            self.menu.print_error("Admin already being added in this transaction")
                            continue

                        new_admin_list.append(new_admin_bytes)
                        self.menu.print_success(f"✓ Added admin: {new_admin_hex.strip()}")

                    except ValueError:
                        self.menu.print_error("Invalid hex format for admin ID")
                        continue

                if len(new_admin_list) > len(current_datum.project_admins):
                    added_count = len(new_admin_list) - len(current_datum.project_admins)
                    self.menu.print_info(f"Will add {added_count} new admin(s) in this transaction")

            elif admin_input.strip().lower() == "remove":
                if len(current_datum.project_admins) == 0:
                    self.menu.print_error("No admins to remove")
                    return
                self.menu.print_info("Current admins:")
                for i, admin in enumerate(current_datum.project_admins):
                    print(f"  {i}: {admin.hex()}")
                try:
                    admin_index = int(self.menu.get_input("Enter index of admin to remove"))
                    if 0 <= admin_index < len(current_datum.project_admins):
                        removed_admin = new_admin_list.pop(admin_index)
                        self.menu.print_info(f"Removed admin: {removed_admin.hex()}")
                    else:
                        self.menu.print_error("Invalid admin index")
                        return
                except ValueError:
                    self.menu.print_error("Invalid admin index")
                    return

        # Option to update Projects list based on deployed projects
        projects_policy_ids = []
        deployed_projects = self.contract_manager.list_project_contracts()
        if deployed_projects:
            self.menu.print_section("DEPLOYED PROJECTS - SELECT TO INCLUDE")
            self.menu.print_info(
                "Select which projects to add to the protocol's projects list:"
            )

            # Display projects with their policy IDs
            project_info = []
            for i, project_name in enumerate(deployed_projects, 1):
                project_contract = self.contract_manager.get_contract(project_name)
                if project_contract:
                    policy_id = project_contract.policy_id
                    project_info.append((project_name, policy_id))
                    print(f"│ {i}. {project_name}")
                    print(f"│    Policy ID: {policy_id}")
                    print("│")

            # Get user selection
            if project_info:
                self.menu.print_info("\nOptions:")
                print("│ - Enter numbers separated by commas (e.g., 1,3,5)")
                print("│ - Enter range (e.g., 1-3)")
                print("│ - Enter 'all' to select all projects")
                print("│ - Press Enter to skip (no projects)")

                selection = self.menu.get_input("Select projects to include").strip()

                selected_indices = []
                if selection.lower() == 'all':
                    selected_indices = list(range(1, len(project_info) + 1))
                elif selection:
                    try:
                        # Parse selection input
                        parts = selection.replace(' ', '').split(',')
                        for part in parts:
                            if '-' in part:
                                # Range selection
                                start, end = part.split('-')
                                selected_indices.extend(range(int(start), int(end) + 1))
                            else:
                                # Single selection
                                selected_indices.append(int(part))
                    except ValueError:
                        self.menu.print_error("Invalid selection format")
                        return

                # Convert selected projects' policy IDs to bytes
                self.menu.print_section("SELECTED PROJECTS")
                for idx in selected_indices:
                    if 1 <= idx <= len(project_info):
                        project_name, policy_id = project_info[idx - 1]
                        # Convert hex policy ID to bytes
                        policy_id_bytes = bytes.fromhex(policy_id)
                        projects_policy_ids.append(policy_id_bytes)
                        self.menu.print_info(f"✓ {project_name} (Policy ID: {policy_id})")

                if not projects_policy_ids:
                    self.menu.print_info("No projects selected")
        else:
            self.menu.print_info("No deployed projects found")

        # oracle_input = self.menu.get_input("Enter new Oracle ID (or press Enter to keep current)")
        # if oracle_input.strip():
        #     try:
        #         new_oracle_id = oracle_input.strip().encode("utf-8")
        #         self.menu.print_info(f"New Oracle ID: {oracle_input.strip()}")
        #     except Exception as e:
        #         self.menu.print_error(f"Invalid Oracle ID: {e}")
        #         return
        # Create new datum with all updates
        new_datum = DatumProtocol(
            protocol_fee=new_fee_lovelace,
            oracle_id=new_oracle_id,
            project_admins=new_admin_list,  # Use updated admins list
            projects=projects_policy_ids,  # Use policy IDs as bytes
        )

        # Select wallet containing user tokens for protocol update
        source_selection = self.select_wallet_or_address_for_source("protocol update authorization")
        if not source_selection:
            self.menu.print_info("Protocol update cancelled")
            return

        user_address, source_wallet_name, should_switch = source_selection

        # Switch to source wallet if a wallet was selected
        if should_switch and source_wallet_name:
            if self.switch_to_wallet(source_wallet_name):
                self.menu.print_info(f"Switched to wallet: {source_wallet_name}")
            else:
                self.menu.print_error(f"Failed to switch to wallet: {source_wallet_name}")
                return

        if user_address is None:
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
            old_admin_state = set(old_datum.project_admins)
            new_admin_state = set(new_datum_result.project_admins)
            admin_changed = old_admin_state != new_admin_state
            admin_status = "changed" if admin_changed else "unchanged"
            print(
                f"│ Project Count: {len(old_datum.project_admins)} → {len(new_datum_result.project_admins)} ({admin_status})"
            )

            if admin_changed:
                added_admins = new_admin_state - old_admin_state
                removed_admins = old_admin_state - new_admin_state
                if added_admins:
                    print(f"│   Added: {[admin.hex()[:16] + '...' for admin in added_admins]}")
                if removed_admins:
                    print(f"│   Removed: {[admin.hex()[:16] + '...' for admin in removed_admins]}")

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
                choice = (
                    int(
                        self.menu.get_input(
                            f"Select project contract to burn tokens from (1-{len(project_contracts)})"
                        )
                    )
                    - 1
                )
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

        # Select wallet containing project tokens to burn
        source_selection = self.select_wallet_or_address_for_source("project token burning")
        if not source_selection:
            self.menu.print_info("Project token burning cancelled")
            return

        user_address, source_wallet_name, should_switch = source_selection

        # Switch to source wallet if a wallet was selected
        if should_switch and source_wallet_name:
            if self.switch_to_wallet(source_wallet_name):
                self.menu.print_info(f"Switched to wallet: {source_wallet_name}")
            else:
                self.menu.print_error(f"Failed to switch to wallet: {source_wallet_name}")
                return

        try:
            self.menu.print_info("Creating project burn transaction...")

            result = self.token_operations.create_project_burn_transaction(
                user_address, selected_project
            )

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

    def mint_grey_tokens_menu(self):
        """Mint grey tokens using UpdateToken redeemer"""
        self.menu.print_header("GREY TOKEN MINTING", "Mint Grey Tokens for Project")

        contracts = self.contract_manager.list_contracts()
        if not contracts:
            self.menu.print_error("No contracts available for grey token minting")
            input("Press Enter to continue...")
            return

        # Project contract selection
        project_contracts = self.contract_manager.list_project_contracts()
        if not project_contracts:
            self.menu.print_error("No project contracts found")
            input("Press Enter to continue...")
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
                choice = (
                    int(
                        self.menu.get_input(
                            f"Select project contract for grey token minting (1-{len(project_contracts)})"
                        )
                    )
                    - 1
                )
                if 0 <= choice < len(project_contracts):
                    selected_project = project_contracts[choice]
                    self.menu.print_info(f"Selected project contract: {selected_project.upper()}")
                else:
                    self.menu.print_error("Invalid project selection")
                    input("Press Enter to continue...")
                    return
            except (ValueError, IndexError):
                self.menu.print_error("Invalid input for project selection")
                input("Press Enter to continue...")
                return

        # Get grey token quantity
        try:
            quantity_input = self.menu.get_input("Enter number of grey tokens to mint (default: 1)")
            grey_token_quantity = int(quantity_input) if quantity_input.strip() else 1

            if grey_token_quantity <= 0:
                self.menu.print_error("Quantity must be positive")
                input("Press Enter to continue...")
                return

        except ValueError:
            self.menu.print_error("Invalid quantity. Please enter a number.")
            input("Press Enter to continue...")
            return

        # Ask for wallet to use for transaction (will pay fees and receive tokens)
        self.menu.print_section("WALLET SELECTION")
        self.menu.print_info(self.get_available_wallets_info())
        wallet_input = self.menu.get_input(
            "Enter wallet name to use for transaction (will pay fees and receive grey tokens) or press Enter for current wallet"
        )

        if wallet_input.strip():
            # Switch to the specified wallet if a wallet name is provided
            resolved_address = self.resolve_address_input(wallet_input.strip(), switch_wallet=True)
            if not resolved_address:
                self.menu.print_error(f"Invalid wallet name: {wallet_input.strip()}")
                input("Press Enter to continue...")
                return
            self.menu.print_info(f"Switched to wallet: {wallet_input.strip()}")
        else:
            self.menu.print_info("Using current wallet for transaction")

        # Show transaction preview
        self.menu.print_section("TRANSACTION PREVIEW")
        current_wallet = self.wallet_manager.get_default_wallet_name()
        print(f"│ Project Contract: {selected_project}")
        print(f"│ Grey Tokens to Mint: {grey_token_quantity:,}")
        print(f"│ Wallet: {current_wallet} (will pay fees and receive tokens)")
        print("│")
        print("│ ⚠️  This will:")
        print("│    • Use UpdateToken redeemer on project contract")
        print("│    • Mint grey tokens to the selected wallet address")

        if not self.menu.confirm_action("Proceed with grey token minting?"):
            self.menu.print_info("Grey token minting cancelled")
            input("Press Enter to continue...")
            return

        try:
            self.menu.print_info("Creating grey token minting transaction...")

            # Create the grey token minting transaction
            result = self.token_operations.create_grey_minting_transaction(
                project_name=selected_project,
                grey_token_quantity=grey_token_quantity,
            )

            if result["success"]:
                self.menu.print_success("✓ Grey token minting transaction created successfully!")
                print(f"│ Transaction ID: {result['tx_id']}")
                print(f"│ Grey Token Name: {result['grey_token_name']}")
                print(f"│ Minting Policy ID: {result['minting_policy_id']}")
                print(f"│ Quantity Minted: {result['quantity']:,}")

                # Submit the transaction
                if self.menu.confirm_action("Submit transaction to blockchain?"):
                    self.menu.print_info("Submitting transaction...")
                    tx_id = self.transactions.submit_transaction(result["transaction"])

                    if tx_id:
                        self.menu.print_success("✓ Grey token minting transaction submitted!")
                        tx_info = self.transactions.get_transaction_info(tx_id)
                        print(f"Explorer: {tx_info['explorer_url']}")
                        self.menu.print_info(
                            "Grey tokens will appear in destination wallet after confirmation"
                        )
                    else:
                        self.menu.print_error("Failed to submit transaction")
                else:
                    self.menu.print_info("Transaction not submitted")
            else:
                self.menu.print_error(
                    f"Failed to create grey token minting transaction: {result['error']}"
                )

        except Exception as e:
            self.menu.print_error(f"Grey token minting failed: {e}")

        input("\nPress Enter to continue...")

    def burn_grey_tokens_menu(self):
        """Burn grey tokens - bypasses project contract validation"""
        self.menu.print_header("GREY TOKEN BURNING", "Burn Grey Tokens")

        try:
            # Ask user to select wallet for token burning
            wallet_selection = self.select_wallet_for_token_operation("burning grey tokens")
            if not wallet_selection:
                self.menu.print_info("Wallet selection cancelled")
                input("Press Enter to continue...")
                return

            wallet_name, user_address = wallet_selection

            # Switch to selected wallet if different from current
            current_wallet = self.wallet_manager.get_default_wallet_name()
            if wallet_name != current_wallet:
                success = self.switch_to_wallet(wallet_name)
                if not success:
                    self.menu.print_error(f"Failed to switch to wallet: {wallet_name}")
                    input("Press Enter to continue...")
                    return
                self.menu.print_info(f"Switched to wallet: {wallet_name}")

            # Get UTXOs from selected wallet
            user_utxos = self.context.utxos(user_address)

            if not user_utxos:
                self.menu.print_error("No UTXOs found in wallet")
                input("Press Enter to continue...")
                return

            # Get stored grey token contracts
            grey_contracts = self.contract_manager.list_grey_token_contracts()
            if not grey_contracts:
                self.menu.print_error("No grey token contracts found. Setup grey tokens first.")
                input("Press Enter to continue...")
                return

            # Find grey tokens in wallet that match stored contracts
            grey_tokens = {}  # {contract_name: {policy_id: {token_name: amount}}}

            for contract_name in grey_contracts:
                grey_contract = self.contract_manager.get_grey_token_contract(
                    contract_name.replace("_grey", "")  # Extract project name
                )
                if not grey_contract:
                    continue

                policy_id_hex = grey_contract.policy_id
                grey_tokens[contract_name] = {}

                # Check user UTXOs for tokens with this policy ID
                for utxo in user_utxos:
                    if utxo.output.amount.multi_asset:
                        for policy_id, assets in utxo.output.amount.multi_asset.items():
                            if policy_id.payload.hex() == policy_id_hex:
                                if policy_id_hex not in grey_tokens[contract_name]:
                                    grey_tokens[contract_name][policy_id_hex] = {}

                                for asset_name, amount in assets.items():
                                    token_name_hex = asset_name.payload.hex()
                                    if (
                                        token_name_hex
                                        not in grey_tokens[contract_name][policy_id_hex]
                                    ):
                                        grey_tokens[contract_name][policy_id_hex][
                                            token_name_hex
                                        ] = 0
                                    grey_tokens[contract_name][policy_id_hex][
                                        token_name_hex
                                    ] += amount

            # Filter out contracts with no tokens
            grey_tokens = {k: v for k, v in grey_tokens.items() if v}

            if not grey_tokens:
                self.menu.print_error("No grey tokens found in wallet for stored contracts")
                input("Press Enter to continue...")
                return

            # Display available grey tokens
            self.menu.print_info("Available Grey Tokens:")
            token_options = []
            option_num = 1

            for contract_name, policy_data in grey_tokens.items():
                project_name = contract_name.replace("_grey", "")
                for policy_id, tokens in policy_data.items():
                    for token_name, amount in tokens.items():
                        short_policy = f"{policy_id[:8]}...{policy_id[-8:]}"
                        short_token = (
                            f"{token_name[:8]}...{token_name[-8:]}"
                            if len(token_name) > 16
                            else token_name
                        )
                        self.menu.print_menu_option(
                            f"{option_num}",
                            f"Project: {project_name}, Policy: {short_policy}, Token: {short_token}, Amount: {amount}",
                        )
                        token_options.append((policy_id, token_name, amount, project_name))
                        option_num += 1

            if not token_options:
                self.menu.print_error("No valid grey tokens found")
                input("Press Enter to continue...")
                return

            # Token selection
            while True:
                try:
                    choice = (
                        input(f"\nSelect token to burn (1-{len(token_options)}) or 'q' to quit: ")
                        .strip()
                        .lower()
                    )
                    if choice == "q":
                        return

                    token_index = int(choice) - 1
                    if 0 <= token_index < len(token_options):
                        (
                            selected_policy_id,
                            selected_token_name,
                            available_amount,
                            selected_project,
                        ) = token_options[token_index]
                        break
                    else:
                        self.menu.print_error(
                            f"Please enter a number between 1 and {len(token_options)}"
                        )
                except ValueError:
                    self.menu.print_error("Please enter a valid number")

            # Quantity selection
            while True:
                try:
                    quantity_input = input(
                        f"\nEnter quantity to burn (max: {available_amount}): "
                    ).strip()
                    burn_quantity = int(quantity_input)
                    if 1 <= burn_quantity <= available_amount:
                        break
                    else:
                        self.menu.print_error(
                            f"Please enter a quantity between 1 and {available_amount}"
                        )
                except ValueError:
                    self.menu.print_error("Please enter a valid number")

            # Confirmation
            self.menu.print_info(f"\nBurning Details:")
            self.menu.print_info(f"  - Wallet: {wallet_name}")
            self.menu.print_info(f"  - Project: {selected_project}")
            self.menu.print_info(f"  - Policy ID: {selected_policy_id}")
            self.menu.print_info(f"  - Token Name: {selected_token_name}")
            self.menu.print_info(f"  - Quantity: {burn_quantity}")

            confirm = input("\nProceed with burning? (y/n): ").strip().lower()
            if confirm != "y":
                self.menu.print_info("Burning cancelled")
                input("Press Enter to continue...")
                return

            # Create and submit burning transaction
            self.menu.print_info("Creating grey token burning transaction...")

            result = self.token_operations.burn_grey_tokens(
                grey_token_policy_id=selected_policy_id,
                grey_token_name=selected_token_name,
                burn_quantity=burn_quantity,
                project_name=selected_project,
            )

            if result["success"]:
                self.menu.print_success("Grey token burning transaction created successfully!")
                self.menu.print_info(f"Transaction ID: {result['tx_id']}")
                self.menu.print_info(f"Burned Quantity: {result['burned_quantity']}")
                self.menu.print_info(f"Remaining Tokens: {result['remaining_tokens']}")

                # Submit transaction
                submit = input("\nSubmit transaction to blockchain? (y/n): ").strip().lower()
                if submit == "y":
                    try:
                        self.context.submit_tx(result["transaction"])
                        self.menu.print_success("Transaction submitted successfully!")
                        self.menu.print_info(f"Transaction ID: {result['tx_id']}")
                    except Exception as submit_error:
                        self.menu.print_error(f"Failed to submit transaction: {submit_error}")
                else:
                    self.menu.print_info("Transaction created but not submitted")
            else:
                self.menu.print_error(
                    f"Failed to create grey token burning transaction: {result['error']}"
                )

        except Exception as e:
            self.menu.print_error(f"Grey token burning failed: {e}")

        input("\nPress Enter to continue...")

    def delete_grey_tokens_menu(self):
        """Delete grey token contracts while preserving project contracts"""
        self.menu.print_header("DELETE GREY TOKENS", "Remove Grey Token Contracts Only")

        # Get available grey token contracts
        grey_contracts = self.contract_manager.list_grey_token_contracts()
        if not grey_contracts:
            self.menu.print_error("No grey token contracts found")
            input("Press Enter to continue...")
            return

        self.menu.print_section("AVAILABLE GREY TOKEN CONTRACTS")
        self.menu.print_info("Select grey token contract to delete (project contracts will be preserved):")

        for i, contract_name in enumerate(grey_contracts, 1):
            # Extract project name from grey contract name
            project_name = contract_name.replace("_grey", "")
            print(f"│ {i}. {contract_name} (associated with {project_name})")

        print()
        try:
            choice = int(
                self.menu.get_input(
                    f"Select grey token contract to delete (1-{len(grey_contracts)}, or 0 to cancel)"
                )
            )

            if choice == 0:
                self.menu.print_info("Operation cancelled")
                input("Press Enter to continue...")
                return

            elif 1 <= choice <= len(grey_contracts):
                grey_contract_name = grey_contracts[choice - 1]
                project_name = grey_contract_name.replace("_grey", "")

                # Show warning
                self.menu.print_warning(
                    f"⚠ This will permanently delete grey token contract '{grey_contract_name}'"
                )
                self.menu.print_info(
                    f"ℹ Project contract '{project_name}' and its NFTs will be preserved"
                )

                if not self.menu.confirm_action("Proceed with grey token contract deletion?"):
                    self.menu.print_info("Deletion cancelled")
                    input("Press Enter to continue...")
                    return

                # Check if it's a reference script that needs UTXO spending
                contract = self.contract_manager.contracts[grey_contract_name]
                is_reference_script = (
                    hasattr(contract, "storage_type")
                    and contract.storage_type == "reference_script"
                )

                if is_reference_script:
                    self.menu.print_section("REFERENCE SCRIPT DELETION")
                    self.menu.print_info("This grey token contract is stored as a reference script on-chain.")
                    self.menu.print_info("The reference script UTXO needs to be spent to complete deletion.")

                    # Get wallet selection for UTXO owner
                    wallet_names = self.wallet_manager.get_wallet_names()
                    self.menu.print_info("\nSelect wallet that owns the reference script UTXO:")
                    for i, wallet_name in enumerate(wallet_names, 1):
                        print(f"{i}. {wallet_name}")

                    try:
                        wallet_choice = (
                            int(self.menu.get_input(f"Select wallet (1-{len(wallet_names)})")) - 1
                        )
                        if 0 <= wallet_choice < len(wallet_names):
                            selected_wallet_name = wallet_names[wallet_choice]
                            selected_wallet = self.wallet_manager.get_wallet(selected_wallet_name)
                        else:
                            self.menu.print_error("Invalid wallet selection")
                            input("Press Enter to continue...")
                            return
                    except ValueError:
                        self.menu.print_error("Invalid input")
                        input("Press Enter to continue...")
                        return

                    # Spend the reference script UTXO
                    destination_address = selected_wallet.enterprise_address
                    self.menu.print_info("Spending reference script UTXO...")
                    spend_result = self.contract_manager.spend_reference_script_utxo(
                        grey_contract_name, selected_wallet, destination_address
                    )
                    if not spend_result["success"]:
                        self.menu.print_error(
                            f"Failed to spend reference script UTXO: {spend_result['error']}"
                        )
                        input("Press Enter to continue...")
                        return
                    self.menu.print_success("✓ Reference script UTXO spent successfully")
                    self.menu.print_info(f"Transaction ID: {spend_result['tx_id']}")

                # Delete the grey token contract
                result = self.contract_manager.delete_grey_token_contract(grey_contract_name)
                if result["success"]:
                    self.menu.print_success(result["message"])
                    if result.get("saved"):
                        self.menu.print_success("✓ Updated contracts file saved to disk")
                    self.menu.print_info(
                        f"ℹ Project contract '{project_name}' and associated NFTs remain available"
                    )
                else:
                    self.menu.print_error(f"Failed to delete grey token contract: {result['error']}")

            else:
                self.menu.print_error("Invalid selection")

        except ValueError:
            self.menu.print_error("Invalid input. Please enter a number.")

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
                    choice = (
                        int(
                            self.menu.get_input(
                                f"Select project contract to update (1-{len(project_contracts)})"
                            )
                        )
                        - 1
                    )
                    if 0 <= choice < len(project_contracts):
                        selected_project = project_contracts[choice]
                        project_contract = self.contract_manager.get_project_contract(
                            selected_project
                        )
                        self.menu.print_info(
                            f"Selected project contract: {selected_project.upper()}"
                        )
                    else:
                        self.menu.print_error("Invalid project selection")
                        return
                except (ValueError, IndexError):
                    self.menu.print_error("Invalid input for project selection")
                    return

            project_nfts_contract = self.contract_manager.get_project_nfts_contract(
                selected_project
            )

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
            current_datum = DatumProject.from_cbor(project_utxo.output.datum.cbor)

            # Enhanced project status display with update capabilities
            self.display_enhanced_project_status(current_datum)

            # Select wallet containing user tokens for project update
            source_selection = self.select_wallet_or_address_for_source("project update authorization")
            if not source_selection:
                self.menu.print_info("Project update cancelled")
                return

            user_address, source_wallet_name, should_switch = source_selection

            # Switch to source wallet if a wallet was selected
            if should_switch and source_wallet_name:
                if self.switch_to_wallet(source_wallet_name):
                    self.menu.print_info(f"Switched to wallet: {source_wallet_name}")
                else:
                    self.menu.print_error(f"Failed to switch to wallet: {source_wallet_name}")
                    return

            # Allow comprehensive project updates regardless of project state for ProjectUpdate operations
            self.handle_initialization_update(current_datum, user_address, selected_project)

        except Exception as e:
            self.menu.print_error(f"Project update failed: {e}")

        input("\nPress Enter to continue...")

    def display_enhanced_project_status(self, current_datum):
        """Display enhanced project status with update capability indicators"""

        # State information
        state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}
        state_name = state_names.get(current_datum.params.project_state, "Unknown")
        is_updatable = (
            True  # Allow updates regardless of project state for ProjectUpdate operations
        )

        self.menu.print_section("CURRENT PROJECT STATUS")

        # Project identification
        project_id_display = (
            current_datum.params.project_id.hex()[:20] + "..."
            if len(current_datum.params.project_id.hex()) > 20
            else current_datum.params.project_id.hex()
        )
        metadata_display = current_datum.params.project_metadata.decode("utf-8", errors="ignore")[
            :50
        ]
        if len(current_datum.params.project_metadata) > 50:
            metadata_display += "..."

        print(f"│ Project ID: {project_id_display} {'[UPDATABLE]' if is_updatable else '[LOCKED]'}")
        print(f"│ Metadata: {metadata_display} {'[UPDATABLE]' if is_updatable else '[LOCKED]'}")
        print(
            f"│ Project State: {current_datum.params.project_state} - {state_name} {'[CAN ADVANCE]' if is_updatable else '[FINAL]'}"
        )

        # Token information
        token_name_display = (
            "empty"
            if not current_datum.project_token.token_name
            or current_datum.project_token.token_name == b""
            else current_datum.project_token.token_name.decode("utf-8", errors="ignore")
        )

        print(
            f"│ Token Name: ({token_name_display}) {'[UPDATABLE]' if is_updatable else '[LOCKED]'}"
        )

        # Supply information
        print(
            f"│ Total Supply: {current_datum.project_token.total_supply:,} {'[UPDATABLE]' if is_updatable else '[LOCKED]'}"
        )

        # Stakeholders and certifications
        print(
            f"│ Stakeholders: {len(current_datum.stakeholders)} entries {'[UPDATABLE]' if is_updatable else '[LOCKED]'}"
        )
        print(
            f"│ Certifications: {len(current_datum.certifications)} entries {'[UPDATABLE]' if is_updatable else '[LOCKED]'}"
        )

        # Show update status summary
        if is_updatable:
            print("│")
            print("│ 🔓 Project is in INITIALIZATION phase - All fields can be modified")
        else:
            print("│")
            print("│ 🔒 Project is LOCKED - Only token operations available")

    def handle_initialization_update(self, current_datum, user_address, project_name):
        """Handle project updates during initialization phase (state == 0)"""
        self.menu.print_section("PROJECT INITIALIZATION UPDATE")
        print("│ All project fields can be modified in initialization phase")
        print("│")

        # Batch-only update mode - all changes are accumulated and submitted together
        self.menu.print_info("PROJECT UPDATE - BATCH MODE ONLY")
        print("│ All changes are accumulated and submitted in a single transaction")
        print("│ Individual field updates have been consolidated into batch mode")
        print("│")

        # Directly call the batch update function
        self.batch_update_all_fields(current_datum, user_address, project_name)

    def handle_locked_project_update(self, current_datum):
        """Handle project updates for locked projects (state >= 1)"""
        self.menu.print_section("PROJECT LOCKED")
        print("│ This project is finalized and most fields are immutable.")
        print("│")
        print("│ 🔒 IMMUTABLE FIELDS:")
        print("│   • Project ID, Metadata, State")
        print("│   • Protocol Policy ID, Token Name")
        print("│   • Total Supply, Stakeholder Details")
        print("│   • Certification Details")
        print("│")
        print("│ ⚙️  AVAILABLE OPERATIONS:")
        print("│   • Token Operations (mint/burn)")
        print("│   • Stakeholder Claim Updates")
        print("│")
        print("│ 💡 TIP: Use 'Token Operations' menu for available actions")

        input("\nPress Enter to continue...")

    def quick_advance_state(self, current_datum, user_address, project_name):
        """Quick state advancement without field changes"""
        new_state = min(current_datum.params.project_state + 1, 3)
        state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}

        print(
            f"│ Current State: {current_datum.params.project_state} ({state_names.get(current_datum.params.project_state)})"
        )
        print(f"│ New State: {new_state} ({state_names.get(new_state)})")

        if not self.menu.confirm_action(
            f"Advance project state from {current_datum.params.project_state} to {new_state}?"
        ):
            self.menu.print_info("State advance cancelled")
            return

        # Use existing transaction method (which defaults to state advancement)
        self.menu.print_info("Creating state advancement transaction...")
        result = self.token_operations.create_project_update_transaction(
            user_address, None, project_name
        )

        if not result["success"]:
            self.menu.print_error(f"Failed to create transaction: {result['error']}")
            return

        self.menu.print_success("State advancement transaction created!")
        print(f"TX ID: {result['tx_id']}")

        if self.menu.confirm_action("Submit transaction to network?"):
            self.menu.print_info("Submitting transaction...")
            tx_id = self.transactions.submit_transaction(result["transaction"])
            self.menu.print_success(f"Transaction submitted! TX ID: {tx_id}")
        else:
            self.menu.print_info("Transaction not submitted")

    def update_project_information(self, current_datum, user_address, project_name):
        """Update project ID, metadata, and state"""
        self.menu.print_section("UPDATE PROJECT INFORMATION")

        # Project ID update
        current_id = current_datum.params.project_id.hex()
        print(f"│ Current Project ID: {current_id[:20]}...")
        new_id_input = self.menu.get_input(
            "Enter new Project ID (64 hex chars) or press Enter to keep current"
        )

        if new_id_input.strip():
            try:
                if len(new_id_input) != 64:
                    raise ValueError("Project ID must be exactly 64 hex characters")
                new_project_id = bytes.fromhex(new_id_input)
            except ValueError as e:
                self.menu.print_error(f"Invalid Project ID: {e}")
                input("Press Enter to continue...")
                return
        else:
            new_project_id = current_datum.params.project_id

        # Metadata update
        current_metadata = current_datum.params.project_metadata.decode("utf-8", errors="ignore")
        print(f"│ Current Metadata: {current_metadata[:50]}...")
        new_metadata_input = self.menu.get_input(
            "Enter new Metadata URL or press Enter to keep current"
        )

        if new_metadata_input.strip():
            new_metadata = new_metadata_input.encode("utf-8")
        else:
            new_metadata = current_datum.params.project_metadata

        # Project State update
        current_state = current_datum.params.project_state
        state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}
        state_descriptions = {
            0: "Full editing allowed - all fields mutable",
            1: "Limited editing - basic fields locked",
            2: "Minimal editing - most fields immutable",
            3: "Read-only - project closed"
        }

        print(f"│ Current State: {current_state} ({state_names.get(current_state)})")
        print("│ Available States:")
        for state_num, name in state_names.items():
            status = "CURRENT" if state_num == current_state else ""
            print(f"│   {state_num}. {name} - {state_descriptions[state_num]} {status}")

        # Get user's choice for new state
        try:
            new_state_input = self.menu.get_input("Select new project state (0-3, or press Enter to keep current)")
            if new_state_input.strip():
                new_state = int(new_state_input)
                if new_state not in [0, 1, 2, 3]:
                    self.menu.print_error("Invalid state. Must be 0, 1, 2, or 3")
                    input("Press Enter to continue...")
                    return
            else:
                new_state = current_state
        except ValueError:
            self.menu.print_error("Invalid input. Please enter a number 0-3")
            input("Press Enter to continue...")
            return

        # Show preview
        self.menu.print_section("PREVIEW CHANGES")
        changes_detected = False

        if new_project_id != current_datum.params.project_id:
            print(f"│ Project ID: {current_id[:20]}... → {new_project_id.hex()[:20]}...")
            changes_detected = True
        if new_metadata != current_datum.params.project_metadata:
            print(f"│ Metadata: {current_metadata[:30]}... → {new_metadata_input[:30]}...")
            changes_detected = True
        if new_state != current_state:
            print(f"│ Project State: {current_state} ({state_names[current_state]}) → {new_state} ({state_names[new_state]})")
            changes_detected = True

            # Show warnings based on state change
            if new_state < current_state:
                self.menu.print_warning("⚠️  REVERTING TO LOWER STATE:")
                print("│   • This will make previously locked fields editable again")
                print("│   • Use caution as this may affect project integrity")
            elif new_state > current_state:
                self.menu.print_warning("⚠️  ADVANCING TO HIGHER STATE:")
                print("│   • This will lock more fields from editing")
                print("│   • Higher states provide more restrictions")

        if not changes_detected:
            self.menu.print_info("No changes detected")
            input("Press Enter to continue...")
            return

        # Prepare update fields
        update_fields = {}
        if new_project_id != current_datum.params.project_id:
            update_fields["project_id"] = new_project_id
        if new_metadata != current_datum.params.project_metadata:
            update_fields["project_metadata"] = new_metadata
        if new_state != current_state:
            update_fields["project_state"] = new_state

        # Create custom datum and submit
        self.create_custom_update_transaction(
            current_datum,
            user_address,
            project_name,
            update_fields,
        )

    def update_token_economics(self, current_datum, user_address, project_name):
        """Update token policy ID, token name, and total supply"""
        self.menu.print_section("UPDATE TOKEN ECONOMICS")

        # Current token information
        current_policy_id = (
            current_datum.project_token.policy_id.hex() if current_datum.project_token.policy_id else "empty"
        )
        current_token_name = (
            current_datum.project_token.token_name.decode("utf-8", errors="ignore")
            if current_datum.project_token.token_name
            else "empty"
        )
        current_total_supply = current_datum.project_token.total_supply

        print(f"│ Current Token Policy ID: {current_policy_id}")
        print(f"│ Current Token Name: {current_token_name}")
        print(f"│ Current Total Supply: {current_total_supply:,}")

        # Token Policy ID update
        new_policy_input = self.menu.get_input(
            "Enter new Token Policy ID (56 hex chars) or press Enter to keep current"
        )

        if new_policy_input.strip():
            try:
                if len(new_policy_input) != 56:
                    raise ValueError("Token Policy ID must be exactly 56 hex characters")
                new_policy_id = bytes.fromhex(new_policy_input)
            except ValueError as e:
                self.menu.print_error(f"Invalid Token Policy ID: {e}")
                input("Press Enter to continue...")
                return
        else:
            new_policy_id = current_datum.project_token.policy_id

        # Token Name update
        new_token_name_input = self.menu.get_input(
            "Enter new Token Name or press Enter to keep current"
        )

        if new_token_name_input.strip():
            new_token_name = new_token_name_input.encode("utf-8")
        else:
            new_token_name = current_datum.project_token.token_name

        # Total Supply update
        new_total_input = self.menu.get_input(
            "Enter new Total Supply or press Enter to keep current"
        )
        if new_total_input.strip():
            try:
                new_total_supply = int(new_total_input)
                if new_total_supply <= 0:
                    raise ValueError("Total supply must be positive")
            except ValueError as e:
                self.menu.print_error(f"Invalid Total Supply: {e}")
                input("Press Enter to continue...")
                return
        else:
            new_total_supply = current_datum.project_token.total_supply

        # Show preview
        self.menu.print_section("PREVIEW CHANGES")
        changes_detected = False

        if new_policy_id != current_datum.project_token.policy_id:
            new_policy_display = new_policy_id.hex() if new_policy_id else "empty"
            print(f"│ Token Policy ID: {current_policy_id} → {new_policy_display}")
            changes_detected = True
        if new_token_name != current_datum.project_token.token_name:
            print(f"│ Token Name: {current_token_name} → {new_token_name_input}")
            changes_detected = True
        if new_total_supply != current_datum.project_token.total_supply:
            print(f"│ Total Supply: {current_datum.project_token.total_supply:,} → {new_total_supply:,}")
            changes_detected = True

        if not changes_detected:
            self.menu.print_info("No changes detected")
            input("Press Enter to continue...")
            return

        # Prepare update fields
        update_fields = {}
        if new_policy_id != current_datum.project_token.policy_id:
            update_fields["token_policy_id"] = new_policy_id
        if new_token_name != current_datum.project_token.token_name:
            update_fields["token_name"] = new_token_name
        if new_total_supply != current_datum.project_token.total_supply:
            update_fields["total_supply"] = new_total_supply

        # Create custom datum and submit
        self.create_custom_update_transaction(
            current_datum,
            user_address,
            project_name,
            update_fields,
        )




    def batch_update_all_fields(self, current_datum, user_address, project_name):
        """Batch update menu allowing accumulation of changes across all categories"""
        self.menu.print_section("BATCH UPDATE ALL FIELDS")
        print("│ Accumulate changes across all categories before creating transaction")
        print("│")

        # Initialize change accumulator
        accumulated_changes = {}

        while True:
            self.display_batch_update_menu(accumulated_changes)

            try:
                choice = self.menu.get_input("Select option (1-9, 0 to cancel)")
                choice_num = int(choice)

                if choice_num == 0:
                    self.menu.print_info("Batch update cancelled")
                    return
                elif choice_num == 1:
                    self.accumulate_project_info_changes(current_datum, accumulated_changes)
                elif choice_num == 2:
                    self.accumulate_token_changes(current_datum, accumulated_changes)
                elif choice_num == 3:
                    self.accumulate_stakeholder_changes(current_datum, accumulated_changes)
                elif choice_num == 4:
                    self.accumulate_certification_changes(current_datum, accumulated_changes)
                elif choice_num == 5:
                    self.review_accumulated_changes(current_datum, accumulated_changes)
                elif choice_num == 6:
                    if accumulated_changes:
                        self.submit_accumulated_changes(
                            current_datum, user_address, project_name, accumulated_changes
                        )
                        return
                    else:
                        self.menu.print_info("No changes accumulated yet")
                        input("Press Enter to continue...")
                elif choice_num == 7:
                    accumulated_changes.clear()
                    self.menu.print_success("All accumulated changes cleared")
                    input("Press Enter to continue...")
                else:
                    self.menu.print_error("Invalid option selected")

            except ValueError:
                self.menu.print_error("Invalid input - please enter a number")

    def display_batch_update_menu(self, accumulated_changes):
        """Display the batch update menu with current status"""
        self.menu.print_section("BATCH UPDATE MENU")

        changes_count = len(accumulated_changes)
        if changes_count > 0:
            print(f"│ 📊 Accumulated Changes: {changes_count} field(s)")
        else:
            print("│ 📊 No changes accumulated yet")
        print("│")

        options = [
            "Update Project Information (ID, Metadata, State)",
            "Update Token Economics (Policy ID, Token Name, Supply)",
            "Update Stakeholders (Participation Management)",
            "Update Certifications (Certification Records)",
            "Review All Changes",
            "Submit All Changes",
            "Clear All Changes",
            "Cancel",
        ]

        self.menu.print_info("BATCH UPDATE OPTIONS:")
        for i, option in enumerate(options, 1):
            if i == len(options):  # Cancel option
                print(f"│ 0. {option}")
            else:
                # Add indicator if changes exist for this category
                indicator = ""
                if i == 1 and any(
                    key in accumulated_changes
                    for key in ["project_id", "project_metadata", "project_state"]
                ):
                    indicator = " ✓"
                elif i == 2 and any(
                    key in accumulated_changes
                    for key in ["token_policy_id", "token_name", "total_supply"]
                ):
                    indicator = " ✓"
                elif i == 3 and any(key in accumulated_changes for key in ["stakeholders"]):
                    indicator = " ✓"
                elif i == 4 and any(key in accumulated_changes for key in ["certifications"]):
                    indicator = " ✓"
                print(f"│ {i}. {option}{indicator}")

    def accumulate_project_info_changes(self, current_datum, accumulated_changes):
        """Accumulate project information changes without creating transaction"""
        self.menu.print_section("ACCUMULATE PROJECT INFO CHANGES")

        # Project ID update
        current_id = current_datum.params.project_id.hex()
        print(f"│ Current Project ID: {current_id[:20]}...")
        new_id_input = self.menu.get_input(
            "Enter new Project ID (64 hex chars) or press Enter to keep current"
        )

        if new_id_input.strip():
            new_project_id = bytes.fromhex(new_id_input)
            accumulated_changes["project_id"] = new_project_id
            self.menu.print_success("✓ Project ID change accumulated")

        # Metadata update - with string-to-bytes conversion
        current_metadata = current_datum.params.project_metadata
        current_metadata_display = (
            current_metadata.decode("utf-8", errors="ignore") if current_metadata else "empty"
        )
        print(f"│ Current Metadata: {current_metadata_display[:50]}...")
        new_metadata_input = self.menu.get_input(
            "Enter new Metadata (string/URL) or press Enter to keep current"
        )

        if new_metadata_input.strip():
            try:
                # Convert string to UTF-8 bytes
                new_metadata = new_metadata_input.encode("utf-8")
                accumulated_changes["project_metadata"] = new_metadata
                self.menu.print_success("✓ Project Metadata change accumulated")
            except Exception as e:
                self.menu.print_error(f"Invalid Metadata: {e}")
                input("Press Enter to continue...")
                return

        # Project State update
        current_state = current_datum.params.project_state
        state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}
        print(
            f"│ Current Project State: {current_state} ({state_names.get(current_state, 'Unknown')})"
        )
        new_state_input = self.menu.get_input(
            "Enter new Project State (0-3) or press Enter to keep current"
        )

        if new_state_input.strip():
            try:
                new_state = int(new_state_input)
                if new_state < 0 or new_state > 3:
                    raise ValueError("Project state must be between 0 and 3")
                # Allow state changes in any direction - user has been warned in UI
                accumulated_changes["project_state"] = new_state
                self.menu.print_success(
                    f"✓ Project State change accumulated: {current_state} → {new_state}"
                )
            except ValueError as e:
                self.menu.print_error(f"Invalid Project State: {e}")
                input("Press Enter to continue...")
                return

        input("Press Enter to continue...")


    def accumulate_token_changes(self, current_datum, accumulated_changes):
        """Accumulate token economics changes without creating transaction"""
        self.menu.print_section("ACCUMULATE TOKEN CHANGES")

        # Token Policy ID update
        current_policy = current_datum.project_token.policy_id.hex()
        print(f"│ Current Token Policy ID: {current_policy}")
        new_policy_input = self.menu.get_input(
            "Enter new Token Policy ID (56 hex chars) or press Enter to keep current"
        )

        if new_policy_input.strip():
            try:
                new_token_policy = bytes.fromhex(new_policy_input)
                if len(new_token_policy) != 28:
                    raise ValueError("Token Policy ID must be exactly 28 bytes (56 hex chars)")
                accumulated_changes["token_policy_id"] = new_token_policy
                self.menu.print_success("✓ Token Policy ID change accumulated")
            except ValueError as e:
                self.menu.print_error(f"Invalid Token Policy ID: {e}")
                input("Press Enter to continue...")
                return

        # Token Name update - with string-to-bytes conversion
        current_token_name = current_datum.project_token.token_name
        current_token_display = (
            current_token_name.decode("utf-8", errors="ignore") if current_token_name else "empty"
        )
        print(f"│ Current Token Name: {current_token_display}")
        new_token_name_input = self.menu.get_input(
            "Enter new Token Name (string) or press Enter to keep current"
        )

        if new_token_name_input.strip():
            try:
                # Convert string to UTF-8 bytes
                new_token_name = new_token_name_input.encode("utf-8")
                accumulated_changes["token_name"] = new_token_name
                self.menu.print_success("✓ Token Name change accumulated")
            except Exception as e:
                self.menu.print_error(f"Invalid Token Name: {e}")
                input("Press Enter to continue...")
                return

        print(f"│ Current Total Supply: {current_datum.project_token.total_supply:,}")

        # Total Supply update
        new_total_input = self.menu.get_input(
            "Enter new Total Supply or press Enter to keep current"
        )
        if new_total_input.strip():
            try:
                new_total_supply = int(new_total_input)
                if new_total_supply <= 0:
                    raise ValueError("Total supply must be positive")
                accumulated_changes["total_supply"] = new_total_supply
                self.menu.print_success("✓ Total Supply change accumulated")
            except ValueError as e:
                self.menu.print_error(f"Invalid Total Supply: {e}")
                input("Press Enter to continue...")
                return


        input("Press Enter to continue...")

    def review_accumulated_changes(self, current_datum, accumulated_changes):
        """Review all accumulated changes"""
        self.menu.print_section("REVIEW ACCUMULATED CHANGES")

        if not accumulated_changes:
            self.menu.print_info("No changes accumulated yet")
            input("Press Enter to continue...")
            return

        print(f"│ Total Changes: {len(accumulated_changes)}")
        print("│")

        # Project Information Changes
        project_info_changes = [
            key for key in accumulated_changes if key in ["project_id", "project_metadata", "project_state"]
        ]
        if project_info_changes:
            print("│ 📋 PROJECT INFORMATION:")
            if "project_id" in accumulated_changes:
                current_id = current_datum.params.project_id.hex()[:20]
                new_id = accumulated_changes["project_id"].hex()[:20]
                print(f"│   • Project ID: {current_id}... → {new_id}...")
            if "project_metadata" in accumulated_changes:
                current_meta = (
                    current_datum.params.project_metadata.hex()[:20]
                    if current_datum.params.project_metadata
                    else "empty"
                )
                new_meta = accumulated_changes["project_metadata"].hex()[:20]
                print(f"│   • Metadata: {current_meta}... → {new_meta}...")
            if "project_state" in accumulated_changes:
                state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}
                current_state = current_datum.params.project_state
                new_state = accumulated_changes["project_state"]
                current_state_name = state_names.get(current_state, "Unknown")
                new_state_name = state_names.get(new_state, "Unknown")
                print(f"│   • Project State: {current_state} ({current_state_name}) → {new_state} ({new_state_name})")
            print("│")

        # Token Economics Changes
        token_changes = [
            key for key in accumulated_changes if key in ["token_policy_id", "token_name", "total_supply"]
        ]
        if token_changes:
            print("│ 💰 TOKEN ECONOMICS:")
            if "token_policy_id" in accumulated_changes:
                current_policy = (
                    current_datum.project_token.policy_id.hex() if current_datum.project_token.policy_id else "empty"
                )
                new_policy = accumulated_changes["token_policy_id"].hex()
                print(f"│   • Token Policy ID: {current_policy} → {new_policy}")
            if "token_name" in accumulated_changes:
                current_name = (
                    current_datum.project_token.token_name.decode("utf-8", errors="ignore")
                    if current_datum.project_token.token_name else "empty"
                )
                new_name = accumulated_changes["token_name"].decode("utf-8", errors="ignore")
                print(f"│   • Token Name: {current_name} → {new_name}")
            if "total_supply" in accumulated_changes:
                current_total = current_datum.project_token.total_supply
                new_total = accumulated_changes["total_supply"]
                print(f"│   • Total Supply: {current_total:,} → {new_total:,}")
            print("│")

        # Stakeholder Changes
        if "stakeholders" in accumulated_changes:
            print("│ 👥 STAKEHOLDER CHANGES:")
            current_count = len(current_datum.stakeholders)
            new_count = len(accumulated_changes["stakeholders"])
            print(f"│   • Stakeholder Count: {current_count} → {new_count}")

            # Calculate total participations
            current_total_participation = sum(s.participation for s in current_datum.stakeholders)
            new_total_participation = sum(s.participation for s in accumulated_changes["stakeholders"])
            print(f"│   • Total Participation: {current_total_participation:,} → {new_total_participation:,}")
            print("│")

        # Certification Changes
        if "certifications" in accumulated_changes:
            print("│ 🏆 CERTIFICATION CHANGES:")
            current_count = len(current_datum.certifications)
            new_count = len(accumulated_changes["certifications"])
            print(f"│   • Certification Count: {current_count} → {new_count}")

            # Calculate total quantities
            current_total_quantity = sum(c.quantity for c in current_datum.certifications)
            new_total_quantity = sum(c.quantity for c in accumulated_changes["certifications"])
            print(f"│   • Total Certified Quantity: {current_total_quantity:,} → {new_total_quantity:,}")
            print("│")


        input("Press Enter to continue...")

    def submit_accumulated_changes(
        self, current_datum, user_address, project_name, accumulated_changes
    ):
        """Submit all accumulated changes in a single transaction"""
        self.menu.print_section("SUBMIT ACCUMULATED CHANGES")

        # Show final summary
        print(f"│ Ready to submit {len(accumulated_changes)} change(s):")
        for key, value in accumulated_changes.items():
            if isinstance(value, bytes):
                print(f"│   • {key}: {value.hex()[:20]}...")
            else:
                print(f"│   • {key}: {value}")
        print("│")

        if not self.menu.confirm_action("Submit all accumulated changes in one transaction?"):
            self.menu.print_info("Batch update cancelled")
            input("Press Enter to continue...")
            return

        # Use existing custom transaction method
        self.create_custom_update_transaction(
            current_datum, user_address, project_name, accumulated_changes
        )

    def update_stakeholders(self, current_datum, user_address, project_name):
        """Update stakeholders in individual transaction"""
        self.menu.print_section("UPDATE STAKEHOLDERS")

        accumulated_changes = {}
        self.accumulate_stakeholder_changes(current_datum, accumulated_changes)

        if accumulated_changes:
            self.create_custom_update_transaction(
                current_datum, user_address, project_name, accumulated_changes
            )

    def update_certifications(self, current_datum, user_address, project_name):
        """Update certifications in individual transaction"""
        self.menu.print_section("UPDATE CERTIFICATIONS")

        accumulated_changes = {}
        self.accumulate_certification_changes(current_datum, accumulated_changes)

        if accumulated_changes:
            self.create_custom_update_transaction(
                current_datum, user_address, project_name, accumulated_changes
            )

    def accumulate_stakeholder_changes(self, current_datum, accumulated_changes):
        """Accumulate stakeholder participation changes without creating transaction"""
        self.menu.print_section("ACCUMULATE STAKEHOLDER CHANGES")

        # Show current stakeholders
        print(f"│ Current Stakeholders ({len(current_datum.stakeholders)}):")
        for i, stakeholder in enumerate(current_datum.stakeholders):
            stakeholder_name = stakeholder.stakeholder.decode("utf-8", errors="ignore")
            pkh_display = (
                (
                    stakeholder.pkh.hex()[:16] + "..."
                    if len(stakeholder.pkh.hex()) > 16
                    else stakeholder.pkh.hex()
                )
                if stakeholder.pkh
                else "empty"
            )
            print(
                f"│   {i+1}. {stakeholder_name} - PKH: {pkh_display} - Participation: {stakeholder.participation:,}"
            )
        print("│")

        # Get current stakeholders list (start with existing) - use deep copy to avoid reference issues
        new_stakeholders = copy.deepcopy(list(current_datum.stakeholders))

        # For batch mode, show a simplified direct action menu
        print("│ STAKEHOLDER OPERATIONS:")
        print("│ 1. Add New Stakeholder")
        print("│ 2. Edit Existing Stakeholder")
        print("│ 3. Remove Stakeholder")
        print("│ 4. View Current List")
        print("│ 0. Done with Stakeholder Changes")

        try:
            choice = self.menu.get_input("Select stakeholder operation (0-4)")
            choice_num = int(choice)

            if choice_num == 0:
                pass  # Skip changes
            elif choice_num == 1:
                self.add_stakeholder_to_list(new_stakeholders)
            elif choice_num == 2:
                self.edit_stakeholder_in_list(new_stakeholders)
            elif choice_num == 3:
                self.remove_stakeholder_from_list(new_stakeholders)
            elif choice_num == 4:
                self.display_stakeholder_list(new_stakeholders)
                input("Press Enter to continue...")
            else:
                self.menu.print_error("Invalid option")

        except ValueError:
            self.menu.print_error("Invalid input - please enter a number")

        # Validate total participation equals total supply
        if new_stakeholders:
            total_participation = sum([s.participation for s in new_stakeholders])
            expected_supply = accumulated_changes.get(
                "total_supply", current_datum.project_token.total_supply
            )

            if total_participation > expected_supply:
                self.menu.print_error(
                    f"Total stakeholder participation ({total_participation:,}) must be less than or equal to total supply ({expected_supply:,})"
                )
                input("Press Enter to continue...")
                return

        # Only add to accumulated changes if stakeholders were modified
        def stakeholders_are_equal(list1, list2):
            """Compare two lists of stakeholders for equality"""
            if len(list1) != len(list2):
                return False

            for s1, s2 in zip(list1, list2):
                if (
                    s1.stakeholder != s2.stakeholder
                    or s1.pkh != s2.pkh
                    or s1.participation != s2.participation
                ):
                    return False
            return True

        if not stakeholders_are_equal(new_stakeholders, list(current_datum.stakeholders)):
            accumulated_changes["stakeholders"] = new_stakeholders
            self.menu.print_success(
                f"✓ Stakeholder changes accumulated ({len(new_stakeholders)} stakeholders)"
            )

        input("Press Enter to continue...")

    def accumulate_certification_changes(self, current_datum, accumulated_changes):
        """Accumulate certification changes without creating transaction"""
        self.menu.print_section("ACCUMULATE CERTIFICATION CHANGES")

        # Check project state restrictions
        project_state = current_datum.params.project_state
        if project_state == 1:
            self.menu.print_warning("⚠️ Project state is 1 (Distributed) - real certification values cannot be modified")
            print("│ In this state:")
            print("│   • real_certification_date and real_quantity must remain empty")
            print("│   • Only basic certification fields can be modified")
            print("│")

        # Show current certifications
        print(f"│ Current Certifications ({len(current_datum.certifications)}):")
        for i, cert in enumerate(current_datum.certifications):
            cert_date = cert.certification_date
            real_date = cert.real_certification_date
            print(
                f"│   {i+1}. Cert Date: {cert_date} - Quantity: {cert.quantity:,} - Real Date: {real_date} - Real Quantity: {cert.real_quantity:,}"
            )
        print("│")

        # Get current certifications list (start with existing)
        new_certifications = list(current_datum.certifications)

        # For batch mode, show a simplified direct action menu
        print("│ CERTIFICATION OPERATIONS:")
        print("│ 1. Add New Certification")
        print("│ 2. Edit Existing Certification")
        print("│ 3. Remove Certification")
        print("│ 4. View Current List")
        print("│ 0. Done with Certification Changes")

        try:
            choice = self.menu.get_input("Select certification operation (0-4)")
            choice_num = int(choice)

            if choice_num == 0:
                pass  # Skip changes
            elif choice_num == 1:
                self.add_certification_to_list(new_certifications, project_state)
            elif choice_num == 2:
                self.edit_certification_in_list(new_certifications, project_state)
            elif choice_num == 3:
                self.remove_certification_from_list(new_certifications)
            elif choice_num == 4:
                self.display_certification_list(new_certifications)
                input("Press Enter to continue...")
            else:
                self.menu.print_error("Invalid option")

        except ValueError:
            self.menu.print_error("Invalid input - please enter a number")

        # Only add to accumulated changes if certifications were modified
        if new_certifications != list(current_datum.certifications):
            accumulated_changes["certifications"] = new_certifications
            self.menu.print_success(
                f"✓ Certification changes accumulated ({len(new_certifications)} certifications)"
            )

        input("Press Enter to continue...")


    def create_custom_update_transaction(
        self, current_datum, user_address, project_name, field_updates
    ):
        """Create transaction with custom field updates"""

        try:
            # Build custom datum with user updates
            custom_datum = self.build_custom_datum(current_datum, field_updates)

            self.menu.print_info("Creating custom update transaction...")
            result = self.token_operations.create_project_update_transaction(
                user_address, custom_datum, project_name
            )

            if not result["success"]:
                self.menu.print_error(f"Failed to create transaction: {result['error']}")
                input("Press Enter to continue...")
                return

            self.menu.print_success("Custom update transaction created!")
            print(f"TX ID: {result['tx_id']}")

            # Show transaction details
            old_datum = result.get("old_datum", current_datum)
            new_datum = result.get("new_datum", custom_datum)
            self.display_transaction_changes(old_datum, new_datum)

            if self.menu.confirm_action("Submit transaction to network?"):
                self.menu.print_info("Submitting transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])
                self.menu.print_success(f"Transaction submitted! TX ID: {tx_id}")
            else:
                self.menu.print_info("Transaction not submitted")

            input("Press Enter to continue...")

        except Exception as e:
            self.menu.print_error(f"Custom update failed: {e}")
            input("Press Enter to continue...")

    def build_custom_datum(self, current_datum, field_updates):
        """Build new datum with selective field updates"""

        # Start with current values
        new_project_id = field_updates.get("project_id", current_datum.params.project_id)
        new_project_metadata = field_updates.get(
            "project_metadata", current_datum.params.project_metadata
        )
        new_project_state = field_updates.get("project_state", current_datum.params.project_state)


        new_policy_id = field_updates.get("token_policy_id", current_datum.project_token.policy_id)
        new_token_name = field_updates.get("token_name", current_datum.project_token.token_name)
        new_total_supply = field_updates.get(
            "total_supply", current_datum.project_token.total_supply
        )

        # Build new structures
        new_params = DatumProjectParams(
            project_id=new_project_id,
            project_metadata=new_project_metadata,
            project_state=new_project_state,
        )

        new_token = TokenProject(
            policy_id=new_policy_id,
            token_name=new_token_name,
            total_supply=new_total_supply,
        )

        # Handle stakeholders and certifications updates
        new_stakeholders = field_updates.get("stakeholders", current_datum.stakeholders)
        new_certifications = field_updates.get("certifications", current_datum.certifications)

        return DatumProject(
            params=new_params,
            project_token=new_token,
            stakeholders=new_stakeholders,
            certifications=new_certifications,
        )

    def display_transaction_changes(self, old_datum, new_datum):
        """Display what changed in the transaction"""
        self.menu.print_section("TRANSACTION CHANGES")

        changes_made = False

        # Check each field for changes
        if old_datum.params.project_id != new_datum.params.project_id:
            print(
                f"│ Project ID: {old_datum.params.project_id.hex()[:20]}... → {new_datum.params.project_id.hex()[:20]}..."
            )
            changes_made = True

        if old_datum.params.project_metadata != new_datum.params.project_metadata:
            old_meta = old_datum.params.project_metadata.decode("utf-8", errors="ignore")[:30]
            new_meta = new_datum.params.project_metadata.decode("utf-8", errors="ignore")[:30]
            print(f"│ Metadata: {old_meta}... → {new_meta}...")
            changes_made = True

        if old_datum.params.project_state != new_datum.params.project_state:
            state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}
            old_state = f"{old_datum.params.project_state} ({state_names.get(old_datum.params.project_state)})"
            new_state = f"{new_datum.params.project_state} ({state_names.get(new_datum.params.project_state)})"
            print(f"│ Project State: {old_state} → {new_state}")
            changes_made = True

        if old_datum.project_token.policy_id != new_datum.project_token.policy_id:
            old_project_policy = (
                old_datum.project_token.policy_id.hex()
                if old_datum.project_token.policy_id
                else "empty"
            )
            new_project_policy = (
                new_datum.project_token.policy_id.hex()
                if new_datum.project_token.policy_id
                else "empty"
            )
            print(f"│ Project Policy: {old_project_policy} → {new_project_policy}")
            changes_made = True

        if old_datum.project_token.token_name != new_datum.project_token.token_name:
            old_name = (
                old_datum.project_token.token_name.decode("utf-8", errors="ignore")
                if old_datum.project_token.token_name
                else "empty"
            )
            new_name = (
                new_datum.project_token.token_name.decode("utf-8", errors="ignore")
                if new_datum.project_token.token_name
                else "empty"
            )
            print(f"│ Token Name: {old_name} → {new_name}")
            changes_made = True

        if old_datum.project_token.total_supply != new_datum.project_token.total_supply:
            print(
                f"│ Total Supply: {old_datum.project_token.total_supply:,} → {new_datum.project_token.total_supply:,}"
            )
            changes_made = True


        if not changes_made:
            print("│ No changes detected")

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

    def select_wallet_for_token_operation(self, purpose: str) -> Optional[tuple]:
        """
        Ask user to select a wallet for token operations and return wallet info

        Args:
            purpose: Description of what the wallet will be used for

        Returns:
            Tuple of (wallet_name, wallet_address) or None if cancelled
        """
        wallets = self.wallet_manager.get_wallet_names()

        if not wallets:
            self.menu.print_error("No wallets available")
            return None

        self.menu.print_section(f"WALLET SELECTION FOR {purpose.upper()}")
        self.menu.print_info(f"Select wallet to use for {purpose}:")

        for i, wallet_name in enumerate(wallets, 1):
            is_active = wallet_name == self.wallet_manager.get_default_wallet_name()
            status = " (CURRENT)" if is_active else ""
            self.menu.print_menu_option(f"{i}", f"{wallet_name}{status}")

        try:
            choice = input(f"\nSelect wallet (1-{len(wallets)}, or 'q' to cancel): ").strip().lower()
            if choice == 'q':
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(wallets):
                wallet_name = wallets[choice_num - 1]
                wallet = self.wallet_manager.get_wallet(wallet_name)
                wallet_address = wallet.get_address(0)
                self.menu.print_info(f"Selected wallet: {wallet_name}")
                return (wallet_name, wallet_address)
            else:
                self.menu.print_error(f"Please enter a number between 1 and {len(wallets)}")
                return None
        except ValueError:
            self.menu.print_error("Please enter a valid number")
            return None

    def select_wallet_or_address_for_destination(self, purpose: str) -> Optional[tuple]:
        """
        Ask user to select a wallet or enter a custom address for destination

        Args:
            purpose: Description of what the destination will be used for

        Returns:
            Tuple of (address, wallet_name_or_none) or None if cancelled
            - address: The selected address (from wallet or custom)
            - wallet_name_or_none: Wallet name if wallet selected, None if custom address
        """
        wallets = self.wallet_manager.get_wallet_names()

        if not wallets:
            self.menu.print_error("No wallets available. Please add a wallet first.")
            return None

        self.menu.print_section(f"DESTINATION SELECTION FOR {purpose.upper()}")
        self.menu.print_info(f"Select destination for {purpose}:")

        # Show wallet options
        for i, wallet_name in enumerate(wallets, 1):
            is_active = wallet_name == self.wallet_manager.get_default_wallet_name()
            status = " (CURRENT)" if is_active else ""
            self.menu.print_menu_option(f"{i}", f"{wallet_name}{status}")

        # Add custom address option
        self.menu.print_menu_option(f"{len(wallets) + 1}", "Enter custom address")
        self.menu.print_menu_option("0", "Cancel")

        try:
            choice = input(f"\nSelect option (0-{len(wallets) + 1}): ").strip()
            if choice == '0':
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(wallets):
                # Wallet selected
                wallet_name = wallets[choice_num - 1]
                wallet = self.wallet_manager.get_wallet(wallet_name)
                wallet_address = wallet.get_address(0)
                self.menu.print_info(f"Selected wallet: {wallet_name}")
                return (wallet_address, wallet_name)
            elif choice_num == len(wallets) + 1:
                # Custom address option selected
                custom_address = self.menu.get_input("Enter destination address").strip()
                if not custom_address:
                    self.menu.print_error("Address cannot be empty")
                    return None

                # Validate the address
                resolved_address = self.resolve_address_input(custom_address)
                if not resolved_address:
                    self.menu.print_error(f"Invalid address: {custom_address}")
                    return None

                try:
                    address_obj = pc.Address.from_primitive(resolved_address)
                    self.menu.print_info(f"Using custom address: {resolved_address[50:]}...")
                    return (address_obj, None)
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return None
            else:
                self.menu.print_error(f"Please enter a number between 0 and {len(wallets) + 1}")
                return None
        except ValueError:
            self.menu.print_error("Please enter a valid number")
            return None

    def select_wallet_or_address_for_source(self, purpose: str) -> Optional[tuple]:
        """
        Ask user to select a wallet or enter a custom address for source operations

        Args:
            purpose: Description of what the source will be used for

        Returns:
            Tuple of (address, wallet_name_or_none, switch_wallet) or None if cancelled
            - address: The selected address (from wallet or custom)
            - wallet_name_or_none: Wallet name if wallet selected, None if custom address
            - switch_wallet: Boolean indicating if we should switch to the selected wallet
        """
        wallets = self.wallet_manager.get_wallet_names()

        if not wallets:
            self.menu.print_error("No wallets available. Please add a wallet first.")
            return None

        self.menu.print_section(f"SOURCE SELECTION FOR {purpose.upper()}")
        self.menu.print_info(f"Select source wallet for {purpose}:")

        # Show wallet options
        for i, wallet_name in enumerate(wallets, 1):
            is_active = wallet_name == self.wallet_manager.get_default_wallet_name()
            status = " (CURRENT)" if is_active else ""
            self.menu.print_menu_option(f"{i}", f"{wallet_name}{status}")

        # Add custom address option
        self.menu.print_menu_option(f"{len(wallets) + 1}", "Enter custom address")
        self.menu.print_menu_option("0", "Cancel")

        try:
            choice = input(f"\nSelect option (0-{len(wallets) + 1}): ").strip()
            if choice == '0':
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(wallets):
                # Wallet selected
                wallet_name = wallets[choice_num - 1]
                wallet = self.wallet_manager.get_wallet(wallet_name)
                wallet_address = wallet.get_address(0)
                self.menu.print_info(f"Selected wallet: {wallet_name}")
                return (wallet_address, wallet_name, True)  # True = switch to this wallet
            elif choice_num == len(wallets) + 1:
                # Custom address option selected
                custom_address = self.menu.get_input("Enter source address").strip()
                if not custom_address:
                    self.menu.print_error("Address cannot be empty")
                    return None

                # Validate the address
                resolved_address = self.resolve_address_input(custom_address)
                if not resolved_address:
                    self.menu.print_error(f"Invalid address: {custom_address}")
                    return None

                try:
                    address_obj = pc.Address.from_primitive(resolved_address)
                    self.menu.print_info(f"Using custom address: {resolved_address[50:]}...")
                    return (address_obj, None, False)  # False = don't switch wallet
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return None
            else:
                self.menu.print_error(f"Please enter a number between 0 and {len(wallets) + 1}")
                return None
        except ValueError:
            self.menu.print_error("Please enter a valid number")
            return None

    def select_storage_type(self) -> Optional[str]:
        """
        Ask user to select storage type for contracts

        Returns:
            Storage type ('local' or 'reference_script') or None if cancelled
        """
        self.menu.print_section("CONTRACT STORAGE TYPE SELECTION")
        print("│ Choose how to store the compiled contracts:")
        print("│")
        print("│ 1. Local Storage (traditional)")
        print("│    • Contracts stored in local JSON file")
        print("│    • Full CBOR data included in transactions")
        print("│    • Higher transaction fees")
        print("│")
        print("│ 2. Reference Script (on-chain)")
        print("│    • Contracts stored as UTXOs on the blockchain")
        print("│    • Transactions reference the script UTXO")
        print("│    • Lower transaction fees for repeated use")
        print("│    • Requires additional setup transaction")
        print()

        try:
            choice = input("Select storage type (1-2): ").strip()
            if choice == "1":
                return "local"
            elif choice == "2":
                return "reference_script"
            else:
                self.menu.print_error("Invalid choice")
                return None
        except (ValueError, EOFError):
            self.menu.print_error("Invalid input")
            return None

    def select_reference_script_wallets(
        self, source_address: pc.Address
    ) -> Optional[Dict[str, Any]]:
        """
        Select wallets for reference script creation
        Can optionally use different funding wallet from compilation wallet

        Args:
            source_address: Address that compiled the contract (default funding source)

        Returns:
            Dictionary with 'source', 'destination' addresses and wallet info or None if cancelled
        """
        self.menu.print_section("REFERENCE SCRIPT WALLET SELECTION")

        # Show compilation address
        self.menu.print_info(
            f"Contract compiled with: {str(source_address)[:20]}..."
        )

        # Ask if user wants to use different funding wallet
        use_different_funding = self.menu.confirm_action(
            "Use different wallet for funding? (default: use compilation wallet)"
        )

        if use_different_funding:
            # Select funding wallet
            self.menu.print_info("Select funding wallet (will pay transaction fees and provide UTXOs):")
            funding_address = self.select_wallet_for_compilation("funding the reference script transaction")
            if not funding_address:
                return None
        else:
            # Use compilation wallet for funding
            funding_address = source_address

        # Select destination wallet (where reference script UTXO will be sent)
        self.menu.print_info("Select destination wallet (will receive reference script UTXO):")
        print("│ You can choose the same wallet or a different one")
        destination_address = self.select_wallet_for_compilation("storage of the reference script")
        if not destination_address:
            return None

        # Get the wallet instance for the funding address to use for signing
        funding_wallet = None
        for wallet_name in self.wallet_manager.get_wallet_names():
            wallet = self.wallet_manager.get_wallet(wallet_name)
            if wallet and wallet.get_address(0) == funding_address:
                funding_wallet = wallet
                break

        if not funding_wallet:
            self.menu.print_error("Could not find wallet for funding address")
            return None

        return {
            "source": funding_address,
            "destination": destination_address,
            "source_wallet": funding_wallet,
        }


    def _handle_reference_script_creation(
        self, contract_names: List[str], source_address: pc.Address
    ) -> None:
        """
        Handle creation of reference scripts for compiled contracts

        Args:
            contract_names: List of contract names to create reference scripts for
            source_address: Address that compiled the contracts (will fund transactions)
        """
        if not contract_names:
            return

        self.menu.print_section("REFERENCE SCRIPT CREATION")
        self.menu.print_info("Creating reference scripts for compiled contracts...")

        # Get available UTXOs (excluding reserved ones) - this also performs automatic cleanup
        reserved_utxos = self.contract_manager.get_reserved_utxos()
        available_utxos = self.contract_manager.get_available_utxos(source_address, min_ada=52_000_000, auto_cleanup=True)

        self.menu.print_info(f"Reserved UTXOs: {reserved_utxos}")

        if not available_utxos:
            self.menu.print_error("No suitable UTXOs available for reference script creation")
            self.menu.print_info("Requirements: UTXOs with >5 ADA that are not reserved for compilation")
            if reserved_utxos:
                self.menu.print_warning(f"Found {len(reserved_utxos)} UTXOs reserved for project compilation")
                self.menu.print_info("Reserved UTXOs cannot be used for reference scripts to prevent conflicts")

            # Check if any UTXOs exist at all
            all_utxos = self.transactions.context.utxos(source_address)
            total_utxos = len(all_utxos) if all_utxos else 0
            suitable_unreserved = sum(1 for utxo in all_utxos if utxo.output.amount.coin > 52_000_000) if all_utxos else 0

            self.menu.print_info(f"Address has {total_utxos} total UTXOs, {suitable_unreserved} with >52 ADA, {len(reserved_utxos)} reserved")
            self.menu.print_info("Suggestion: Send additional ADA to this address or wait for compilation UTXOs to be released")
            return

        # Get wallet addresses for reference script creation
        wallet_info = self.select_reference_script_wallets(source_address)
        if not wallet_info:
            self.menu.print_error("Reference script creation cancelled - contracts stored locally")
            return

        successful_conversions = []
        failed_conversions = []

        for contract_name in contract_names:
            # Skip protocol contract (not applicable for reference scripts yet)
            if contract_name == "protocol":
                continue

            self.menu.print_info(f"Creating reference script for {contract_name}...")

            try:
                # Create reference script transaction
                if contract_name.startswith("project") and not contract_name.endswith("_nfts"):
                    # Handle project validator
                    result = self.transactions.create_reference_script(
                        project_name=contract_name,
                        destination_address=wallet_info["destination"],
                        source_wallet=wallet_info["source_wallet"],
                        available_utxos=available_utxos,
                    )
                elif contract_name.endswith("_nfts"):
                    # Handle project NFTs minting policy
                    base_project_name = contract_name.replace("_nfts", "")
                    result = self.transactions.create_project_nfts_reference_script(
                        project_name=base_project_name,
                        source_address=wallet_info["source"],
                        destination_address=wallet_info["destination"],
                        source_wallet=wallet_info["source_wallet"],
                        available_utxos=available_utxos,
                    )
                else:
                    self.menu.print_warning(
                        f"Skipping {contract_name} - reference script not supported"
                    )
                    continue

                if result["success"]:
                    # Submit the transaction
                    submit_result = self.transactions.submit_transaction(result["transaction"])

                    if submit_result:  # submit_result is tx_hash on success, None on failure
                        # Mark input UTXO as spent to clean up tracking
                        if "spent_utxo" in result:
                            spent_utxo_ref = f"{result['spent_utxo']['tx_id']}:{result['spent_utxo']['index']}"
                            self.contract_manager.mark_utxo_as_spent(spent_utxo_ref)
                            print(f"Marked UTXO as spent: {spent_utxo_ref}")

                        # Convert contract to reference script
                        ref_utxo = result["reference_utxo"]
                        conversion_success = self.contract_manager.convert_to_reference_script(
                            contract_name,
                            ref_utxo["tx_id"],
                            ref_utxo["output_index"],
                            ref_utxo["address"],
                        )

                        if conversion_success:
                            successful_conversions.append(
                                {
                                    "name": contract_name,
                                    "tx_id": ref_utxo["tx_id"],
                                    "explorer_url": result.get("explorer_url", ""),
                                }
                            )
                            self.menu.print_success(
                                f"✅ {contract_name} reference script created successfully"
                            )
                            self.menu.print_info(f"Transaction submitted: {submit_result}")
                        else:
                            failed_conversions.append(contract_name)
                            self.menu.print_error(
                                f"❌ Failed to convert {contract_name} to reference script"
                            )
                    else:
                        failed_conversions.append(contract_name)
                        self.menu.print_error(
                            f"❌ Failed to submit reference script transaction for {contract_name}"
                        )
                else:
                    failed_conversions.append(contract_name)
                    self.menu.print_error(
                        f"❌ Failed to create reference script for {contract_name}: {result.get('error', 'Unknown error')}"
                    )

            except Exception as e:
                failed_conversions.append(contract_name)
                self.menu.print_error(
                    f"❌ Error creating reference script for {contract_name}: {e}"
                )

        # Show summary
        if successful_conversions:
            self.menu.print_section("REFERENCE SCRIPT CREATION SUMMARY")
            self.menu.print_success(
                f"✅ Successfully created {len(successful_conversions)} reference scripts:"
            )
            for conversion in successful_conversions:
                print(f"│ {conversion['name']}: {conversion['tx_id'][:16]}...")
                if conversion["explorer_url"]:
                    print(f"│   Explorer: {conversion['explorer_url']}")

        if failed_conversions:
            self.menu.print_error(
                f"❌ Failed to create reference scripts for: {', '.join(failed_conversions)}"
            )
            self.menu.print_info("These contracts will remain stored locally")

        # Save the updated contracts (with reference script metadata)
        if successful_conversions:
            self.contract_manager._save_contracts()

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
            self.menu.print_menu_option("2", "Compile Protocol Contracts", "✓")
            self.menu.print_menu_option("3", "Compile Project Contracts", "✓")
            self.menu.print_menu_option("4", "Mint Protocol Tokens", "✓")
            self.menu.print_menu_option("5", "Burn Tokens", "✓")
            self.menu.print_menu_option("6", "Update Protocol Datum", "✓")
            self.menu.print_menu_option("7", "Create Project", "✓")
            self.menu.print_menu_option("8", "Burn Project Tokens", "✓")
            self.menu.print_menu_option("9", "Update Project Datum", "✓")
            self.menu.print_menu_option("10", "Mint Grey Tokens", "🪙")
            self.menu.print_menu_option("11", "Burn Grey Tokens", "🔥")
            self.menu.print_separator()
            self.menu.print_menu_option("12", "Delete Empty Contract", "🗑")
            self.menu.print_menu_option("13", "Delete Grey Tokens Only", "🧹")
            self.menu.print_menu_option("0", "Back to Main Menu")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-13)")

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

                    # Ask for storage type
                    storage_type = self.select_storage_type()
                    if not storage_type:
                        self.menu.print_info("Compilation cancelled")
                        continue

                    self.menu.print_info("Starting contract compilation...")
                    result = self.contract_manager.compile_contracts(
                        protocol_address, project_address, force=True
                    )

                    if result["success"]:
                        self.menu.print_success(result["message"])
                        if result.get("contracts"):
                            print(f"Compiled contracts: {', '.join(result['contracts'])}")

                        # Handle reference script creation if selected
                        if storage_type == "reference_script":
                            self._handle_reference_script_creation(
                                result.get("contracts", []), project_address
                            )
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
                self.mint_grey_tokens_menu()
            elif choice == "11":
                self.burn_grey_tokens_menu()
            elif choice == "12":
                self.delete_empty_contract_menu()
            elif choice == "13":
                self.delete_grey_tokens_menu()
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

        self.menu.print_info(
            "This will compile a new project contract using the existing protocol contract."
        )

        # Compile project contract
        try:
            # Ask for project wallet selection
            project_address = self.select_wallet_for_compilation(
                "compilation of new project contract"
            )
            if not project_address:
                self.menu.print_info("Compilation cancelled")
                input("\nPress Enter to continue...")
                return

            # Ask for storage type
            storage_type = self.select_storage_type()
            if not storage_type:
                self.menu.print_info("Compilation cancelled")
                input("\nPress Enter to continue...")
                return

            self.menu.print_info("Compiling project contract...")
            result = self.contract_manager.compile_project_contract_only(project_address)

            if result["success"]:
                self.menu.print_success("✅ Project contract compiled successfully!")
                self.menu.print_section("COMPILATION RESULTS")
                print(f"│ Contract Name: {result['project_name'].upper()}")
                print(f"│ Policy ID: {result['project_policy_id']}")
                print(f"│ Used UTXO: {result.get('used_utxo', 'N/A')}")
                print(f"│ Saved to Disk: {'✓' if result['saved'] else '✗'}")
                print()

                # Handle reference script creation if selected
                if storage_type == "reference_script":
                    self._handle_reference_script_creation(
                        [result["project_name"]], project_address
                    )
                elif result["saved"]:
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

        # Filter out minting policies and grey token contracts (they can't be deleted directly)
        deletable_contracts = [name for name in contracts if not name.endswith(("_nfts", "_grey"))]

        if not deletable_contracts:
            self.menu.print_error(
                "No deletable contracts found (only minting policies and grey contracts exist)"
            )
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
            choice = int(
                self.menu.get_input(
                    f"Select contract to delete (1-{len(deletable_contracts)}, or 0 to cancel)"
                )
            )
            if choice == 0:
                self.menu.print_info("Operation cancelled")
                input("\nPress Enter to continue...")
                return
            elif 1 <= choice <= len(deletable_contracts):
                contract_name = deletable_contracts[choice - 1]

                # Check if this is a project contract to warn about associated NFT deletion
                is_project_contract = contract_name == "project" or contract_name.startswith(
                    "project_"
                )
                project_nfts_name = f"{contract_name}_nfts"
                has_project_nfts = (
                    is_project_contract and project_nfts_name in self.contract_manager.contracts
                )

                grey_contract_name = f"{contract_name}_grey"
                has_grey_tokens = (
                    is_project_contract and grey_contract_name in self.contract_manager.contracts
                )

                # Ask about deletion scope if this is a project contract with grey tokens
                delete_grey_tokens = True  # Default to delete everything
                if is_project_contract and has_grey_tokens:
                    self.menu.print_section("DELETION OPTIONS")
                    self.menu.print_info("This project has associated grey token contracts.")
                    self.menu.print_info("Choose deletion scope:")
                    print("│ 1. Delete project + NFTs + grey tokens (full cascade)")
                    print("│ 2. Delete project + NFTs only (preserve grey tokens)")

                    scope_choice = self.menu.get_input("Select deletion scope (1-2, default: 1)")
                    if scope_choice.strip() == "2":
                        delete_grey_tokens = False
                        self.menu.print_info("Grey token contracts will be preserved")
                    else:
                        self.menu.print_info("Full cascade deletion selected")

                warning_msg = f"⚠ This will permanently delete contract '{contract_name}' if it has zero balance"
                if has_project_nfts:
                    warning_msg += f"\n  It will also delete the associated '{project_nfts_name}' minting policy"
                if has_grey_tokens:
                    if delete_grey_tokens:
                        warning_msg += f"\n  It will also delete the associated '{grey_contract_name}' contracts"
                    else:
                        warning_msg += f"\n  Grey token contracts will be preserved for future use"

                self.menu.print_warning(warning_msg)
                if not self.menu.confirm_action("Proceed with deletion?"):
                    self.menu.print_info("Deletion cancelled")
                    input("\nPress Enter to continue...")
                    return

                # Check if this is a reference script contract that needs UTXO spending
                contract = self.contract_manager.contracts[contract_name]
                is_reference_script = (
                    hasattr(contract, "storage_type")
                    and contract.storage_type == "reference_script"
                )

                if is_reference_script:
                    self.menu.print_section("REFERENCE SCRIPT DELETION")
                    self.menu.print_info("This contract is stored as a reference script on-chain.")
                    self.menu.print_info(
                        "The reference script UTXO needs to be spent to complete deletion."
                    )

                    # Get wallet selection for UTXO owner
                    wallet_names = self.wallet_manager.get_wallet_names()
                    self.menu.print_info("\nSelect wallet that owns the reference script UTXO:")
                    for i, wallet_name in enumerate(wallet_names, 1):
                        print(f"{i}. {wallet_name}")

                    try:
                        wallet_choice = (
                            int(self.menu.get_input(f"Select wallet (1-{len(wallet_names)})")) - 1
                        )
                        if 0 <= wallet_choice < len(wallet_names):
                            selected_wallet_name = wallet_names[wallet_choice]
                            selected_wallet = self.wallet_manager.get_wallet(selected_wallet_name)
                        else:
                            self.menu.print_error("Invalid wallet selection")
                            input("Press Enter to continue...")
                            return
                    except ValueError:
                        self.menu.print_error("Invalid input")
                        input("Press Enter to continue...")
                        return

                    # Select destination for remaining ADA
                    destination_selection = self.select_wallet_or_address_for_destination("remaining ADA from contract deletion")
                    if not destination_selection:
                        self.menu.print_info("Contract deletion cancelled")
                        input("Press Enter to continue...")
                        return

                    destination_address, destination_wallet_name = destination_selection

                    # Spend the reference script UTXO
                    self.menu.print_info("Spending reference script UTXO...")
                    spend_result = self.contract_manager.spend_reference_script_utxo(
                        contract_name, selected_wallet, destination_address
                    )

                    if not spend_result["success"]:
                        self.menu.print_error(
                            f"Failed to spend reference script UTXO: {spend_result['error']}"
                        )
                        input("Press Enter to continue...")
                        return

                    self.menu.print_success(f"✓ Reference script UTXO spent successfully")
                    self.menu.print_info(f"Transaction ID: {spend_result['tx_id']}")
                    self.menu.print_info(f"Destination: {spend_result['destination']}")

                # Attempt deletion (for both reference scripts and local contracts)
                result = self.contract_manager.delete_contract_if_empty(
                    contract_name, delete_grey_tokens=delete_grey_tokens
                )

                if result["success"]:
                    self.menu.print_success(result["message"])
                    if result.get("saved"):
                        self.menu.print_success("✓ Updated contracts file saved to disk")

                    # Show information about deleted contracts
                    deleted_contracts = result.get("deleted_contracts", [contract_name])
                    if len(deleted_contracts) > 1:
                        self.menu.print_info(
                            f"ℹ Deleted {len(deleted_contracts)} contracts: {', '.join(deleted_contracts)}"
                        )

                    # Show different messages based on deletion reason
                    if "unused address" in result["message"]:
                        self.menu.print_info(
                            "ℹ Contract(s) were never deployed/used, so they were safe to delete"
                        )
                    else:
                        self.menu.print_info(
                            "ℹ Contract(s) had zero balance and no tokens, so they were safe to delete"
                        )
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

    def add_stakeholder_to_list(self, stakeholders_list):
        """Add a new stakeholder to the list"""

        stakeholder_name = self.menu.get_input(
            "Enter stakeholder name/role (e.g., 'investor', 'landowner', 'verifier')"
        )
        if not stakeholder_name.strip():
            self.menu.print_error("Stakeholder name cannot be empty")
            return

        stakeholder_pkh = self.menu.get_input(
            "Enter stakeholder public key hash (56 hex chars, or press Enter for empty)"
        )

        if stakeholder_pkh.strip():
            pkh_bytes = bytes.fromhex(stakeholder_pkh)
            # try:
            #     if len(pkh_bytes) != 28:
            #         raise ValueError("PKH must be exactly 28 bytes (56 hex chars)")
            # except ValueError as e:
            #     self.menu.print_error(f"Invalid PKH: {e}")
            #     return
        else:
            # Empty PKH is allowed (e.g., for "investor" stakeholders)
            pkh_bytes = b""

        participation = self.menu.get_input("Enter participation amount (lovelace)")
        participation_amount = int(participation)
        # try:
        #     if participation_amount <= 0:
        #         raise ValueError("Participation must be positive")
        # except ValueError as e:
        #     self.menu.print_error(f"Invalid participation: {e}")
        #     return

        stakeholder_claimed = TrueData()

        new_stakeholder = StakeHolderParticipation(
            stakeholder=stakeholder_name.encode("utf-8"),
            pkh=pkh_bytes,
            participation=participation_amount,
            claimed=stakeholder_claimed
        )

        stakeholders_list.append(new_stakeholder)
        self.menu.print_success(f"✓ Added stakeholder: {stakeholder_name}")

    def edit_stakeholder_in_list(self, stakeholders_list):
        """Edit an existing stakeholder in the list"""
        if not stakeholders_list:
            self.menu.print_info("No stakeholders to edit")
            return

        self.display_stakeholder_list(stakeholders_list)

        try:
            index = int(self.menu.get_input("Enter stakeholder number to edit")) - 1
            if index < 0 or index >= len(stakeholders_list):
                self.menu.print_error("Invalid stakeholder number")
                return

            stakeholder = stakeholders_list[index]
            current_name = stakeholder.stakeholder.decode("utf-8", errors="ignore")
            current_participation = stakeholder.participation

            # Edit participation
            new_participation = self.menu.get_input(
                f"Enter new participation (current: {current_participation:,}) or press Enter to keep"
            )
            if new_participation.strip():
                try:
                    participation_amount = int(new_participation)
                    if participation_amount <= 0:
                        raise ValueError("Participation must be positive")
                    stakeholder.participation = participation_amount

                    # Ensure claimed doesn't exceed new participation

                except ValueError as e:
                    self.menu.print_error(f"Invalid participation: {e}")
                    return

            # Edit PKH (Public Key Hash)
            current_pkh = stakeholder.pkh.hex() if stakeholder.pkh else ""
            pkh_display = (
                current_pkh[:16] + "..." if len(current_pkh) > 16 else current_pkh or "empty"
            )
            new_pkh = self.menu.get_input(
                f"Enter new PKH (current: {pkh_display}) or press Enter to keep (56 hex chars or empty)"
            )
            if new_pkh.strip():
                try:
                    if len(new_pkh.strip()) != 56:
                        raise ValueError("PKH must be exactly 56 hex characters")
                    pkh_bytes = bytes.fromhex(new_pkh.strip())
                    stakeholder.pkh = pkh_bytes
                    self.menu.print_success("✓ PKH updated")
                except ValueError as e:
                    self.menu.print_error(f"Invalid PKH: {e}")
                    return
            # If new_pkh is empty (user pressed Enter), keep current PKH (no action needed)

            # Note: Amount claimed is automatically updated when grey tokens are minted

            self.menu.print_success(f"✓ Updated stakeholder: {current_name}")

        except ValueError:
            self.menu.print_error("Invalid input - please enter a number")

    def remove_stakeholder_from_list(self, stakeholders_list):
        """Remove a stakeholder from the list"""
        if not stakeholders_list:
            self.menu.print_info("No stakeholders to remove")
            return

        self.display_stakeholder_list(stakeholders_list)

        try:
            index = int(self.menu.get_input("Enter stakeholder number to remove")) - 1
            if index < 0 or index >= len(stakeholders_list):
                self.menu.print_error("Invalid stakeholder number")
                return

            removed = stakeholders_list.pop(index)
            stakeholder_name = removed.stakeholder.decode("utf-8", errors="ignore")
            self.menu.print_success(f"✓ Removed stakeholder: {stakeholder_name}")

        except ValueError:
            self.menu.print_error("Invalid input - please enter a number")

    def display_stakeholder_list(self, stakeholders_list):
        """Display the current stakeholder list"""
        if not stakeholders_list:
            print("│ No stakeholders in list")
            return

        print(f"│ Stakeholders ({len(stakeholders_list)}):")
        total_participation = 0
        for i, stakeholder in enumerate(stakeholders_list):
            name = stakeholder.stakeholder.decode("utf-8", errors="ignore")
            pkh_display = stakeholder.pkh.hex()[:16] + "..." if stakeholder.pkh else "empty"
            print(
                f"│   {i+1}. {name} - PKH: {pkh_display} - Participation: {stakeholder.participation:,}"
            )
            total_participation += stakeholder.participation
        print(f"│ Total Participation: {total_participation:,}")

    def add_certification_to_list(self, certifications_list, project_state=0):
        """Add a new certification to the list"""

        cert_date = self.menu.get_input("Enter certification date (POSIX timestamp)")
        try:
            certification_date = int(cert_date)
            if certification_date < 0:
                raise ValueError("Certification date must be positive")
        except ValueError as e:
            self.menu.print_error(f"Invalid certification date: {e}")
            return

        quantity = self.menu.get_input("Enter quantity of carbon credits certified")
        try:
            cert_quantity = int(quantity)
            if cert_quantity <= 0:
                raise ValueError("Quantity must be positive")
        except ValueError as e:
            self.menu.print_error(f"Invalid quantity: {e}")
            return

        # Handle real certification date based on project state
        if project_state == 1:
            # Project state is 1: real fields must be empty
            real_certification_date = 0
            real_cert_quantity = 0
            self.menu.print_info("Real certification fields set to empty (project state is 1)")
        else:
            real_date = self.menu.get_input(
                "Enter real certification date (POSIX timestamp, default: same as cert date)"
            )
            try:
                real_certification_date = int(real_date) if real_date.strip() else certification_date
                if real_certification_date < 0:
                    raise ValueError("Real certification date must be positive")
            except ValueError as e:
                self.menu.print_error(f"Invalid real certification date: {e}")
                return

            real_quantity = self.menu.get_input(
                "Enter real quantity certified (default: same as quantity)"
            )
            try:
                real_cert_quantity = int(real_quantity) if real_quantity.strip() else cert_quantity
                if real_cert_quantity < 0:
                    raise ValueError("Real quantity must be non-negative")
            except ValueError as e:
                self.menu.print_error(f"Invalid real quantity: {e}")
                return

        new_certification = Certification(
            certification_date=certification_date,
            quantity=cert_quantity,
            real_certification_date=real_certification_date,
            real_quantity=real_cert_quantity,
        )

        certifications_list.append(new_certification)
        self.menu.print_success(f"✓ Added certification: {cert_quantity:,} credits")

    def edit_certification_in_list(self, certifications_list, project_state=0):
        """Edit an existing certification in the list"""
        if not certifications_list:
            self.menu.print_info("No certifications to edit")
            return

        self.display_certification_list(certifications_list)

        try:
            index = int(self.menu.get_input("Enter certification number to edit")) - 1
            if index < 0 or index >= len(certifications_list):
                self.menu.print_error("Invalid certification number")
                return

            cert = certifications_list[index]

            # Handle real certification fields based on project state
            if project_state == 1:
                # Project state is 1: real fields cannot be changed and must be empty
                cert.real_certification_date = 0
                cert.real_quantity = 0
                self.menu.print_info("Real certification fields set to empty (project state is 1 - changes not allowed)")
            else:
                # Edit real certification date (can only increase)
                new_real_date = self.menu.get_input(
                    f"Enter new real certification date (current: {cert.real_certification_date}) or press Enter to keep"
                )
                if new_real_date.strip():
                    try:
                        real_date = int(new_real_date)
                        if real_date < cert.real_certification_date:
                            raise ValueError("Real certification date can only increase")
                        cert.real_certification_date = real_date
                    except ValueError as e:
                        self.menu.print_error(f"Invalid real date: {e}")
                        return

                # Edit real quantity (can only increase)
                new_real_quantity = self.menu.get_input(
                    f"Enter new real quantity (current: {cert.real_quantity:,}) or press Enter to keep"
                )
                if new_real_quantity.strip():
                    try:
                        real_qty = int(new_real_quantity)
                        if real_qty < cert.real_quantity:
                            raise ValueError("Real quantity can only increase")
                        cert.real_quantity = real_qty
                    except ValueError as e:
                        self.menu.print_error(f"Invalid real quantity: {e}")
                        return

            self.menu.print_success(f"✓ Updated certification")

        except ValueError:
            self.menu.print_error("Invalid input - please enter a number")

    def remove_certification_from_list(self, certifications_list):
        """Remove a certification from the list"""
        if not certifications_list:
            self.menu.print_info("No certifications to remove")
            return

        self.display_certification_list(certifications_list)

        try:
            index = int(self.menu.get_input("Enter certification number to remove")) - 1
            if index < 0 or index >= len(certifications_list):
                self.menu.print_error("Invalid certification number")
                return

            removed = certifications_list.pop(index)
            self.menu.print_success(f"✓ Removed certification: {removed.quantity:,} credits")

        except ValueError:
            self.menu.print_error("Invalid input - please enter a number")

    def display_certification_list(self, certifications_list):
        """Display the current certification list"""
        if not certifications_list:
            print("│ No certifications in list")
            return

        print(f"│ Certifications ({len(certifications_list)}):")
        for i, cert in enumerate(certifications_list):
            print(
                f"│   {i+1}. Date: {cert.certification_date} - Qty: {cert.quantity:,} - Real Date: {cert.real_certification_date} - Real Qty: {cert.real_quantity:,}"
            )


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
