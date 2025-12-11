from fastapi import APIRouter, Security

from api.routers.api_v1.endpoints import admin, transactions, wallets
from api.routers.admin import tenants as admin_tenants
from api.utils.security import get_api_key

# NOTE: contracts endpoint disabled - requires MongoDB migration (still uses PostgreSQL)
# from api.routers.api_v1.endpoints import contracts


api_router = APIRouter()

api_router.include_router(wallets.router, prefix="/wallets", tags=["Wallets"])
api_router.include_router(
    transactions.router, prefix="/transactions", tags=["Transactions"]
)
# NOTE: contracts endpoint disabled - requires MongoDB migration
# api_router.include_router(
#     contracts.router, prefix="/contracts", tags=["Contracts"], dependencies=[Security(get_api_key)]
# )

# Tenant admin endpoints: sessions + API keys (tenant API key + CORE wallet)
api_router.include_router(
    admin.router, prefix="/admin", tags=["Tenant Admin"]
)

# Platform admin endpoints: tenant management (admin API key only)
api_router.include_router(admin_tenants.router)
