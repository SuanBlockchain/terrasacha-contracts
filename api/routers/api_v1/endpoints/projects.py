

from fastapi import APIRouter


router = APIRouter()
from api.utils.security import generate_api_key


@router.get("/generate-api-key")
async def get_new_api_key():
    api_key = generate_api_key()

    return {"api_key": api_key}