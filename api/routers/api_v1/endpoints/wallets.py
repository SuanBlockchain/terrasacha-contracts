from fastapi import APIRouter

from cardano_offchain.wallet import CardanoWallet


router = APIRouter()



@router.get("/get-wallet/{wallet_name}")
async def get_wallet(wallet_name: str):
    wallet = CardanoWallet.get_wallet(wallet_name)

    return {"wallet": wallet}