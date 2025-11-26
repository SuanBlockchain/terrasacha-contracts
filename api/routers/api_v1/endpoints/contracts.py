"""
Contract Endpoints

FastAPI endpoints for smart contract compilation and querying.
Database-backed contract management for API workflow.

Note: CLI workflow uses JSON files (ContractManager) - this is API-only.
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from api.registries.contract_registry import list_all_contracts, get_contract_file_path, get_contract_info
from api.database.connection import get_session
from api.database.models import Wallet
from api.dependencies.auth import WalletAuthContext, require_core_wallet
from api.schemas.contract import (
    AvailableContractInfo,
    AvailableContractsResponse,
    CompileContractRequest,
    CompileContractResponse,
    ContractErrorResponse,
    DbContractListItem,
    DbContractListResponse,
)
from api.services.contract_service import ContractService, ContractCompilationError, ContractNotFoundError
from sqlalchemy import select


router = APIRouter()


# ============================================================================
# Contract Compilation Endpoints
# ============================================================================


@router.get(
    "/available",
    response_model=AvailableContractsResponse,
    summary="List available contracts",
    description="Get list of all available Opshin contracts that can be compiled.",
)
async def list_available_contracts() -> AvailableContractsResponse:
    """
    List all available contracts for compilation.

    Returns contracts grouped by type:
    - **Minting**: Token minting policies (myUSDFree, project_nfts, protocol_nfts, grey)
    - **Spending**: Spending validators (investor, project, protocol)

    Each contract includes:
    - Name and file path
    - Description of functionality
    - Whether it requires compilation parameters
    - Description of required parameters (if any)

    **Example:**
    ```
    GET /api/v1/contracts/available
    ```

    **Response:**
    ```json
    {
      "minting": [
        {
          "name": "myUSDFree",
          "file_path": "minting_policies/myUSDFree.py",
          "description": "USDA faucet minting policy",
          "requires_params": false,
          "param_description": null
        }
      ],
      "spending": [...],
      "total": 7
    }
    ```
    """
    all_contracts = list_all_contracts()

    minting_contracts = [AvailableContractInfo(**contract) for contract in all_contracts["minting"]]
    spending_contracts = [AvailableContractInfo(**contract) for contract in all_contracts["spending"]]

    return AvailableContractsResponse(
        minting=minting_contracts,
        spending=spending_contracts,
        total=len(minting_contracts) + len(spending_contracts)
    )


@router.post(
    "/compile",
    response_model=CompileContractResponse,
    summary="Compile Opshin contract (CORE only)",
    description="Compile an Opshin smart contract from file path or source code. Stores in database. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request or compilation failed"},
        401: {"model": ContractErrorResponse, "description": "Authentication required"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_contract(
    request: CompileContractRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> CompileContractResponse:
    """
    Compile an Opshin smart contract (CORE wallets only).

    This endpoint:
    1. Accepts contract source code or file path
    2. Compiles using Opshin
    3. Stores compiled contract in database
    4. Returns contract information

    **Authentication Required:**
    - CORE wallet only (admin privileges)

    **Compilation Options:**
    1. **From registry**: Use `contract_name` from available contracts (recommended)
    2. **Custom source**: Provide `source_code` directly

    **Example Requests:**

    From available contract (automatic file lookup):
    ```json
    {
        "contract_name": "grey",
        "contract_type": "minting",
        "compilation_params": ["<project_nfts_policy_id_bytes>"]
    }
    ```

    Custom source code:
    ```json
    {
        "contract_name": "my_custom_validator",
        "contract_type": "spending",
        "source_code": "#!opshin\\nfrom opshin.prelude import *\\n..."
    }
    ```

    **Tip**: Call `GET /api/v1/contracts/available` to see available contracts
    """
    try:
        # Get wallet's network from database
        stmt = select(Wallet).where(Wallet.id == core_wallet.wallet_id)
        result = await session.execute(stmt)
        db_wallet = result.scalar_one_or_none()

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {core_wallet.wallet_id} not found")

        # Create contract service
        contract_service = ContractService(session)

        # Compile contract
        if request.source_code:
            # Option 2: Compile from custom source code
            contract = await contract_service.compile_contract_from_source(
                source_code=request.source_code,
                contract_name=request.contract_name,
                network=db_wallet.network,
                contract_type=request.contract_type,
                compilation_params=request.compilation_params
            )
        else:
            # Option 1: Compile from registry (automatic file lookup)
            file_path = get_contract_file_path(request.contract_name, request.contract_type)

            if not file_path:
                # Get contract info to provide helpful error message
                contract_info = get_contract_info(request.contract_name, request.contract_type)
                if contract_info:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Contract '{request.contract_name}' found but file path lookup failed"
                    )
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Contract '{request.contract_name}' not found in {request.contract_type} registry. "
                               f"Use GET /api/v1/contracts/available to see available contracts, "
                               f"or provide custom source_code."
                    )

            # Compile from registered contract file
            full_path = f"src/terrasacha_contracts/{file_path}"
            contract = await contract_service.compile_contract_from_file(
                contract_path=full_path,
                contract_name=request.contract_name,
                network=db_wallet.network,
                contract_type=request.contract_type,
                compilation_params=request.compilation_params
            )

        return CompileContractResponse(
            success=True,
            policy_id=contract.policy_id,
            contract_name=contract.name,
            cbor_hex=contract.cbor_hex,
            testnet_address=contract.testnet_addr,
            mainnet_address=contract.mainnet_addr,
            contract_type=contract.contract_type.value,
            source_hash=contract.source_hash,
            version=contract.version,
            compiled_at=contract.compiled_at
        )

    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile contract: {str(e)}")


# ============================================================================
# Contract Query Endpoints
# ============================================================================


@router.get(
    "/",
    response_model=DbContractListResponse,
    summary="List all compiled contracts (CORE only)",
    description="Get list of all compiled contracts stored in database. Optionally filter by network. Requires CORE wallet.",
)
async def list_contracts(
    network: str | None = None,
    _core_wallet: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> DbContractListResponse:
    """
    List all compiled contracts from database.

    Returns contract metadata including:
    - Contract name and policy ID
    - Addresses (testnet/mainnet)
    - Version and compilation timestamp
    - Network (testnet/mainnet)

    **Query Parameters:**
    - `network` (optional): Filter by network ("testnet" or "mainnet")

    **Example:**
    ```
    GET /api/v1/contracts/
    GET /api/v1/contracts/?network=testnet
    ```
    """
    try:
        contract_service = ContractService(session)

        # Parse network filter
        from api.enums import NetworkType
        network_filter = None
        if network:
            try:
                # Strip whitespace and convert to lowercase
                network_cleaned = network.strip().lower()
                network_filter = NetworkType(network_cleaned)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid network: '{network}'. Must be 'testnet' or 'mainnet'"
                )

        contracts = await contract_service.list_contracts(network=network_filter)

        contract_items = [
            DbContractListItem(
                policy_id=c.policy_id,
                name=c.name,
                contract_type=c.contract_type.value,
                testnet_address=c.testnet_addr,
                mainnet_address=c.mainnet_addr,
                version=c.version,
                source_hash=c.source_hash,
                compiled_at=c.compiled_at,
                network=c.network.value
            )
            for c in contracts
        ]

        return DbContractListResponse(
            contracts=contract_items,
            total=len(contract_items)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list contracts: {str(e)}")


@router.get(
    "/{policy_id}",
    response_model=CompileContractResponse,
    summary="Get contract by policy ID",
    description="Get detailed information about a specific compiled contract.",
    responses={
        404: {"model": ContractErrorResponse, "description": "Contract not found"},
    },
)
async def get_contract(
    policy_id: str = Path(..., description="Contract policy ID (script hash)"),
    session: AsyncSession = Depends(get_session),
) -> CompileContractResponse:
    """
    Get detailed contract information by policy ID.

    Returns full contract details including:
    - Source code and hash
    - Compiled CBOR hex
    - Addresses and policy ID
    - Compilation metadata (version, timestamp)

    **Example:**
    ```
    GET /api/v1/contracts/a1b2c3d4e5f6...
    ```
    """
    try:
        contract_service = ContractService(session)
        contract = await contract_service.get_contract(policy_id)

        return CompileContractResponse(
            success=True,
            policy_id=contract.policy_id,
            contract_name=contract.name,
            cbor_hex=contract.cbor_hex,
            testnet_address=contract.testnet_addr,
            mainnet_address=contract.mainnet_addr,
            contract_type=contract.contract_type.value,
            source_hash=contract.source_hash,
            version=contract.version,
            compiled_at=contract.compiled_at
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get contract: {str(e)}")


# ============================================================================
# Contract Management Endpoints
# ============================================================================


@router.delete(
    "/{policy_id}",
    summary="Delete contract (CORE only)",
    description="Delete a contract from the database. Requires CORE wallet.",
    responses={
        404: {"model": ContractErrorResponse, "description": "Contract not found"},
    },
)
async def delete_contract(
    policy_id: str = Path(..., description="Contract policy ID to delete"),
    _core_wallet: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Delete a contract from the database (CORE wallets only).

    **Authentication Required:**
    - CORE wallet only (admin privileges)

    **Example:**
    ```
    DELETE /api/v1/contracts/a1b2c3d4e5f6...
    ```
    """
    try:
        contract_service = ContractService(session)
        success = await contract_service.delete_contract(policy_id)

        return {
            "success": success,
            "message": f"Contract {policy_id} deleted successfully"
        }

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete contract: {str(e)}")
