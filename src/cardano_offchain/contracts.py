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

from .chain_context import CardanoChainContext


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

        # Load existing contracts
        self._load_contracts()

    def _get_contracts_file_path(self) -> pathlib.Path:
        """Get the path for contracts storage file"""
        return pathlib.Path(f"contracts_{self.network}.json")

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
            "contracts": {},
        }

        for name, contract in self.contracts.items():
            contracts_data["contracts"][name] = {
                "policy_id": contract.policy_id,
                "testnet_addr": str(contract.testnet_addr),
                "mainnet_addr": str(contract.mainnet_addr),
                "cbor_hex": contract.cbor.hex(),
            }

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

            # Reconstruct PlutusContract objects from saved data
            saved_contracts = contracts_data.get("contracts", {})
            self.contracts = {}

            for name, contract_data in saved_contracts.items():
                try:
                    # Convert hex string back to bytes
                    cbor_bytes = bytes.fromhex(contract_data["cbor_hex"])

                    # Create PlutusV2Script from CBOR data
                    script = pc.PlutusV2Script(cbor_bytes)

                    # Create PlutusContract from the script
                    plutus_contract = PlutusContract(script)

                    # Validate addresses and policy ID match
                    if (
                        str(plutus_contract.testnet_addr) != contract_data["testnet_addr"]
                        or str(plutus_contract.mainnet_addr) != contract_data["mainnet_addr"]
                        or plutus_contract.policy_id != contract_data["policy_id"]
                    ):
                        continue

                    self.contracts[name] = plutus_contract

                except Exception:
                    continue

            return len(self.contracts) > 0

        except Exception:
            return False

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

    def compile_contracts(self, address: pc.Address, force: bool = False) -> Dict[str, Any]:
        """
        Compile OpShin smart contracts

        Args:
            address: Address to get UTXOs from for compilation
            force: Force recompilation even if contracts exist

        Returns:
            Compilation result dictionary
        """
        # Check if we need to compile
        if (
            not force
            and self.contracts
            and self.compilation_utxo
            and self._is_compilation_utxo_available(address)
        ):
            return {
                "success": True,
                "message": "Contracts already compiled and UTXO available",
                "skipped": True,
            }

        try:
            # Find suitable UTXO for compilation
            utxos = self.context.utxos(address)
            utxo_to_spend = None
            for utxo in utxos:
                if utxo.output.amount.coin > 3000000:
                    utxo_to_spend = utxo
                    break

            if not utxo_to_spend:
                return {
                    "success": False,
                    "error": "No suitable UTXO found for compilation (need >3 ADA)",
                }

            # Store compilation UTXO metadata
            self.compilation_utxo = {
                "tx_id": utxo_to_spend.input.transaction_id.payload.hex(),
                "index": utxo_to_spend.input.index,
                "amount": utxo_to_spend.output.amount.coin,
            }

            oref = TxOutRef(
                id=TxId(utxo_to_spend.input.transaction_id.payload), idx=utxo_to_spend.input.index
            )

            # Compile contracts (excluding authentication_nfts which needs dynamic compilation)
            compiled_contracts = {}

            # Build protocol validator
            protocol_path = self.spending_contracts_path / "protocol.py"
            if protocol_path.exists():
                protocol_contract = build(protocol_path, oref)
                compiled_contracts["protocol"] = PlutusContract(protocol_contract)

            # Build project validator (requires protocol policy ID parameter)
            project_path = self.spending_contracts_path / "project.py"
            if project_path.exists():
                protocol_policy_id = bytes.fromhex(PlutusContract(protocol_contract).policy_id)
                print(
                    "Using the following Protocol Policy ID to compile the project contract:",
                    compiled_contracts["protocol"].policy_id,
                )
                if protocol_policy_id:
                    self._set_recursion_limit(2000)
                    project_contract = build(project_path, protocol_policy_id)
                    compiled_contracts["project"] = PlutusContract(project_contract)

            if not compiled_contracts:
                return {"success": False, "error": "No contract files found to compile"}

            self.contracts = compiled_contracts

            # Save contracts to disk
            save_success = self._save_contracts()

            return {
                "success": True,
                "message": f"Successfully compiled {len(compiled_contracts)} contracts",
                "contracts": list(compiled_contracts.keys()),
                "saved": save_success,
                "compilation_utxo": self.compilation_utxo,
            }

        except Exception as e:
            return {"success": False, "error": f"Compilation failed: {e}"}

    def get_contract(self, name: str) -> Optional[PlutusContract]:
        """
        Get compiled contract by name

        Args:
            name: Contract name

        Returns:
            PlutusContract instance or None if not found
        """
        return self.contracts.get(name)

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

            # Check balance
            try:
                utxos = self.api.address_utxos(str(contract_address))
                balance = sum(
                    int(utxo.amount[0].quantity)
                    for utxo in utxos
                    if utxo.amount[0].unit == "lovelace"
                )
            except:
                balance = 0

            contracts_info[name] = {
                "policy_id": contract.policy_id,
                "address": str(contract_address),
                "balance": balance,
                "balance_ada": balance / 1_000_000,
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

    def create_minting_contract(self, utxo_ref: TxOutRef) -> Optional[PlutusContract]:
        """
        Dynamically compile the authentication_nfts minting policy with a specific UTXO reference

        Args:
            utxo_ref: Transaction output reference to use for compilation

        Returns:
            PlutusContract instance or None if compilation failed
        """
        try:
            auth_nfts_path = self.minting_contracts_path / "authentication_nfts.py"
            if not auth_nfts_path.exists():
                return None

            # Compile the authentication_nfts contract with the provided UTXO reference
            auth_contract = build(auth_nfts_path, utxo_ref)
            return PlutusContract(auth_contract)

        except Exception:
            return None
