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
from typing import Any, Optional, List, Dict

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
            # active_wallet_name = self.wallet_manager.get_default_wallet_name()
            self.menu.print_info("ℹ Available wallets: default, project, investor")
            user_address_input = self.menu.get_input(
                "Enter address or wallet name containing tokens to burn (or press Enter for default wallet address)"
            )

            user_address = None
            if user_address_input.strip():
                # Use the existing resolve_address_input method that supports wallet names
                # For project burn operations, switch to the wallet if a wallet name is provided
                resolved_address = self.resolve_address_input(
                    user_address_input.strip(), switch_wallet=True
                )
                if resolved_address:
                    try:
                        user_address = pc.Address.from_primitive(resolved_address)
                        if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                            self.menu.print_info(
                                f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}..."
                            )
                        else:
                            self.menu.print_info(
                                f"Using specified address: {resolved_address[50:]}..."
                            )
                    except Exception as e:
                        self.menu.print_error(f"Invalid address format: {e}")
                        return
                else:
                    self.menu.print_error(
                        f"Invalid address or wallet name: {user_address_input.strip()}"
                    )
                    return
            else:
                self.menu.print_info("Using default wallet address")

            # print(f"\nSEND ADA (From: {active_wallet_name})")
            # print("-" * 40)

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

        # Show available wallets for user convenience
        self.menu.print_info("ℹ Available wallets: default, project, investor")

        destin_address_str = self.menu.get_input(
            "Enter destination address or wallet name (or press Enter for default)"
        )

        destination_address = None
        if destin_address_str.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # Switch to the wallet if a wallet name is provided so transaction uses correct signing keys
            resolved_address = self.resolve_address_input(
                destin_address_str.strip(), switch_wallet=True
            )
            if resolved_address:
                try:
                    destination_address = pc.Address.from_primitive(resolved_address)
                    # Show resolved address if it was a wallet name
                    if destin_address_str.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(
                            f"Resolved wallet '{destin_address_str.strip()}' to: {resolved_address}"
                        )
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(
                    f"Invalid address or wallet name: {destin_address_str.strip()}"
                )
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
                if stakeholder_pkh == "":
                    stakeholder_pkh = b""
                elif stakeholder_pkh and len(stakeholder_pkh) != 56:
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
            resolved_address = self.resolve_address_input(
                destin_address_str.strip(), switch_wallet=True
            )
            if resolved_address:
                try:
                    destination_address = pc.Address.from_primitive(resolved_address)
                    # Show resolved address if it was a wallet name
                    if destin_address_str.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(
                            f"Resolved wallet '{destin_address_str.strip()}' to: {resolved_address}"
                        )
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(
                    f"Invalid address or wallet name: {destin_address_str.strip()}"
                )
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
                    # Get project contracts (excluding NFT minting policies for user display)
                    project_contracts = self.contract_manager.list_project_contracts()

                    # For deployment marking, we need to include both project contracts and their NFTs
                    deployed_contracts = project_contracts.copy()
                    for project_name in project_contracts:
                        project_nfts_name = f"{project_name}_nfts"
                        if project_nfts_name in self.contract_manager.contracts:
                            deployed_contracts.append(project_nfts_name)

                    if self.contract_manager.mark_contract_as_deployed(deployed_contracts):
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
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        user_address_input = self.menu.get_input(
            "Enter address or wallet name containing tokens to burn (or press Enter for default wallet address)"
        )

        user_address = None
        if user_address_input.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # For burn operations, switch to the wallet if a wallet name is provided
            resolved_address = self.resolve_address_input(
                user_address_input.strip(), switch_wallet=True
            )
            if resolved_address:
                try:
                    user_address = pc.Address.from_primitive(resolved_address)
                    if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(
                            f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}..."
                        )
                    else:
                        self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(
                    f"Invalid address or wallet name: {user_address_input.strip()}"
                )
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
            print(f"│ Admins Count: {len(current_datum.project_admins)}")
            if current_datum.project_admins:
                print(
                    f"│ Admins: {[admin.hex()[:16] + '...' for admin in current_datum.project_admins[:3]]}"
                )
                if len(current_datum.project_admins) > 3:
                    print(f"│           ... and {len(current_datum.project_admins) - 3} more")
            else:
                print(f"│ Admins: None (empty)")
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

        # Create new datum with all updates
        new_datum = DatumProtocol(
            protocol_fee=new_fee_lovelace,
            oracle_id=new_oracle_id,
            project_admins=new_admin_list,  # Use updated admins list
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
            resolved_address = self.resolve_address_input(
                user_address_input.strip(), switch_wallet=True
            )
            if resolved_address:
                try:
                    user_address = pc.Address.from_primitive(resolved_address)
                    if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(
                            f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}..."
                        )
                    else:
                        self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(
                    f"Invalid address or wallet name: {user_address_input.strip()}"
                )
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
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        user_address_input = self.menu.get_input(
            "Enter address or wallet name containing tokens to burn (or press Enter for default wallet address)"
        )

        user_address = None
        if user_address_input.strip():
            # Use the existing resolve_address_input method that supports wallet names
            # For project burn operations, switch to the wallet if a wallet name is provided
            resolved_address = self.resolve_address_input(
                user_address_input.strip(), switch_wallet=True
            )
            if resolved_address:
                try:
                    user_address = pc.Address.from_primitive(resolved_address)
                    if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(
                            f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}..."
                        )
                    else:
                        self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    return
            else:
                self.menu.print_error(
                    f"Invalid address or wallet name: {user_address_input.strip()}"
                )
                return
        else:
            self.menu.print_info("Using default wallet address")

        try:
            self.menu.print_info("Creating project burn transaction...")
            # Temporary function to test reference scripts

            # result = self.token_operations.create_reference_script(selected_project)
            # tx_id = self.transactions.submit_transaction(result["transaction"])

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

        # Get destination address (optional)
        self.menu.print_info("ℹ Available wallets: default, project, investor")
        destination_input = self.menu.get_input(
            "Enter destination address or wallet name (or press Enter for default wallet)"
        )

        destination_address = None
        if destination_input.strip():
            resolved_address = self.resolve_address_input(destination_input.strip())
            if resolved_address:
                try:
                    destination_address = pc.Address.from_primitive(resolved_address)
                    if destination_input.strip() in self.wallet_manager.get_wallet_names():
                        self.menu.print_info(
                            f"Resolved wallet '{destination_input.strip()}' to: {resolved_address[50:]}..."
                        )
                    else:
                        self.menu.print_info(f"Using specified address: {resolved_address[50:]}...")
                except Exception as e:
                    self.menu.print_error(f"Invalid address format: {e}")
                    input("Press Enter to continue...")
                    return
            else:
                self.menu.print_error(
                    f"Invalid address or wallet name: {destination_input.strip()}"
                )
                input("Press Enter to continue...")
                return
        else:
            self.menu.print_info("Using default wallet address")

        # Show transaction preview
        self.menu.print_section("TRANSACTION PREVIEW")
        print(f"│ Project Contract: {selected_project}")
        print(f"│ Grey Tokens to Mint: {grey_token_quantity:,}")
        print(
            f"│ Destination: {'Default wallet' if not destination_address else 'Specified address'}"
        )
        print("│")
        print("│ ⚠️  This will:")
        print("│    • Use UpdateToken redeemer on project contract")
        print("│    • Increment current_supply in project datum")
        print("│    • Update stakeholder amount_claimed")
        print("│    • Mint grey tokens to destination address")

        if not self.menu.confirm_action("Proceed with grey token minting?"):
            self.menu.print_info("Grey token minting cancelled")
            input("Press Enter to continue...")
            return

        try:
            self.menu.print_info("Creating grey token minting transaction...")

            # Create the grey token minting transaction
            result = self.token_operations.create_grey_minting_transaction(
                destination_address=destination_address,
                project_name=selected_project,
                grey_token_quantity=grey_token_quantity,
            )

            if result["success"]:
                self.menu.print_success("✓ Grey token minting transaction created successfully!")
                print(f"│ Transaction ID: {result['tx_id']}")
                print(f"│ Grey Token Name: {result['grey_token_name']}")
                print(f"│ Minting Policy ID: {result['minting_policy_id']}")
                print(f"│ Quantity Minted: {result['quantity']:,}")
                print(f"│ New Current Supply: {result.get('new_current_supply', 'N/A'):,}")

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
            # Get user's wallet address to find grey tokens
            user_address = self.wallet_manager.get_wallet().get_address()
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
            from terrasacha_contracts.validators.project import DatumProject

            current_datum = DatumProject.from_cbor(project_utxo.output.datum.cbor)

            # Enhanced project status display with update capabilities
            self.display_enhanced_project_status(current_datum)

            # Ask for user address
            self.menu.print_info("ℹ Available wallets: default, project, investor")
            user_address_input = self.menu.get_input(
                "Enter address or wallet name containing user tokens (or press Enter for default wallet address)"
            )

            user_address = None
            if user_address_input.strip():
                # Use the existing resolve_address_input method that supports wallet names
                # For project update operations, switch to the wallet if a wallet name is provided
                resolved_address = self.resolve_address_input(
                    user_address_input.strip(), switch_wallet=True
                )
                if resolved_address:
                    try:
                        user_address = pc.Address.from_primitive(resolved_address)
                        if user_address_input.strip() in self.wallet_manager.get_wallet_names():
                            self.menu.print_info(
                                f"Resolved wallet '{user_address_input.strip()}' to: {resolved_address[50:]}..."
                            )
                        else:
                            self.menu.print_info(
                                f"Using specified address: {resolved_address[50:]}..."
                            )
                    except Exception as e:
                        self.menu.print_error(f"Invalid address format: {e}")
                        return
                else:
                    self.menu.print_error(
                        f"Invalid address or wallet name: {user_address_input.strip()}"
                    )
                    return
            else:
                self.menu.print_info("Using default wallet address")

            # State-based update routing
            if current_datum.params.project_state == 0:
                # Initialization phase - show comprehensive update options
                self.handle_initialization_update(current_datum, user_address, selected_project)
            else:
                # Project locked - show limited options
                self.handle_locked_project_update(current_datum)

        except Exception as e:
            self.menu.print_error(f"Project update failed: {e}")

        input("\nPress Enter to continue...")

    def display_enhanced_project_status(self, current_datum):
        """Display enhanced project status with update capability indicators"""
        from terrasacha_contracts.validators.project import DatumProject

        # State information
        state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}
        state_name = state_names.get(current_datum.params.project_state, "Unknown")
        is_updatable = current_datum.params.project_state == 0

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

        # Protocol and token information
        protocol_policy_display = (
            "empty"
            if not current_datum.protocol_policy_id or current_datum.protocol_policy_id == b""
            else current_datum.protocol_policy_id.hex()[:20] + "..."
        )
        token_name_display = (
            "empty"
            if not current_datum.project_token.token_name
            or current_datum.project_token.token_name == b""
            else current_datum.project_token.token_name.decode("utf-8", errors="ignore")
        )

        print(
            f"│ Protocol Policy: ({protocol_policy_display}) {'[UPDATABLE]' if is_updatable else '[LOCKED]'}"
        )
        print(
            f"│ Token Name: ({token_name_display}) {'[UPDATABLE]' if is_updatable else '[LOCKED]'}"
        )

        # Supply information
        print(
            f"│ Current Supply: {current_datum.project_token.current_supply:,} {'[UPDATABLE]' if is_updatable else '[TOKEN OPS ONLY]'}"
        )
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

        # Show update options menu
        options = [
            "Update Project Information (ID, Metadata, State)",
            "Update Protocol Settings (Protocol Policy ID)",
            "Update Token Economics (Policy ID, Token Name, Supply)",
            "Update Stakeholders (Participation Management)",
            "Update Certifications (Certification Records)",
            "Batch Update All Fields (Accumulate Changes)",
            "Advance Project State (0→1)",
            "Quick State Advance Only",
            "Cancel",
        ]

        self.menu.print_info("UPDATE OPTIONS:")
        for i, option in enumerate(options, 1):
            if i == len(options):  # Cancel option
                print(f"│ 0. {option}")
            else:
                print(f"│ {i}. {option}")

        try:
            choice = self.menu.get_input("Select update option (1-8, 0 to cancel)")
            choice_num = int(choice)

            if choice_num == 0:
                self.menu.print_info("Project update cancelled")
                return
            elif choice_num == 1:
                self.update_project_information(current_datum, user_address, project_name)
            elif choice_num == 2:
                self.update_protocol_settings(current_datum, user_address, project_name)
            elif choice_num == 3:
                self.update_token_economics(current_datum, user_address, project_name)
            elif choice_num == 4:
                self.update_stakeholders(current_datum, user_address, project_name)
            elif choice_num == 5:
                self.update_certifications(current_datum, user_address, project_name)
            elif choice_num == 6:
                self.batch_update_all_fields(current_datum, user_address, project_name)
            elif choice_num == 7:
                self.advance_project_state(current_datum, user_address, project_name)
            elif choice_num == 8:
                # Quick advance - just increment state
                self.quick_advance_state(current_datum, user_address, project_name)
            else:
                self.menu.print_error("Invalid option selected")

        except ValueError:
            self.menu.print_error("Invalid input - please enter a number")

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
        """Update project ID and metadata"""
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

        # Show preview
        self.menu.print_section("PREVIEW CHANGES")
        if new_project_id != current_datum.params.project_id:
            print(f"│ Project ID: {current_id[:20]}... → {new_project_id.hex()[:20]}...")
        if new_metadata != current_datum.params.project_metadata:
            print(f"│ Metadata: {current_metadata[:30]}... → {new_metadata_input[:30]}...")

        if (
            new_project_id == current_datum.params.project_id
            and new_metadata == current_datum.params.project_metadata
        ):
            self.menu.print_info("No changes detected")
            input("Press Enter to continue...")
            return

        # Create custom datum and submit
        self.create_custom_update_transaction(
            current_datum,
            user_address,
            project_name,
            {"project_id": new_project_id, "project_metadata": new_metadata},
        )

    def update_protocol_settings(self, current_datum, user_address, project_name):
        """Update protocol policy ID and token name"""
        self.menu.print_section("UPDATE PROTOCOL SETTINGS")

        # Protocol Policy ID update
        current_policy = (
            current_datum.protocol_policy_id.hex() if current_datum.protocol_policy_id else "empty"
        )
        print(f"│ Current Protocol Policy ID: {current_policy}")
        new_policy_input = self.menu.get_input(
            "Enter new Protocol Policy ID (56 hex chars) or press Enter to keep current"
        )

        if new_policy_input.strip():
            try:
                if len(new_policy_input) != 56:
                    raise ValueError("Protocol Policy ID must be exactly 56 hex characters")
                new_protocol_policy = bytes.fromhex(new_policy_input)
            except ValueError as e:
                self.menu.print_error(f"Invalid Protocol Policy ID: {e}")
                input("Press Enter to continue...")
                return
        else:
            new_protocol_policy = current_datum.protocol_policy_id

        # Token Name update
        current_token_name = (
            current_datum.project_token.token_name.decode("utf-8", errors="ignore")
            if current_datum.project_token.token_name
            else "empty"
        )
        print(f"│ Current Token Name: {current_token_name}")
        new_token_name_input = self.menu.get_input(
            "Enter new Token Name or press Enter to keep current"
        )

        if new_token_name_input.strip():
            new_token_name = new_token_name_input.encode("utf-8")
        else:
            new_token_name = current_datum.project_token.token_name

        # Show preview
        self.menu.print_section("PREVIEW CHANGES")
        if new_protocol_policy != current_datum.protocol_policy_id:
            print(f"│ Protocol Policy: {current_policy} → {new_protocol_policy.hex()}")
        if new_token_name != current_datum.project_token.token_name:
            print(f"│ Token Name: {current_token_name} → {new_token_name_input}")

        if (
            new_protocol_policy == current_datum.protocol_policy_id
            and new_token_name == current_datum.project_token.token_name
        ):
            self.menu.print_info("No changes detected")
            input("Press Enter to continue...")
            return

        # Create custom datum and submit
        self.create_custom_update_transaction(
            current_datum,
            user_address,
            project_name,
            {"protocol_policy_id": new_protocol_policy, "token_name": new_token_name},
        )

    def update_token_economics(self, current_datum, user_address, project_name):
        """Update token supply settings or setup grey tokens"""
        self.menu.print_section("TOKEN ECONOMICS MANAGEMENT")

        # Show current token information
        print(f"│ Current Total Supply: {current_datum.project_token.total_supply:,}")
        print(f"│ Current Supply: {current_datum.project_token.current_supply:,}")

        # Check if grey tokens are already setup by checking if there's a grey contract policy
        try:
            # Try to get project contract to derive grey policy ID
            project_contract = self.contract_manager.get_project_contract(project_name)
            if project_contract:
                grey_contract = self.contract_manager.create_minting_contract(
                    "grey", bytes.fromhex(project_contract.policy_id)
                )
                grey_policy_id = grey_contract.policy_id if grey_contract else None
            else:
                grey_policy_id = None
        except:
            grey_policy_id = None

        if grey_policy_id:
            print(f"│ Grey Token Policy ID: {grey_policy_id}")
            print(f"│ Grey Token Name: {current_datum.project_token.token_name.hex()}")

        print("│")
        print("│ TOKEN MANAGEMENT OPTIONS:")
        print("│ 1. Update Project Token Economics (Supply)")
        print("│ 2. Setup Grey Tokens for Project")
        print("│ 0. Cancel")

        try:
            choice = self.menu.get_input("Select option (1-2, 0 to cancel)")
            choice_num = int(choice)

            if choice_num == 0:
                self.menu.print_info("Token economics update cancelled")
                return
            elif choice_num == 1:
                self.update_project_token_supply(current_datum, user_address, project_name)
            elif choice_num == 2:
                self.setup_grey_tokens_for_project(current_datum, user_address, project_name)
            else:
                self.menu.print_error("Invalid option selected")
                input("Press Enter to continue...")

        except ValueError:
            self.menu.print_error("Invalid input. Please enter a number.")
            input("Press Enter to continue...")

    def update_project_token_supply(self, current_datum, user_address, project_name):
        """Update project token supply settings (original functionality)"""
        self.menu.print_section("UPDATE PROJECT TOKEN SUPPLY")

        print(f"│ Current Total Supply: {current_datum.project_token.total_supply:,}")
        print(f"│ Current Supply: {current_datum.project_token.current_supply:,}")

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

        # Current Supply update
        new_current_input = self.menu.get_input(
            "Enter new Current Supply or press Enter to keep current"
        )
        if new_current_input.strip():
            try:
                new_current_supply = int(new_current_input)
                if new_current_supply < 0:
                    raise ValueError("Current supply cannot be negative")
                if new_current_supply > new_total_supply:
                    raise ValueError("Current supply cannot exceed total supply")
            except ValueError as e:
                self.menu.print_error(f"Invalid Current Supply: {e}")
                input("Press Enter to continue...")
                return
        else:
            new_current_supply = current_datum.project_token.current_supply

        # Show preview
        self.menu.print_section("PREVIEW CHANGES")
        if new_total_supply != current_datum.project_token.total_supply:
            print(
                f"│ Total Supply: {current_datum.project_token.total_supply:,} → {new_total_supply:,}"
            )
        if new_current_supply != current_datum.project_token.current_supply:
            print(
                f"│ Current Supply: {current_datum.project_token.current_supply:,} → {new_current_supply:,}"
            )

        if (
            new_total_supply == current_datum.project_token.total_supply
            and new_current_supply == current_datum.project_token.current_supply
        ):
            self.menu.print_info("No changes detected")
            input("Press Enter to continue...")
            return

        # Create custom datum and submit
        self.create_custom_update_transaction(
            current_datum,
            user_address,
            project_name,
            {"total_supply": new_total_supply, "current_supply": new_current_supply},
        )

    def setup_grey_tokens_for_project(self, current_datum, user_address, project_name):
        """Setup grey token information in project datum using UpdateProject redeemer"""
        self.menu.print_section("SETUP GREY TOKENS")

        # Get project contract to derive grey policy ID
        try:
            project_contract = self.contract_manager.get_project_contract(project_name)
            if not project_contract:
                self.menu.print_error("Project contract not found")
                input("Press Enter to continue...")
                return

            # Compile grey contract to get unique policy ID
            grey_contract = self.contract_manager.create_minting_contract(
                "grey", bytes.fromhex(project_contract.policy_id)
            )
            if not grey_contract:
                self.menu.print_error("Failed to compile grey minting contract")
                input("Press Enter to continue...")
                return

            grey_policy_id = grey_contract.policy_id
            self.menu.print_info(f"Grey Contract Policy ID: {grey_policy_id}")

            # Store the grey contract for future use with naming pattern {project_name}_grey
            grey_contract_name = f"{project_name}_grey"
            self.contract_manager.contracts[grey_contract_name] = grey_contract

            # Save contracts to disk
            if self.contract_manager._save_contracts():
                self.menu.print_info(f"Stored grey contract as: {grey_contract_name}")
            else:
                self.menu.print_warning("Grey contract compiled but failed to save to disk")

        except Exception as e:
            self.menu.print_error(f"Error getting grey contract info: {e}")
            input("Press Enter to continue...")
            return

        # Generate unique token name for grey tokens
        import time
        import random

        # Create unique token name using project name and timestamp
        base_name = f"GREY_{project_name}_{int(time.time())}"
        if len(base_name) > 32:  # Cardano token name limit
            base_name = f"GREY_{int(time.time())}"

        grey_token_name = base_name.encode("utf-8")

        print("│")
        print(f"│ Project Contract: {project_name}")
        print(f"│ Grey Policy ID: {grey_policy_id}")
        print(f"│ Grey Token Name: {base_name}")
        print("│")
        print("│ This will update the project datum to include grey token information.")
        print("│ After setup, you can mint grey tokens using the 'Mint Grey Tokens' menu option.")

        # Get token supply settings
        try:
            total_supply_input = self.menu.get_input(
                "Enter grey token total supply (default: 1000)"
            )
            total_supply = int(total_supply_input) if total_supply_input.strip() else 1000

            if total_supply <= 0:
                raise ValueError("Total supply must be positive")

        except ValueError as e:
            self.menu.print_error(f"Invalid total supply: {e}")
            input("Press Enter to continue...")
            return

        if not self.menu.confirm_action("Setup grey tokens for this project?"):
            self.menu.print_info("Grey token setup cancelled")
            input("Press Enter to continue...")
            return

        # Create token changes to include grey token info
        # For now, we're updating the existing project_token with grey token information
        # In future, this could be a separate grey_token field in the datum
        token_changes = {
            "token_policy_id": bytes.fromhex(grey_policy_id),
            "token_name": grey_token_name,
            "total_supply": total_supply,
            "current_supply": 0,  # Start with 0 current supply
        }

        self.menu.print_section("PREVIEW GREY TOKEN SETUP")
        print(f"│ Grey Policy ID: {grey_policy_id}")
        print(f"│ Grey Token Name: {base_name}")
        print(f"│ Total Supply: {total_supply:,}")
        print(f"│ Initial Current Supply: 0")
        print("│")
        print("│ ⚠️  This will replace current token info in project datum")

        if not self.menu.confirm_action("Proceed with grey token setup?"):
            self.menu.print_info("Grey token setup cancelled")
            input("Press Enter to continue...")
            return

        # Create custom datum and submit using UpdateProject redeemer
        self.create_custom_update_transaction(
            current_datum,
            user_address,
            project_name,
            token_changes,
        )

        self.menu.print_success("✓ Grey token setup transaction created!")
        self.menu.print_info(
            "After transaction confirms, you can mint grey tokens via main menu option 10"
        )
        input("Press Enter to continue...")

    def advance_project_state(self, current_datum, user_address, project_name):
        """Advance project state with optional field changes"""
        self.menu.print_section("ADVANCE PROJECT STATE")

        current_state = current_datum.params.project_state
        new_state = min(current_state + 1, 3)
        state_names = {0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}

        print(f"│ Current State: {current_state} ({state_names.get(current_state)})")
        print(f"│ New State: {new_state} ({state_names.get(new_state)})")
        print("│")
        print("│ ⚠️  WARNING: Once advanced, most fields become immutable!")

        if not self.menu.confirm_action(
            f"Advance project state from {current_state} to {new_state}?"
        ):
            self.menu.print_info("State advance cancelled")
            input("Press Enter to continue...")
            return

        # Create custom datum and submit
        self.create_custom_update_transaction(
            current_datum, user_address, project_name, {"project_state": new_state}
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
                choice = self.menu.get_input("Select option (1-8, 0 to cancel)")
                choice_num = int(choice)

                if choice_num == 0:
                    self.menu.print_info("Batch update cancelled")
                    return
                elif choice_num == 1:
                    self.accumulate_project_info_changes(current_datum, accumulated_changes)
                elif choice_num == 2:
                    self.accumulate_protocol_changes(current_datum, accumulated_changes)
                elif choice_num == 3:
                    self.accumulate_token_changes(current_datum, accumulated_changes)
                elif choice_num == 4:
                    self.accumulate_stakeholder_changes(current_datum, accumulated_changes)
                elif choice_num == 5:
                    self.accumulate_certification_changes(current_datum, accumulated_changes)
                elif choice_num == 6:
                    self.review_accumulated_changes(current_datum, accumulated_changes)
                elif choice_num == 7:
                    if accumulated_changes:
                        self.submit_accumulated_changes(
                            current_datum, user_address, project_name, accumulated_changes
                        )
                        return
                    else:
                        self.menu.print_info("No changes accumulated yet")
                        input("Press Enter to continue...")
                elif choice_num == 8:
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
            "Update Protocol Settings (Protocol Policy ID)",
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
                elif i == 2 and any(key in accumulated_changes for key in ["protocol_policy_id"]):
                    indicator = " ✓"
                elif i == 3 and any(
                    key in accumulated_changes
                    for key in ["token_policy_id", "token_name", "total_supply", "current_supply"]
                ):
                    indicator = " ✓"
                elif i == 4 and any(key in accumulated_changes for key in ["stakeholders"]):
                    indicator = " ✓"
                elif i == 5 and any(key in accumulated_changes for key in ["certifications"]):
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
            try:
                new_project_id = bytes.fromhex(new_id_input)
                if len(new_project_id) != 32:
                    raise ValueError("Project ID must be exactly 32 bytes (64 hex chars)")
                accumulated_changes["project_id"] = new_project_id
                self.menu.print_success("✓ Project ID change accumulated")
            except ValueError as e:
                self.menu.print_error(f"Invalid Project ID: {e}")
                input("Press Enter to continue...")
                return

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
                if new_state < current_state:
                    raise ValueError("Project state can only move forward")
                accumulated_changes["project_state"] = new_state
                self.menu.print_success(
                    f"✓ Project State change accumulated: {current_state} → {new_state}"
                )
            except ValueError as e:
                self.menu.print_error(f"Invalid Project State: {e}")
                input("Press Enter to continue...")
                return

        input("Press Enter to continue...")

    def accumulate_protocol_changes(self, current_datum, accumulated_changes):
        """Accumulate protocol settings changes without creating transaction"""
        self.menu.print_section("ACCUMULATE PROTOCOL CHANGES")

        # Protocol Policy ID update
        current_policy = (
            current_datum.protocol_policy_id.hex() if current_datum.protocol_policy_id else "empty"
        )
        print(f"│ Current Protocol Policy ID: {current_policy}")
        new_policy_input = self.menu.get_input(
            "Enter new Protocol Policy ID (56 hex chars) or press Enter to keep current"
        )

        if new_policy_input.strip():
            try:
                new_protocol_policy = bytes.fromhex(new_policy_input)
                if len(new_protocol_policy) != 28:
                    raise ValueError("Protocol Policy ID must be exactly 28 bytes (56 hex chars)")
                accumulated_changes["protocol_policy_id"] = new_protocol_policy
                self.menu.print_success("✓ Protocol Policy ID change accumulated")
            except ValueError as e:
                self.menu.print_error(f"Invalid Protocol Policy ID: {e}")
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
        print(f"│ Current Supply: {current_datum.project_token.current_supply:,}")

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

        # Current Supply update
        new_current_input = self.menu.get_input(
            "Enter new Current Supply or press Enter to keep current"
        )
        if new_current_input.strip():
            try:
                new_current_supply = int(new_current_input)
                if new_current_supply < 0:
                    raise ValueError("Current supply cannot be negative")
                # Check against accumulated or current total supply
                total_to_check = accumulated_changes.get(
                    "total_supply", current_datum.project_token.total_supply
                )
                if new_current_supply > total_to_check:
                    raise ValueError("Current supply cannot exceed total supply")
                accumulated_changes["current_supply"] = new_current_supply
                self.menu.print_success("✓ Current Supply change accumulated")
            except ValueError as e:
                self.menu.print_error(f"Invalid Current Supply: {e}")
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
            key for key in accumulated_changes if key in ["project_id", "project_metadata"]
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
            print("│")

        # Protocol Settings Changes
        protocol_changes = [
            key for key in accumulated_changes if key in ["protocol_policy_id", "token_name"]
        ]
        if protocol_changes:
            print("│ 🔗 PROTOCOL SETTINGS:")
            if "protocol_policy_id" in accumulated_changes:
                current_policy = (
                    current_datum.protocol_policy_id.hex()
                    if current_datum.protocol_policy_id
                    else "empty"
                )
                new_policy = accumulated_changes["protocol_policy_id"].hex()
                print(f"│   • Protocol Policy: {current_policy} → {new_policy}")
            if "token_name" in accumulated_changes:
                current_name = current_datum.project_token.token_name.hex()
                new_name = accumulated_changes["token_name"].hex()
                print(f"│   • Token Name: {current_name} → {new_name}")
            print("│")

        # Token Economics Changes
        token_changes = [
            key for key in accumulated_changes if key in ["total_supply", "current_supply"]
        ]
        if token_changes:
            print("│ 💰 TOKEN ECONOMICS:")
            if "total_supply" in accumulated_changes:
                current_total = current_datum.project_token.total_supply
                new_total = accumulated_changes["total_supply"]
                print(f"│   • Total Supply: {current_total:,} → {new_total:,}")
            if "current_supply" in accumulated_changes:
                current_supply = current_datum.project_token.current_supply
                new_supply = accumulated_changes["current_supply"]
                print(f"│   • Current Supply: {current_supply:,} → {new_supply:,}")
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
                f"│   {i+1}. {stakeholder_name} - PKH: {pkh_display} - Participation: {stakeholder.participation:,} - Claimed: {stakeholder.amount_claimed:,}"
            )
        print("│")

        # Get current stakeholders list (start with existing)
        new_stakeholders = list(current_datum.stakeholders)

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

            if total_participation != expected_supply:
                self.menu.print_error(
                    f"Total stakeholder participation ({total_participation:,}) must equal total supply ({expected_supply:,})"
                )
                input("Press Enter to continue...")
                return

        # Only add to accumulated changes if stakeholders were modified
        if new_stakeholders != list(current_datum.stakeholders):
            accumulated_changes["stakeholders"] = new_stakeholders
            self.menu.print_success(
                f"✓ Stakeholder changes accumulated ({len(new_stakeholders)} stakeholders)"
            )

        input("Press Enter to continue...")

    def accumulate_certification_changes(self, current_datum, accumulated_changes):
        """Accumulate certification changes without creating transaction"""
        self.menu.print_section("ACCUMULATE CERTIFICATION CHANGES")

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
                self.add_certification_to_list(new_certifications)
            elif choice_num == 2:
                self.edit_certification_in_list(new_certifications)
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
        from terrasacha_contracts.validators.project import (
            DatumProject,
            DatumProjectParams,
            TokenProject,
        )

        try:
            # Build custom datum with user updates
            custom_datum = self.build_custom_datum(current_datum, field_updates)

            if not self.menu.confirm_action("Create transaction with these changes?"):
                self.menu.print_info("Transaction creation cancelled")
                input("Press Enter to continue...")
                return

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
        from terrasacha_contracts.validators.project import (
            DatumProject,
            DatumProjectParams,
            TokenProject,
        )

        # Start with current values
        new_project_id = field_updates.get("project_id", current_datum.params.project_id)
        new_project_metadata = field_updates.get(
            "project_metadata", current_datum.params.project_metadata
        )
        new_project_state = field_updates.get("project_state", current_datum.params.project_state)

        new_protocol_policy_id = field_updates.get(
            "protocol_policy_id", current_datum.protocol_policy_id
        )

        new_policy_id = field_updates.get("token_policy_id", current_datum.project_token.policy_id)
        new_token_name = field_updates.get("token_name", current_datum.project_token.token_name)
        new_total_supply = field_updates.get(
            "total_supply", current_datum.project_token.total_supply
        )
        new_current_supply = field_updates.get(
            "current_supply", current_datum.project_token.current_supply
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
            current_supply=new_current_supply,
        )

        # Handle stakeholders and certifications updates
        new_stakeholders = field_updates.get("stakeholders", current_datum.stakeholders)
        new_certifications = field_updates.get("certifications", current_datum.certifications)

        return DatumProject(
            protocol_policy_id=new_protocol_policy_id,
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

        if old_datum.protocol_policy_id != new_datum.protocol_policy_id:
            old_policy = (
                old_datum.protocol_policy_id.hex() if old_datum.protocol_policy_id else "empty"
            )
            new_policy = (
                new_datum.protocol_policy_id.hex() if new_datum.protocol_policy_id else "empty"
            )
            print(f"│ Protocol Policy: {old_policy} → {new_policy}")
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

        if old_datum.project_token.current_supply != new_datum.project_token.current_supply:
            print(
                f"│ Current Supply: {old_datum.project_token.current_supply:,} → {new_datum.project_token.current_supply:,}"
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
        Select destination wallet for reference script creation
        Source wallet is already determined from contract compilation

        Args:
            source_address: Address that compiled the contract (will fund transaction)

        Returns:
            Dictionary with 'source', 'destination' addresses and wallet info or None if cancelled
        """
        self.menu.print_section("REFERENCE SCRIPT WALLET SELECTION")

        # Source is already determined - it's the wallet that compiled the contract
        self.menu.print_info(
            f"Source wallet (contract compilation + funding): {str(source_address)[:20]}..."
        )

        # Select destination wallet (where reference script UTXO will be sent)
        self.menu.print_info("Select destination wallet (will receive reference script UTXO):")
        print("│ You can choose the same wallet or a different one")
        destination_address = self.select_wallet_for_compilation("storage of the reference script")
        if not destination_address:
            return None

        # Get the wallet instance for the source address to use for signing
        source_wallet = None
        for wallet_name in self.wallet_manager.get_wallet_names():
            wallet = self.wallet_manager.get_wallet(wallet_name)
            if wallet and wallet.get_address(0) == source_address:
                source_wallet = wallet
                break

        if not source_wallet:
            self.menu.print_error("Could not find wallet for source address")
            return None

        return {
            "source": source_address,
            "destination": destination_address,
            "source_wallet": source_wallet,
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
                        source_address=wallet_info["source"],
                        destination_address=wallet_info["destination"],
                        source_wallet=wallet_info["source_wallet"],
                    )
                elif contract_name.endswith("_nfts"):
                    # Handle project NFTs minting policy
                    base_project_name = contract_name.replace("_nfts", "")
                    result = self.transactions.create_project_nfts_reference_script(
                        project_name=base_project_name,
                        source_address=wallet_info["source"],
                        destination_address=wallet_info["destination"],
                        source_wallet=wallet_info["source_wallet"],
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
            self.menu.print_menu_option("2", "Compile/Recompile All Contracts", "✓")
            self.menu.print_menu_option("3", "Compile New Project Contract Only", "✓")
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
            self.menu.print_menu_option("0", "Back to Main Menu")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-12)")

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
        self.menu.print_info(
            "The new project contract will be automatically assigned the next available index."
        )

        if not self.menu.confirm_action("Proceed with project contract compilation?"):
            self.menu.print_info("Compilation cancelled")
            input("\nPress Enter to continue...")
            return

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
                print(f"│ Policy ID: {result['policy_id']}")
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

                warning_msg = f"⚠ This will permanently delete contract '{contract_name}' if it has zero balance"
                if has_project_nfts:
                    warning_msg += f"\n  It will also delete the associated '{project_nfts_name}' minting policy"

                self.menu.print_warning(warning_msg)
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
        from terrasacha_contracts.validators.project import StakeHolderParticipation

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
            try:
                pkh_bytes = bytes.fromhex(stakeholder_pkh)
                if len(pkh_bytes) != 28:
                    raise ValueError("PKH must be exactly 28 bytes (56 hex chars)")
            except ValueError as e:
                self.menu.print_error(f"Invalid PKH: {e}")
                return
        else:
            # Empty PKH is allowed (e.g., for "investor" stakeholders)
            pkh_bytes = b""

        participation = self.menu.get_input("Enter participation amount (lovelace)")
        try:
            participation_amount = int(participation)
            if participation_amount <= 0:
                raise ValueError("Participation must be positive")
        except ValueError as e:
            self.menu.print_error(f"Invalid participation: {e}")
            return

        amount_claimed = self.menu.get_input("Enter amount already claimed (default: 0)")
        try:
            claimed_amount = int(amount_claimed) if amount_claimed.strip() else 0
            if claimed_amount < 0 or claimed_amount > participation_amount:
                raise ValueError("Amount claimed must be between 0 and participation amount")
        except ValueError as e:
            self.menu.print_error(f"Invalid amount claimed: {e}")
            return

        new_stakeholder = StakeHolderParticipation(
            stakeholder=stakeholder_name.encode("utf-8"),
            pkh=pkh_bytes,
            participation=participation_amount,
            amount_claimed=claimed_amount,
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
            current_claimed = stakeholder.amount_claimed

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
                    if stakeholder.amount_claimed > participation_amount:
                        stakeholder.amount_claimed = participation_amount
                        self.menu.print_info(f"Amount claimed adjusted to {participation_amount:,}")

                except ValueError as e:
                    self.menu.print_error(f"Invalid participation: {e}")
                    return

            # Edit amount claimed
            new_claimed = self.menu.get_input(
                f"Enter new amount claimed (current: {current_claimed:,}) or press Enter to keep"
            )
            if new_claimed.strip():
                try:
                    claimed_amount = int(new_claimed)
                    if claimed_amount < 0 or claimed_amount > stakeholder.participation:
                        raise ValueError(
                            f"Amount claimed must be between 0 and {stakeholder.participation:,}"
                        )
                    stakeholder.amount_claimed = claimed_amount
                except ValueError as e:
                    self.menu.print_error(f"Invalid amount claimed: {e}")
                    return

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
                f"│   {i+1}. {name} - PKH: {pkh_display} - Participation: {stakeholder.participation:,} - Claimed: {stakeholder.amount_claimed:,}"
            )
            total_participation += stakeholder.participation
        print(f"│ Total Participation: {total_participation:,}")

    def add_certification_to_list(self, certifications_list):
        """Add a new certification to the list"""
        from terrasacha_contracts.validators.project import Certification

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

    def edit_certification_in_list(self, certifications_list):
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
