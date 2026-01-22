"""
Asset Endpoints

FastAPI endpoints for Cardano native asset information.
Provides asset details and policy-based asset queries via Blockfrost API.
"""

import logging

from blockfrost import ApiError
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.dependencies.auth import WalletAuthContext, get_wallet_from_token
from api.dependencies.chain_context import get_chain_context
from api.schemas.asset import (
    AssetDetailResponse,
    AssetErrorResponse,
    AssetMetadata,
    PolicyAssetDetailItem,
    PolicyAssetItem,
    PolicyAssetsDetailResponse,
    PolicyAssetsResponse,
)
from cardano_offchain.chain_context import CardanoChainContext


logger = logging.getLogger(__name__)

router = APIRouter()


def _decode_asset_name(hex_name: str) -> str | None:
    """Attempt to decode hex asset name to UTF-8 string"""
    try:
        if not hex_name:
            return None
        return bytes.fromhex(hex_name).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _parse_asset_metadata(raw_metadata: dict | None) -> AssetMetadata | None:
    """Parse raw metadata into structured format"""
    if not raw_metadata:
        return None

    return AssetMetadata(
        name=raw_metadata.get("name"),
        description=raw_metadata.get("description"),
        ticker=raw_metadata.get("ticker"),
        url=raw_metadata.get("url"),
        logo=raw_metadata.get("logo"),
        decimals=raw_metadata.get("decimals"),
        raw=raw_metadata,
    )


