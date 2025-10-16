
from api.routers.api_v1.endpoints import projects, wallets
from api.utils.security import get_api_key

from fastapi import APIRouter, Security


api_router = APIRouter()

api_router.include_router(
    projects.router,
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Security(get_api_key)],
)
api_router.include_router(
    wallets.router,
    prefix="/wallets",
    tags=["Wallets"],
    dependencies=[Security(get_api_key)],
)