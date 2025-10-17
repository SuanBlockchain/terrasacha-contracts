"""
Wallet Endpoints

FastAPI endpoints for wallet management operations.
Provides wallet information, balance checking, address generation, and switching.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.schemas.wallet import (
    DerivedAddressInfo,
    ErrorResponse,
    GenerateAddressesRequest,
    GenerateAddressesResponse,
    SwitchWalletRequest,
    SwitchWalletResponse,
    WalletAddressInfo,
    WalletBalanceInfo,
    WalletBalanceResponse,
    WalletBalances,
    WalletExportData,
    WalletExportResponse,
    WalletInfoResponse,
    WalletListItem,
    WalletListResponse,
)
from cardano_offchain.chain_context import CardanoChainContext
from cardano_offchain.wallet import WalletManager


router = APIRouter()

# Global state for wallet management
_wallet_manager: WalletManager | None = None
_chain_context: CardanoChainContext | None = None


# ============================================================================
# Dependencies
# ============================================================================


def get_wallet_manager() -> WalletManager:
    """Get or initialize the wallet manager"""
    global _wallet_manager
    if _wallet_manager is None:
        network = os.getenv("network", "testnet")
        _wallet_manager = WalletManager.from_environment(network)
        if not _wallet_manager.get_wallet_names():
            raise HTTPException(
                status_code=500,
                detail="No wallets configured. Set wallet_mnemonic or wallet_mnemonic_<role> environment variables",
            )
    return _wallet_manager


def get_chain_context() -> CardanoChainContext:
    """Get or initialize the chain context"""
    global _chain_context
    if _chain_context is None:
        network = os.getenv("network", "testnet")
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        if not blockfrost_api_key:
            raise HTTPException(status_code=500, detail="Missing blockfrost_api_key environment variable")
        _chain_context = CardanoChainContext(network, blockfrost_api_key)
    return _chain_context


# ============================================================================
# Wallet List & Info Endpoints
# ============================================================================


@router.get(
    "/",
    response_model=WalletListResponse,
    summary="List all wallets",
    description="Get a list of all configured wallets with basic information",
)
async def list_wallets(wallet_manager: WalletManager = Depends(get_wallet_manager)) -> WalletListResponse:
    """
    List all configured wallets.

    Returns wallet names, addresses, and indicates which is the default/active wallet.
    """
    try:
        wallet_names = wallet_manager.get_wallet_names()
        default_wallet_name = wallet_manager.get_default_wallet_name()

        wallets = []
        for name in wallet_names:
            wallet = wallet_manager.get_wallet(name)
            if wallet:
                wallets.append(
                    WalletListItem(
                        name=name,
                        network=wallet.network,
                        enterprise_address=str(wallet.enterprise_address),
                        is_default=(name == default_wallet_name),
                    )
                )

        return WalletListResponse(wallets=wallets, total=len(wallets), default_wallet=default_wallet_name)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list wallets: {str(e)}")


@router.get(
    "/{wallet_name}",
    response_model=WalletInfoResponse,
    summary="Get wallet details",
    description="Get detailed information about a specific wallet including addresses",
    responses={404: {"model": ErrorResponse, "description": "Wallet not found"}},
)
async def get_wallet_info(
    wallet_name: str = Path(..., description="Name of the wallet to retrieve"),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
) -> WalletInfoResponse:
    """
    Get detailed information about a specific wallet.

    Returns:
    - Main addresses (enterprise and staking)
    - Derived addresses (if any have been generated)
    - Network type
    - Whether this is the default wallet
    """
    try:
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        default_wallet_name = wallet_manager.get_default_wallet_name()

        # Get wallet info
        wallet_info = wallet.get_wallet_info()

        # Convert to response format
        main_addresses = WalletAddressInfo(
            enterprise=wallet_info["main_addresses"]["enterprise"], staking=wallet_info["main_addresses"]["staking"]
        )

        derived_addresses = [
            DerivedAddressInfo(
                index=addr["index"],
                path=addr["path"],
                enterprise_address=addr["enterprise_address"],
                staking_address=addr["staking_address"],
            )
            for addr in wallet_info["derived_addresses"]
        ]

        return WalletInfoResponse(
            name=wallet_name,
            network=wallet_info["network"],
            main_addresses=main_addresses,
            derived_addresses=derived_addresses,
            is_default=(wallet_name == default_wallet_name),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get wallet info: {str(e)}")


# ============================================================================
# Wallet Operations Endpoints
# ============================================================================


@router.post(
    "/switch",
    response_model=SwitchWalletResponse,
    summary="Switch active wallet",
    description="Change the currently active/default wallet",
    responses={404: {"model": ErrorResponse, "description": "Wallet not found"}},
)
async def switch_wallet(
    request: SwitchWalletRequest, wallet_manager: WalletManager = Depends(get_wallet_manager)
) -> SwitchWalletResponse:
    """
    Switch the active/default wallet.

    This changes which wallet is used by default for subsequent operations.
    """
    try:
        if request.wallet_name not in wallet_manager.get_wallet_names():
            raise HTTPException(status_code=404, detail=f"Wallet '{request.wallet_name}' not found")

        success = wallet_manager.set_default_wallet(request.wallet_name)

        if success:
            return SwitchWalletResponse(
                success=True,
                message=f"Successfully switched to wallet '{request.wallet_name}'",
                active_wallet=request.wallet_name,
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to switch wallet")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to switch wallet: {str(e)}")


@router.post(
    "/{wallet_name}/addresses/generate",
    response_model=GenerateAddressesResponse,
    summary="Generate new addresses",
    description="Generate new derived addresses for a wallet",
    responses={404: {"model": ErrorResponse, "description": "Wallet not found"}},
)
async def generate_addresses(
    wallet_name: str = Path(..., description="Name of the wallet"),
    request: GenerateAddressesRequest = GenerateAddressesRequest(),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
) -> GenerateAddressesResponse:
    """
    Generate new derived addresses for a wallet.

    Creates new payment addresses following the BIP44 derivation standard.
    Each address has both an enterprise version (payment only) and a staking version.
    """
    try:
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        # Generate addresses
        generated = wallet.generate_addresses(request.count)

        # Convert to response format
        addresses = [
            DerivedAddressInfo(
                index=addr["index"],
                path=addr["derivation_path"],
                enterprise_address=str(addr["enterprise_address"]),
                staking_address=str(addr["staking_address"]),
            )
            for addr in generated
        ]

        return GenerateAddressesResponse(wallet_name=wallet_name, addresses=addresses, count=len(addresses))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate addresses: {str(e)}")


# ============================================================================
# Balance Endpoints
# ============================================================================


@router.get(
    "/{wallet_name}/balances",
    response_model=WalletBalanceResponse,
    summary="Check wallet balances",
    description="Get balance information for a wallet including main and derived addresses",
    responses={404: {"model": ErrorResponse, "description": "Wallet not found"}},
)
async def check_wallet_balances(
    wallet_name: str = Path(..., description="Name of the wallet"),
    limit_addresses: int = Query(5, ge=1, le=20, description="Number of derived addresses to check (1-20)"),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> WalletBalanceResponse:
    """
    Check balances for a wallet.

    Queries the blockchain for current balances across:
    - Main enterprise address
    - Main staking address
    - Derived addresses (up to specified limit)

    Returns total balance across all addresses.
    """
    try:
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        # Get API for balance checking
        api = chain_context.get_api()

        # Check balances
        balance_data = wallet.check_balances(api, limit_addresses=limit_addresses)

        # Convert to response format
        main_addresses_balance = {
            "enterprise": WalletBalanceInfo(
                address=balance_data["main_addresses"]["enterprise"]["address"],
                balance_lovelace=balance_data["main_addresses"]["enterprise"]["balance"],
                balance_ada=balance_data["main_addresses"]["enterprise"]["balance"] / 1_000_000,
            ),
            "staking": WalletBalanceInfo(
                address=balance_data["main_addresses"]["staking"]["address"],
                balance_lovelace=balance_data["main_addresses"]["staking"].get("balance", 0),
                balance_ada=balance_data["main_addresses"]["staking"].get("balance", 0) / 1_000_000,
            ),
        }

        derived_addresses_balance = [
            WalletBalanceInfo(
                address=addr["address"], balance_lovelace=addr["balance"], balance_ada=addr["balance"] / 1_000_000
            )
            for addr in balance_data["derived_addresses"]
        ]

        balances = WalletBalances(
            main_addresses=main_addresses_balance,
            derived_addresses=derived_addresses_balance,
            total_balance_lovelace=balance_data["total_balance"],
            total_balance_ada=balance_data["total_balance"] / 1_000_000,
        )

        return WalletBalanceResponse(wallet_name=wallet_name, balances=balances, checked_at=datetime.now(timezone.utc))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check balances: {str(e)}")


# ============================================================================
# Export Endpoint
# ============================================================================


@router.get(
    "/export",
    response_model=WalletExportResponse,
    summary="Export wallet data",
    description="Export all wallet information to JSON format",
)
async def export_wallets(wallet_manager: WalletManager = Depends(get_wallet_manager)) -> WalletExportResponse:
    """
    Export all wallet data.

    Returns complete wallet information for all configured wallets,
    suitable for backup or external use.

    Does NOT include sensitive information like mnemonics or private keys.
    """
    try:
        wallet_names = wallet_manager.get_wallet_names()
        wallet_data_list = []

        for name in wallet_names:
            wallet = wallet_manager.get_wallet(name)
            if wallet:
                wallet_info = wallet.get_wallet_info()

                main_addresses = WalletAddressInfo(
                    enterprise=wallet_info["main_addresses"]["enterprise"],
                    staking=wallet_info["main_addresses"]["staking"],
                )

                derived_addresses = [
                    DerivedAddressInfo(
                        index=addr["index"],
                        path=addr["path"],
                        enterprise_address=addr["enterprise_address"],
                        staking_address=addr["staking_address"],
                    )
                    for addr in wallet_info["derived_addresses"]
                ]

                wallet_data_list.append(
                    WalletExportData(
                        name=name,
                        network=wallet_info["network"],
                        addresses=main_addresses,
                        derived_addresses=derived_addresses,
                        created_at=None,  # TODO: Get from database when integrated
                    )
                )

        return WalletExportResponse(
            export_timestamp=datetime.now(timezone.utc), wallets=wallet_data_list, total_wallets=len(wallet_data_list)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export wallets: {str(e)}")
