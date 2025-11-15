from fastapi import APIRouter, Security

from api.routers.api_v1.endpoints import admin, contracts, transactions, wallets
from api.utils.security import get_api_key


api_router = APIRouter()

api_router.include_router(wallets.router, prefix="/wallets", tags=["Wallets"], dependencies=[Security(get_api_key)])
api_router.include_router(
    transactions.router, prefix="/transactions", tags=["Transactions"], dependencies=[Security(get_api_key)]
)
api_router.include_router(
    contracts.router, prefix="/contracts", tags=["Contracts"], dependencies=[Security(get_api_key)]
)
api_router.include_router(
    admin.router, prefix="/admin", tags=["Admin"], dependencies=[Security(get_api_key)]
)
