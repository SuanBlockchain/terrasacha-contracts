"""
Contract Endpoints

FastAPI endpoints for smart contract compilation and querying.
Database-backed contract management for API workflow.

Note: CLI workflow uses JSON files (ContractManager) - this is API-only.
"""

from fastapi import APIRouter, Depends, HTTPException, Path

from api.registries.contract_registry import list_all_contracts, get_contract_file_path, get_contract_info, _registry
from api.services.contract_registry_service import ContractRegistryService
from api.dependencies.tenant import get_tenant_database, get_tenant_context
from api.database.models import WalletMongo
from api.dependencies.auth import WalletAuthContext, require_core_wallet
from api.schemas.contract import (
    AvailableContractInfo,
    AvailableContractsResponse,
    CompilationUtxoInfo,
    CompiledProtocolContractInfo,
    CompileContractRequest,
    CompileCustomContractRequest,
    CompileContractResponse,
    CompileProtocolRequest,
    CompileProtocolResponse,
    ContractErrorResponse,
    DbContractListItem,
    DbContractListResponse,
    MintProtocolRequest,
    MintProtocolResponse,
)
from api.services.contract_service_mongo import (
    MongoContractService,
    ContractCompilationError,
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
    "/mint-protocol",
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
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> MintProtocolResponse:
    """
    Build an unsigned minting transaction for protocol NFTs (CORE wallets only).

    This endpoint builds the transaction to mint protocol authentication NFTs:
    - **REF token**: Sent to the protocol contract address with a DatumProtocol
    - **USER token**: Sent to the destination address (or wallet address)

    **Prerequisites:**
    - Protocol contracts must be compiled first: `POST /api/v1/contracts/compile-protocol`
    - The compilation UTXO must still be unspent on-chain

    **Required Fields:**
    - `protocol_nfts_policy_id`: Which compiled protocol_nfts to use. Get this from
      the `compile-protocol` response or `GET /api/v1/contracts/`

    **No password required** — only builds the unsigned transaction.

    **Flow:**
    1. `POST /api/v1/contracts/compile-protocol` -> note `protocol_nfts.policy_id`
    2. `POST /api/v1/contracts/mint-protocol` (this endpoint) -> get `transaction_id`
    3. `POST /api/v1/transactions/sign` with `transaction_id` + password
    4. `POST /api/v1/transactions/submit` with `transaction_id`
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

        # Build minting transaction
        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.build_mint_protocol_transaction(
            wallet_address=db_wallet.enterprise_address,
            network=db_wallet.network,
            wallet_id=wallet_id,
            chain_context=chain_context,
            protocol_nfts_policy_id=request.protocol_nfts_policy_id,
            destination_address=request.destination_address,
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
    tenant_db=Depends(get_tenant_database),
) -> DbContractListResponse:
    """
    List all compiled contracts from database.

    Returns contract metadata including:
    - Contract name and policy ID
    - Addresses (testnet/mainnet)
    - Version and compilation timestamp
    - Network (testnet/mainnet)

    **Authentication Required:**
    - Valid API key (admin or tenant)

    **Query Parameters:**
    - `network` (optional): Filter by network ("testnet" or "mainnet")

    **Example:**
    ```
    GET /api/v1/contracts/
    GET /api/v1/contracts/?network=testnet
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

        contract_items = []
        for c in contracts:
            # Get description from registry for pre-defined contracts
            description = None
            if not c.is_custom_contract:
                contract_info = get_contract_info(c.name, c.contract_type)
                if contract_info:
                    description = contract_info["description"]

            contract_items.append(
                DbContractListItem(
                    policy_id=c.policy_id,
                    name=c.name,
                    description=description,
                    contract_type=c.contract_type,
                    testnet_address=c.testnet_addr,
                    mainnet_address=c.mainnet_addr,
                    version=c.version,
                    source_hash=c.source_hash,
                    compiled_at=c.compiled_at,
                    network=c.network,
                    category=c.category,
                    is_custom_contract=c.is_custom_contract
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
            source_hash=contract.source_hash,
            version=contract.version,
            compiled_at=contract.compiled_at,
            category=contract.category,
            is_custom_contract=contract.is_custom_contract
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
    tenant_db=Depends(get_tenant_database),
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
        contract_service = MongoContractService(database=tenant_db)
        await contract_service.delete_contract(policy_id)

        return {
            "success": True,
            "message": f"Contract {policy_id} deleted successfully"
        }

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete contract: {str(e)}")
