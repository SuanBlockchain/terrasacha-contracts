"""
API Registries Package

Contains registry modules for contracts and other resources.
"""

# Legacy API (backward compatible)
from api.registries.contract_registry import (
    list_all_contracts,
    get_contract_info,
    get_contract_file_path,
    ContractRegistry,
    _registry,
)

# New structured definitions
from api.registries.contract_definitions import (
    ContractName,
    ContractCategory,
    ContractDefinition,
    ParameterSpec,
    CONTRACTS,
)

__all__ = [
    # Legacy functions (backward compatible)
    "list_all_contracts",
    "get_contract_info",
    "get_contract_file_path",
    # New registry API
    "ContractRegistry",
    "_registry",
    # Definitions
    "ContractName",
    "ContractCategory",
    "ContractDefinition",
    "ParameterSpec",
    "CONTRACTS",
]
