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
ENV_FILE = PROJECT_ROOT / "menu/.env"
load_dotenv(ENV_FILE)

# Import core Cardano functionality
from src.cardano_offchain import (
    CardanoWallet,
    CardanoChainContext,
    CardanoTransactions,
    ContractManager,
    TokenOperations,
)
from terrasacha_contracts.validators.protocol import DatumProtocol
from tests.menu.menu_formatter import MenuFormatter


class CardanoCLI:
    """Console interface for Cardano dApp operations"""

    def __init__(self):
        """Initialize the CLI interface"""
        # Get environment variables
        self.network = os.getenv("network", "testnet")
        wallet_mnemonic = os.getenv("wallet_mnemonic")
        blockfrost_api_key = os.getenv("blockfrost_api_key")

        if not wallet_mnemonic or not blockfrost_api_key:
            raise ValueError(
                "Missing required environment variables: wallet_mnemonic, blockfrost_api_key"
            )

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

        # Add context property for convenience
        self.context = self.chain_context.get_context()

        # Generate initial addresses
        self.wallet.generate_addresses(10)

    def display_wallet_info(self):
        """Display comprehensive wallet information"""
        print("\n" + "=" * 80)
        print("CARDANO DAPP WALLET INFORMATION")
        print("=" * 80)

        wallet_info = self.wallet.get_wallet_info()

        print(f"Network: {self.network.upper()}")
        print(f"Wallet Type: HD Wallet (BIP32)")

        print("\nMAIN ADDRESSES:")
        print(
            f"Enterprise (Payment Only): {wallet_info['main_addresses']['enterprise']}"
        )
        print(f"Staking Enabled: {wallet_info['main_addresses']['staking']}")

        print(f"\nDERIVED ADDRESSES (First 10):")
        for addr_info in wallet_info["derived_addresses"]:
            print(
                f"Index {addr_info['index']:2d} | {addr_info['path']:20s} | {addr_info['enterprise_address']}"
            )

        # Check and display balances
        print(f"\nCHECKING BALANCES...")
        balances = self.wallet.check_balances(self.chain_context.get_api())

        print(f"\nBALANCE SUMMARY:")
        print(
            f"Enterprise Address: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA"
        )

        for addr in balances["derived_addresses"]:
            if addr["balance"] > 0:
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
            print(
                f"Enterprise: {balances['main_addresses']['enterprise']['balance']/1_000_000:.6f} ADA"
            )

            to_address = input("Recipient address: ").strip()
            amount = float(input("Amount (ADA): "))

            print(f"Sending {amount} ADA to {to_address[:20]}...")

            tx = self.transactions.create_simple_transaction(to_address, amount)
            if tx:
                tx_id = self.transactions.submit_transaction(tx)
                if tx_id:
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(
                        f"Transaction submitted successfully! TX ID: {tx_info['tx_id']}"
                    )
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
            self.menu.print_error(
                "No contracts compiled yet. Please compile contracts first."
            )
            input("\nPress Enter to continue...")
            return

        # Display compilation info
        if contracts_info["compilation_utxo"]:
            utxo = contracts_info["compilation_utxo"]
            main_address = self.wallet.get_address(0)
            utxo_available = self.contract_manager._is_compilation_utxo_available(
                main_address
            )
            utxo_status = "✓ Available" if utxo_available else "✗ Consumed"

            self.menu.print_section("COMPILATION INFORMATION")
            print(f"│ Compilation UTXO: {utxo['tx_id'][:16]}...:{utxo['index']}")
            print(f"│ UTXO Amount: {utxo['amount']/1_000_000:.6f} ADA")
            print(f"│ UTXO Status: {utxo_status}")
            print()

        # Display contract details
        self.menu.print_section("CONTRACT DETAILS")

        for name, info in contracts_info["contracts"].items():
            status = "✓" if info["balance"] > 0 else "○"
            self.menu.print_contract_info(
                name=name.upper(),
                policy_id=info["policy_id"],
                address=info["address"],
                balance=info["balance_ada"],
                status=status,
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

        if compilation_info[
            "compilation_utxo"
        ] and not self.contract_manager._is_compilation_utxo_available(main_address):
            self.menu.print_warning(
                "⚠ WARNING: The UTXO used for compilation has been consumed!\n"
                "Testing will use a different UTXO and may produce different token names."
            )
            if not self.menu.confirm_action("Continue with testing?"):
                return

        self.menu.print_info(
            "This will mint two NFTs: one protocol token and one user token"
        )
        destin_address_str = self.menu.get_input(
            "Enter destination address for user token (or press Enter for default)"
        )

        destination_address = None
        if destin_address_str.strip():
            try:
                destination_address = pc.Address.from_primitive(
                    destin_address_str.strip()
                )
            except Exception as e:
                self.menu.print_error(f"Invalid address format: {e}")
                return
        else:
            self.menu.print_info("Using default address (wallet address)")

        try:
            self.menu.print_info("Creating minting transaction...")
            result = self.token_operations.create_minting_transaction(
                destination_address
            )

            if not result["success"]:
                self.menu.print_error(
                    f"Failed to create transaction: {result['error']}"
                )
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

        self.menu.print_info(
            "This will burn protocol and user NFTs (tokens will be permanently destroyed)"
        )
        user_address_input = self.menu.get_input(
            "Enter address containing tokens to burn (or press Enter for default wallet address)"
        )

        user_address = None
        if user_address_input.strip():
            try:
                user_address = pc.Address.from_primitive(user_address_input.strip())
                self.menu.print_info(
                    f"Using specified address: {str(user_address)[:50]}..."
                )
            except Exception as e:
                self.menu.print_error(f"Invalid address format: {e}")
                return
        else:
            self.menu.print_info("Using default wallet address")

        try:
            self.menu.print_info("Creating burn transaction...")
            result = self.token_operations.create_burn_transaction(user_address)

            if not result["success"]:
                self.menu.print_error(
                    f"Failed to create transaction: {result['error']}"
                )
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
            minting_policy_id = pc.ScriptHash(
                bytes.fromhex(protocol_nfts_contract.policy_id)
            )

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
            print(f"│ Admin Count: {len(current_datum.protocol_admin)}")
            print(
                f"│ Admin PKHs: {[admin.hex()[:16] + '...' for admin in current_datum.protocol_admin]}"
            )
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
        new_admin_list = current_datum.protocol_admin.copy()
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
            self.menu.print_info(
                f"Using default increment: {new_fee_lovelace / 1_000_000:.6f} ADA"
            )

        # Option to update Oracle ID
        oracle_input = self.menu.get_input(
            "Enter new Oracle ID (or press Enter to keep current)"
        )
        if oracle_input.strip():
            try:
                new_oracle_id = oracle_input.strip().encode("utf-8")
                self.menu.print_info(f"New Oracle ID: {oracle_input.strip()}")
            except Exception as e:
                self.menu.print_error(f"Invalid Oracle ID: {e}")
                return

        # Option to update Admin list
        admin_input = self.menu.get_input("Update admins? (add/remove/keep) [keep]")
        if admin_input.strip().lower() in ["add", "remove"]:
            if admin_input.strip().lower() == "add":
                new_admin_hex = self.menu.get_input(
                    "Enter new admin public key hash (hex)"
                )
                try:
                    new_admin_bytes = bytes.fromhex(new_admin_hex.strip())
                    if len(new_admin_bytes) != 28:
                        self.menu.print_error(
                            "Admin public key hash must be 28 bytes (56 hex chars)"
                        )
                        return
                    new_admin_list.append(new_admin_bytes)
                    self.menu.print_info(f"Added admin: {new_admin_hex.strip()}")
                except ValueError:
                    self.menu.print_error(
                        "Invalid hex format for admin public key hash"
                    )
                    return

            elif admin_input.strip().lower() == "remove":
                if len(current_datum.protocol_admin) <= 1:
                    self.menu.print_error(
                        "Cannot remove admin - must have at least one admin"
                    )
                    return
                self.menu.print_info("Current admins:")
                for i, admin in enumerate(current_datum.protocol_admin):
                    print(f"  {i}: {admin.hex()}")
                try:
                    admin_index = int(
                        self.menu.get_input("Enter index of admin to remove")
                    )
                    if 0 <= admin_index < len(current_datum.protocol_admin):
                        removed_admin = new_admin_list.pop(admin_index)
                        self.menu.print_info(f"Removed admin: {removed_admin.hex()}")
                    else:
                        self.menu.print_error("Invalid admin index")
                        return
                except ValueError:
                    self.menu.print_error("Invalid admin index")
                    return

        # Option to update Projects list
        project_input = self.menu.get_input("Update projects? (add/remove/keep) [keep]")
        if project_input.strip().lower() in ["add", "remove"]:
            if project_input.strip().lower() == "add":
                new_project_hex = self.menu.get_input("Enter new project ID (hex)")
                try:
                    new_project_bytes = bytes.fromhex(new_project_hex.strip())
                    if len(new_project_bytes) > 32:  # Reasonable limit for project ID
                        self.menu.print_error(
                            "Project ID should not exceed 32 bytes (64 hex chars)"
                        )
                        return
                    if len(new_projects_list) >= 10:  # Protocol validation limit
                        self.menu.print_error(
                            "Cannot add more projects - maximum limit of 10 reached"
                        )
                        return
                    new_projects_list.append(new_project_bytes)
                    self.menu.print_info(f"Added project: {new_project_hex.strip()}")
                except ValueError:
                    self.menu.print_error("Invalid hex format for project ID")
                    return

            elif project_input.strip().lower() == "remove":
                if len(current_datum.projects) == 0:
                    self.menu.print_error("No projects to remove")
                    return
                self.menu.print_info("Current projects:")
                for i, project in enumerate(current_datum.projects):
                    print(f"  {i}: {project.hex()}")
                try:
                    project_index = int(
                        self.menu.get_input("Enter index of project to remove")
                    )
                    if 0 <= project_index < len(current_datum.projects):
                        removed_project = new_projects_list.pop(project_index)
                        self.menu.print_info(
                            f"Removed project: {removed_project.hex()}"
                        )
                    else:
                        self.menu.print_error("Invalid project index")
                        return
                except ValueError:
                    self.menu.print_error("Invalid project index")
                    return

        # Create new datum with all updates
        new_datum = DatumProtocol(
            protocol_admin=new_admin_list,
            protocol_fee=new_fee_lovelace,
            oracle_id=new_oracle_id,
            projects=new_projects_list,  # Use updated projects list
        )

        # Option to specify user address
        user_address_input = self.menu.get_input(
            "Enter address containing user tokens (or press Enter for default wallet address)"
        )

        user_address = None
        if user_address_input.strip():
            try:
                user_address = pc.Address.from_primitive(user_address_input.strip())
                self.menu.print_info(
                    f"Using specified address: {str(user_address)[:50]}..."
                )
            except Exception as e:
                self.menu.print_error(f"Invalid address format: {e}")
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
                self.menu.print_error(
                    f"Failed to create update transaction: {result['error']}"
                )
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

            # Compare Admin changes
            old_admin_set = set(old_datum.protocol_admin)
            new_admin_set = set(new_datum_result.protocol_admin)
            admin_changed = old_admin_set != new_admin_set
            admin_status = "changed" if admin_changed else "unchanged"
            print(
                f"│ Admin Count: {len(old_datum.protocol_admin)} → {len(new_datum_result.protocol_admin)} ({admin_status})"
            )

            if admin_changed:
                added_admins = new_admin_set - old_admin_set
                removed_admins = old_admin_set - new_admin_set
                if added_admins:
                    print(
                        f"│   Added: {[admin.hex()[:16] + '...' for admin in added_admins]}"
                    )
                if removed_admins:
                    print(
                        f"│   Removed: {[admin.hex()[:16] + '...' for admin in removed_admins]}"
                    )

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

            if self.menu.confirm_action(
                "Submit protocol update transaction to network?"
            ):
                self.menu.print_info("Submitting protocol update transaction...")
                tx_id = self.transactions.submit_transaction(result["transaction"])

                if tx_id:
                    self.menu.print_success(
                        "Protocol update transaction submitted successfully!"
                    )
                    self.menu.print_info("Protocol parameters have been updated.")
                    tx_info = self.transactions.get_transaction_info(tx_id)
                    print(f"Explorer: {tx_info['explorer_url']}")
                else:
                    self.menu.print_error(
                        "Failed to submit protocol update transaction"
                    )
            else:
                self.menu.print_info("Protocol update transaction cancelled by user")

        except Exception as e:
            self.menu.print_error(f"Protocol update failed: {e}")

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
            self.menu.print_header(
                "SMART CONTRACT MANAGEMENT", f"Status: {contract_status}"
            )
            self.menu.print_breadcrumb(["Main Menu", "Contract Menu"])

            # Display menu options
            self.menu.print_section("CONTRACT OPERATIONS")
            self.menu.print_menu_option("1", "Display Contracts Info", "✓")
            self.menu.print_menu_option("2", "Compile/Recompile Contracts", "✓")
            self.menu.print_menu_option("3", "Mint Tokens", "✓")
            self.menu.print_menu_option("4", "Burn Tokens", "✓")
            self.menu.print_menu_option("5", "Update Protocol Datum", "✓")
            self.menu.print_separator()
            self.menu.print_menu_option("0", "Back to Main Menu")
            self.menu.print_footer()

            choice = self.menu.get_input("Select an option (0-5)")

            if choice == "0":
                self.menu.print_info("Returning to main menu...")
                break
            elif choice == "1":
                self.display_contracts_info()
            elif choice == "2":
                try:
                    main_address = self.wallet.get_address(0)
                    result = self.contract_manager.compile_contracts(
                        main_address, force=True
                    )
                    if result["success"]:
                        self.menu.print_success(result["message"])
                    else:
                        self.menu.print_error(result["error"])
                except Exception as e:
                    self.menu.print_error(f"Compilation failed: {e}")
            elif choice == "3":
                self.test_contracts_menu()
            elif choice == "4":
                self.burn_tokens_menu()
            elif choice == "5":
                self.update_protocol_menu()
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
            self.menu.print_header(
                "TERRASACHA CARDANO DAPP", "Smart Contract Management Interface"
            )
            self.menu.print_status_bar(
                network=self.network.upper(),
                balance=balances["total_balance"] / 1_000_000,
                contracts_status=contract_status,
            )

            # Display menu options
            self.menu.print_section("MAIN MENU")
            self.menu.print_menu_option("1", "Display Wallet Info & Balances")
            self.menu.print_menu_option("2", "Generate New Addresses")
            self.menu.print_menu_option("3", "Send ADA")
            self.menu.print_menu_option(
                "4", "Enter Contract Menu", "💼" if contracts else ""
            )
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
                    count = int(
                        self.menu.get_input("How many new addresses to generate")
                    )
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
        cli.display_wallet_info()

        # Start interactive menu
        cli.interactive_menu()

    except Exception as e:
        print(f"Error initializing dApp: {e}")


if __name__ == "__main__":
    main()
