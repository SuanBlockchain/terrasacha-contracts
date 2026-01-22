"""
Asset Schemas

Pydantic models for asset-related API requests and responses.
"""

from pydantic import BaseModel, Field


class AssetMetadata(BaseModel):
    """On-chain or off-chain metadata for an asset"""

    name: str | None = Field(None, description="Asset name from metadata")
    description: str | None = Field(None, description="Asset description")
    ticker: str | None = Field(None, description="Token ticker symbol")
    url: str | None = Field(None, description="Project URL")
    logo: str | None = Field(None, description="Logo image URL or base64")
    decimals: int | None = Field(None, description="Token decimals")
    raw: dict | None = Field(None, description="Raw metadata object")


class AssetDetailResponse(BaseModel):
    """Detailed information about a single Cardano native asset"""

    asset: str = Field(description="Asset identifier (policy_id + hex asset name)")
    policy_id: str = Field(description="Policy ID (script hash)")
    asset_name: str = Field(description="Asset name (hex-encoded)")
    asset_name_decoded: str | None = Field(
        None, description="Human-readable asset name (if decodable)"
    )
    fingerprint: str = Field(description="CIP-14 asset fingerprint")
    quantity: str = Field(
        description="Total circulating quantity (as string for large numbers)"
    )
    initial_mint_tx_hash: str = Field(description="Transaction hash of first mint")
    mint_or_burn_count: int = Field(description="Number of mint/burn transactions")
    onchain_metadata: dict | None = Field(
        None, description="On-chain metadata (CIP-25/CIP-68)"
    )
    onchain_metadata_standard: str | None = Field(
        None, description="Metadata standard (CIP25v1, CIP25v2, CIP68v1)"
    )
    onchain_metadata_extra: str | None = Field(None, description="Extra metadata if any")
    metadata: AssetMetadata | None = Field(None, description="Parsed metadata")


class PolicyAssetItem(BaseModel):
    """Summary of an asset under a policy ID"""

    asset: str = Field(description="Asset identifier (policy_id + hex asset name)")
    asset_name: str = Field(description="Asset name (hex-encoded)")
    asset_name_decoded: str | None = Field(
        None, description="Human-readable asset name"
    )
    quantity: str = Field(description="Total circulating quantity")


class PolicyAssetDetailItem(BaseModel):
    """Full detail of an asset under a policy ID (when include_details=True)"""

    asset: str = Field(description="Asset identifier")
    policy_id: str = Field(description="Policy ID")
    asset_name: str = Field(description="Asset name (hex-encoded)")
    asset_name_decoded: str | None = Field(
        None, description="Human-readable asset name"
    )
    fingerprint: str = Field(description="CIP-14 asset fingerprint")
    quantity: str = Field(description="Total circulating quantity")
    initial_mint_tx_hash: str | None = Field(None, description="First mint transaction")
    mint_or_burn_count: int | None = Field(None, description="Mint/burn count")
    onchain_metadata: dict | None = Field(None, description="On-chain metadata")
    metadata: AssetMetadata | None = Field(None, description="Parsed metadata")


class PolicyAssetsResponse(BaseModel):
    """Response for listing assets under a policy ID"""

    policy_id: str = Field(description="The queried policy ID")
    assets: list[PolicyAssetItem] = Field(description="List of assets")
    total: int = Field(description="Total assets returned")
    page: int = Field(description="Current page number")
    limit: int = Field(description="Results per page")
    has_more: bool = Field(description="Whether more results are available")


class PolicyAssetsDetailResponse(BaseModel):
    """Response for listing assets with full details under a policy ID"""

    policy_id: str = Field(description="The queried policy ID")
    assets: list[PolicyAssetDetailItem] = Field(
        description="List of assets with details"
    )
    total: int = Field(description="Total assets returned")
    page: int = Field(description="Current page number")
    limit: int = Field(description="Results per page")
    has_more: bool = Field(description="Whether more results are available")


class AssetErrorResponse(BaseModel):
    """Error response for asset operations"""

    success: bool = Field(default=False)
    error: str = Field(description="Error message")
    error_code: str | None = Field(None, description="Error code")
