"""
Contract Registry

Enhanced contract registry with structured definitions and type safety.
Provides backward-compatible API while using dataclasses and enums internally.
"""

from typing import TypedDict

from api.registries.contract_definitions import (
    CONTRACTS,
    ContractDefinition,
    ContractName,
    ContractCategory,
    ParameterSpec
)


class ContractInfo(TypedDict):
    """Contract information (legacy format for backward compatibility)"""
    name: str
    file_path: str
    description: str
    requires_params: bool
    param_description: str | None


class ContractRegistry:
    """
    Enhanced registry with structured queries.

    Provides type-safe access to contract definitions with support
    for filtering by name, type, category, and tags.
    """

    def __init__(self, contracts: list[ContractDefinition] = CONTRACTS):
        """
        Initialize registry with contract definitions.

        Args:
            contracts: List of ContractDefinition instances
        """
        self._contracts = {c.name.value: c for c in contracts}

    def get_definition(self, name: str) -> ContractDefinition | None:
        """
        Get contract definition by name.

        Args:
            name: Contract name (string value from ContractName enum)

        Returns:
            ContractDefinition or None if not found
        """
        return self._contracts.get(name)

    def get_all_definitions(self) -> list[ContractDefinition]:
        """
        Get all contract definitions.

        Returns:
            List of all ContractDefinition instances
        """
        return list(self._contracts.values())

    def get_by_type(self, contract_type: str) -> list[ContractDefinition]:
        """
        Get contracts by type.

        Args:
            contract_type: "minting" or "spending"

        Returns:
            List of ContractDefinition instances of the specified type
        """
        return [c for c in self._contracts.values() if c.contract_type == contract_type]

    def get_by_category(self, category: str) -> list[ContractDefinition]:
        """
        Get contracts by category.

        Args:
            category: Category name (string value from ContractCategory enum)

        Returns:
            List of ContractDefinition instances in the specified category
        """
        return [c for c in self._contracts.values() if c.category.value == category]

    def get_by_tag(self, tag: str) -> list[ContractDefinition]:
        """
        Get contracts by tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of ContractDefinition instances with the specified tag
        """
        return [c for c in self._contracts.values() if tag in c.tags]


# ============================================================================
# Global Registry Instance
# ============================================================================

_registry = ContractRegistry()


# ============================================================================
# Backward-Compatible Functions
# ============================================================================
# These functions maintain the old API for existing code


def get_contract_info(contract_name: str, contract_type: str) -> ContractInfo | None:
    """
    Get contract information by name and type (legacy format).

    Args:
        contract_name: Name of the contract
        contract_type: "minting" or "spending"

    Returns:
        ContractInfo dict or None if not found
    """
    definition = _registry.get_definition(contract_name)

    if not definition or definition.contract_type != contract_type:
        return None

    # Convert parameters to legacy format
    param_description = None
    if definition.parameters:
        param_description = "Requires: [" + ", ".join(p.name for p in definition.parameters) + "]"

    return {
        "name": definition.name.value,
        "file_path": definition.file_path,
        "description": definition.description,
        "requires_params": definition.requires_params,
        "param_description": param_description,
    }


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
    List all available contracts grouped by type (legacy format).

    Returns:
        Dictionary with "minting" and "spending" keys containing contract lists
    """
    minting_definitions = _registry.get_by_type("minting")
    spending_definitions = _registry.get_by_type("spending")

    return {
        "minting": [
            get_contract_info(c.name.value, "minting")
            for c in minting_definitions
        ],
        "spending": [
            get_contract_info(c.name.value, "spending")
            for c in spending_definitions
        ],
    }


# Note: add_minting_contract and add_spending_contract functions have been
# removed as they were never used and are not needed with the new structured approach.
# Contracts should be added to contract_definitions.py instead.
