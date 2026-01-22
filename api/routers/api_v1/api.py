from fastapi import APIRouter, Security

from api.routers.api_v1.endpoints import admin, assets, contracts, transactions, wallets
from api.routers.admin import tenants as admin_tenants, tenant_contracts
from api.utils.security import get_api_key


api_router = APIRouter()

api_router.include_router(wallets.router, prefix="/wallets", tags=["Wallets"])
api_router.include_router(
    transactions.router, prefix="/transactions", tags=["Transactions"]
)
api_router.include_router(assets.router, prefix="/assets", tags=["Assets"])
api_router.include_router(
    contracts.router, prefix="/contracts", tags=["Contracts"]
)

# Tenant admin endpoints: sessions + API keys (tenant API key + CORE wallet)
api_router.include_router(
    admin.router, prefix="/admin", tags=["Tenant Admin"]
)

# Platform admin endpoints: tenant management (admin API key only)
api_router.include_router(admin_tenants.router)

# Platform admin endpoints: tenant contract configuration (admin API key only)
api_router.include_router(tenant_contracts.router)
