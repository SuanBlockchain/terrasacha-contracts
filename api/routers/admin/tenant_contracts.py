"""
Admin Endpoints for Tenant Contract Configuration

Allows administrators to configure which contracts are available to each tenant.
Provides granular control over contract availability via contract names or categories.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from api.database.models import Tenant, TenantContractConfig
from api.services.contract_registry_service import ContractRegistryService
from api.registries.contract_registry import _registry

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


# ============================================================================
# Request/Response Schemas
# ============================================================================


class TenantContractConfigRequest(BaseModel):
    """Request to create or update tenant contract configuration"""

    enabled_contracts: list[str] = Field(
        default=[],
        description="List of contract names to enable (if set, only these contracts available)"
    )
    disabled_contracts: list[str] = Field(
        default=[],
        description="List of contract names to disable"
    )
    enabled_categories: list[str] = Field(
        default=[],
        description="List of categories to enable (if set, only contracts in these categories available)"
    )
    disabled_categories: list[str] = Field(
        default=[],
        description="List of categories to disable"
    )
    allow_custom_contracts: bool = Field(
        default=True,
        description="Allow compilation from custom source code"
    )
    notes: str | None = Field(
        None,
        description="Optional notes about this configuration"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "enabled_categories": ["core_protocol", "project_management"],
                "disabled_contracts": ["myUSDFree"],
                "allow_custom_contracts": False,
                "notes": "Production tenant - no test contracts"
            }
        }


class TenantContractConfigResponse(BaseModel):
    """Response with tenant contract configuration"""

    success: bool = Field(default=True)
    tenant_id: str
    config: dict | None = None
    effective_contracts: list[str] | None = Field(
        None,
        description="List of contract names that are enabled for this tenant"
    )
    message: str | None = None


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/{tenant_id}/contracts/config",
    response_model=TenantContractConfigResponse,
    summary="Create or update tenant contract configuration (Admin only)",
    description="Configure which contracts are available to a specific tenant.",
)
async def create_tenant_contract_config(
    tenant_id: str = Path(..., description="Tenant ID to configure"),
    config_request: TenantContractConfigRequest = None,
    # TODO: Add admin auth dependency here
) -> TenantContractConfigResponse:
    """
    Create or update tenant contract configuration (admin only).

    Allows administrators to control which contracts are available to each tenant:
    - **enabled_contracts**: If set, only these specific contracts are available
    - **disabled_contracts**: Explicitly disable specific contracts
    - **enabled_categories**: If set, only contracts in these categories are available
    - **disabled_categories**: Explicitly disable entire categories
    - **allow_custom_contracts**: Control whether custom source code compilation is allowed

    **Filtering Priority** (highest to lowest):
    1. disabled_contracts - explicitly disabled contracts
    2. disabled_categories - explicitly disabled categories
    3. enabled_contracts - if set, only these contracts allowed
    4. enabled_categories - if set, only contracts in these categories allowed
    5. Default: all contracts enabled

    **Example:**
    ```
    POST /api/admin/tenants/acme_corp/contracts/config
    {
      "enabled_categories": ["core_protocol", "project_management"],
      "disabled_contracts": ["myUSDFree"],
      "allow_custom_contracts": false
    }
    ```
    """
    # Verify tenant exists
    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    # Check if config already exists
    existing_config = await TenantContractConfig.find_one(
        TenantContractConfig.tenant_id == tenant_id
    )

    if existing_config:
        # Update existing
        existing_config.enabled_contracts = config_request.enabled_contracts
        existing_config.disabled_contracts = config_request.disabled_contracts
        existing_config.enabled_categories = config_request.enabled_categories
        existing_config.disabled_categories = config_request.disabled_categories
        existing_config.allow_custom_contracts = config_request.allow_custom_contracts
        existing_config.notes = config_request.notes
        existing_config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await existing_config.save()
        config = existing_config
    else:
        # Create new
        config = TenantContractConfig(
            tenant_id=tenant_id,
            **config_request.model_dump()
        )
        await config.insert()

    # Calculate effective contracts for this tenant
    registry_service = ContractRegistryService(_registry)
    contracts_dict = await registry_service.get_available_contracts(tenant_id=tenant_id)
    effective_contracts = [
        c.name.value
        for contract_list in [contracts_dict["minting"], contracts_dict["spending"]]
        for c in contract_list
    ]

    return TenantContractConfigResponse(
        success=True,
        tenant_id=tenant_id,
        config=config.model_dump(),
        effective_contracts=effective_contracts,
        message=f"Contract configuration {'updated' if existing_config else 'created'} for tenant '{tenant_id}'"
    )


@router.get(
    "/{tenant_id}/contracts/config",
    response_model=TenantContractConfigResponse,
    summary="Get tenant contract configuration (Admin only)",
    description="Retrieve the contract configuration for a specific tenant.",
)
async def get_tenant_contract_config(
    tenant_id: str = Path(..., description="Tenant ID to query"),
    # TODO: Add admin auth dependency here
) -> TenantContractConfigResponse:
    """
    Get tenant contract configuration (admin only).

    Returns the current contract configuration for a tenant, or indicates
    if no configuration exists (meaning all contracts are available).

    **Example:**
    ```
    GET /api/admin/tenants/acme_corp/contracts/config
    ```
    """
    # Verify tenant exists
    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    config = await TenantContractConfig.find_one(
        TenantContractConfig.tenant_id == tenant_id
    )

    if not config:
        # Calculate effective contracts (all contracts since no config)
        registry_service = ContractRegistryService(_registry)
        contracts_dict = await registry_service.get_available_contracts(tenant_id=None)  # None = all
        effective_contracts = [
            c.name.value
            for contract_list in [contracts_dict["minting"], contracts_dict["spending"]]
            for c in contract_list
        ]

        return TenantContractConfigResponse(
            success=True,
            tenant_id=tenant_id,
            config=None,
            effective_contracts=effective_contracts,
            message="No configuration found - all contracts available (default)"
        )

    # Calculate effective contracts for this tenant
    registry_service = ContractRegistryService(_registry)
    contracts_dict = await registry_service.get_available_contracts(tenant_id=tenant_id)
    effective_contracts = [
        c.name.value
        for contract_list in [contracts_dict["minting"], contracts_dict["spending"]]
        for c in contract_list
    ]

    return TenantContractConfigResponse(
        success=True,
        tenant_id=tenant_id,
        config=config.model_dump(),
        effective_contracts=effective_contracts
    )


@router.delete(
    "/{tenant_id}/contracts/config",
    response_model=TenantContractConfigResponse,
    summary="Delete tenant contract configuration (Admin only)",
    description="Delete tenant contract configuration and reset to defaults (all contracts available).",
)
async def delete_tenant_contract_config(
    tenant_id: str = Path(..., description="Tenant ID to reset"),
    # TODO: Add admin auth dependency here
) -> TenantContractConfigResponse:
    """
    Delete tenant contract configuration and reset to defaults (admin only).

    Removes any contract restrictions for the tenant, making all contracts available.

    **Example:**
    ```
    DELETE /api/admin/tenants/acme_corp/contracts/config
    ```
    """
    # Verify tenant exists
    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    config = await TenantContractConfig.find_one(
        TenantContractConfig.tenant_id == tenant_id
    )

    if not config:
        return TenantContractConfigResponse(
            success=True,
            tenant_id=tenant_id,
            message="No configuration found - already using defaults (all contracts available)"
        )

    await config.delete()

    # Clear cache for this tenant
    registry_service = ContractRegistryService(_registry)
    registry_service.clear_cache(tenant_id)

    return TenantContractConfigResponse(
        success=True,
        tenant_id=tenant_id,
        message=f"Configuration deleted for tenant '{tenant_id}' - reset to defaults (all contracts available)"
    )
