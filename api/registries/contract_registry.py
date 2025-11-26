"""
Contract Registry

Central registry of available Opshin contracts for compilation.
Makes it easy to add new contracts and see what's available.
"""

from typing import TypedDict


class ContractInfo(TypedDict):
    """Contract information"""
    name: str
    file_path: str
    description: str
    requires_params: bool
    param_description: str | None


# ============================================================================
# Minting Policy Contracts
# ============================================================================

MINTING_CONTRACTS: dict[str, ContractInfo] = {
    "myUSDFree": {
        "name": "myUSDFree",
        "file_path": "minting_policies/myUSDFree.py",
        "description": "USDA faucet minting policy - free minting for testing",
        "requires_params": False,
        "param_description": None,
    },
    "project_nfts": {
        "name": "project_nfts",
        "file_path": "minting_policies/project_nfts.py",
        "description": "Project NFTs minting policy - requires UTXO reference and protocol policy ID",
        "requires_params": True,
        "param_description": "Requires: [TxOutRef, protocol_policy_id_bytes]",
    },
    "protocol_nfts": {
        "name": "protocol_nfts",
        "file_path": "minting_policies/protocol_nfts.py",
        "description": "Protocol NFTs minting policy - requires UTXO reference",
        "requires_params": True,
        "param_description": "Requires: [TxOutRef]",
    },
    "grey": {
        "name": "grey",
        "file_path": "minting_policies/grey.py",
        "description": "Grey token minting policy - requires project NFTs policy ID",
        "requires_params": True,
        "param_description": "Requires: [project_nfts_policy_id_bytes]",
    },
}


# ============================================================================
# Spending Validator Contracts
# ============================================================================

SPENDING_CONTRACTS: dict[str, ContractInfo] = {
    "investor": {
        "name": "investor",
        "file_path": "validators/investor.py",
        "description": "Investor contract - manages grey token sales",
        "requires_params": True,
        "param_description": "Requires: [protocol_policy_id_bytes, grey_policy_id_bytes, grey_token_name_bytes]",
    },
    "project": {
        "name": "project",
        "file_path": "validators/project.py",
        "description": "Project contract - manages project state and carbon credits",
        "requires_params": True,
        "param_description": "Requires: [project_nfts_policy_id_bytes]",
    },
    "protocol": {
        "name": "protocol",
        "file_path": "validators/protocol.py",
        "description": "Protocol contract - manages global protocol state",
        "requires_params": True,
        "param_description": "Requires: [protocol_nfts_policy_id_bytes]",
    },
}


# ============================================================================
# Registry Functions
# ============================================================================


def get_contract_info(contract_name: str, contract_type: str) -> ContractInfo | None:
    """
    Get contract information by name and type.

    Args:
        contract_name: Name of the contract
        contract_type: "minting" or "spending"

    Returns:
        ContractInfo or None if not found
    """
    if contract_type == "minting":
        return MINTING_CONTRACTS.get(contract_name)
    elif contract_type == "spending":
        return SPENDING_CONTRACTS.get(contract_name)
    return None


def get_contract_file_path(contract_name: str, contract_type: str) -> str | None:
    """
    Get the file path for a contract.

    Args:
        contract_name: Name of the contract
        contract_type: "minting" or "spending"

    Returns:
        File path relative to src/terrasacha_contracts/ or None if not found
    """
    info = get_contract_info(contract_name, contract_type)
    return info["file_path"] if info else None


def list_all_contracts() -> dict[str, list[ContractInfo]]:
    """
    List all available contracts grouped by type.

    Returns:
        Dictionary with "minting" and "spending" keys containing contract lists
    """
    return {
        "minting": list(MINTING_CONTRACTS.values()),
        "spending": list(SPENDING_CONTRACTS.values()),
    }


def add_minting_contract(
    name: str,
    file_path: str,
    description: str,
    requires_params: bool = False,
    param_description: str | None = None
) -> None:
    """
    Dynamically add a new minting contract to the registry.

    Args:
        name: Contract name
        file_path: Path relative to src/terrasacha_contracts/
        description: Human-readable description
        requires_params: Whether compilation requires parameters
        param_description: Description of required parameters
    """
    MINTING_CONTRACTS[name] = {
        "name": name,
        "file_path": file_path,
        "description": description,
        "requires_params": requires_params,
        "param_description": param_description,
    }


def add_spending_contract(
    name: str,
    file_path: str,
    description: str,
    requires_params: bool = False,
    param_description: str | None = None
) -> None:
    """
    Dynamically add a new spending contract to the registry.

    Args:
        name: Contract name
        file_path: Path relative to src/terrasacha_contracts/
        description: Human-readable description
        requires_params: Whether compilation requires parameters
        param_description: Description of required parameters
    """
    SPENDING_CONTRACTS[name] = {
        "name": name,
        "file_path": file_path,
        "description": description,
        "requires_params": requires_params,
        "param_description": param_description,
    }
