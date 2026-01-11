"""
Contract Registry Service

Service layer for querying contract registry with tenant-specific filtering.
Bridges static registry definitions with dynamic tenant configurations.
"""

from typing import Optional

from api.registries.contract_registry import ContractRegistry
from api.registries.contract_definitions import ContractDefinition
from api.database.models import TenantContractConfig


class ContractRegistryService:
    """
    Service for querying contract registry with tenant-specific filtering.

    Bridges the gap between static registry and tenant configuration.
    Provides efficient caching of tenant configurations.
    """

    def __init__(self, registry: ContractRegistry):
        """
        Initialize contract registry service.

        Args:
            registry: ContractRegistry instance with all contract definitions
        """
        self.registry = registry
        self._config_cache: dict[str, Optional[TenantContractConfig]] = {}

    async def get_available_contracts(
        self,
        tenant_id: str | None = None,
        contract_type: str | None = None,
        category: str | None = None,
    ) -> dict[str, list[ContractDefinition]]:
        """
        Get available contracts with optional tenant filtering.

        Args:
            tenant_id: Filter by tenant configuration (None = no tenant filtering)
            contract_type: Filter by "minting" or "spending"
            category: Filter by ContractCategory value

        Returns:
            Dictionary with "minting" and "spending" keys containing ContractDefinition lists
        """
        # Start with all contracts from registry
        all_contracts = self.registry.get_all_definitions()

        # Apply tenant filtering if tenant_id provided
        if tenant_id:
            config = await self._get_tenant_config(tenant_id)
            all_contracts = self._apply_tenant_filter(all_contracts, config)

        # Apply type filtering
        if contract_type:
            all_contracts = [c for c in all_contracts if c.contract_type == contract_type]

        # Apply category filtering
        if category:
            all_contracts = [c for c in all_contracts if c.category.value == category]

        # Group by type
        return {
            "minting": [c for c in all_contracts if c.contract_type == "minting"],
            "spending": [c for c in all_contracts if c.contract_type == "spending"]
        }

    async def validate_contract_for_tenant(
        self,
        contract_name: str,
        tenant_id: str
    ) -> tuple[bool, str | None]:
        """
        Validate if a contract is available for a tenant.

        Args:
            contract_name: Name of the contract to validate
            tenant_id: Tenant ID to validate against

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if contract is available, False otherwise
            - error_message: Error description if not valid, None if valid
        """
        # Check if contract exists in registry
        definition = self.registry.get_definition(contract_name)
        if not definition:
            return False, f"Contract '{contract_name}' not found in registry"

        # Check tenant configuration
        config = await self._get_tenant_config(tenant_id)
        if not self._is_contract_enabled(definition, config):
            return False, f"Contract '{contract_name}' is not available for your tenant"

        return True, None

    async def is_custom_contract_allowed(self, tenant_id: str) -> bool:
        """
        Check if custom contract compilation is allowed for a tenant.

        Args:
            tenant_id: Tenant ID to check

        Returns:
            True if custom contracts are allowed, False otherwise
        """
        config = await self._get_tenant_config(tenant_id)
        if not config:
            return True  # No config = allow custom contracts (default)
        return config.allow_custom_contracts

    def clear_cache(self, tenant_id: str | None = None):
        """
        Clear configuration cache.

        Args:
            tenant_id: Clear cache for specific tenant, or None to clear all
        """
        if tenant_id:
            self._config_cache.pop(tenant_id, None)
        else:
            self._config_cache.clear()

    async def _get_tenant_config(self, tenant_id: str) -> TenantContractConfig | None:
        """
        Get tenant config from database (with caching).

        Args:
            tenant_id: Tenant ID to get configuration for

        Returns:
            TenantContractConfig or None if no configuration exists
        """
        # Check cache first
        if tenant_id in self._config_cache:
            return self._config_cache[tenant_id]

        # Query database
        config = await TenantContractConfig.find_one(
            TenantContractConfig.tenant_id == tenant_id
        )

        # Cache result (including None)
        self._config_cache[tenant_id] = config
        return config

    def _apply_tenant_filter(
        self,
        contracts: list[ContractDefinition],
        config: TenantContractConfig | None
    ) -> list[ContractDefinition]:
        """
        Apply tenant configuration filter to contract list.

        Args:
            contracts: List of contracts to filter
            config: Tenant configuration (None = no filtering)

        Returns:
            Filtered list of contracts
        """
        if not config:
            return contracts  # No config = all contracts available

        filtered = []
        for contract in contracts:
            if self._is_contract_enabled(contract, config):
                filtered.append(contract)

        return filtered

    def _is_contract_enabled(
        self,
        contract: ContractDefinition,
        config: TenantContractConfig | None
    ) -> bool:
        """
        Check if a specific contract is enabled for tenant.

        Filtering priority (highest to lowest):
        1. disabled_contracts - explicitly disabled contracts
        2. disabled_categories - explicitly disabled categories
        3. enabled_contracts - if set, only these contracts allowed
        4. enabled_categories - if set, only contracts in these categories allowed
        5. Default: all contracts enabled

        Args:
            contract: Contract definition to check
            config: Tenant configuration (None = all enabled)

        Returns:
            True if contract is enabled, False otherwise
        """
        if not config:
            return True  # No config = all enabled

        contract_name = contract.name.value
        category = contract.category.value

        # Priority 1: Check disabled contracts (highest priority)
        if contract_name in config.disabled_contracts:
            return False

        # Priority 2: Check disabled categories
        if category in config.disabled_categories:
            return False

        # Priority 3: Check enabled contracts (if set, only these are allowed)
        if config.enabled_contracts:
            return contract_name in config.enabled_contracts

        # Priority 4: Check enabled categories (if set, only these are allowed)
        if config.enabled_categories:
            return category in config.enabled_categories

        # Default: enabled
        return True
