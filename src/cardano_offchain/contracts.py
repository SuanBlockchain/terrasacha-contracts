"""
Contract Management

Pure contract functionality without console dependencies.
Handles contract compilation, state management, and persistence.
"""

import json
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import pycardano as pc
from opshin.builder import PlutusContract, build
from opshin.prelude import TxId, TxOutRef

from cardano_offchain.wallet import CardanoWallet

from .chain_context import CardanoChainContext


class ReferenceScriptContract:
    """
    Placeholder contract for reference scripts stored on-chain.
    Contains metadata to locate and reference the script UTXO.
    """

    def __init__(
        self,
        policy_id: str,
        testnet_addr: str,
        mainnet_addr: str,
        reference_tx_id: str,
        reference_output_index: int,
        reference_address: str,
    ):
        self.policy_id = policy_id
        self.testnet_addr = pc.Address.from_primitive(testnet_addr)
        self.mainnet_addr = pc.Address.from_primitive(mainnet_addr)
        self.storage_type = "reference_script"
        self.reference_tx_id = reference_tx_id
        self.reference_output_index = reference_output_index
        self.reference_address = reference_address

    @property
    def cbor(self):
        """
        For reference scripts, CBOR is retrieved from the UTXO when needed.
        This property should not be accessed directly - use get_reference_script() instead.
        """
        raise NotImplementedError(
            "Reference script CBOR must be retrieved from UTXO using get_reference_script()"
        )

    def get_reference_utxo(self) -> Dict[str, Any]:
        """Get the reference UTXO information"""
        return {
            "tx_id": self.reference_tx_id,
            "output_index": self.reference_output_index,
            "address": self.reference_address,
        }


