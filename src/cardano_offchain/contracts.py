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

from cardano_offchain.chain_context import CardanoChainContext

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
        self.project_compilation_utxos: Dict[str, Dict[str, Any]] = {}  # Track compilation UTXOs per project
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
        # Always save the current state, even if empty
        contracts_data = {
            "network": self.network,
            "compilation_timestamp": time.time(),
            "compilation_utxo": self.compilation_utxo if self.contracts else None,
            "project_compilation_utxos": self.project_compilation_utxos if self.contracts else {},
            "used_utxos": list(self.used_utxos) if self.contracts else [],  # Clear UTXOs when no contracts
            "contracts": {},
        }

        # If we have contracts, add them to the data
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

        # If all contracts are deleted, clear the used_utxos and project_compilation_utxos as well for a fresh start
        if not self.contracts:
            self.used_utxos.clear()
            self.project_compilation_utxos.clear()

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

            # Load project compilation UTXOs
            self.project_compilation_utxos = contracts_data.get("project_compilation_utxos", {})

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

    def get_project_compilation_utxo(self, project_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the compilation UTXO information for a specific project contract

        Args:
            project_name: Name of the project contract (e.g., "project", "project_1")

        Returns:
            Dictionary containing UTXO information or None if not found
        """
        return self.project_compilation_utxos.get(project_name)

    def get_project_compilation_utxo_as_txoutref(self, compilation_utxo: Optional[Dict[str, Any]]) -> Optional[TxOutRef]:
        """
        Get the compilation UTXO for a project as a TxOutRef object

        Args:
            compilation_utxo: Compilation UTXO dictionary from get_project_compilation_utxo()

        Returns:
            TxOutRef object or None if not found
        """
        # compilation_utxo = self.get_project_compilation_utxo(project_name)
        if not compilation_utxo:
            return None

        try:
            return TxOutRef(
                id=TxId(bytes.fromhex(compilation_utxo["tx_id"])),
                idx=compilation_utxo["index"]
            )
        except Exception:
            return None

    def get_reserved_utxos(self) -> set:
        """
        Get set of UTXO references that are reserved for project compilation.
        These UTXOs should not be spent by other operations like reference script creation.

        Args:
            address: Optional address to filter reserved UTXOs by wallet (only returns UTXOs for this address)

        Returns:
            Set of UTXO references in format "tx_id:index"
        """
        reserved_utxos = set()

        # Add protocol compilation UTXO if it exists
        if self.compilation_utxo:
            utxo_ref = f"{self.compilation_utxo['tx_id']}:{self.compilation_utxo['index']}"
            reserved_utxos.add(utxo_ref)

        # Add all project compilation UTXOs
        for project_name, compilation_info in self.project_compilation_utxos.items():
            utxo_ref = f"{compilation_info['tx_id']}:{compilation_info['index']}"
            reserved_utxos.add(utxo_ref)

        return reserved_utxos

    def get_available_utxos(self, address: pc.Address, min_ada: int = 3000000, auto_cleanup: bool = True) -> List[pc.UTxO]:
        """
        Get UTXOs from address that are NOT reserved for compilation.

        Args:
            address: Address to query UTXOs from
            min_ada: Minimum ADA amount required (default 3 ADA)
            auto_cleanup: Whether to automatically clean up spent UTXOs from tracking (default True)

        Returns:
            List of available UTxO objects excluding reserved ones
        """
        try:
            # Automatically clean up spent UTXOs if requested
            if auto_cleanup:
                cleanup_result = self.cleanup_spent_utxos(address)
                if cleanup_result["total_removed"] > 0:
                    print(f"Cleaned up {cleanup_result['total_removed']} spent UTXOs from tracking")

            # Get all UTXOs from the address
            all_utxos = self.context.utxos(address)

            # Get reserved UTXO references (should be clean after cleanup)
            reserved_utxo_refs = self.get_reserved_utxos()

            # Filter out reserved UTXOs and apply minimum ADA requirement
            available_utxos = []
            for utxo in all_utxos:
                utxo_ref = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"

                # Skip if this UTXO is reserved
                if utxo_ref in reserved_utxo_refs:
                    continue

                # Skip if doesn't meet minimum ADA requirement
                if utxo.output.amount.coin < min_ada:
                    continue

                available_utxos.append(utxo)

            return available_utxos

        except Exception:
            return []

    def cleanup_spent_utxos(self, address: pc.Address = None) -> Dict[str, Any]:
        """
        Remove spent UTXOs from tracking (used_utxos and compilation_utxos).
        This should be called periodically to clean up stale UTXO references.

        Args:
            address: Optional address to check UTXOs against. If None, checks all addresses.

        Returns:
            Dictionary with cleanup results
        """
        cleanup_results = {
            "removed_used_utxos": [],
            "removed_compilation_utxos": [],
            "removed_project_compilation_utxos": [],
            "total_removed": 0,
            "errors": []
        }

        try:
            # Get all UTXOs for the address if provided
            if address:
                available_utxos = self.context.utxos(address)
                available_utxo_refs = {
                    f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
                    for utxo in available_utxos
                }
            else:
                available_utxo_refs = None

            # Clean up used_utxos
            utxos_to_remove = []
            for utxo_ref in self.used_utxos.copy():
                if available_utxo_refs is None:
                    # If no address provided, we can't verify - skip for now
                    continue

                if utxo_ref not in available_utxo_refs:
                    utxos_to_remove.append(utxo_ref)
                    self.used_utxos.remove(utxo_ref)
                    cleanup_results["removed_used_utxos"].append(utxo_ref)

            # Clean up protocol compilation_utxo
            if self.compilation_utxo and available_utxo_refs is not None:
                compilation_ref = f"{self.compilation_utxo['tx_id']}:{self.compilation_utxo['index']}"
                if compilation_ref not in available_utxo_refs:
                    cleanup_results["removed_compilation_utxos"].append(compilation_ref)
                    self.compilation_utxo = None

            # Clean up project_compilation_utxos
            projects_to_remove = []
            for project_name, compilation_info in self.project_compilation_utxos.items():
                if available_utxo_refs is None:
                    continue

                utxo_ref = f"{compilation_info['tx_id']}:{compilation_info['index']}"
                if utxo_ref not in available_utxo_refs:
                    projects_to_remove.append(project_name)
                    cleanup_results["removed_project_compilation_utxos"].append(f"{project_name}: {utxo_ref}")

            # Remove spent project compilation UTXOs
            for project_name in projects_to_remove:
                del self.project_compilation_utxos[project_name]

            cleanup_results["total_removed"] = (
                len(cleanup_results["removed_used_utxos"]) +
                len(cleanup_results["removed_compilation_utxos"]) +
                len(cleanup_results["removed_project_compilation_utxos"])
            )

            # Save changes if any UTXOs were removed
            if cleanup_results["total_removed"] > 0:
                save_success = self._save_contracts()
                cleanup_results["saved"] = save_success
                if not save_success:
                    cleanup_results["errors"].append("Failed to save changes to contracts file")

            return cleanup_results

        except Exception as e:
            cleanup_results["errors"].append(f"UTXO cleanup failed: {e}")
            return cleanup_results

    def mark_utxo_as_spent(self, utxo_ref: str, project_name: str = None) -> bool:
        """
        Mark a specific UTXO as spent and remove it from tracking.
        Should be called when a transaction that spends the UTXO is successfully submitted.

        Args:
            utxo_ref: UTXO reference in format "tx_id:index"
            project_name: Optional project name if this is a project compilation UTXO

        Returns:
            True if UTXO was tracked and removed, False if not found
        """
        removed = False

        # Remove from used_utxos
        if utxo_ref in self.used_utxos:
            self.used_utxos.remove(utxo_ref)
            removed = True
            print(f"Removed spent UTXO from used_utxos: {utxo_ref}")

        # Remove from protocol compilation_utxo
        if self.compilation_utxo:
            compilation_ref = f"{self.compilation_utxo['tx_id']}:{self.compilation_utxo['index']}"
            if compilation_ref == utxo_ref:
                self.compilation_utxo = None
                removed = True
                print(f"Removed spent protocol compilation UTXO: {utxo_ref}")

        # Remove from project_compilation_utxos
        if project_name and project_name in self.project_compilation_utxos:
            compilation_info = self.project_compilation_utxos[project_name]
            project_utxo_ref = f"{compilation_info['tx_id']}:{compilation_info['index']}"
            if project_utxo_ref == utxo_ref:
                del self.project_compilation_utxos[project_name]
                removed = True
                print(f"Removed spent project compilation UTXO for {project_name}: {utxo_ref}")
        else:
            # If no project_name provided, check all project UTXOs
            projects_to_remove = []
            for proj_name, compilation_info in self.project_compilation_utxos.items():
                project_utxo_ref = f"{compilation_info['tx_id']}:{compilation_info['index']}"
                if project_utxo_ref == utxo_ref:
                    projects_to_remove.append(proj_name)
                    removed = True
                    print(f"Removed spent project compilation UTXO for {proj_name}: {utxo_ref}")

            for proj_name in projects_to_remove:
                del self.project_compilation_utxos[proj_name]

        # Save changes if any UTXO was removed
        if removed:
            self._save_contracts()

        return removed

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
        self, protocol_address: pc.Address, force: bool = False
    ) -> Dict[str, Any]:
        """
        Compile OpShin protocol smart contracts (protocol_nfts and protocol)

        Args:
            protocol_address: Address to get UTXOs from for protocol contract compilation
            force: Force recompilation even if contracts exist

        Returns:
            Compilation result dictionary
        """
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


            # Store compilation UTXO metadata for protocol (primary)
            self.compilation_utxo = {
                "tx_id": protocol_utxo_to_spend.input.transaction_id.payload.hex(),
                "index": protocol_utxo_to_spend.input.index,
                "amount": protocol_utxo_to_spend.output.amount.coin,
            }

            # Track used UTXOs to ensure contract uniqueness
            protocol_utxo_ref = f"{protocol_utxo_to_spend.input.transaction_id.payload.hex()}:{protocol_utxo_to_spend.input.index}"
            self.used_utxos.add(protocol_utxo_ref)

            # Create oref for protocol contracts
            protocol_oref = TxOutRef(
                id=TxId(protocol_utxo_to_spend.input.transaction_id.payload),
                idx=protocol_utxo_to_spend.input.index,
            )

            # Compile contracts (excluding authentication_nfts which needs dynamic compilation)
            compiled_contracts = {}

            # Build protocol_nfts minting policy first (protocol validator needs its policy ID)
            protocol_nfts_path = self.minting_contracts_path / "protocol_nfts.py"
            if protocol_nfts_path.exists():
                print(
                    f"Compiling protocol_nfts minting policy using UTXO: {protocol_utxo_to_spend.input.transaction_id}:{protocol_utxo_to_spend.input.index}"
                )
                protocol_nfts_contract = build(protocol_nfts_path, protocol_oref)
                compiled_contracts["protocol_nfts"] = PlutusContract(protocol_nfts_contract)

            # Build protocol validator using protocol_nfts policy ID
            protocol_path = self.spending_contracts_path / "protocol.py"
            if protocol_path.exists():
                if "protocol_nfts" not in compiled_contracts:
                    raise Exception("protocol_nfts must be compiled before protocol validator")

                protocol_nfts_policy_id = bytes.fromhex(compiled_contracts["protocol_nfts"].policy_id)
                print(
                    f"Compiling protocol contract using protocol_nfts policy ID: {compiled_contracts['protocol_nfts'].policy_id}"
                )
                protocol_contract = build(protocol_path, protocol_nfts_policy_id)
                compiled_contracts["protocol"] = PlutusContract(protocol_contract)

            if not compiled_contracts:
                return {"success": False, "error": "No contract files found to compile"}

            # Handle contract replacement based on force flag
            if not force:
                # If not forcing, merge protocol contracts with existing contracts
                for name, contract in compiled_contracts.items():
                    self.contracts[name] = contract
            else:
                # If forcing recompilation, replace only protocol contracts (preserve project contracts)
                # Remove existing protocol contracts
                existing_protocol_contracts = ["protocol", "protocol_nfts"]
                for contract_name in existing_protocol_contracts:
                    if contract_name in self.contracts:
                        del self.contracts[contract_name]

                # Add new protocol contracts
                for name, contract in compiled_contracts.items():
                    self.contracts[name] = contract

            return {
                "success": True,
                "message": f"Successfully compiled {len(compiled_contracts)} protocol contracts",
                "contracts": list(compiled_contracts.keys()),
                "saved": False,  # Not saved until deployed
                "compilation_utxo": self.compilation_utxo,
            }

        except Exception as e:
            return {"success": False, "error": f"Compilation failed: {e}"}

    def compile_project_contract_only(self, project_address: pc.Address = None) -> Dict[str, Any]:
        """
        Compile project contracts (project_nfts and project) using existing protocol contracts.

        Args:
            project_address: Address to get UTXOs from for project contract compilation

        Returns:
            Dictionary containing compilation results
        """
        try:
            # Check if protocol contracts exist
            if "protocol" not in self.contracts or "protocol_nfts" not in self.contracts:
                return {
                    "success": False,
                    "error": "Protocol contracts must be compiled first. Use option 2 'Compile Protocol Contracts' first.",
                }

            # Check if project.py exists
            project_path = self.spending_contracts_path / "project.py"
            if not project_path.exists():
                return {"success": False, "error": "Project contract file not found"}

            # Check if project_nfts.py exists
            project_nfts_path = self.minting_contracts_path / "project_nfts.py"
            if not project_nfts_path.exists():
                return {"success": False, "error": "Project NFTs minting policy file not found"}

            # Get protocol contracts from existing compilation
            protocol_contract = self.contracts["protocol"]
            protocol_nfts_contract = self.contracts["protocol_nfts"]
            # Get a UTXO for unique contract compilation (different from protocol)
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

            oref = TxOutRef(
                id=TxId(utxo_to_spend.input.transaction_id.payload), idx=utxo_to_spend.input.index
            )

            print(f"Compiling project_nfts minting policy using UTXO: {utxo_to_spend.input.transaction_id}:{utxo_to_spend.input.index}")
            print(f"Using Protocol Policy ID: {protocol_nfts_contract.policy_id}")

            # Determine project contract name (support multiple projects)
            project_name = "project"
            if project_name in self.contracts:
                # Find next available index
                index = 1
                while f"{project_name}_{index}" in self.contracts:
                    index += 1
                project_name = f"{project_name}_{index}"
                print(f"Project contract will be stored as: {project_name}")

            # Reserve compilation UTXO BEFORE any compilation to prevent conflicts
            compilation_utxo_info = {
                "tx_id": utxo_to_spend.input.transaction_id.payload.hex(),
                "index": utxo_to_spend.input.index,
                "amount": utxo_to_spend.output.amount.coin,
                "compilation_timestamp": time.time(),
            }
            self.project_compilation_utxos[project_name] = compilation_utxo_info

            # Mark this UTXO as used to ensure uniqueness for future compilations
            utxo_ref = (
                f"{utxo_to_spend.input.transaction_id.payload.hex()}:{utxo_to_spend.input.index}"
            )
            self.used_utxos.add(utxo_ref)

            # Compile project_nfts minting policy first
            protocol_nfts_policy_id_bytes = bytes.fromhex(protocol_nfts_contract.policy_id)
            project_nfts_contract = build(project_nfts_path, oref, protocol_nfts_policy_id_bytes)
            project_nfts_policy_id = PlutusContract(project_nfts_contract).policy_id

            print(f"Project NFTs policy ID: {project_nfts_policy_id}")

            # Compile project contract with policy IDs
            self._set_recursion_limit(2000)
            token_policy_id = bytes.fromhex(project_nfts_policy_id)

            print(f"Compiling project contract with:")
            print(f"  Protocol Policy ID: {protocol_contract.policy_id}")
            print(f"  Token Policy ID: {project_nfts_policy_id}")

            project_contract = build(project_path, token_policy_id)

            # Add contracts to storage
            project_nfts_name = f"{project_name}_nfts"
            self.contracts[project_nfts_name] = PlutusContract(project_nfts_contract)
            self.contracts[project_name] = PlutusContract(project_contract)

            # Save contracts to JSON file
            save_success = self._save_contracts()

            return {
                "success": True,
                "message": f"Successfully compiled project contracts '{project_nfts_name}' and '{project_name}'",
                "contracts": [project_nfts_name, project_name],
                "project_name": project_name,
                "project_nfts_name": project_nfts_name,
                "project_policy_id": PlutusContract(project_contract).policy_id,
                "project_nfts_policy_id": project_nfts_policy_id,
                "used_utxo": f"{utxo_to_spend.input.transaction_id}:{utxo_to_spend.input.index}",
                "saved": save_success,
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
        """List all available project contract names (excluding NFT minting policies, grey token contracts, and investor contracts)"""
        project_contracts = []
        for name in sorted(self.contracts.keys()):
            if (name == "project" or name.startswith("project_")) and not name.endswith(
                ("_nfts", "_grey", "_investor")
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

    def delete_grey_token_contract(self, grey_contract_name: str) -> Dict[str, Any]:
        """
        Delete only a grey token contract while preserving the associated project contract

        Args:
            grey_contract_name: Name of the grey token contract to delete (e.g., "project_1_grey")

        Returns:
            Dictionary with success status and message
        """
        if not grey_contract_name.endswith("_grey"):
            return {"success": False, "error": f"'{grey_contract_name}' is not a grey token contract"}

        if grey_contract_name not in self.contracts:
            return {"success": False, "error": f"Grey token contract '{grey_contract_name}' not found"}

        try:
            # Delete the grey token contract
            del self.contracts[grey_contract_name]

            # Save the updated contracts file
            save_success = self._save_contracts()

            message = f"Grey token contract '{grey_contract_name}' deleted successfully"
            return {
                "success": True,
                "message": message,
                "saved": save_success,
                "deleted_contracts": [grey_contract_name]
            }

        except Exception as e:
            return {"success": False, "error": f"Error deleting grey token contract: {e}"}

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

    def compile_grey_contract(self, project_name: str) -> Dict[str, Any]:
        """
        Compile grey token minting contract for a specific project.
        Grey contract requires the project NFTs minting policy ID as a compilation parameter.

        Args:
            project_name: Name of the project to compile grey contract for

        Returns:
            Dictionary containing compilation results
        """
        try:
            # Get the project contract
            project_contract = self.get_project_contract(project_name)
            if not project_contract:
                return {
                    "success": False,
                    "error": f"Project contract '{project_name}' not found. Compile the project first.",
                }

            # Get the project NFTs minting policy contract
            project_nfts_contract = self.get_project_nfts_contract(project_name)
            if not project_nfts_contract:
                return {
                    "success": False,
                    "error": f"Project NFTs contract for '{project_name}' not found. Compile the project first.",
                }

            # Check if grey.py exists
            grey_path = self.minting_contracts_path / "grey.py"
            if not grey_path.exists():
                return {"success": False, "error": "Grey contract file (grey.py) not found"}

            # Compile grey contract with project NFTs policy_id as parameter
            project_nfts_policy_id_bytes = bytes.fromhex(project_nfts_contract.policy_id)
            grey_contract = self.create_minting_contract("grey", project_nfts_policy_id_bytes)

            if not grey_contract:
                return {"success": False, "error": "Failed to compile grey contract"}

            # Store grey contract with naming convention: {project_name}_grey
            grey_contract_name = f"{project_name}_grey"
            self.contracts[grey_contract_name] = grey_contract

            # Save to disk
            saved = self.mark_contract_as_deployed([grey_contract_name])

            return {
                "success": True,
                "grey_contract_name": grey_contract_name,
                "grey_policy_id": grey_contract.policy_id,
                "project_name": project_name,
                "project_nfts_policy_id": project_nfts_contract.policy_id,
                "saved": saved,
            }

        except Exception as e:
            return {"success": False, "error": f"Grey contract compilation failed: {e}"}

    def compile_usda_contract(self) -> Dict[str, Any]:
        """
        Compile myUSDFree (USDA faucet) minting policy contract.
        This is a simple free-minting contract that doesn't require any compilation parameters.

        Returns:
            Dictionary containing compilation results
        """
        try:
            # Check if already compiled
            if self.get_contract("myUSDFree"):
                return {
                    "success": True,
                    "message": "myUSDFree contract already compiled",
                    "skipped": True,
                }

            # Check if myUSDFree.py exists
            usda_path = self.minting_contracts_path / "myUSDFree.py"
            if not usda_path.exists():
                return {"success": False, "error": "myUSDFree contract file not found"}

            # Compile myUSDFree contract (no parameters needed - free mint)
            print("Compiling myUSDFree minting policy...")
            usda_contract = build(usda_path)

            # Store contract
            self.contracts["myUSDFree"] = PlutusContract(usda_contract)

            # Save to disk
            saved = self.mark_contract_as_deployed(["myUSDFree"])

            return {
                "success": True,
                "message": "Successfully compiled myUSDFree contract",
                "contract_name": "myUSDFree",
                "policy_id": self.contracts["myUSDFree"].policy_id,
                "saved": saved,
            }

        except Exception as e:
            return {"success": False, "error": f"myUSDFree contract compilation failed: {e}"}

    def compile_investor_contract(self, project_name: str) -> Dict[str, Any]:
        """
        Compile investor spending contract for a specific project.
        Investor contract requires three compilation parameters: protocol policy ID, grey token policy ID, and grey token name.

        Args:
            project_name: Name of the project to compile investor contract for

        Returns:
            Dictionary containing compilation results
        """
        try:
            # Get the protocol NFTs contract for protocol policy ID
            protocol_nfts_contract = self.get_contract("protocol_nfts")
            if not protocol_nfts_contract:
                return {
                    "success": False,
                    "error": "Protocol NFTs contract not found. Compile protocol contracts first.",
                }

            # Get the project contract
            project_contract = self.get_project_contract(project_name)
            if not project_contract:
                return {
                    "success": False,
                    "error": f"Project contract '{project_name}' not found. Compile the project first.",
                }

            # Get the grey token contract for this project
            grey_contract = self.get_grey_token_contract(project_name)
            if not grey_contract:
                return {
                    "success": False,
                    "error": f"Grey token contract for '{project_name}' not found. Compile grey contract first (Option 4).",
                }

            # Check if investor.py exists
            investor_path = self.spending_contracts_path / "investor.py"
            if not investor_path.exists():
                return {"success": False, "error": "Investor contract file (investor.py) not found"}

            # Get grey token info from project datum
            datum_result = self.get_contract_datum(project_name)
            if not datum_result["success"]:
                return {
                    "success": False,
                    "error": f"Failed to get project datum: {datum_result.get('error', 'Unknown error')}",
                }

            # Extract grey token policy ID from datum
            grey_policy_id_hex = datum_result["datum"]["project_token"]["policy_id"]
            grey_token_name_hex = datum_result["datum"]["project_token"]["token_name"]

            # Convert to bytes
            grey_policy_id_bytes = bytes.fromhex(grey_policy_id_hex)
            grey_token_name_bytes = bytes.fromhex(grey_token_name_hex)

            # Get protocol policy ID
            protocol_policy_id_bytes = bytes.fromhex(protocol_nfts_contract.policy_id)

            print(f"Compiling investor contract with:")
            print(f"  Protocol Policy ID: {protocol_nfts_contract.policy_id}")
            print(f"  Grey Token Policy ID: {grey_policy_id_hex}")
            print(f"  Grey Token Name: {grey_token_name_hex}")

            # Set recursion limit before compilation
            self._set_recursion_limit(2000)

            # Compile investor contract with protocol_policy_id, grey_token_policy_id, and grey_token_name
            investor_contract = build(investor_path, protocol_policy_id_bytes, grey_policy_id_bytes, grey_token_name_bytes)

            # Store investor contract with naming convention: {project_name}_investor
            investor_contract_name = f"{project_name}_investor"
            self.contracts[investor_contract_name] = PlutusContract(investor_contract)

            # Save to disk
            saved = self.mark_contract_as_deployed([investor_contract_name])

            return {
                "success": True,
                "investor_contract_name": investor_contract_name,
                "investor_address": str(PlutusContract(investor_contract).testnet_addr),
                "project_name": project_name,
                "protocol_policy_id": protocol_nfts_contract.policy_id,
                "grey_policy_id": grey_policy_id_hex,
                "grey_token_name": grey_token_name_hex,
                "saved": saved,
            }

        except Exception as e:
            return {"success": False, "error": f"Investor contract compilation failed: {e}"}

    def load_contract_from_artifacts(
        self, contract_name: str, artifacts_subdir: str = "minting_policies"
    ) -> Dict[str, Any]:
        """
        Load a pre-compiled contract from the artifacts directory.
        Useful for standalone contracts that don't require dynamic compilation.

        Args:
            contract_name: Name of the contract (without file extension)
            artifacts_subdir: Subdirectory in artifacts ("minting_policies" or "validators")

        Returns:
            Dictionary containing success status and contract info
        """
        try:
            # Construct path to artifacts
            artifacts_base = pathlib.Path("./src/artifacts")
            contract_cbor_path = artifacts_base / artifacts_subdir / f"{contract_name}.cbor"

            if not contract_cbor_path.exists():
                return {
                    "success": False,
                    "error": f"Contract artifacts not found at {contract_cbor_path}. Run build script first.",
                }

            # Read CBOR file
            with open(contract_cbor_path, "rb") as f:
                cbor_bytes = f.read()

            # Create PlutusV2Script from CBOR
            script = pc.PlutusV2Script(cbor_bytes)

            # Create PlutusContract from script
            contract = PlutusContract(script)

            # Store contract
            self.contracts[contract_name] = contract

            # Save to disk
            saved = self.mark_contract_as_deployed([contract_name])

            return {
                "success": True,
                "contract_name": contract_name,
                "policy_id": contract.policy_id,
                "testnet_addr": str(contract.testnet_addr),
                "mainnet_addr": str(contract.mainnet_addr),
                "saved": saved,
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to load contract from artifacts: {e}"}

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
            is_minting_policy = name.endswith("_nfts") or name.endswith("_grey") or name == "myUSDFree"

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

    def get_contract_datum(self, contract_name: str) -> Optional[Dict[str, Any]]:
        """
        Query and decode the datum from a contract's UTXO on the blockchain

        Args:
            contract_name: Name of the contract to query (e.g., "protocol", "project", "project_1")

        Returns:
            Dictionary containing decoded datum data or None if not found/invalid
        """
        if contract_name not in self.contracts:
            return {
                "success": False,
                "error": f"Contract '{contract_name}' not found in compiled contracts"
            }

        contract = self.contracts[contract_name]

        # Skip minting policies - they don't have UTXOs with datums
        if contract_name.endswith("_nfts") or contract_name.endswith("_grey") or contract_name == "myUSDFree":
            return {
                "success": False,
                "error": f"'{contract_name}' is a minting policy and doesn't have datum data"
            }

        try:
            # Get contract address
            contract_address = (
                contract.testnet_addr
                if self.chain_context.cardano_network == pc.Network.TESTNET
                else contract.mainnet_addr
            )

            # Query UTXOs at the contract address
            try:
                utxos = self.context.utxos(contract_address)
            except Exception as api_error:
                if hasattr(api_error, "status_code") and api_error.status_code == 404:
                    return {
                        "success": False,
                        "error": f"No UTXOs found at contract address (contract never used)"
                    }
                raise

            if not utxos:
                return {
                    "success": False,
                    "error": f"No UTXOs found at contract address"
                }

            # Get the first UTXO (contracts should typically have one UTXO with the state)
            utxo = utxos[0]

            # Extract datum
            if not utxo.output.datum:
                return {
                    "success": False,
                    "error": "UTXO does not contain a datum"
                }

            # Decode datum based on contract type
            from terrasacha_contracts.validators.protocol import DatumProtocol
            from terrasacha_contracts.validators.project import DatumProject

            try:
                # Determine contract type and decode accordingly
                if contract_name == "protocol":
                    datum = DatumProtocol.from_cbor(utxo.output.datum.cbor)
                    return {
                        "success": True,
                        "contract_name": contract_name,
                        "contract_type": "protocol",
                        "datum": {
                            "project_admins": [admin.hex() for admin in datum.project_admins],
                            "protocol_fee": datum.protocol_fee,
                            "oracle_id": datum.oracle_id.hex(),
                            "projects": [proj.hex() for proj in datum.projects]
                        },
                        "utxo_ref": f"{utxo.input.transaction_id}:{utxo.input.index}",
                        "balance": utxo.output.amount.coin,
                        "balance_ada": utxo.output.amount.coin / 1_000_000
                    }
                elif contract_name.startswith("project") and not contract_name.endswith("_nfts"):
                    datum = DatumProject.from_cbor(utxo.output.datum.cbor)
                    return {
                        "success": True,
                        "contract_name": contract_name,
                        "contract_type": "project",
                        "datum": {
                            "params": {
                                "project_id": datum.params.project_id.hex(),
                                "project_metadata": datum.params.project_metadata.hex(),
                                "project_state": datum.params.project_state
                            },
                            "project_token": {
                                "policy_id": datum.project_token.policy_id.hex(),
                                "token_name": datum.project_token.token_name.hex(),
                                "total_supply": datum.project_token.total_supply
                            },
                            "stakeholders": [
                                {
                                    "stakeholder": sh.stakeholder.hex(),
                                    "pkh": sh.pkh.hex(),
                                    "participation": sh.participation,
                                    "claimed": str(sh.claimed)
                                }
                                for sh in datum.stakeholders
                            ],
                            "certifications": [
                                {
                                    "certification_date": cert.certification_date,
                                    "quantity": cert.quantity,
                                    "real_certification_date": cert.real_certification_date,
                                    "real_quantity": cert.real_quantity
                                }
                                for cert in datum.certifications
                            ]
                        },
                        "utxo_ref": f"{utxo.input.transaction_id}:{utxo.input.index}",
                        "balance": utxo.output.amount.coin,
                        "balance_ada": utxo.output.amount.coin / 1_000_000
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Unknown contract type for datum decoding: {contract_name}"
                    }

            except Exception as decode_error:
                return {
                    "success": False,
                    "error": f"Failed to decode datum: {str(decode_error)}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to query contract datum: {str(e)}"
            }

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

    def mark_contract_as_deployed(self, contract_names: List[str], cleanup_address: pc.Address = None) -> bool:
        """
        Mark contracts as deployed and save them to disk.
        Also performs UTXO cleanup to remove spent compilation UTXOs.

        Args:
            contract_names: List of contract names to mark as deployed
            cleanup_address: Optional address to clean up spent UTXOs from

        Returns:
            True if saved successfully, False otherwise
        """
        # Verify all contracts exist in memory
        for name in contract_names:
            if name not in self.contracts:
                return False

        # Clean up spent UTXOs if address provided
        if cleanup_address:
            cleanup_result = self.cleanup_spent_utxos(cleanup_address)
            if cleanup_result["total_removed"] > 0:
                print(f"Cleaned up {cleanup_result['total_removed']} spent compilation UTXOs after deployment")

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
        self, contract_name: str, delete_associated_nfts: bool = True, delete_grey_tokens: bool = True
    ) -> Dict[str, Any]:
        """
        Delete a contract if it has zero balance (no active tokens)
        For project contracts, also deletes the associated project NFTs minting policy

        Args:
            contract_name: Name of contract to check and potentially delete
            delete_associated_nfts: If True, also delete associated project NFTs minting policy
            delete_grey_tokens: If True, also delete associated grey token contracts

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

                        if delete_grey_tokens:
                            grey_contract_name = f"{contract_name}_grey"
                            if grey_contract_name in self.contracts:
                                del self.contracts[grey_contract_name]
                                deleted_contracts.append(grey_contract_name)

                    # Clean up compilation tracking for deleted project contracts
                    if contract_name == "project" or contract_name.startswith("project_"):
                        if contract_name in self.project_compilation_utxos:
                            compilation_info = self.project_compilation_utxos[contract_name]
                            utxo_ref = f"{compilation_info['tx_id']}:{compilation_info['index']}"
                            self.used_utxos.discard(utxo_ref)
                            del self.project_compilation_utxos[contract_name]

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

                    # Also delete associated NFTs and grey token minting policies if they exist
                    if delete_associated_nfts:
                        # Handle project contracts
                        if contract_name == "project" or contract_name.startswith("project_"):
                            project_nfts_name = f"{contract_name}_nfts"
                            if project_nfts_name in self.contracts:
                                del self.contracts[project_nfts_name]
                                deleted_contracts.append(project_nfts_name)

                            if delete_grey_tokens:
                                grey_contract_name = f"{contract_name}_grey"
                                if grey_contract_name in self.contracts:
                                    del self.contracts[grey_contract_name]
                                    deleted_contracts.append(grey_contract_name)

                        # Handle protocol contract
                        elif contract_name == "protocol":
                            protocol_nfts_name = "protocol_nfts"
                            if protocol_nfts_name in self.contracts:
                                del self.contracts[protocol_nfts_name]
                                deleted_contracts.append(protocol_nfts_name)

                    # Clean up compilation tracking for deleted project contracts
                    if contract_name == "project" or contract_name.startswith("project_"):
                        if contract_name in self.project_compilation_utxos:
                            compilation_info = self.project_compilation_utxos[contract_name]
                            utxo_ref = f"{compilation_info['tx_id']}:{compilation_info['index']}"
                            self.used_utxos.discard(utxo_ref)
                            del self.project_compilation_utxos[contract_name]

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

            # Also delete associated NFTs and grey token minting policies if they exist
            if delete_associated_nfts:
                # Handle project contracts
                if contract_name == "project" or contract_name.startswith("project_"):
                    project_nfts_name = f"{contract_name}_nfts"
                    if project_nfts_name in self.contracts:
                        del self.contracts[project_nfts_name]
                        deleted_contracts.append(project_nfts_name)

                    if delete_grey_tokens:
                        grey_contract_name = f"{contract_name}_grey"
                        if grey_contract_name in self.contracts:
                            del self.contracts[grey_contract_name]
                            deleted_contracts.append(grey_contract_name)

                # Handle protocol contract
                elif contract_name == "protocol":
                    protocol_nfts_name = "protocol_nfts"
                    if protocol_nfts_name in self.contracts:
                        del self.contracts[protocol_nfts_name]
                        deleted_contracts.append(protocol_nfts_name)

            # Clean up compilation tracking for deleted project contracts
            if contract_name == "project" or contract_name.startswith("project_"):
                if contract_name in self.project_compilation_utxos:
                    compilation_info = self.project_compilation_utxos[contract_name]
                    utxo_ref = f"{compilation_info['tx_id']}:{compilation_info['index']}"
                    self.used_utxos.discard(utxo_ref)
                    del self.project_compilation_utxos[contract_name]

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
