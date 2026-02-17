"""
Contract Endpoints

FastAPI endpoints for smart contract compilation and querying.
Database-backed contract management for API workflow.

Note: CLI workflow uses JSON files (ContractManager) - this is API-only.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.registries.contract_registry import list_all_contracts, get_contract_file_path, get_contract_info, _registry
from api.services.contract_registry_service import ContractRegistryService
from api.dependencies.tenant import get_tenant_database, get_tenant_context
from api.database.models import WalletMongo
from api.dependencies.auth import WalletAuthContext, require_core_wallet
from api.schemas.contract import (
    AvailableContractInfo,
    AvailableContractsResponse,
    BurnProtocolRequest,
    BurnProtocolResponse,
    CompilationUtxoInfo,
    CompiledProtocolContractInfo,
    CompileContractRequest,
    CompileCustomContractRequest,
    CompileContractResponse,
    CompileProjectRequest,
    CompileProjectResponse,
    CompileProtocolRequest,
    CompileProtocolResponse,
    ContractDatumResponse,
    ContractErrorResponse,
    DbContractListItem,
    DbContractListResponse,
    InvalidateContractRequest,
    InvalidateContractResponse,
    InvalidatedContractInfo,
    MintProjectRequest,
    MintProjectResponse,
    MintProtocolRequest,
    MintProtocolResponse,
)
from api.services.contract_service_mongo import (
    MongoContractService,
    ContractAlreadyExistsError,
    ContractCompilationError,
    ContractDeleteBlockedError,
    ContractInvalidationError,
    ContractNotFoundError,
    InvalidContractParametersError,
)
from api.dependencies.chain_context import get_chain_context
from cardano_offchain.chain_context import CardanoChainContext


router = APIRouter()


# ============================================================================
# Contract Compilation Endpoints
# ============================================================================


@router.get(
    "/available",
    response_model=AvailableContractsResponse,
    summary="List available contracts",
    description="Get list of all available Opshin contracts that can be compiled (filtered by tenant configuration).",
)
async def list_available_contracts(
    category: str | None = None,
    tenant_id: str = Depends(get_tenant_context)
) -> AvailableContractsResponse:
    """
    List all available contracts for compilation with tenant-specific filtering.

    Returns contracts grouped by type:
    - **Minting**: Token minting policies (myUSDFree, project_nfts, protocol_nfts, grey)
    - **Spending**: Spending validators (investor, project, protocol)

    Each contract includes:
    - Name, file path, and description
    - Category (core_protocol, project_management, token_management, testing)
    - Whether it requires compilation parameters
    - Description of required parameters (if any)
    - Optional tags for filtering

    **Query Parameters:**
    - `category` (optional): Filter by category

    **Tenant Filtering:**
    Contracts are filtered based on tenant configuration. If your tenant has restrictions,
    you will only see contracts that are enabled for your tenant.

    **Example:**
    ```
    GET /api/v1/contracts/available
    GET /api/v1/contracts/available?category=core_protocol
    ```

    **Response:**
    ```json
    {
      "minting": [
        {
          "name": "myUSDFree",
          "file_path": "minting_policies/myUSDFree.py",
          "description": "USDA faucet minting policy",
          "category": "testing",
          "requires_params": false,
          "param_description": null,
          "tags": ["testing", "faucet"]
        }
      ],
      "spending": [...],
      "total": 7
    }
    ```
    """
    # Create registry service
    registry_service = ContractRegistryService(_registry)

    # Get contracts with tenant filtering
    contracts_dict = await registry_service.get_available_contracts(
        tenant_id=tenant_id if tenant_id != "admin" else None,  # Admin sees all contracts
        category=category
    )

    # Convert to response schema
    minting_contracts = [
        AvailableContractInfo(
            name=c.name.value,
            file_path=c.file_path,
            description=c.description,
            category=c.category.value,
            requires_params=c.requires_params,
            param_description=", ".join(p.description for p in c.parameters) if c.parameters else None,
            tags=c.tags
        )
        for c in contracts_dict["minting"]
    ]

    spending_contracts = [
        AvailableContractInfo(
            name=c.name.value,
            file_path=c.file_path,
            description=c.description,
            category=c.category.value,
            requires_params=c.requires_params,
            param_description=", ".join(p.description for p in c.parameters) if c.parameters else None,
            tags=c.tags
        )
        for c in contracts_dict["spending"]
    ]

    return AvailableContractsResponse(
        minting=minting_contracts,
        spending=spending_contracts,
        total=len(minting_contracts) + len(spending_contracts)
    )


@router.post(
    "/compile",
    response_model=CompileContractResponse,
    summary="Compile registry contract (CORE only)",
    description="Compile a pre-defined contract from the registry. Use GET /available to see available contracts. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request or compilation failed"},
        401: {"model": ContractErrorResponse, "description": "Authentication required"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required or contract not available for tenant"},
        404: {"model": ContractErrorResponse, "description": "Contract not found in registry"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_contract(
    request: CompileContractRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    tenant_id: str = Depends(get_tenant_context)
) -> CompileContractResponse:
    """
    Compile a registry contract (CORE wallets only).

    This endpoint compiles **pre-defined contracts** from the contract registry.
    These are audited, production-ready contracts maintained by your organization.

    **Available Contracts:**
    - Call `GET /api/v1/contracts/available` to browse all registry contracts
    - Contracts are categorized: core_protocol, project_management, token_management, testing

    **Registry Contracts:**
    - ✅ Audited and reviewed
    - ✅ Part of official protocol
    - ✅ Subject to tenant filtering rules
    - ✅ Versioned and tracked

    ---

    **Authentication Required:**
    - CORE wallet (Bearer token)
    - Valid API key (admin or tenant)

    **Tenant Permissions:**
    - Contracts may be enabled/disabled per tenant
    - Admin API key sees all contracts
    - Tenant API key sees only allowed contracts

    ---

    **Examples:**

    Simple contract (no parameters):
    ```json
    {
        "contract_name": "myUSDFree",
        "contract_type": "minting"
    }
    ```

    Parameterized contract:
    ```json
    {
        "contract_name": "grey",
        "contract_type": "minting",
        "compilation_params": ["<project_nfts_policy_id_bytes>"]
    }
    ```

    Spending validator:
    ```json
    {
        "contract_name": "protocol",
        "contract_type": "spending"
    }
    ```

    ---

    **For custom contracts:** Use `POST /api/v1/contracts/compile-custom` instead.
    """
    try:
        # Create registry service for tenant validation
        registry_service = ContractRegistryService(_registry)

        # Validate contract availability for tenant
        is_valid, error_msg = await registry_service.validate_contract_for_tenant(
            contract_name=request.contract_name,
            tenant_id=tenant_id if tenant_id != "admin" else "default"  # Admin can compile any contract
        )
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_msg)

        # Get wallet's network from database (MongoDB)
        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": core_wallet.wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {core_wallet.wallet_id} not found")

        # Convert to model to access network field
        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        # Create contract service
        contract_service = MongoContractService(database=tenant_db)

        # Get registry definition for metadata
        definition = _registry.get_definition(request.contract_name)

        # Get file path from registry
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
                           f"Use GET /api/v1/contracts/available to see available contracts. "
                           f"For custom contracts, use POST /api/v1/contracts/compile-custom"
                )

        # Compile from registered contract file
        full_path = f"src/terrasacha_contracts/{file_path}"
        contract = await contract_service.compile_contract_from_file(
            contract_path=full_path,
            contract_name=request.contract_name,
            network=db_wallet.network,
            contract_type=request.contract_type,
            wallet_id=core_wallet.wallet_id,
            compilation_params=request.compilation_params
        )

        # Add registry linkage fields
        contract.is_custom_contract = False
        contract.registry_contract_name = definition.name.value if definition else None
        contract.category = definition.category.value if definition else None

        # Save updated contract with registry linkage fields
        if tenant_db is not None:
            collection = tenant_db.get_collection("contracts")
            contract_dict = contract.model_dump(by_alias=True, exclude={"id"})
            contract_dict["_id"] = contract.policy_id
            contract_dict.pop("policy_id", None)
            await collection.replace_one({"_id": contract.policy_id}, contract_dict, upsert=True)

        return CompileContractResponse(
            success=True,
            policy_id=contract.policy_id,
            contract_name=contract.name,
            cbor_hex=contract.cbor_hex,
            testnet_address=contract.testnet_addr,
            mainnet_address=contract.mainnet_addr,
            contract_type=contract.contract_type,
            source_hash=contract.source_hash,
            version=contract.version,
            compiled_at=contract.compiled_at,
            category=contract.category,
            is_custom_contract=contract.is_custom_contract
        )

    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile contract: {str(e)}")


@router.post(
    "/compile-custom",
    response_model=CompileContractResponse,
    summary="Compile custom contract from source (CORE only)",
    description="Compile a custom Opshin smart contract from source code. Requires CORE wallet and tenant permission.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid source code or compilation failed"},
        401: {"model": ContractErrorResponse, "description": "Authentication required"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required or custom contracts not allowed for tenant"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_custom_contract(
    request: CompileCustomContractRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    tenant_id: str = Depends(get_tenant_context)
) -> CompileContractResponse:
    """
    Compile a custom Opshin smart contract from source code (CORE wallets only).

    This endpoint allows you to compile **custom smart contracts** from raw Opshin source code.

    **⚠️ Important:**
    - Custom contracts are NOT audited
    - Test thoroughly before using on mainnet
    - Requires tenant permission (`allow_custom_contracts = true`)
    - Admin API key always allowed
    - Results in `is_custom_contract = true` in database

    **Use Cases:**
    - Experimental contracts
    - Tenant-specific business logic
    - Rapid prototyping
    - Testing new contract ideas

    ---

    **Authentication Required:**
    - CORE wallet (Bearer token)
    - Valid API key (admin or tenant)

    **Tenant Permissions:**
    - Requires `allow_custom_contracts = true` in tenant configuration
    - Admin API key bypasses this requirement

    ---

    **Source Code Requirements:**
    - Must start with `#!opshin` shebang
    - For spending validators: `def validator(datum, redeemer, context) -> None`
    - For minting policies: `def validator(redeemer, context) -> None`

    ---

    **Example: Always-succeeds validator**
    ```json
    {
        "contract_name": "my_test_validator",
        "contract_type": "spending",
        "source_code": "#!opshin\\nfrom opshin.prelude import *\\n\\ndef validator(datum: Nothing, redeemer: Nothing, context: ScriptContext) -> None:\\n    assert True, \\"Always succeeds\\""
    }
    ```

    **Example: Signature-check minting policy**
    ```json
    {
        "contract_name": "my_nft_policy",
        "contract_type": "minting",
        "source_code": "#!opshin\\nfrom opshin.prelude import *\\n\\ndef validator(redeemer: Nothing, context: ScriptContext) -> None:\\n    tx_info: TxInfo = context.tx_info\\n    required_pkh = bytes.fromhex(\\"fe2d2b5ba9a01b09b2d5c573a7fb2b46d4d8601d00dcc3fec1e1402d\\")\\n    assert required_pkh in tx_info.signatories, \\"Must be signed\\""
    }
    ```

    ---

    **For registry contracts:** Use `POST /api/v1/contracts/compile` instead.
    """
    try:
        # Create registry service for tenant validation
        registry_service = ContractRegistryService(_registry)

        # Check if custom contracts are allowed for tenant
        if tenant_id != "admin":  # Admin can always compile custom contracts
            is_allowed = await registry_service.is_custom_contract_allowed(tenant_id)
            if not is_allowed:
                raise HTTPException(
                    status_code=403,
                    detail="Custom contract compilation is not allowed for your tenant. Please contact your administrator."
                )

        # Get wallet's network from database (MongoDB)
        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": core_wallet.wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {core_wallet.wallet_id} not found")

        # Convert to model to access network field
        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        # Create contract service
        contract_service = MongoContractService(database=tenant_db)

        # Compile from custom source code
        contract = await contract_service.compile_contract_from_source(
            source_code=request.source_code,
            contract_name=request.contract_name,
            network=db_wallet.network,
            contract_type=request.contract_type,
            wallet_id=core_wallet.wallet_id,
            compilation_params=None  # Custom contracts don't support parameters in this version
        )

        # Mark as custom contract
        contract.is_custom_contract = True
        contract.registry_contract_name = None
        contract.category = None

        # Save contract to database
        if tenant_db is not None:
            collection = tenant_db.get_collection("contracts")
            contract_dict = contract.model_dump(by_alias=True, exclude={"id"})
            contract_dict["_id"] = contract.policy_id
            contract_dict.pop("policy_id", None)
            await collection.replace_one({"_id": contract.policy_id}, contract_dict, upsert=True)

        return CompileContractResponse(
            success=True,
            policy_id=contract.policy_id,
            contract_name=contract.name,
            cbor_hex=contract.cbor_hex,
            testnet_address=contract.testnet_addr,
            mainnet_address=contract.mainnet_addr,
            contract_type=contract.contract_type,
            source_hash=contract.source_hash,
            version=contract.version,
            compiled_at=contract.compiled_at,
            category=contract.category,
            is_custom_contract=contract.is_custom_contract
        )

    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile custom contract: {str(e)}")


@router.post(
    "/compile-protocol",
    response_model=CompileProtocolResponse,
    summary="Compile protocol contracts (CORE only)",
    description="Compile protocol_nfts minting policy and protocol spending validator. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request or no suitable UTXO"},
        401: {"model": ContractErrorResponse, "description": "Authentication required"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Wallet not found"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_protocol_contracts(
    request: CompileProtocolRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> CompileProtocolResponse:
    """
    Compile protocol contracts (protocol_nfts and protocol).

    This endpoint replicates the CLI "Compile Protocol Contracts" functionality (option 2).
    It compiles the core protocol contracts needed for the Terrasacha system:

    1. **protocol_nfts** - Minting policy for protocol authentication NFTs
    2. **protocol** - Spending validator for managing projects

    **Compilation Process:**
    1. Finds a suitable UTXO (>3 ADA) from the specified wallet
    2. Compiles `protocol_nfts.py` using the UTXO reference (makes policy unique)
    3. Compiles `protocol.py` using the protocol_nfts policy ID

    **UTXO Selection:**
    - By default, auto-selects the first UTXO with >3 ADA
    - Use `utxo_ref` parameter to specify a specific UTXO (format: `tx_hash:index`)

    ---

    **Authentication Required:**
    - CORE wallet (Bearer token)
    - Valid API key (admin or tenant)

    ---

    **Examples:**

    Auto-select UTXO:
    ```json
    {
        "force": true
    }
    ```

    Use authenticated wallet:
    ```json
    {
        "wallet_id": null,
        "force": true
    }
    ```

    Specify UTXO:
    ```json
    {
        "wallet_id": "abc123...",
        "utxo_ref": "abcd1234...ef:0",
        "force": true
    }
    ```

    ---

    **Response:**
    ```json
    {
        "success": true,
        "message": "Successfully compiled 2 protocol contracts",
        "protocol_nfts": {
            "policy_id": "abc123...",
            "contract_name": "protocol_nfts",
            "contract_type": "minting",
            "cbor_hex": "590abc..."
        },
        "protocol": {
            "policy_id": "def456...",
            "contract_name": "protocol",
            "contract_type": "spending",
            "testnet_address": "addr_test1..."
        },
        "compilation_utxo": {
            "tx_id": "abc123...",
            "index": 0,
            "amount_lovelace": 5000000,
            "amount_ada": 5.0
        }
    }
    ```
    """
    try:
        # Determine which wallet to use
        wallet_id = request.wallet_id or core_wallet.wallet_id

        # Get wallet from database
        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")

        # Convert to model
        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        # Create contract service
        contract_service = MongoContractService(database=tenant_db)

        # Compile protocol contracts
        result = await contract_service.compile_protocol_contracts(
            wallet_address=db_wallet.enterprise_address,
            network=db_wallet.network,
            wallet_id=core_wallet.wallet_id,
            chain_context=chain_context,
            utxo_ref=request.utxo_ref,
            force=request.force,
        )

        # Build response
        protocol_nfts_info = None
        protocol_info = None

        if result.get("protocol_nfts"):
            contract = result["protocol_nfts"]
            protocol_nfts_info = CompiledProtocolContractInfo(
                policy_id=contract.policy_id,
                contract_name=contract.name,
                contract_type=contract.contract_type,
                cbor_hex=contract.cbor_hex,
                testnet_address=contract.testnet_addr,
                mainnet_address=contract.mainnet_addr,
                version=contract.version,
                compiled_at=contract.compiled_at,
            )

        if result.get("protocol"):
            contract = result["protocol"]
            protocol_info = CompiledProtocolContractInfo(
                policy_id=contract.policy_id,
                contract_name=contract.name,
                contract_type=contract.contract_type,
                cbor_hex=contract.cbor_hex,
                testnet_address=contract.testnet_addr,
                mainnet_address=contract.mainnet_addr,
                version=contract.version,
                compiled_at=contract.compiled_at,
            )

        compilation_utxo = None
        if result.get("compilation_utxo"):
            utxo = result["compilation_utxo"]
            compilation_utxo = CompilationUtxoInfo(
                tx_id=utxo["tx_id"],
                index=utxo["index"],
                amount_lovelace=utxo["amount_lovelace"],
                amount_ada=utxo["amount_ada"],
            )

        return CompileProtocolResponse(
            success=result["success"],
            message=result["message"],
            protocol_nfts=protocol_nfts_info,
            protocol=protocol_info,
            compilation_utxo=compilation_utxo,
            skipped=result.get("skipped", False),
            error=result.get("error"),
        )

    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile protocol contracts: {str(e)}")


@router.post(
    "/{policy_id}/mint-protocol",
    response_model=MintProtocolResponse,
    summary="Build mint protocol NFTs transaction (CORE only)",
    description="Build an unsigned transaction to mint protocol REF and USER NFTs. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request or compilation UTXO not found"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Protocol contracts not found"},
        500: {"model": ContractErrorResponse, "description": "Transaction building failed"},
    },
)
async def mint_protocol_nfts(
    request: MintProtocolRequest,
    policy_id: str = Path(..., description="Policy ID of the compiled protocol_nfts minting policy"),
    destination_address: str | None = Query(
        None, description="Address to send USER token to. If not provided, uses the CORE wallet address."
    ),
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> MintProtocolResponse:
    """
    Build an unsigned minting transaction for protocol NFTs (CORE wallets only).

    This endpoint builds the transaction to mint protocol authentication NFTs:
    - **REF token**: Sent to the protocol contract address with a DatumProtocol
    - **USER token**: Sent to the destination address (or CORE wallet address)

    **Prerequisites:**
    - Protocol contracts must be compiled first: `POST /api/v1/contracts/compile-protocol`
    - The compilation UTXO must still be unspent on-chain

    **No password required** — only builds the unsigned transaction.

    **Flow:**
    1. `POST /api/v1/contracts/compile-protocol` -> note `protocol_nfts.policy_id`
    2. `POST /api/v1/contracts/{policy_id}/mint-protocol` (this endpoint) -> get `transaction_id`
    3. `POST /api/v1/transactions/sign` with `transaction_id` + password
    4. `POST /api/v1/transactions/submit` with `transaction_id`
    """
    try:
        wallet_id = core_wallet.wallet_id

        # Get wallet from database
        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")

        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        # Build minting transaction
        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.build_mint_protocol_transaction(
            wallet_address=db_wallet.enterprise_address,
            network=db_wallet.network,
            wallet_id=wallet_id,
            chain_context=chain_context,
            protocol_nfts_policy_id=policy_id,
            destination_address=destination_address,
            protocol_admins=request.protocol_admins,
            protocol_fee=request.protocol_fee,
            oracle_id=request.oracle_id,
            projects=request.projects,
        )

        return MintProtocolResponse(
            success=result["success"],
            transaction_id=result["transaction_id"],
            tx_cbor=result["tx_cbor"],
            protocol_token_name=result["protocol_token_name"],
            user_token_name=result["user_token_name"],
            minting_policy_id=result["minting_policy_id"],
            protocol_contract_address=result["protocol_contract_address"],
            compilation_utxo=CompilationUtxoInfo(
                tx_id=result["compilation_utxo"]["tx_id"],
                index=result["compilation_utxo"]["index"],
                amount_lovelace=result["compilation_utxo"]["amount_lovelace"],
                amount_ada=result["compilation_utxo"]["amount_ada"],
            ),
            fee_lovelace=result["fee_lovelace"],
            inputs=result["inputs"],
            outputs=result["outputs"],
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build minting transaction: {str(e)}")


@router.post(
    "/burn-protocol",
    response_model=BurnProtocolResponse,
    summary="Build burn protocol NFTs transaction (CORE only)",
    description="Build an unsigned transaction to burn protocol REF and USER NFTs. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request or tokens not found on-chain"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Protocol contracts not found"},
        500: {"model": ContractErrorResponse, "description": "Transaction building failed"},
    },
)
async def burn_protocol_nfts(
    request: BurnProtocolRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> BurnProtocolResponse:
    """
    Build an unsigned burn transaction for protocol NFTs (CORE wallets only).

    This endpoint builds the transaction to burn (destroy) protocol authentication NFTs:
    - **REF token**: Consumed from the protocol contract address
    - **USER token**: Consumed from the wallet address

    Both tokens are burned (negative mint) and cease to exist on-chain.

    **Prerequisites:**
    - Protocol NFTs must already be minted (REF at contract, USER at wallet)

    **Required Fields:**
    - `protocol_nfts_policy_id`: Which policy's tokens to burn

    **No password required** — only builds the unsigned transaction.

    **Flow:**
    1. `POST /api/v1/contracts/burn-protocol` (this endpoint) -> get `transaction_id`
    2. `POST /api/v1/transactions/sign` with `transaction_id` + password
    3. `POST /api/v1/transactions/submit` with `transaction_id`
    """
    try:
        # Determine which wallet to use
        wallet_id = request.wallet_id or core_wallet.wallet_id

        # Get wallet from database
        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")

        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        # Build burn transaction
        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.build_burn_protocol_transaction(
            wallet_address=db_wallet.enterprise_address,
            network=db_wallet.network,
            wallet_id=wallet_id,
            chain_context=chain_context,
            protocol_nfts_policy_id=request.protocol_nfts_policy_id,
        )

        return BurnProtocolResponse(
            success=result["success"],
            transaction_id=result["transaction_id"],
            tx_cbor=result["tx_cbor"],
            protocol_token_name=result["protocol_token_name"],
            user_token_name=result["user_token_name"],
            minting_policy_id=result["minting_policy_id"],
            protocol_contract_address=result["protocol_contract_address"],
            fee_lovelace=result["fee_lovelace"],
            inputs=result["inputs"],
            outputs=result["outputs"],
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build burn transaction: {str(e)}")


@router.post(
    "/invalidate",
    response_model=InvalidateContractResponse,
    summary="Invalidate contracts after burn (CORE only)",
    description="Mark a contract and its dependents as inactive after confirming the burn transaction landed on-chain. Works for protocol, project, and other contract types. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Already invalidated or no burn transaction found"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Contract not found"},
        500: {"model": ContractErrorResponse, "description": "Invalidation failed"},
    },
)
async def invalidate_contracts(
    request: InvalidateContractRequest,
    _core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
) -> InvalidateContractResponse:
    """
    Invalidate contracts after burn confirmation (CORE wallets only).

    After burning tokens (burn → sign → submit), the contracts are no longer
    functional on-chain. This endpoint marks them as inactive in the database.

    Works for any contract type: protocol, project, etc.

    **Prerequisites:**
    - A burn transaction (`burn_protocol`, `burn_project`, etc.) must exist in
      SUBMITTED or CONFIRMED state for the given policy_id

    **What it does:**
    - Marks the target contract as `is_active=false`
    - Finds any contracts compiled with this policy_id as a parameter
      (e.g., protocol spending validator depends on protocol_nfts policy_id)
      and marks them as `is_active=false` too
    - Records `invalidated_at` timestamp on all affected contracts

    **Idempotent guard:** Returns 400 if the contract is already invalidated.

    **Flow:**
    1. Burn: `POST /burn-protocol` (or project equivalent) → sign → submit
    2. Verify burn tx landed on-chain
    3. `POST /invalidate` (this endpoint) with the minting policy's `policy_id`
    """
    try:
        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.invalidate_contracts(
            policy_id=request.policy_id,
        )

        return InvalidateContractResponse(
            success=result["success"],
            message=result["message"],
            invalidated_contracts=[
                InvalidatedContractInfo(**c) for c in result["invalidated_contracts"]
            ],
            burn_tx_hash=result["burn_tx_hash"],
            burn_tx_status=result["burn_tx_status"],
            invalidated_at=result["invalidated_at"],
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ContractInvalidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invalidate contracts: {str(e)}")


@router.post(
    "/compile-project",
    response_model=CompileProjectResponse,
    summary="Compile project contracts (CORE only)",
    description="Compile project_nfts minting policy and project spending validator. Requires CORE wallet and existing protocol contracts.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request, no suitable UTXO, or name conflict"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Wallet or protocol contracts not found"},
        409: {"model": ContractErrorResponse, "description": "Contract name already exists"},
        500: {"model": ContractErrorResponse, "description": "Compilation failed"},
    },
)
async def compile_project_contracts(
    request: CompileProjectRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> CompileProjectResponse:
    """
    Compile project contracts (project_nfts and project).

    Compiles project-level contracts needed for a specific project:

    1. **project_nfts** - Minting policy for project authentication NFTs
    2. **project** - Spending validator for managing the project

    **Prerequisites:**
    - Protocol contracts must be compiled first: `POST /api/v1/contracts/compile-protocol`
    - A `protocol_nfts_policy_id` from the compile-protocol response

    **Compilation Process:**
    1. Finds a suitable UTXO (>3 ADA) from the specified wallet
    2. Compiles `project_nfts.py` using the UTXO + protocol_nfts_policy_id
    3. Compiles `project.py` using the project_nfts policy ID

    **Flow:**
    1. `POST /contracts/compile-protocol` -> note `protocol_nfts.policy_id`
    2. `POST /contracts/compile-project` (this endpoint)
    3. Deploy as reference script if needed: `POST /contracts/deploy-reference-script`
    """
    try:
        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": request.wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {request.wallet_id} not found")

        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        contract_service = MongoContractService(database=tenant_db)

        result = await contract_service.compile_project_contracts(
            wallet_address=db_wallet.enterprise_address,
            network=db_wallet.network,
            wallet_id=request.wallet_id,
            chain_context=chain_context,
            project_name=request.project_name,
            protocol_nfts_policy_id=request.protocol_nfts_policy_id,
            utxo_ref=request.utxo_ref,
            force=request.force,
        )

        # Build response
        project_nfts_info = None
        project_info = None

        if result.get("project_nfts"):
            contract = result["project_nfts"]
            project_nfts_info = CompiledProtocolContractInfo(
                policy_id=contract.policy_id,
                contract_name=contract.name,
                contract_type=contract.contract_type,
                cbor_hex=contract.cbor_hex,
                testnet_address=contract.testnet_addr,
                mainnet_address=contract.mainnet_addr,
                version=contract.version,
                compiled_at=contract.compiled_at,
            )

        if result.get("project"):
            contract = result["project"]
            project_info = CompiledProtocolContractInfo(
                policy_id=contract.policy_id,
                contract_name=contract.name,
                contract_type=contract.contract_type,
                cbor_hex=contract.cbor_hex,
                testnet_address=contract.testnet_addr,
                mainnet_address=contract.mainnet_addr,
                version=contract.version,
                compiled_at=contract.compiled_at,
            )

        compilation_utxo = None
        if result.get("compilation_utxo"):
            utxo = result["compilation_utxo"]
            compilation_utxo = CompilationUtxoInfo(
                tx_id=utxo["tx_id"],
                index=utxo["index"],
                amount_lovelace=utxo["amount_lovelace"],
                amount_ada=utxo["amount_ada"],
            )

        return CompileProjectResponse(
            success=result["success"],
            message=result["message"],
            project_nfts=project_nfts_info,
            project=project_info,
            compilation_utxo=compilation_utxo,
            protocol_nfts_policy_id=result.get("protocol_nfts_policy_id"),
            project_name=result.get("project_name"),
            skipped=result.get("skipped", False),
            error=result.get("error"),
        )

    except ContractAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile project contracts: {str(e)}")


@router.post(
    "/{policy_id}/mint-project",
    response_model=MintProjectResponse,
    summary="Build mint project NFTs transaction (CORE only)",
    description="Build an unsigned transaction to mint project REF and USER NFTs with initial DatumProject. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request or compilation UTXO not found"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Project contracts not found"},
        500: {"model": ContractErrorResponse, "description": "Transaction building failed"},
    },
)
async def mint_project_nfts(
    request: MintProjectRequest,
    policy_id: str = Path(..., description="Policy ID of the compiled project_nfts minting policy"),
    destination_address: str | None = Query(
        None, description="Address to send USER token to. If not provided, uses the CORE wallet address."
    ),
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> MintProjectResponse:
    """
    Build an unsigned minting transaction for project NFTs (CORE wallets only).

    This endpoint builds the transaction to mint project authentication NFTs:
    - **REF token**: Sent to the project contract address with a DatumProject
    - **USER token**: Sent to the destination address (or CORE wallet address)

    The minting policy validates that the protocol UTXO exists as a reference
    input and that an admin from the protocol datum signed the transaction.

    **Prerequisites:**
    - Protocol contracts must be compiled and minted first
    - Project contracts must be compiled: `POST /api/v1/contracts/compile-project`
    - The compilation UTXO must still be unspent on-chain

    **No password required** — only builds the unsigned transaction.

    **Flow:**
    1. `POST /api/v1/contracts/compile-project` -> note `project_nfts.policy_id`
    2. `POST /api/v1/contracts/{policy_id}/mint-project` (this endpoint) -> get `transaction_id`
    3. `POST /api/v1/transactions/sign` with `transaction_id` + password
    4. `POST /api/v1/transactions/submit` with `transaction_id`
    """
    try:
        wallet_id = core_wallet.wallet_id

        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")

        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        # Convert stakeholder/certification Pydantic models to dicts for service layer
        stakeholders_dicts = [s.model_dump() for s in request.stakeholders] if request.stakeholders else None
        certifications_dicts = [c.model_dump() for c in request.certifications] if request.certifications else None

        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.build_mint_project_transaction(
            wallet_address=db_wallet.enterprise_address,
            network=db_wallet.network,
            wallet_id=wallet_id,
            chain_context=chain_context,
            project_nfts_policy_id=policy_id,
            project_id=request.project_id,
            destination_address=destination_address,
            project_metadata=request.project_metadata,
            stakeholders=stakeholders_dicts,
            certifications=certifications_dicts,
            investment_tokens=request.investment_tokens,
        )

        return MintProjectResponse(
            success=result["success"],
            transaction_id=result["transaction_id"],
            tx_cbor=result["tx_cbor"],
            project_token_name=result["project_token_name"],
            user_token_name=result["user_token_name"],
            minting_policy_id=result["minting_policy_id"],
            project_contract_address=result["project_contract_address"],
            compilation_utxo=CompilationUtxoInfo(
                tx_id=result["compilation_utxo"]["tx_id"],
                index=result["compilation_utxo"]["index"],
                amount_lovelace=result["compilation_utxo"]["amount_lovelace"],
                amount_ada=result["compilation_utxo"]["amount_ada"],
            ),
            fee_lovelace=result["fee_lovelace"],
            inputs=result["inputs"],
            outputs=result["outputs"],
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build project minting transaction: {str(e)}")


# ============================================================================
# Contract Query Endpoints
# ============================================================================


@router.get(
    "/",
    response_model=DbContractListResponse,
    summary="List all compiled contracts",
    description="Get list of all compiled contracts stored in database. Optionally filter by network.",
)
async def list_contracts(
    network: str | None = None,
    enrich: bool = Query(
        False,
        description="When true, queries on-chain state to populate has_minted_tokens and balance_lovelace. "
        "Adds latency due to blockchain queries."
    ),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> DbContractListResponse:
    """
    List all compiled contracts from database.

    Returns contract metadata including:
    - Contract name and policy ID
    - Addresses (testnet/mainnet)
    - Version and compilation timestamp
    - Network (testnet/mainnet)
    - On-chain status (when `?enrich=true`)

    **Authentication Required:**
    - Valid API key (admin or tenant)

    **Query Parameters:**
    - `network` (optional): Filter by network ("testnet" or "mainnet")
    - `enrich` (optional, default false): Query blockchain for on-chain token status

    **Example:**
    ```
    GET /api/v1/contracts/
    GET /api/v1/contracts/?network=testnet
    GET /api/v1/contracts/?enrich=true
    ```
    """
    try:
        contract_service = MongoContractService(database=tenant_db)

        # Validate network filter
        network_filter = None
        if network:
            # Strip whitespace and convert to lowercase
            network_cleaned = network.strip().lower()
            if network_cleaned not in ["testnet", "mainnet"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid network: '{network}'. Must be 'testnet' or 'mainnet'"
                )
            network_filter = network_cleaned

        contracts, total = await contract_service.list_contracts(network=network_filter)

        # Enrich with on-chain status if requested
        enrichment: dict[str, dict] = {}
        if enrich:
            enrichment = await contract_service.enrich_contract_status(contracts, chain_context)

        contract_items = []
        for c in contracts:
            # Get description from registry for pre-defined contracts
            description = None
            if not c.is_custom_contract:
                contract_info = get_contract_info(c.name, c.contract_type)
                if contract_info:
                    description = contract_info["description"]

            status = enrichment.get(c.policy_id, {})

            contract_items.append(
                DbContractListItem(
                    policy_id=c.policy_id,
                    name=c.name,
                    description=description,
                    contract_type=c.contract_type,
                    testnet_address=c.testnet_addr,
                    mainnet_address=c.mainnet_addr,
                    compilation_params=c.compilation_params,
                    version=c.version,
                    source_hash=c.source_hash,
                    compiled_at=c.compiled_at,
                    network=c.network,
                    category=c.category,
                    is_custom_contract=c.is_custom_contract,
                    is_active=c.is_active,
                    invalidated_at=c.invalidated_at,
                    has_minted_tokens=status.get("has_minted_tokens"),
                    balance_lovelace=status.get("balance_lovelace"),
                )
            )

        return DbContractListResponse(
            contracts=contract_items,
            total=total
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
    tenant_db=Depends(get_tenant_database),
) -> CompileContractResponse:
    """
    Get detailed contract information by policy ID.

    Returns full contract details including:
    - Source code and hash
    - Compiled CBOR hex
    - Addresses and policy ID
    - Compilation parameters (UTXO ref, linked policy IDs)
    - Compilation metadata (version, timestamp)

    **Example:**
    ```
    GET /api/v1/contracts/a1b2c3d4e5f6...
    ```
    """
    try:
        contract_service = MongoContractService(database=tenant_db)
        contract = await contract_service.get_contract(policy_id)

        # Get description from registry for pre-defined contracts
        description = None
        if not contract.is_custom_contract:
            contract_info = get_contract_info(contract.name, contract.contract_type)
            if contract_info:
                description = contract_info["description"]

        return CompileContractResponse(
            success=True,
            policy_id=contract.policy_id,
            contract_name=contract.name,
            description=description,
            cbor_hex=contract.cbor_hex,
            testnet_address=contract.testnet_addr,
            mainnet_address=contract.mainnet_addr,
            contract_type=contract.contract_type,
            compilation_params=contract.compilation_params,
            source_hash=contract.source_hash,
            version=contract.version,
            compiled_at=contract.compiled_at,
            category=contract.category,
            is_custom_contract=contract.is_custom_contract,
            is_active=contract.is_active,
            invalidated_at=contract.invalidated_at,
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get contract: {str(e)}")


@router.get(
    "/{policy_id}/datum",
    response_model=ContractDatumResponse,
    summary="Query on-chain datum for a contract",
    description="Query the current on-chain datum for a protocol, project, or investor contract. "
    "Accepts any policy_id (minting policy or spending validator). Read-only, no CORE wallet required.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Cannot resolve contract or UTXO not found"},
        404: {"model": ContractErrorResponse, "description": "Contract not found"},
        500: {"model": ContractErrorResponse, "description": "Failed to query datum"},
    },
)
async def get_contract_datum(
    policy_id: str = Path(..., description="Contract policy ID (minting policy or spending validator)"),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> ContractDatumResponse:
    """
    Query the current on-chain datum for a contract.

    Accepts any `policy_id` — minting policy (e.g. `protocol_nfts_policy_id`)
    or spending validator (e.g. `protocol_policy_id`). The endpoint resolves
    the spending address and locates the UTXO holding the REF token, then
    decodes the attached datum.

    **Supported contract types:** protocol, project, investor

    **Example:**
    ```
    GET /api/v1/contracts/{protocol_nfts_policy_id}/datum
    GET /api/v1/contracts/{project_nfts_policy_id}/datum
    ```
    """
    try:
        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.get_contract_datum(
            policy_id=policy_id,
            chain_context=chain_context,
        )

        return ContractDatumResponse(**result)

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query contract datum: {str(e)}")


# ============================================================================
# Contract Management Endpoints
# ============================================================================


@router.delete(
    "/{policy_id}",
    summary="Delete contract (CORE only)",
    description="Delete a contract from the database. Validates on-chain state before deletion. Requires CORE wallet.",
    responses={
        404: {"model": ContractErrorResponse, "description": "Contract not found"},
        409: {"model": ContractErrorResponse, "description": "Contract has active tokens or dependencies"},
    },
)
async def delete_contract(
    policy_id: str = Path(..., description="Contract policy ID to delete"),
    _core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> dict:
    """
    Delete a contract from the database (CORE wallets only).

    Validates on-chain state before deletion:
    - Blocks deletion if active tokens exist on-chain (returns 409 with burn guidance)
    - Blocks deletion of protocol contracts with dependent project contracts

    **Authentication Required:**
    - CORE wallet only (admin privileges)

    **Example:**
    ```
    DELETE /api/v1/contracts/a1b2c3d4e5f6...
    ```
    """
    try:
        contract_service = MongoContractService(database=tenant_db)
        await contract_service.delete_contract(policy_id, chain_context=chain_context)

        return {
            "success": True,
            "message": f"Contract {policy_id} deleted successfully"
        }

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ContractDeleteBlockedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete contract: {str(e)}")