class ContractManager:
    """Manages smart contract compilation and state"""

    def __init__(
        self, chain_context: CardanoChainContext, contracts_dir: str = "./src/terrasacha_contracts"
    ):
        """
        Initialize contract manager

        Args:
            chain_context: CardanoChainContext instance
            contracts_dir: Path to contracts directory
        """
        self.chain_context = chain_context
        self.context = chain_context.get_context()
        self.api = chain_context.get_api()
        self.network = chain_context.network

        self.contracts_dir = contracts_dir
        self.minting_contracts_path = pathlib.Path(contracts_dir) / "minting_policies"
        self.spending_contracts_path = pathlib.Path(contracts_dir) / "validators"

        # Contract storage
        self.contracts: Dict[str, PlutusContract] = {}
        self.contract_metadata: Dict[str, Any] = {}
        self.compilation_utxo: Optional[Dict[str, Any]] = None
        self.used_utxos: set = set()  # Track all UTXOs used for contract compilation

        # Load existing contracts
        self._load_contracts()

    def _get_contracts_file_path(self) -> pathlib.Path:
        """Get the path for contracts storage file"""
        return pathlib.Path(f"contracts_{self.network}.json")

    def spend_reference_script_utxo(
        self, contract_name: str, wallet: CardanoWallet, destination_address: pc.Address
    ) -> Dict[str, Any]:
        """
        Spend a reference script UTXO and send remaining ADA to destination address

        Args:
            contract_name: Name of the reference script contract
            wallet: Wallet that owns the reference script UTXO
            destination_address: Where to send the remaining ADA

        Returns:
            Dictionary with success status and transaction details
        """
        if contract_name not in self.contracts:
            return {"success": False, "error": f"Contract '{contract_name}' not found"}

        contract = self.contracts[contract_name]

        # Check if this is a reference script contract
        if not hasattr(contract, "storage_type") or contract.storage_type != "reference_script":
            return {
                "success": False,
                "error": f"Contract '{contract_name}' is not a reference script",
            }

        try:
            # Get the reference UTXO information
            ref_utxo_info = contract.get_reference_utxo()
            tx_id = ref_utxo_info["tx_id"]
            output_index = ref_utxo_info["output_index"]

            # Find the UTXO on-chain
            try:
                # Check if UTXO still exists
                utxo_exists = False
                wallet_utxos = self.context.utxos(wallet.get_address(0))

                for utxo in wallet_utxos:
                    if str(utxo.input.transaction_id) == tx_id and utxo.input.index == output_index:
                        utxo_exists = True
                        reference_utxo = utxo
                        break

                if not utxo_exists:
                    return {
                        "success": False,
                        "error": f"Reference script UTXO {tx_id}:{output_index} not found or already spent",
                    }

                # Build transaction to spend the reference script UTXO
                builder = pc.TransactionBuilder(self.context)

                # Add the reference script UTXO as input
                builder.add_input(reference_utxo)

                builder.fee_buffer = 1_000_000

                # Build and sign transaction
                signing_key = wallet.get_signing_key(0)
                signed_tx = builder.build_and_sign(
                    [signing_key], change_address=destination_address
                )

                # Submit transaction
                tx_id = self.context.submit_tx(signed_tx)

                return {
                    "success": True,
                    "message": f"Reference script UTXO spent successfully",
                    "tx_id": tx_id,
                    # "ada_sent": ada_sent / 1_000_000,
                    "destination": str(destination_address),
                }

            except Exception as api_error:
                return {
                    "success": False,
                    "error": f"Failed to spend reference script UTXO: {str(api_error)}",
                }

        except Exception as e:
            return {"success": False, "error": f"Reference script deletion failed: {str(e)}"}

    def _save_contracts(self) -> bool:
        """
        Save compiled contracts to disk with metadata

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.contracts:
            return False

        contracts_data = {
            "network": self.network,
            "compilation_timestamp": time.time(),
            "compilation_utxo": self.compilation_utxo,
            "used_utxos": list(self.used_utxos),  # Persist used UTXOs for uniqueness tracking
            "contracts": {},
        }

        for name, contract in self.contracts.items():
            # Check if this contract has reference script metadata
            contract_data = {
                "policy_id": contract.policy_id,
                "testnet_addr": str(contract.testnet_addr),
                "mainnet_addr": str(contract.mainnet_addr),
                "storage_type": getattr(contract, "storage_type", "local"),
            }

            # Add appropriate data based on storage type
            if hasattr(contract, "storage_type") and contract.storage_type == "reference_script":
                # Store reference script UTXO information
                contract_data.update(
                    {
                        "reference_utxo": {
                            "tx_id": contract.reference_tx_id,
                            "output_index": contract.reference_output_index,
                            "address": contract.reference_address,
                        }
                    }
                )
            else:
                # Store full CBOR for local contracts
                contract_data["cbor_hex"] = contract.cbor.hex()

            contracts_data["contracts"][name] = contract_data

        try:
            with open(self._get_contracts_file_path(), "w") as f:
                json.dump(contracts_data, f, indent=2)
            return True
        except Exception:
            return False

    def _load_contracts(self) -> bool:
        """
        Load compiled contracts from disk if available

        Returns:
            True if loaded successfully, False otherwise
        """
        contracts_file = self._get_contracts_file_path()
        if not contracts_file.exists():
            return False

        try:
            with open(contracts_file, "r") as f:
                contracts_data = json.load(f)

            # Validate network matches
            if contracts_data.get("network") != self.network:
                return False

            # Load compilation UTXO
            self.compilation_utxo = contracts_data.get("compilation_utxo")

            # Load used UTXOs for uniqueness tracking
            saved_used_utxos = contracts_data.get("used_utxos", [])
            self.used_utxos = set(saved_used_utxos)

            # Reconstruct PlutusContract objects from saved data
            saved_contracts = contracts_data.get("contracts", {})
            # Preserve any existing in-memory contracts (they may be newer/not yet saved)
            in_memory_contracts = self.contracts.copy()

            # Load saved contracts, but don't overwrite in-memory ones
            for name, contract_data in saved_contracts.items():
                # Skip if we already have this contract in memory
                if name in in_memory_contracts:
                    continue

                try:
                    storage_type = contract_data.get("storage_type", "local")

                    if storage_type == "reference_script":
                        # Create a reference script contract placeholder
                        ref_data = contract_data["reference_utxo"]
                        contract = ReferenceScriptContract(
                            policy_id=contract_data["policy_id"],
                            testnet_addr=contract_data["testnet_addr"],
                            mainnet_addr=contract_data["mainnet_addr"],
                            reference_tx_id=ref_data["tx_id"],
                            reference_output_index=ref_data["output_index"],
                            reference_address=ref_data["address"],
                        )
                    else:
                        # Load local contract with CBOR
                        cbor_bytes = bytes.fromhex(contract_data["cbor_hex"])
                        script = pc.PlutusV2Script(cbor_bytes)
                        # Create PlutusContract from the script
                        contract = PlutusContract(script)

                        # Validate addresses and policy ID match for local contracts
                        if (
                            str(contract.testnet_addr) != contract_data["testnet_addr"]
                            or str(contract.mainnet_addr) != contract_data["mainnet_addr"]
                            or contract.policy_id != contract_data["policy_id"]
                        ):
                            continue  # Skip invalid contracts

                    # Store the contract
                    self.contracts[name] = contract

                except Exception:
                    # Skip contracts that fail to load
                    continue

            return True

        except Exception:
            return False

    def get_contract_script_info(self, contract_name: str) -> Optional[Dict[str, Any]]:
        """
        Get script information for a contract (CBOR for local, reference info for reference scripts)

        Args:
            contract_name: Name of the contract

        Returns:
            Dictionary with script information or None if contract not found
        """
        if contract_name not in self.contracts:
            return None

        contract = self.contracts[contract_name]

        if isinstance(contract, ReferenceScriptContract):
            return {
                "type": "reference_script",
                "reference_utxo": {
                    "tx_id": contract.reference_tx_id,
                    "output_index": contract.reference_output_index,
                    "address": contract.reference_address,
                },
                "policy_id": contract.policy_id,
            }
        else:
            return {"type": "local", "cbor": contract.cbor, "policy_id": contract.policy_id}

    def _is_compilation_utxo_available(self, address: pc.Address) -> bool:
        """
        Check if the compilation UTXO is still available

        Args:
            address: Address to check UTXOs

        Returns:
            True if UTXO is available, False otherwise
        """
        if not self.compilation_utxo:
            return False

        try:
            utxos = self.context.utxos(address)
            for utxo in utxos:
                if (
                    utxo.input.transaction_id.payload.hex() == self.compilation_utxo["tx_id"]
                    and utxo.input.index == self.compilation_utxo["index"]
                ):
                    return True
            return False
        except Exception:
            return False

    def _set_recursion_limit(self, limit: int = 2000):

        # Check if the new limit is greater than the current one
        if limit > sys.getrecursionlimit():
            # Set the new recursion limit
            sys.setrecursionlimit(limit)
            print("Recursion limit updated successfully.")
        else:
            print("New limit must be greater than the current limit.")

    def get_contract_status(self, address: pc.Address) -> str:
        """
        Get current contract compilation status

        Args:
            address: Address to check UTXO availability

        Returns:
            Status string
        """
        if not self.contracts:
            return "Not compiled"
        elif not self.compilation_utxo:
            return "Compiled (unknown UTXO)"
        elif self._is_compilation_utxo_available(address):
            return "✓ Ready"
        else:
            return "⚠ UTXO consumed"

    def compile_contracts(
        self, protocol_address: pc.Address, project_address: pc.Address = None, force: bool = False
    ) -> Dict[str, Any]:
        """
        Compile OpShin smart contracts

        Args:
            protocol_address: Address to get UTXOs from for protocol contract compilation
            project_address: Address to get UTXOs from for project contract compilation (defaults to protocol_address)
            force: Force recompilation even if contracts exist

        Returns:
            Compilation result dictionary
        """
        # Default project address to protocol address if not provided (backward compatibility)
        if project_address is None:
            project_address = protocol_address
        # Check if we need to compile
        if (
            not force
            and self.contracts
            and self.compilation_utxo
            and self._is_compilation_utxo_available(protocol_address)
        ):
            return {
                "success": True,
                "message": "Contracts already compiled and UTXO available",
                "skipped": True,
            }

        try:
            # Find suitable UTXO for protocol contract compilation
            protocol_utxos = self.context.utxos(protocol_address)
            protocol_utxo_to_spend = None
            for utxo in protocol_utxos:
                if utxo.output.amount.coin > 3000000:
                    utxo_ref = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
                    if utxo_ref not in self.used_utxos:
                        protocol_utxo_to_spend = utxo
                        break

            if not protocol_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for protocol compilation (need >3 ADA)",
                }

            # Find suitable UTXO for project contract compilation
            project_utxos = self.context.utxos(project_address)
            project_utxo_to_spend = None
            for utxo in project_utxos:
                if utxo.output.amount.coin > 3000000:
                    utxo_ref = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
                    # Make sure it's a different UTXO if same address and not previously used
                    if (
                        protocol_address == project_address
                        and utxo.input.transaction_id == protocol_utxo_to_spend.input.transaction_id
                        and utxo.input.index == protocol_utxo_to_spend.input.index
                    ):
                        continue
                    if utxo_ref not in self.used_utxos:
                        project_utxo_to_spend = utxo
                        break

            if not project_utxo_to_spend:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for project compilation (need >3 ADA)",
                }

            # Store compilation UTXO metadata for protocol (primary)
            self.compilation_utxo = {
                "tx_id": protocol_utxo_to_spend.input.transaction_id.payload.hex(),
                "index": protocol_utxo_to_spend.input.index,
                "amount": protocol_utxo_to_spend.output.amount.coin,
            }

            # Track used UTXOs to ensure contract uniqueness
            protocol_utxo_ref = f"{protocol_utxo_to_spend.input.transaction_id.payload.hex()}:{protocol_utxo_to_spend.input.index}"
            project_utxo_ref = f"{project_utxo_to_spend.input.transaction_id.payload.hex()}:{project_utxo_to_spend.input.index}"
            self.used_utxos.add(protocol_utxo_ref)
            self.used_utxos.add(project_utxo_ref)

            # Create orefs for each contract
            protocol_oref = TxOutRef(
                id=TxId(protocol_utxo_to_spend.input.transaction_id.payload),
                idx=protocol_utxo_to_spend.input.index,
            )

            project_oref = TxOutRef(
                id=TxId(project_utxo_to_spend.input.transaction_id.payload),
                idx=project_utxo_to_spend.input.index,
            )

            # Compile contracts (excluding authentication_nfts which needs dynamic compilation)
            compiled_contracts = {}

            # Build protocol validator using protocol wallet UTXO
            protocol_path = self.spending_contracts_path / "protocol.py"
            if protocol_path.exists():
                print(
                    f"Compiling protocol contract using UTXO: {protocol_utxo_to_spend.input.transaction_id}:{protocol_utxo_to_spend.input.index}"
                )
                protocol_contract = build(protocol_path, protocol_oref)
                compiled_contracts["protocol"] = PlutusContract(protocol_contract)

            # Build project validator (requires protocol policy ID parameter) using project wallet UTXO
            project_path = self.spending_contracts_path / "project.py"
            if project_path.exists():
                protocol_policy_id = bytes.fromhex(PlutusContract(protocol_contract).policy_id)
                print(
                    "Using the following Protocol Policy ID to compile the project contract:",
                    compiled_contracts["protocol"].policy_id,
                )
                print(
                    f"Compiling project contract using UTXO: {project_utxo_to_spend.input.transaction_id}:{project_utxo_to_spend.input.index}"
                )
                if protocol_policy_id:
                    self._set_recursion_limit(2000)
                    project_contract = build(project_path, project_oref)

                    # Determine project contract name (support multiple projects)
                    project_name = "project"

                    if not force:
                        # When not forcing (incremental compilation), check for existing projects
                        existing_projects = [
                            name
                            for name in self.contracts.keys()
                            if name == "project" or name.startswith("project_")
                        ]
                        if existing_projects:
                            # Find next available index
                            index = 1
                            while f"{project_name}_{index}" in self.contracts:
                                index += 1
                            project_name = f"{project_name}_{index}"
                            print(f"Project contract will be stored as: {project_name}")
                    else:
                        # When forcing (full recompilation), start fresh with "project"
                        print(
                            f"Starting fresh - project contract will be stored as: {project_name}"
                        )

                    compiled_contracts[project_name] = PlutusContract(project_contract)

            if not compiled_contracts:
                return {"success": False, "error": "No contract files found to compile"}

            # Handle contract replacement based on force flag
            if not force:
                # If not forcing, merge with existing contracts (preserve existing projects)
                for name, contract in compiled_contracts.items():
                    self.contracts[name] = contract
            else:
                # If forcing recompilation, completely replace all contracts (start fresh)
                # This compiles protocol + one new project contract only
                self.contracts = compiled_contracts

            return {
                "success": True,
                "message": f"Successfully compiled {len(compiled_contracts)} contracts",
                "contracts": list(compiled_contracts.keys()),
                "saved": False,  # Not saved until deployed
                "compilation_utxo": self.compilation_utxo,
            }

        except Exception as e:
            return {"success": False, "error": f"Compilation failed: {e}"}

    def compile_project_contract_only(self, project_address: pc.Address = None) -> Dict[str, Any]:
        """
        Compile only a new project contract using existing protocol contract.
        This allows creating additional project contracts without recompiling everything.

        Args:
            project_address: Address to get UTXOs from for project contract compilation

        Returns:
            Dictionary containing compilation results
        """
        try:
            # Check if protocol contract exists
            if "protocol" not in self.contracts:
                return {
                    "success": False,
                    "error": "Protocol contract must be compiled first. Use compile_contracts() to compile the full suite.",
                }

            # Check if project.py exists
            project_path = self.spending_contracts_path / "project.py"
            if not project_path.exists():
                return {"success": False, "error": "Project contract file not found"}

            # Get protocol policy ID from existing contract
            protocol_contract = self.contracts["protocol"]

            # Get a UTXO for unique contract compilation
            if project_address is None:
                return {
                    "success": False,
                    "error": "Project address required to find UTXOs for unique project compilation",
                }

            utxos = self.context.utxos(project_address)
            utxo_to_spend = None

            # Find available UTXO that hasn't been used for compilation
            for utxo in utxos:
                if utxo.output.amount.coin > 3000000:
                    utxo_ref = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
                    if utxo_ref not in self.used_utxos:
                        utxo_to_spend = utxo
                        break

            # If no unused UTXO found, use any available UTXO (fallback for edge cases)
            if not utxo_to_spend:
                for utxo in utxos:
                    if utxo.output.amount.coin > 3000000:
                        utxo_to_spend = utxo
                        print(
                            f"Warning: Reusing UTXO {utxo.input.transaction_id}:{utxo.input.index} - contract may be identical to previous"
                        )
                        break

            if not utxo_to_spend:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for compilation (need >3 ADA)",
                }

            # utxos = self.api.address_utxos(str(address))
            # if not utxos:
            #     return {"success": False, "error": "No UTXOs found at address for project compilation"}

            # Use the first available UTXO for compilation
            # selected_utxo = utxos[0]
            oref = TxOutRef(
                id=TxId(utxo_to_spend.input.transaction_id.payload), idx=utxo_to_spend.input.index
            )

            print(
                f"Compiling project contract using Protocol Policy ID: {protocol_contract.policy_id}"
            )
            print(f"Using UTXO: {utxo_to_spend.input.transaction_id}:{utxo_to_spend.input.index}")

            # Mark this UTXO as used to ensure uniqueness for future compilations
            utxo_ref = (
                f"{utxo_to_spend.input.transaction_id.payload.hex()}:{utxo_to_spend.input.index}"
            )
            self.used_utxos.add(utxo_ref)

            # Determine project contract name (support multiple projects)
            project_name = "project"
            if project_name in self.contracts:
                # Find next available index
                index = 1
                while f"{project_name}_{index}" in self.contracts:
                    index += 1
                project_name = f"{project_name}_{index}"
                print(f"Project contract will be stored as: {project_name}")

            # Compile project contract with oref and protocol_policy_id
            self._set_recursion_limit(2000)
            project_contract = build(project_path, oref)

            # Add to contracts
            self.contracts[project_name] = PlutusContract(project_contract)

            return {
                "success": True,
                "message": f"Successfully compiled project contract as '{project_name}'",
                "project_name": project_name,
                "policy_id": PlutusContract(project_contract).policy_id,
                "used_utxo": f"{utxo_to_spend.input.transaction_id}:{utxo_to_spend.input.index}",
                "saved": False,  # Not saved until deployed
            }

        except Exception as e:
            return {"success": False, "error": f"Project compilation failed: {e}"}

    def get_contract(self, name: str) -> Optional[PlutusContract]:
        """
        Get compiled contract by name

        Args:
            name: Contract name

        Returns:
            PlutusContract instance or None if not found
        """
        return self.contracts.get(name)

    def get_project_contract(self, project_name: str = None) -> Optional[PlutusContract]:
        """
        Get a project contract by name. If no specific name is provided,
        returns the default project contract for backward compatibility.

        Args:
            project_name: Specific project contract name (e.g., "project_1", "project_2")
                         If None, returns the default "project" contract

        Returns:
            PlutusContract or None if not found
        """
        if project_name:
            return self.contracts.get(project_name)

        # For backward compatibility, return "project" if it exists,
        # otherwise return the first available project contract
        if "project" in self.contracts:
            return self.contracts["project"]

        # Find first project contract (project_1, project_2, etc.)
        for name in sorted(self.contracts.keys()):
            if name.startswith("project_"):
                return self.contracts[name]

        return None

    def list_project_contracts(self) -> list:
        """List all available project contract names (excluding NFT minting policies and grey token contracts)"""
        project_contracts = []
        for name in sorted(self.contracts.keys()):
            if (name == "project" or name.startswith("project_")) and not name.endswith(
                ("_nfts", "_grey")
            ):
                project_contracts.append(name)
        return project_contracts

    def list_grey_token_contracts(self) -> list:
        """List all available grey token contract names"""
        grey_contracts = []
        for name in sorted(self.contracts.keys()):
            if name.endswith("_grey"):
                grey_contracts.append(name)
        return grey_contracts

    def get_project_name_from_contract(self, contract: PlutusContract) -> Optional[str]:
        """
        Find the project name for a given contract instance

        Args:
            contract: PlutusContract instance to find name for

        Returns:
            Project name or None if not found
        """
        for name, stored_contract in self.contracts.items():
            if (name == "project" or name.startswith("project_")) and stored_contract == contract:
                return name
        return None

    def get_project_nfts_contract(self, project_name: str) -> Optional[PlutusContract]:
        """
        Get the project NFTs minting policy contract for a specific project

        Args:
            project_name: Name of the project (e.g., "project", "project_1")

        Returns:
            PlutusContract for the project's NFTs minting policy or None if not found
        """
        project_nfts_name = f"{project_name}_nfts"
        return self.contracts.get(project_nfts_name)

    def get_grey_token_contract(self, project_name: str) -> Optional[PlutusContract]:
        """
        Get the grey token minting policy contract for a specific project

        Args:
            project_name: Name of the project (e.g., "project", "project_1")

        Returns:
            PlutusContract for the project's grey token minting policy or None if not found
        """
        grey_contract_name = f"{project_name}_grey"
        return self.contracts.get(grey_contract_name)

    def get_contracts_info(self) -> Dict[str, Any]:
        """
        Get comprehensive contract information

        Returns:
            Dictionary containing contract information
        """
        if not self.contracts:
            return {"contracts": {}, "compilation_utxo": None}

        contracts_info = {}
        for name, contract in self.contracts.items():
            contract_address = (
                contract.testnet_addr
                if self.chain_context.cardano_network == pc.Network.TESTNET
                else contract.mainnet_addr
            )

            # Check if this is a minting policy (NFT contract) or spending validator
            is_minting_policy = name.endswith("_nfts")

            if is_minting_policy:
                # For minting policies, only policy ID matters (no balance)
                contracts_info[name] = {"policy_id": contract.policy_id, "type": "minting_policy"}
            else:
                # For spending validators, check balance
                try:
                    utxos = self.api.address_utxos(str(contract_address))
                    balance = sum(
                        int(utxo.amount[0].quantity)
                        for utxo in utxos
                        if utxo.amount[0].unit == "lovelace"
                    )
                except Exception as api_error:
                    # Handle 404 errors (address never used) as zero balance
                    if (hasattr(api_error, "status_code") and api_error.status_code == 404) or (
                        "status_code" in str(api_error) and "404" in str(api_error)
                    ):
                        balance = 0
                    else:
                        # Other errors also default to 0 for display purposes
                        balance = 0

                contracts_info[name] = {
                    "policy_id": contract.policy_id,
                    "address": str(contract_address),
                    "balance": balance,
                    "balance_ada": balance / 1_000_000,
                    "type": "spending_validator",
                }

        return {
            "contracts": contracts_info,
            "compilation_utxo": self.compilation_utxo,
            "total_contracts": len(self.contracts),
        }

    def list_contracts(self) -> List[str]:
        """
        Get list of compiled contract names

        Returns:
            List of contract names
        """
        return list(self.contracts.keys())

    def create_minting_contract(
        self, contract_name: str, utxo_ref: TxOutRef
    ) -> Optional[PlutusContract]:
        """
        Dynamically compile a minting policy with a specific UTXO reference.
        Supports both NFT contracts (ending with _nfts.py) and regular minting contracts.

        Args:
            contract_name: Name of the contract (without file extension)
            utxo_ref: Transaction output reference to use for compilation

        Returns:
            PlutusContract instance or None if compilation failed
        """
        try:
            # First try NFT contracts (with _nfts.py suffix)
            auth_nfts_path = self.minting_contracts_path / f"{contract_name}_nfts.py"
            if auth_nfts_path.exists():
                auth_contract = build(auth_nfts_path, utxo_ref)
                return PlutusContract(auth_contract)

            # If NFT contract doesn't exist, try regular minting contract (with .py suffix)
            minting_path = self.minting_contracts_path / f"{contract_name}.py"
            if minting_path.exists():
                auth_contract = build(minting_path, utxo_ref)
                return PlutusContract(auth_contract)

            # Neither path exists
            return None

        except Exception:
            return None

    def mark_contract_as_deployed(self, contract_names: List[str]) -> bool:
        """
        Mark contracts as deployed and save them to disk

        Args:
            contract_names: List of contract names to mark as deployed

        Returns:
            True if saved successfully, False otherwise
        """
        # Verify all contracts exist in memory
        for name in contract_names:
            if name not in self.contracts:
                return False

        # Save contracts to disk now that they're deployed
        return self._save_contracts()

    def get_reference_script_cbor(self, contract_name: str) -> Optional[bytes]:
        """
        Retrieve the CBOR of a reference script from its UTXO

        Args:
            contract_name: Name of the reference script contract

        Returns:
            CBOR bytes or None if not found/not a reference script
        """
        if contract_name not in self.contracts:
            return None

        contract = self.contracts[contract_name]
        if not isinstance(contract, ReferenceScriptContract):
            return None

        try:
            # Query the UTXO containing the reference script
            tx_id = contract.reference_tx_id
            output_index = contract.reference_output_index

            # Get the UTXO from the blockchain
            utxos = self.context.utxos(pc.Address.from_primitive(contract.reference_address))

            for utxo in utxos:
                if (
                    utxo.input.transaction_id.payload.hex() == tx_id
                    and utxo.input.index == output_index
                ):
                    # Extract script from UTXO
                    if utxo.output.script:
                        return utxo.output.script.data

            return None

        except Exception:
            return None

    def convert_to_reference_script(
        self,
        contract_name: str,
        reference_tx_id: str,
        reference_output_index: int,
        reference_address: str,
    ) -> bool:
        """
        Convert a local contract to a reference script contract

        Args:
            contract_name: Name of the contract to convert
            reference_tx_id: Transaction ID containing the reference script
            reference_output_index: Output index of the reference script
            reference_address: Address containing the reference script UTXO

        Returns:
            True if successful, False otherwise
        """
        if contract_name not in self.contracts:
            return False

        current_contract = self.contracts[contract_name]
        if isinstance(current_contract, ReferenceScriptContract):
            return False  # Already a reference script

        try:
            # Create new reference script contract
            ref_contract = ReferenceScriptContract(
                policy_id=current_contract.policy_id,
                testnet_addr=str(current_contract.testnet_addr),
                mainnet_addr=str(current_contract.mainnet_addr),
                reference_tx_id=reference_tx_id,
                reference_output_index=reference_output_index,
                reference_address=reference_address,
            )

            # Replace the contract
            self.contracts[contract_name] = ref_contract

            return True

        except Exception:
            return False

    def delete_contract_if_empty(
        self, contract_name: str, delete_associated_nfts: bool = True
    ) -> Dict[str, Any]:
        """
        Delete a contract if it has zero balance (no active tokens)
        For project contracts, also deletes the associated project NFTs minting policy

        Args:
            contract_name: Name of contract to check and potentially delete
            delete_associated_nfts: If True, also delete associated project NFTs minting policy

        Returns:
            Dictionary with success status and message
        """
        if contract_name not in self.contracts:
            return {"success": False, "error": f"Contract '{contract_name}' not found"}

        contract = self.contracts[contract_name]

        # Skip minting policies (they don't have balances)
        if contract_name.endswith("_nfts"):
            return {"success": False, "error": "Cannot delete minting policy contracts directly"}

        try:
            # Check contract balance
            contract_address = (
                contract.testnet_addr
                if self.chain_context.cardano_network == pc.Network.TESTNET
                else contract.mainnet_addr
            )

            try:
                utxos = self.api.address_utxos(str(contract_address))
            except Exception as api_error:
                # Handle 404 errors - address never used, so zero balance
                if hasattr(api_error, "status_code") and api_error.status_code == 404:
                    # Address not found = never used = zero balance = safe to delete
                    deleted_contracts = [contract_name]
                    del self.contracts[contract_name]

                    # Also delete associated project NFTs and grey token minting policies if they exist
                    if delete_associated_nfts and (
                        contract_name == "project" or contract_name.startswith("project_")
                    ):
                        project_nfts_name = f"{contract_name}_nfts"
                        if project_nfts_name in self.contracts:
                            del self.contracts[project_nfts_name]
                            deleted_contracts.append(project_nfts_name)

                        grey_contract_name = f"{contract_name}_grey"
                        if grey_contract_name in self.contracts:
                            del self.contracts[grey_contract_name]
                            deleted_contracts.append(grey_contract_name)

                    save_success = self._save_contracts()
                    message = f"Contract{'s' if len(deleted_contracts) > 1 else ''} {', '.join(deleted_contracts)} deleted successfully (unused address - zero balance)"
                    return {
                        "success": True,
                        "message": message,
                        "saved": save_success,
                        "deleted_contracts": deleted_contracts,
                    }
                elif "status_code" in str(api_error) and "404" in str(api_error):
                    # Handle different error formats that might contain 404
                    deleted_contracts = [contract_name]
                    del self.contracts[contract_name]

                    # Also delete associated project NFTs and grey token minting policies if they exist
                    if delete_associated_nfts and (
                        contract_name == "project" or contract_name.startswith("project_")
                    ):
                        project_nfts_name = f"{contract_name}_nfts"
                        if project_nfts_name in self.contracts:
                            del self.contracts[project_nfts_name]
                            deleted_contracts.append(project_nfts_name)

                        grey_contract_name = f"{contract_name}_grey"
                        if grey_contract_name in self.contracts:
                            del self.contracts[grey_contract_name]
                            deleted_contracts.append(grey_contract_name)

                    save_success = self._save_contracts()
                    message = f"Contract{'s' if len(deleted_contracts) > 1 else ''} {', '.join(deleted_contracts)} deleted successfully (unused address - zero balance)"
                    return {
                        "success": True,
                        "message": message,
                        "saved": save_success,
                        "deleted_contracts": deleted_contracts,
                    }
                else:
                    # Other API errors should be reported
                    raise api_error

            # Address exists and has UTXOs - check balances
            balance = sum(
                int(utxo.amount[0].quantity) for utxo in utxos if utxo.amount[0].unit == "lovelace"
            )

            # Check for any tokens (not just ADA)
            has_tokens = False
            for utxo in utxos:
                if len(utxo.amount) > 1:  # More than just lovelace
                    has_tokens = True
                    break

            if balance > 0 or has_tokens:
                return {
                    "success": False,
                    "error": f"Contract '{contract_name}' still has balance ({balance/1_000_000:.6f} ADA) or tokens. Cannot delete.",
                    "balance": balance,
                    "has_tokens": has_tokens,
                }

            # Safe to delete - no balance and no tokens
            deleted_contracts = [contract_name]
            del self.contracts[contract_name]

            # Also delete associated project NFTs and grey token minting policies if they exist
            if delete_associated_nfts and (
                contract_name == "project" or contract_name.startswith("project_")
            ):
                project_nfts_name = f"{contract_name}_nfts"
                if project_nfts_name in self.contracts:
                    del self.contracts[project_nfts_name]
                    deleted_contracts.append(project_nfts_name)

                grey_contract_name = f"{contract_name}_grey"
                if grey_contract_name in self.contracts:
                    del self.contracts[grey_contract_name]
                    deleted_contracts.append(grey_contract_name)

            # Update saved contracts file
            save_success = self._save_contracts()

            message = f"Contract{'s' if len(deleted_contracts) > 1 else ''} {', '.join(deleted_contracts)} deleted successfully (zero balance confirmed)"
            return {
                "success": True,
                "message": message,
                "saved": save_success,
                "deleted_contracts": deleted_contracts,
            }

        except Exception as e:
            return {"success": False, "error": f"Error checking contract balance: {e}"}