@router.get(
    "/{asset_id}",
    response_model=AssetDetailResponse,
    summary="Get asset details",
    description="Get detailed information about a specific Cardano native asset by asset ID (policy_id + hex asset name).",
    responses={
        401: {"model": AssetErrorResponse, "description": "Authentication required"},
        404: {"model": AssetErrorResponse, "description": "Asset not found"},
        500: {"model": AssetErrorResponse, "description": "Failed to query asset"},
    },
)
async def get_asset_detail(
    asset_id: str = Path(
        ...,
        description="Asset ID: concatenation of policy_id and hex-encoded asset name",
        min_length=56,
    ),
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> AssetDetailResponse:
    """
    Get detailed information about a specific Cardano native asset.

    The asset ID is the concatenation of the policy ID (56 hex characters)
    and the hex-encoded asset name.

    **Returns:**
    - Asset identification (policy_id, asset_name, fingerprint)
    - Supply information (quantity, mint/burn count)
    - Metadata (on-chain CIP-25/CIP-68 metadata if available)
    - First mint transaction hash

    **Authentication required:** Bearer token from wallet unlock.
    """
    try:
        api = chain_context.get_api()

        try:
            asset_info = api.asset(asset_id, return_type="json")
        except ApiError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise HTTPException(
                    status_code=404, detail=f"Asset not found: {asset_id}"
                )
            raise HTTPException(
                status_code=500, detail=f"Blockfrost API error: {str(e)}"
            )

        policy_id = asset_info.get("policy_id", asset_id[:56])
        asset_name_hex = asset_info.get(
            "asset_name", asset_id[56:] if len(asset_id) > 56 else ""
        )

        asset_name_decoded = _decode_asset_name(asset_name_hex)

        onchain_metadata = asset_info.get("onchain_metadata")
        metadata = _parse_asset_metadata(onchain_metadata) if onchain_metadata else None

        return AssetDetailResponse(
            asset=asset_info.get("asset", asset_id),
            policy_id=policy_id,
            asset_name=asset_name_hex,
            asset_name_decoded=asset_name_decoded,
            fingerprint=asset_info.get("fingerprint", ""),
            quantity=asset_info.get("quantity", "0"),
            initial_mint_tx_hash=asset_info.get("initial_mint_tx_hash", ""),
            mint_or_burn_count=asset_info.get("mint_or_burn_count", 0),
            onchain_metadata=onchain_metadata,
            onchain_metadata_standard=asset_info.get("onchain_metadata_standard"),
            onchain_metadata_extra=asset_info.get("onchain_metadata_extra"),
            metadata=metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get asset detail for {asset_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to query asset: {str(e)}")


@router.get(
    "/policy/{policy_id}",
    response_model=PolicyAssetsResponse,
    summary="List assets under policy",
    description="Get list of all assets minted under a specific policy ID.",
    responses={
        401: {"model": AssetErrorResponse, "description": "Authentication required"},
        404: {
            "model": AssetErrorResponse,
            "description": "Policy not found or has no assets",
        },
        500: {
            "model": AssetErrorResponse,
            "description": "Failed to query policy assets",
        },
    },
)
async def list_policy_assets(
    policy_id: str = Path(
        ...,
        description="Policy ID (56 hex characters)",
        min_length=56,
        max_length=56,
    ),
    page: int = Query(1, ge=1, le=1000, description="Page number (1-1000)"),
    limit: int = Query(100, ge=1, le=100, description="Results per page (1-100)"),
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> PolicyAssetsResponse:
    """
    List all assets minted under a specific policy ID.

    Returns a paginated list of asset summaries. For full details of each asset,
    use the `/assets/{asset_id}` endpoint or the `/assets/policy/{policy_id}/details`
    endpoint.

    **Pagination:**
    - `page`: Page number (starts at 1)
    - `limit`: Results per page (max 100)

    **Authentication required:** Bearer token from wallet unlock.
    """
    try:
        api = chain_context.get_api()

        try:
            assets_list = api.assets_policy(
                policy_id, return_type="json", count=limit, page=page, order="asc"
            )
        except ApiError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                return PolicyAssetsResponse(
                    policy_id=policy_id,
                    assets=[],
                    total=0,
                    page=page,
                    limit=limit,
                    has_more=False,
                )
            raise HTTPException(
                status_code=500, detail=f"Blockfrost API error: {str(e)}"
            )

        assets = []
        for asset in assets_list:
            asset_id = asset.get("asset", "")
            asset_name_hex = asset_id[56:] if len(asset_id) > 56 else ""

            assets.append(
                PolicyAssetItem(
                    asset=asset_id,
                    asset_name=asset_name_hex,
                    asset_name_decoded=_decode_asset_name(asset_name_hex),
                    quantity=asset.get("quantity", "0"),
                )
            )

        has_more = len(assets_list) == limit

        return PolicyAssetsResponse(
            policy_id=policy_id,
            assets=assets,
            total=len(assets),
            page=page,
            limit=limit,
            has_more=has_more,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list assets for policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to query policy assets: {str(e)}"
        )


@router.get(
    "/policy/{policy_id}/details",
    response_model=PolicyAssetsDetailResponse,
    summary="List assets with full details under policy",
    description="Get all assets under a policy ID with full details for each asset. Warning: slower than basic list.",
    responses={
        401: {"model": AssetErrorResponse, "description": "Authentication required"},
        404: {
            "model": AssetErrorResponse,
            "description": "Policy not found or has no assets",
        },
        500: {
            "model": AssetErrorResponse,
            "description": "Failed to query policy assets",
        },
    },
)
async def list_policy_assets_with_details(
    policy_id: str = Path(
        ...,
        description="Policy ID (56 hex characters)",
        min_length=56,
        max_length=56,
    ),
    page: int = Query(
        1, ge=1, le=100, description="Page number (1-100, lower max due to detail queries)"
    ),
    limit: int = Query(
        10, ge=1, le=20, description="Results per page (1-20, limited for performance)"
    ),
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> PolicyAssetsDetailResponse:
    """
    List all assets under a policy ID with **full details** for each asset.

    This endpoint replicates the behavior from the reference code that calls
    `assets_policy()` then fetches `asset()` details for each result.

    **Warning:** This endpoint makes N+1 API calls (1 for the list + 1 for each asset detail).
    For large policies, use the basic `/policy/{policy_id}` endpoint and fetch details
    individually.

    **Pagination:**
    - `page`: Page number (max 100 due to performance)
    - `limit`: Results per page (max 20 due to multiple API calls)

    **Authentication required:** Bearer token from wallet unlock.
    """
    try:
        api = chain_context.get_api()

        try:
            assets_list = api.assets_policy(
                policy_id, return_type="json", count=limit, page=page, order="asc"
            )
        except ApiError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                return PolicyAssetsDetailResponse(
                    policy_id=policy_id,
                    assets=[],
                    total=0,
                    page=page,
                    limit=limit,
                    has_more=False,
                )
            raise HTTPException(
                status_code=500, detail=f"Blockfrost API error: {str(e)}"
            )

        detailed_assets = []
        for asset_summary in assets_list:
            asset_id = asset_summary.get("asset", "")

            try:
                asset_detail = api.asset(asset_id, return_type="json")

                asset_name_hex = asset_detail.get("asset_name", "")
                onchain_metadata = asset_detail.get("onchain_metadata")

                detailed_assets.append(
                    PolicyAssetDetailItem(
                        asset=asset_detail.get("asset", asset_id),
                        policy_id=asset_detail.get("policy_id", policy_id),
                        asset_name=asset_name_hex,
                        asset_name_decoded=_decode_asset_name(asset_name_hex),
                        fingerprint=asset_detail.get("fingerprint", ""),
                        quantity=asset_detail.get("quantity", "0"),
                        initial_mint_tx_hash=asset_detail.get("initial_mint_tx_hash"),
                        mint_or_burn_count=asset_detail.get("mint_or_burn_count"),
                        onchain_metadata=onchain_metadata,
                        metadata=_parse_asset_metadata(onchain_metadata),
                    )
                )
            except ApiError as e:
                logger.warning(f"Failed to get details for asset {asset_id}: {str(e)}")
                continue

        has_more = len(assets_list) == limit

        return PolicyAssetsDetailResponse(
            policy_id=policy_id,
            assets=detailed_assets,
            total=len(detailed_assets),
            page=page,
            limit=limit,
            has_more=has_more,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list asset details for policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to query policy assets: {str(e)}"
        )
