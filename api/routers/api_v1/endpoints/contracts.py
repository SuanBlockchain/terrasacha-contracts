"""
Contract Endpoints

FastAPI endpoints for smart contract compilation and querying.
Provides contract compilation, listing, datum querying, and deletion.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Path

from api.schemas.contract import (
    CompileGreyRequest,
    CompileGreyResponse,
    CompileInvestorRequest,
    CompileInvestorResponse,
    CompileProjectRequest,
    CompileProjectResponse,
    CompileProtocolRequest,
    CompileProtocolResponse,
    ContractDatumResponse,
    ContractDetailResponse,
    ContractErrorResponse,
    ContractInfoResponse,
    ContractListItem,
    ContractListResponse,
    ContractType,
    InvestorDatum,
    ProjectDatum,
    ProtocolDatum,
)
from cardano_offchain.chain_context import CardanoChainContext
from cardano_offchain.contracts import ContractManager
from cardano_offchain.wallet import WalletManager


router = APIRouter()

# Global state for contract management
_contract_manager: ContractManager | None = None
_chain_context: CardanoChainContext | None = None
_wallet_manager: WalletManager | None = None


# ============================================================================
# Dependencies
# ============================================================================


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


def get_contract_manager(chain_context: CardanoChainContext = Depends(get_chain_context)) -> ContractManager:
    """Get or initialize the contract manager"""
    global _contract_manager
    if _contract_manager is None:
        _contract_manager = ContractManager(chain_context)
    return _contract_manager


# ============================================================================
# Compilation Endpoints
# ============================================================================


@router.post(
    "/compile/protocol",
    response_model=CompileProtocolResponse,
    summary="Compile protocol contracts",
    description="Compile protocol_nfts and protocol contracts using a UTXO from the specified wallet",
    responses={500: {"model": ContractErrorResponse, "description": "Compilation failed"}},
)
async def compile_protocol_contracts(
    request: CompileProtocolRequest,
    contract_manager: ContractManager = Depends(get_contract_manager),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
) -> CompileProtocolResponse:
    """
    Compile protocol smart contracts.

    This endpoint:
    1. Gets a suitable UTXO (>3 ADA) from the specified wallet
    2. Compiles protocol_nfts minting policy using the UTXO
    3. Compiles protocol spending validator using protocol_nfts policy ID
    4. Stores contracts in memory and saves to disk

    The compilation UTXO must remain unspent to preserve contract uniqueness.
    """
    try:
        # Get wallet for UTXO
        wallet_name = request.wallet_name if request.wallet_name else wallet_manager.get_default_wallet_name()
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        # Get wallet address
        protocol_address = wallet.get_address(0)

        # Compile contracts
        result = contract_manager.compile_contracts(protocol_address, force=request.force)

        if not result["success"]:
            return CompileProtocolResponse(success=False, error=result.get("error"))

        # Return success response
        return CompileProtocolResponse(
            success=True,
            message=result.get("message"),
            contracts=result.get("contracts"),
            protocol_policy_id=(
                contract_manager.get_contract("protocol").policy_id
                if contract_manager.get_contract("protocol")
                else None
            ),
            protocol_nfts_policy_id=(
                contract_manager.get_contract("protocol_nfts").policy_id
                if contract_manager.get_contract("protocol_nfts")
                else None
            ),
            compilation_utxo=result.get("compilation_utxo"),
            skipped=result.get("skipped", False),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile protocol contracts: {str(e)}")


@router.post(
    "/compile/project",
    response_model=CompileProjectResponse,
    summary="Compile project contracts",
    description="Compile project_nfts and project contracts for a new carbon credit project",
    responses={
        400: {"model": ContractErrorResponse, "description": "Protocol not compiled"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_project_contracts(
    request: CompileProjectRequest,
    contract_manager: ContractManager = Depends(get_contract_manager),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
) -> CompileProjectResponse:
    """
    Compile project smart contracts.

    This endpoint:
    1. Validates protocol contracts exist
    2. Gets a unique UTXO from the specified wallet
    3. Compiles project_nfts minting policy with protocol_nfts policy ID
    4. Compiles project spending validator with project_nfts policy ID
    5. Auto-names projects (project, project_1, project_2, etc.)

    Each project gets a unique compilation UTXO for contract uniqueness.
    """
    try:
        # Get wallet for UTXO
        wallet_name = request.wallet_name if request.wallet_name else wallet_manager.get_default_wallet_name()
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        # Get wallet address
        project_address = wallet.get_address(0)

        # Compile project contracts
        result = contract_manager.compile_project_contract_only(project_address)

        if not result["success"]:
            error = result.get("error", "Unknown error")
            # Check if it's a protocol prerequisite error
            if "Protocol contracts must be compiled first" in error:
                raise HTTPException(status_code=400, detail=error)
            return CompileProjectResponse(success=False, error=error)

        # Return success response
        return CompileProjectResponse(
            success=True,
            message=result.get("message"),
            project_name=result.get("project_name"),
            project_nfts_name=result.get("project_nfts_name"),
            project_policy_id=result.get("project_policy_id"),
            project_nfts_policy_id=result.get("project_nfts_policy_id"),
            used_utxo=result.get("used_utxo"),
            saved=result.get("saved", False),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile project contracts: {str(e)}")


@router.post(
    "/compile/grey",
    response_model=CompileGreyResponse,
    summary="Compile grey token contract",
    description="Compile grey token minting policy for a specific project",
    responses={
        400: {"model": ContractErrorResponse, "description": "Project not found"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_grey_contract(
    request: CompileGreyRequest, contract_manager: ContractManager = Depends(get_contract_manager)
) -> CompileGreyResponse:
    """
    Compile grey token minting contract.

    This endpoint:
    1. Validates the project contract exists
    2. Compiles grey minting policy using project_nfts policy ID
    3. Names it {project_name}_grey

    Grey tokens represent carbon credits before certification.
    """
    try:
        # Compile grey contract
        result = contract_manager.compile_grey_contract(request.project_name)

        if not result["success"]:
            error = result.get("error", "Unknown error")
            # Check if it's a project prerequisite error
            if "not found" in error.lower():
                raise HTTPException(status_code=400, detail=error)
            return CompileGreyResponse(success=False, error=error)

        # Return success response
        return CompileGreyResponse(
            success=True,
            message=result.get("message", f"Successfully compiled grey contract for {request.project_name}"),
            grey_contract_name=result.get("grey_contract_name"),
            grey_policy_id=result.get("grey_policy_id"),
            project_name=result.get("project_name"),
            project_nfts_policy_id=result.get("project_nfts_policy_id"),
            saved=result.get("saved", False),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile grey contract: {str(e)}")


@router.post(
    "/compile/investor",
    response_model=CompileInvestorResponse,
    summary="Compile investor contract",
    description="Compile investor spending contract for grey token marketplace",
    responses={
        400: {"model": ContractErrorResponse, "description": "Grey contract not found or no datum"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_investor_contract(
    request: CompileInvestorRequest, contract_manager: ContractManager = Depends(get_contract_manager)
) -> CompileInvestorResponse:
    """
    Compile investor contract for grey token sales.

    This endpoint:
    1. Validates protocol, project, and grey contracts exist
    2. Queries project datum for grey token info
    3. Compiles investor spending validator
    4. Names it {project_name}_investor

    Investor contracts enable marketplace trading of grey tokens.
    """
    try:
        # Compile investor contract
        result = contract_manager.compile_investor_contract(request.project_name)

        if not result["success"]:
            error = result.get("error", "Unknown error")
            # Check for prerequisite errors
            if "not found" in error.lower() or "datum" in error.lower():
                raise HTTPException(status_code=400, detail=error)
            return CompileInvestorResponse(success=False, error=error)

        # Return success response
        return CompileInvestorResponse(
            success=True,
            message=result.get("message", f"Successfully compiled investor contract for {request.project_name}"),
            investor_contract_name=result.get("investor_contract_name"),
            investor_address=result.get("investor_address"),
            project_name=result.get("project_name"),
            protocol_policy_id=result.get("protocol_policy_id"),
            grey_policy_id=result.get("grey_policy_id"),
            grey_token_name=result.get("grey_token_name"),
            saved=result.get("saved", False),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile investor contract: {str(e)}")


# ============================================================================
# Query Endpoints
# ============================================================================


@router.get(
    "/",
    response_model=ContractListResponse,
    summary="List all contracts",
    description="Get a list of all compiled contracts with their details and balances",
)
async def list_contracts(contract_manager: ContractManager = Depends(get_contract_manager)) -> ContractListResponse:
    """
    List all compiled contracts.

    Returns contract information including:
    - Name and policy ID
    - Contract type (minting_policy or spending_validator)
    - Address and balance (for spending validators only)
    - Compilation UTXO information
    """
    try:
        contracts_info = contract_manager.get_contracts_info()

        contract_list = []
        for name, info in contracts_info["contracts"].items():
            # Determine contract type
            is_minting = info.get("type") == "minting_policy"

            contract_list.append(
                ContractListItem(
                    name=name,
                    policy_id=info["policy_id"],
                    contract_type=ContractType.MINTING_POLICY if is_minting else ContractType.SPENDING_VALIDATOR,
                    address=info.get("address"),
                    balance_lovelace=info.get("balance"),
                    balance_ada=info.get("balance_ada"),
                )
            )

        return ContractListResponse(
            contracts=contract_list, total=len(contract_list), compilation_utxo=contracts_info.get("compilation_utxo")
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list contracts: {str(e)}")


@router.get(
    "/info",
    response_model=ContractInfoResponse,
    summary="Get comprehensive contract info",
    description="Get detailed information about all contracts (similar to CLI display)",
)
async def get_contracts_info(contract_manager: ContractManager = Depends(get_contract_manager)) -> ContractInfoResponse:
    """
    Get comprehensive contract information.

    Returns complete contract details including:
    - All contract metadata
    - Balances for spending validators
    - Compilation UTXO information
    - Contract types and policy IDs
    """
    try:
        info = contract_manager.get_contracts_info()
        return ContractInfoResponse(
            contracts=info["contracts"],
            compilation_utxo=info.get("compilation_utxo"),
            total_contracts=info.get("total_contracts", 0),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get contract info: {str(e)}")


@router.get(
    "/{contract_name}",
    response_model=ContractDetailResponse,
    summary="Get contract details",
    description="Get detailed information about a specific contract",
    responses={404: {"model": ContractErrorResponse, "description": "Contract not found"}},
)
async def get_contract_details(
    contract_name: str = Path(..., description="Name of the contract"),
    contract_manager: ContractManager = Depends(get_contract_manager),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> ContractDetailResponse:
    """
    Get details for a specific contract.

    Returns:
    - Contract addresses and policy ID
    - Storage type (local or reference script)
    - Current balance (for spending validators)
    - Compilation UTXO information
    - Reference script UTXO (if applicable)
    """
    try:
        contract = contract_manager.get_contract(contract_name)
        if not contract:
            raise HTTPException(status_code=404, detail=f"Contract '{contract_name}' not found")

        # Get contract type
        is_minting = contract_name.endswith("_nfts") or contract_name.endswith("_grey") or contract_name == "myUSDFree"

        # Get balance for spending validators
        balance_lovelace = None
        balance_ada = None

        if not is_minting:
            contract_address = contract.testnet_addr if chain_context.network == "testnet" else contract.mainnet_addr
            try:
                api = chain_context.get_api()
                utxos = api.address_utxos(str(contract_address))
                balance_lovelace = sum(
                    int(utxo.amount[0].quantity) for utxo in utxos if utxo.amount[0].unit == "lovelace"
                )
                balance_ada = balance_lovelace / 1_000_000
            except Exception:
                # Handle 404 or other errors - default to 0 balance
                balance_lovelace = 0
                balance_ada = 0.0

        # Get storage type and reference info
        storage_type = getattr(contract, "storage_type", "local")
        reference_utxo = None
        if storage_type == "reference_script":
            reference_utxo = contract.get_reference_utxo()

        # Get compilation UTXO
        compilation_utxo = None
        if contract_name in ["protocol", "protocol_nfts"]:
            compilation_utxo = contract_manager.compilation_utxo
        elif (
            contract_name.startswith("project")
            and not contract_name.endswith("_grey")
            and not contract_name.endswith("_investor")
        ):
            # Extract base project name
            base_name = contract_name.replace("_nfts", "")
            compilation_utxo = contract_manager.get_project_compilation_utxo(base_name)

        return ContractDetailResponse(
            name=contract_name,
            policy_id=contract.policy_id,
            contract_type=ContractType.MINTING_POLICY if is_minting else ContractType.SPENDING_VALIDATOR,
            storage_type=storage_type,
            testnet_address=str(contract.testnet_addr),
            mainnet_address=str(contract.mainnet_addr),
            balance_lovelace=balance_lovelace,
            balance_ada=balance_ada,
            compilation_utxo=compilation_utxo,
            reference_utxo=reference_utxo,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get contract details: {str(e)}")


@router.get(
    "/{contract_name}/datum",
    response_model=ContractDatumResponse,
    summary="Query contract datum",
    description="Query and decode the datum from a contract's UTXO on the blockchain",
    responses={
        400: {"model": ContractErrorResponse, "description": "Minting policy (no datum)"},
        404: {"model": ContractErrorResponse, "description": "Contract not found or no UTXOs"},
    },
)
async def get_contract_datum(
    contract_name: str = Path(..., description="Name of the contract"),
    contract_manager: ContractManager = Depends(get_contract_manager),
) -> ContractDatumResponse:
    """
    Query contract datum from blockchain.

    This endpoint:
    1. Queries the contract address for UTXOs
    2. Extracts the datum from the first UTXO
    3. Decodes it based on contract type:
       - **Protocol**: admins, fee, oracle_id, projects
       - **Project**: params, token info, stakeholders, certifications
       - **Investor**: seller_pkh, grey token amount, price, min purchase

    **Note:** Minting policies don't have datums and will return an error.
    """
    try:
        result = contract_manager.get_contract_datum(contract_name)

        if not result or not result.get("success"):
            error = result.get("error", "Unknown error") if result else "Failed to query datum"

            # Determine appropriate status code
            if "not found" in error.lower():
                raise HTTPException(status_code=404, detail=error)
            elif "minting policy" in error.lower():
                raise HTTPException(status_code=400, detail=error)
            else:
                raise HTTPException(status_code=500, detail=error)

        # Parse datum based on contract type
        contract_type = result["contract_type"]
        datum_data = result["datum"]

        # Convert to appropriate Pydantic model
        if contract_type == "protocol":
            datum = ProtocolDatum(**datum_data)
        elif contract_type == "project":
            datum = ProjectDatum(**datum_data)
        elif contract_type == "investor":
            datum = InvestorDatum(**datum_data)
        else:
            raise HTTPException(status_code=500, detail=f"Unknown contract type: {contract_type}")

        return ContractDatumResponse(
            success=True,
            contract_name=result["contract_name"],
            contract_type=contract_type,
            datum=datum,
            utxo_ref=result.get("utxo_ref"),
            balance_lovelace=result.get("balance"),
            balance_ada=result.get("balance_ada"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query contract datum: {str(e)}")


# ============================================================================
# Utility Endpoints
# ============================================================================


@router.delete(
    "/{contract_name}",
    summary="Delete empty contract",
    description="Delete a contract if it has zero balance (no active tokens)",
    responses={
        400: {"model": ContractErrorResponse, "description": "Contract has balance or is minting policy"},
        404: {"model": ContractErrorResponse, "description": "Contract not found"},
    },
)
async def delete_contract(
    contract_name: str = Path(..., description="Name of the contract to delete"),
    contract_manager: ContractManager = Depends(get_contract_manager),
) -> dict:
    """
    Delete an empty contract.

    This endpoint:
    1. Checks if the contract exists
    2. Verifies the contract has zero balance
    3. Deletes the contract and associated NFT minting policies
    4. Cleans up compilation UTXO tracking
    5. Saves updated contracts to disk

    **Safety:** Only contracts with zero balance can be deleted.
    """
    try:
        result = contract_manager.delete_contract_if_empty(contract_name)

        if not result["success"]:
            error = result.get("error", "Unknown error")

            # Determine appropriate status code
            if "not found" in error.lower():
                raise HTTPException(status_code=404, detail=error)
            elif "balance" in error.lower() or "minting policy" in error.lower():
                raise HTTPException(status_code=400, detail=error)
            else:
                raise HTTPException(status_code=500, detail=error)

        return {
            "success": True,
            "message": result.get("message"),
            "deleted_contracts": result.get("deleted_contracts", []),
            "saved": result.get("saved", False),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete contract: {str(e)}")
