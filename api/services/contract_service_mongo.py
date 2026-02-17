"""
MongoDB Contract Service

Business logic for compiling and managing smart contracts.
Supports Opshin contract compilation with versioning and multi-tenant isolation.

MongoDB/Beanie version for multi-tenant architecture.
"""

import hashlib
import sys
import tempfile
import pathlib
from datetime import datetime, timezone
from typing import Optional

from opshin.builder import PlutusContract, build
import pycardano as pc

from api.database.models import ContractMongo, TransactionMongo
from api.enums import TransactionStatus


# Custom exceptions
class ContractCompilationError(Exception):
    """Raised when Opshin compilation fails"""
    pass


class ContractNotFoundError(Exception):
    """Raised when contract not found in database"""
    pass


class ContractAlreadyExistsError(Exception):
    """Raised when trying to compile a contract that already exists"""
    pass


class InvalidContractParametersError(Exception):
    """Raised when compilation parameters are invalid"""
    pass


class ContractInvalidationError(Exception):
    """Raised when contract invalidation fails (e.g., already invalidated, no burn tx)"""
    pass


class ContractDeleteBlockedError(Exception):
    """Raised when contract deletion is blocked by active on-chain tokens or dependencies"""
    pass


class MongoContractService:
    """Service for managing smart contract compilation (MongoDB version)"""

    def __init__(self, database=None):
        """
        Initialize contract service with optional database context.

        Args:
            database: MongoDB database instance for tenant isolation.
                     If None, uses the globally initialized database (not recommended for multi-tenant).
        """
        self.database = database

    def _get_contract_collection(self):
        """Get the contracts collection from the tenant database."""
        if self.database is not None:
            return self.database.get_collection("contracts")
        return None

    async def _find_contract_by_policy_id(self, policy_id: str) -> Optional[ContractMongo]:
        """Find contract by policy_id using tenant database."""
        if self.database is not None:
            collection = self._get_contract_collection()
            contract_dict = await collection.find_one({"_id": policy_id})
            if contract_dict:
                # Convert _id to policy_id for the model
                contract_dict["policy_id"] = contract_dict.pop("_id")
                return ContractMongo.model_validate(contract_dict)
            return None
        else:
            return await ContractMongo.find_one(ContractMongo.policy_id == policy_id)

    async def compile_contract_from_file(
        self,
        contract_path: str,
        contract_name: str,
        network: str,
        contract_type: str,
        wallet_id: str,
        compilation_params: Optional[list] = None,
        description: Optional[str] = None,
    ) -> ContractMongo:
        """
        Compile a smart contract from a file using Opshin.

        Args:
            contract_path: Path to the Opshin contract file (.py)
            contract_name: Human-readable name for the contract
            network: "testnet" or "mainnet"
            contract_type: "spending" or "minting"
            wallet_id: ID of the CORE wallet compiling the contract
            compilation_params: Optional list of parameters for compilation
            description: Optional description of the contract

        Returns:
            ContractMongo: The compiled and stored contract

        Raises:
            ContractCompilationError: If compilation fails
            FileNotFoundError: If contract file doesn't exist
        """
        # Verify file exists
        contract_file = pathlib.Path(contract_path)
        if not contract_file.exists():
            raise FileNotFoundError(f"Contract file not found: {contract_path}")

        # Read source code
        with open(contract_path, 'r') as f:
            source_code = f.read()

        # Calculate source hash for versioning
        source_hash = hashlib.sha256(source_code.encode()).hexdigest()

        # Check for existing contract with same source
        if self.database is not None:
            collection = self._get_contract_collection()
            existing = await collection.find_one({
                "name": contract_name,
                "network": network,
                "source_hash": source_hash
            })

            if existing:
                # Already compiled this exact version
                existing["policy_id"] = existing.pop("_id")
                return ContractMongo.model_validate(existing)

        # Compile using Opshin
        try:
            if compilation_params:
                # Convert string parameters to appropriate types if needed
                processed_params = []
                for param in compilation_params:
                    # Handle common parameter types
                    if param.startswith("0x"):
                        # Hex string - convert to bytes
                        processed_params.append(bytes.fromhex(param[2:]))
                    else:
                        # Keep as is
                        processed_params.append(param)

                compiled = build(str(contract_file), *processed_params)
            else:
                compiled = build(str(contract_file))
        except Exception as e:
            raise ContractCompilationError(f"Opshin compilation failed: {str(e)}")

        # Extract compiled artifacts
        try:
            plutus_contract = PlutusContract(compiled)
            policy_id = plutus_contract.policy_id
            cbor_hex = plutus_contract.cbor.hex()

            # Get addresses (only applicable for spending validators)
            testnet_addr = None
            mainnet_addr = None
            if contract_type == "spending":
                if hasattr(plutus_contract, 'testnet_addr') and plutus_contract.testnet_addr:
                    testnet_addr = str(plutus_contract.testnet_addr)
                if hasattr(plutus_contract, 'mainnet_addr') and plutus_contract.mainnet_addr:
                    mainnet_addr = str(plutus_contract.mainnet_addr)
        except Exception as e:
            raise ContractCompilationError(f"Failed to extract compiled artifacts: {str(e)}")

        # Version management (increment if recompiling same contract name)
        version = 1
        if self.database is not None:
            collection = self._get_contract_collection()
            existing_versions = await collection.find({
                "name": contract_name,
                "network": network
            }).sort("version", -1).limit(1).to_list(1)

            if existing_versions:
                version = existing_versions[0]["version"] + 1

        # Create contract record
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        contract = ContractMongo(
            policy_id=policy_id,
            name=contract_name,
            contract_type=contract_type,
            cbor_hex=cbor_hex,
            testnet_addr=testnet_addr,
            mainnet_addr=mainnet_addr,
            source_file=str(contract_path),
            source_hash=source_hash,
            compilation_params=[str(p) for p in compilation_params] if compilation_params else None,
            version=version,
            network=network,
            wallet_id=wallet_id,
            description=description,
            compiled_at=now,
            created_at=now,
            updated_at=now
        )

        # Save to MongoDB
        if self.database is not None:
            collection = self._get_contract_collection()
            contract_dict = contract.model_dump(by_alias=True, exclude={"id"})
            # Use policy_id as _id for unique constraint
            contract_dict["_id"] = contract.policy_id
            contract_dict.pop("policy_id", None)  # Remove duplicate field

            try:
                await collection.insert_one(contract_dict)
            except Exception as e:
                if "duplicate key" in str(e).lower():
                    raise ContractAlreadyExistsError(
                        f"Contract with policy_id '{policy_id}' already exists"
                    )
                raise ContractCompilationError(f"Failed to save contract: {str(e)}")
        else:
            await contract.insert()

        return contract

    async def compile_contract_from_source(
        self,
        source_code: str,
        contract_name: str,
        network: str,
        contract_type: str,
        wallet_id: str,
        compilation_params: Optional[list] = None,
        description: Optional[str] = None,
    ) -> ContractMongo:
        """
        Compile a smart contract from source code using Opshin.

        Args:
            source_code: Opshin contract source code
            contract_name: Human-readable name for the contract
            network: "testnet" or "mainnet"
            contract_type: "spending" or "minting"
            wallet_id: ID of the CORE wallet compiling the contract
            compilation_params: Optional list of parameters for compilation
            description: Optional description of the contract

        Returns:
            ContractMongo: The compiled and stored contract

        Raises:
            ContractCompilationError: If compilation fails
        """
        # Calculate source hash
        source_hash = hashlib.sha256(source_code.encode()).hexdigest()

        # Check for existing contract with same source
        if self.database is not None:
            collection = self._get_contract_collection()
            existing = await collection.find_one({
                "name": contract_name,
                "network": network,
                "source_hash": source_hash
            })

            if existing:
                # Already compiled this exact version
                existing["policy_id"] = existing.pop("_id")
                return ContractMongo.model_validate(existing)

        # Create temporary file for compilation
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(source_code)
                temp_path = temp_file.name

            # Compile from the temporary file
            contract = await self.compile_contract_from_file(
                contract_path=temp_path,
                contract_name=contract_name,
                network=network,
                contract_type=contract_type,
                wallet_id=wallet_id,
                compilation_params=compilation_params,
                description=description,
            )

            return contract
        finally:
            # Clean up temporary file
            try:
                pathlib.Path(temp_path).unlink()
            except Exception:
                pass  # Ignore cleanup errors

    async def list_contracts(
        self,
        network: Optional[str] = None,
        contract_type: Optional[str] = None,
        wallet_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContractMongo], int]:
        """
        List compiled contracts with optional filtering.

        Args:
            network: Filter by network ("testnet" or "mainnet")
            contract_type: Filter by contract type ("spending" or "minting")
            wallet_id: Filter by wallet ID
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            Tuple of (list of contracts, total count)
        """
        if self.database is not None:
            collection = self._get_contract_collection()

            # Build query filter
            query_filter = {}
            if network:
                query_filter["network"] = network
            if contract_type:
                query_filter["contract_type"] = contract_type
            if wallet_id:
                query_filter["wallet_id"] = wallet_id

            # Get total count
            total = await collection.count_documents(query_filter)

            # Get contracts
            cursor = collection.find(query_filter).sort("created_at", -1).skip(offset).limit(limit)
            contracts_list = await cursor.to_list(length=limit)

            # Convert to models
            contracts = []
            for contract_dict in contracts_list:
                contract_dict["policy_id"] = contract_dict.pop("_id")
                contracts.append(ContractMongo.model_validate(contract_dict))

            return contracts, total
        else:
            # Fallback to Beanie query
            query = ContractMongo.find()
            if network:
                query = query.find(ContractMongo.network == network)
            if contract_type:
                query = query.find(ContractMongo.contract_type == contract_type)
            if wallet_id:
                query = query.find(ContractMongo.wallet_id == wallet_id)

            total = await query.count()
            contracts = await query.sort(-ContractMongo.created_at).skip(offset).limit(limit).to_list()

            return contracts, total

    async def get_contract(self, policy_id: str) -> ContractMongo:
        """
        Get a contract by policy ID.

        Args:
            policy_id: The contract's policy ID (script hash)

        Returns:
            ContractMongo: The contract

        Raises:
            ContractNotFoundError: If contract not found
        """
        contract = await self._find_contract_by_policy_id(policy_id)
        if not contract:
            raise ContractNotFoundError(f"Contract not found: {policy_id}")
        return contract

    async def get_reserved_compilation_utxos(self) -> set[str]:
        """
        Get UTXO refs reserved for contract compilation (not yet minted).

        Returns a set of "tx_hash:index" strings for UTXOs that are stored
        in compilation_params of minting policy contracts. These UTXOs must
        not be spent by regular transactions since they're needed for minting.
        """
        reserved = set()
        if self.database is None:
            return reserved
        collection = self._get_contract_collection()
        async for doc in collection.find({"compilation_params": {"$exists": True}}):
            params = doc.get("compilation_params", [])
            if params:
                first_param = params[0]
                if ":" in first_param and len(first_param) > 60:
                    reserved.add(first_param)
        return reserved

    async def get_contract_datum(self, policy_id: str, chain_context) -> dict:
        """
        Query the current on-chain datum for a contract identified by policy_id.

        Accepts any policy_id (minting or spending). Resolves to the correct
        spending address and minting policy to locate the UTXO holding the
        REF token, then decodes the attached datum.

        Args:
            policy_id: Any contract policy_id (minting policy or spending validator)
            chain_context: CardanoChainContext instance

        Returns:
            dict with contract_name, contract_type, datum dict, utxo_ref, balance

        Raises:
            ContractNotFoundError: If contract not found
            InvalidContractParametersError: If UTXO/datum cannot be located
        """
        from terrasacha_contracts.util import DatumProtocol, DatumProject, DatumInvestor
        from api.services.transaction_service_mongo import _extract_amount_from_value

        if self.database is None:
            raise ContractCompilationError("Database context required for datum queries")

        collection = self._get_contract_collection()

        # 1. Look up the contract
        contract_doc = await collection.find_one({"_id": policy_id})
        if not contract_doc:
            raise ContractNotFoundError(f"Contract not found: {policy_id}")

        contract_doc["policy_id"] = contract_doc.pop("_id")
        contract = ContractMongo.model_validate(contract_doc)

        registry_name = contract.registry_contract_name
        contract_type = contract.contract_type

        # 2. Determine the spending address and minting policy_id
        #    - If this is a minting policy (e.g. protocol_nfts, project_nfts):
        #      find the associated spending validator and use its address
        #    - If this is a spending validator (e.g. protocol, project, investor):
        #      use its own address and find the associated minting policy
        spending_contract = None
        minting_policy_id_hex = None

        if contract_type == "minting":
            # This is a minting policy — find the spending validator compiled with this policy_id
            minting_policy_id_hex = contract.policy_id

            # Determine the expected spending validator name
            spending_name_map = {
                "protocol_nfts": "protocol",
                "project_nfts": "project",
            }
            expected_spending_name = spending_name_map.get(registry_name)
            if not expected_spending_name:
                raise InvalidContractParametersError(
                    f"Cannot resolve spending validator for minting policy '{registry_name}' ({policy_id}). "
                    "Datum query is supported for protocol_nfts, project_nfts, protocol, project, and investor contracts."
                )

            spending_docs = await collection.find({
                "registry_contract_name": expected_spending_name,
                "compilation_params": [contract.policy_id],
            }).sort("compiled_at", -1).limit(1).to_list(1)

            if not spending_docs:
                raise ContractNotFoundError(
                    f"Spending validator '{expected_spending_name}' compiled with policy {policy_id} not found."
                )

            spending_doc = spending_docs[0]
            spending_doc["policy_id"] = spending_doc.pop("_id")
            spending_contract = ContractMongo.model_validate(spending_doc)

        elif contract_type == "spending":
            spending_contract = contract

            # Find the minting policy from compilation_params
            if contract.compilation_params and len(contract.compilation_params) > 0:
                minting_policy_id_hex = contract.compilation_params[0]
            else:
                raise InvalidContractParametersError(
                    f"Spending validator '{registry_name}' ({policy_id}) has no compilation_params — "
                    "cannot determine which minting policy's token to look for."
                )
        else:
            raise InvalidContractParametersError(
                f"Unsupported contract_type '{contract_type}' for datum query."
            )

        # 3. Get the spending address
        network = spending_contract.network
        if network == "testnet":
            if not spending_contract.testnet_addr:
                raise InvalidContractParametersError(
                    f"Spending contract {spending_contract.policy_id} has no testnet address."
                )
            spending_address = pc.Address.from_primitive(spending_contract.testnet_addr)
        else:
            if not spending_contract.mainnet_addr:
                raise InvalidContractParametersError(
                    f"Spending contract {spending_contract.policy_id} has no mainnet address."
                )
            spending_address = pc.Address.from_primitive(spending_contract.mainnet_addr)

        minting_script_hash = pc.ScriptHash(bytes.fromhex(minting_policy_id_hex))

        # 4. Query UTXOs at the spending address and find the one with the minting policy's token
        utxos = chain_context.context.utxos(spending_address)
        if not utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at contract address {spending_address}"
            )

        target_utxo = None
        for utxo in utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == minting_script_hash:
                        target_utxo = utxo
                        break
            if target_utxo:
                break

        if not target_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with minting policy {minting_policy_id_hex} found at {spending_address}"
            )

        # 5. Decode the datum
        if not target_utxo.output.datum:
            raise InvalidContractParametersError(
                f"UTXO at {spending_address} has no inline datum attached."
            )

        # Determine the datum type from the spending contract's registry name
        spending_name = spending_contract.registry_contract_name or ""

        if spending_name == "protocol":
            datum_obj = DatumProtocol.from_cbor(target_utxo.output.datum.cbor)
            datum_type = "protocol"
            datum_dict = {
                "project_admins": [a.hex() for a in datum_obj.project_admins],
                "protocol_fee": datum_obj.protocol_fee,
                "oracle_id": datum_obj.oracle_id.hex() if datum_obj.oracle_id else "",
                "projects": [p.hex() for p in datum_obj.projects],
            }
        elif spending_name == "project":
            datum_obj = DatumProject.from_cbor(target_utxo.output.datum.cbor)
            datum_type = "project"

            def _bool_data_to_str(bd) -> str:
                return "True" if bd.CONSTR_ID == 1 else "False"

            datum_dict = {
                "params": {
                    "project_id": datum_obj.params.project_id.hex(),
                    "project_metadata": datum_obj.params.project_metadata.hex() if datum_obj.params.project_metadata else "",
                    "project_state": datum_obj.params.project_state,
                },
                "project_token": {
                    "policy_id": datum_obj.project_token.policy_id.hex() if datum_obj.project_token.policy_id else "",
                    "token_name": datum_obj.project_token.token_name.hex() if datum_obj.project_token.token_name else "",
                    "total_supply": datum_obj.project_token.total_supply,
                },
                "stakeholders": [
                    {
                        "stakeholder": s.stakeholder.hex(),
                        "pkh": s.pkh.hex(),
                        "participation": s.participation,
                        "claimed": _bool_data_to_str(s.claimed),
                    }
                    for s in datum_obj.stakeholders
                ],
                "certifications": [
                    {
                        "certification_date": c.certification_date,
                        "quantity": c.quantity,
                        "real_certification_date": c.real_certification_date,
                        "real_quantity": c.real_quantity,
                    }
                    for c in datum_obj.certifications
                ],
            }
        elif spending_name == "investor":
            datum_obj = DatumInvestor.from_cbor(target_utxo.output.datum.cbor)
            datum_type = "investor"
            datum_dict = {
                "seller_pkh": datum_obj.seller_pkh.hex(),
                "grey_token_amount": datum_obj.grey_token_amount,
                "price_per_token": {
                    "price": datum_obj.price_per_token.price,
                    "precision": datum_obj.price_per_token.precision,
                },
                "min_purchase_amount": datum_obj.min_purchase_amount,
            }
        else:
            raise InvalidContractParametersError(
                f"Unsupported contract type '{spending_name}' for datum decoding. "
                "Supported: protocol, project, investor."
            )

        # 6. Build response
        utxo_ref = f"{target_utxo.input.transaction_id.payload.hex()}:{target_utxo.input.index}"
        balance_lovelace = target_utxo.output.amount.coin

        return {
            "success": True,
            "contract_name": spending_contract.name,
            "contract_type": datum_type,
            "datum": datum_dict,
            "utxo_ref": utxo_ref,
            "balance_lovelace": balance_lovelace,
            "balance_ada": balance_lovelace / 1_000_000,
        }

    async def enrich_contract_status(
        self, contracts: list[ContractMongo], chain_context
    ) -> dict[str, dict]:
        """
        For each spending validator, check if it has active tokens on-chain.
        Returns dict keyed by policy_id -> {has_minted_tokens, balance_lovelace}.

        For minting policies, maps their status to the associated spending validator's status.
        """
        enrichment: dict[str, dict] = {}
        if self.database is None or not contracts:
            return enrichment

        collection = self._get_contract_collection()

        # Separate spending validators and minting policies
        spending_contracts = [c for c in contracts if c.contract_type == "spending"]
        minting_contracts = [c for c in contracts if c.contract_type == "minting"]

        # Query on-chain status for each spending validator
        spending_status: dict[str, dict] = {}  # policy_id -> {has_minted_tokens, balance_lovelace}
        for sc in spending_contracts:
            network = sc.network
            address_str = sc.testnet_addr if network == "testnet" else sc.mainnet_addr
            if not address_str:
                enrichment[sc.policy_id] = {"has_minted_tokens": False, "balance_lovelace": 0}
                spending_status[sc.policy_id] = enrichment[sc.policy_id]
                continue

            try:
                spending_address = pc.Address.from_primitive(address_str)
                utxos = chain_context.context.utxos(spending_address)

                total_lovelace = sum(u.output.amount.coin for u in utxos)
                has_tokens = any(
                    u.output.amount.multi_asset
                    for u in utxos
                )
                enrichment[sc.policy_id] = {
                    "has_minted_tokens": has_tokens,
                    "balance_lovelace": total_lovelace,
                }
                spending_status[sc.policy_id] = enrichment[sc.policy_id]
            except Exception:
                enrichment[sc.policy_id] = {"has_minted_tokens": None, "balance_lovelace": None}
                spending_status[sc.policy_id] = enrichment[sc.policy_id]

        # For minting policies, find the linked spending validator and mirror its status
        spending_name_map = {
            "protocol_nfts": "protocol",
            "project_nfts": "project",
        }
        for mc in minting_contracts:
            registry_name = mc.registry_contract_name
            expected_spending = spending_name_map.get(registry_name)
            if not expected_spending:
                enrichment[mc.policy_id] = {"has_minted_tokens": None, "balance_lovelace": None}
                continue

            # Check if linked spending validator is already in our list
            linked = None
            for sc in spending_contracts:
                if (sc.registry_contract_name == expected_spending
                        and sc.compilation_params
                        and mc.policy_id in sc.compilation_params):
                    linked = sc
                    break

            if linked and linked.policy_id in spending_status:
                enrichment[mc.policy_id] = {
                    "has_minted_tokens": spending_status[linked.policy_id]["has_minted_tokens"],
                    "balance_lovelace": None,  # minting policies don't have addresses
                }
            else:
                # Look up in DB
                spending_docs = await collection.find({
                    "registry_contract_name": expected_spending,
                    "compilation_params": [mc.policy_id],
                }).sort("compiled_at", -1).limit(1).to_list(1)

                if spending_docs:
                    sd = spending_docs[0]
                    sd["policy_id"] = sd.pop("_id")
                    sp_contract = ContractMongo.model_validate(sd)
                    addr = sp_contract.testnet_addr if sp_contract.network == "testnet" else sp_contract.mainnet_addr
                    if addr:
                        try:
                            sp_addr = pc.Address.from_primitive(addr)
                            utxos = chain_context.context.utxos(sp_addr)
                            has_tokens = any(u.output.amount.multi_asset for u in utxos)
                            enrichment[mc.policy_id] = {"has_minted_tokens": has_tokens, "balance_lovelace": None}
                        except Exception:
                            enrichment[mc.policy_id] = {"has_minted_tokens": None, "balance_lovelace": None}
                    else:
                        enrichment[mc.policy_id] = {"has_minted_tokens": False, "balance_lovelace": None}
                else:
                    enrichment[mc.policy_id] = {"has_minted_tokens": None, "balance_lovelace": None}

        return enrichment

    async def delete_contract(self, policy_id: str, chain_context=None) -> None:
        """
        Delete a contract by policy ID, with cascading validations.

        If chain_context is provided, checks on-chain state before allowing deletion:
        - Blocks deletion of minting policies with active tokens on-chain
        - Blocks deletion of spending validators with active tokens on-chain
        - Blocks deletion of protocol contracts with dependent project contracts

        Args:
            policy_id: The contract's policy ID (script hash)
            chain_context: Optional CardanoChainContext for on-chain validation

        Raises:
            ContractNotFoundError: If contract not found
            ContractDeleteBlockedError: If deletion is blocked by active tokens or dependencies
        """
        if self.database is not None:
            collection = self._get_contract_collection()

            # Look up the contract first
            contract_doc = await collection.find_one({"_id": policy_id})
            if not contract_doc:
                raise ContractNotFoundError(f"Contract not found: {policy_id}")

            contract_doc_copy = dict(contract_doc)
            contract_doc_copy["policy_id"] = contract_doc_copy.pop("_id")
            contract = ContractMongo.model_validate(contract_doc_copy)

            # Run on-chain validations if chain_context is provided
            if chain_context is not None:
                await self._validate_delete(contract, collection, chain_context)

            result = await collection.delete_one({"_id": policy_id})
            if result.deleted_count == 0:
                raise ContractNotFoundError(f"Contract not found: {policy_id}")
        else:
            contract = await self._find_contract_by_policy_id(policy_id)
            if not contract:
                raise ContractNotFoundError(f"Contract not found: {policy_id}")
            await contract.delete()

    async def _validate_delete(self, contract: ContractMongo, collection, chain_context) -> None:
        """
        Validate that a contract can be safely deleted.

        Raises ContractDeleteBlockedError if deletion is blocked.
        """
        registry_name = contract.registry_contract_name
        contract_type = contract.contract_type

        spending_name_map = {
            "protocol_nfts": "protocol",
            "project_nfts": "project",
        }

        # --- Minting policy deletion (protocol_nfts, project_nfts) ---
        if contract_type == "minting" and registry_name in spending_name_map:
            expected_spending = spending_name_map[registry_name]

            # Find the linked spending validator
            spending_docs = await collection.find({
                "registry_contract_name": expected_spending,
                "compilation_params": [contract.policy_id],
            }).sort("compiled_at", -1).limit(1).to_list(1)

            if spending_docs:
                sd = spending_docs[0]
                sd_copy = dict(sd)
                sd_copy["policy_id"] = sd_copy.pop("_id")
                sp_contract = ContractMongo.model_validate(sd_copy)
                addr = sp_contract.testnet_addr if sp_contract.network == "testnet" else sp_contract.mainnet_addr

                if addr:
                    try:
                        sp_addr = pc.Address.from_primitive(addr)
                        utxos = chain_context.context.utxos(sp_addr)
                        has_tokens = any(u.output.amount.multi_asset for u in utxos)
                        if has_tokens:
                            total_lovelace = sum(u.output.amount.coin for u in utxos)
                            balance_ada = total_lovelace / 1_000_000
                            raise ContractDeleteBlockedError(
                                f"Cannot delete '{contract.name}': active tokens exist on-chain "
                                f"at {addr} (balance: {balance_ada:.2f} ADA). "
                                f"Burn tokens first using POST /contracts/burn-protocol, "
                                f"then POST /contracts/invalidate."
                            )
                    except ContractDeleteBlockedError:
                        raise
                    except Exception:
                        pass  # If chain query fails, allow deletion

        # --- Spending validator deletion (protocol, project) ---
        elif contract_type == "spending" and registry_name in ("protocol", "project"):
            addr = contract.testnet_addr if contract.network == "testnet" else contract.mainnet_addr

            # Check on-chain balance
            if addr:
                try:
                    sp_addr = pc.Address.from_primitive(addr)
                    utxos = chain_context.context.utxos(sp_addr)
                    has_tokens = any(u.output.amount.multi_asset for u in utxos)
                    if has_tokens:
                        total_lovelace = sum(u.output.amount.coin for u in utxos)
                        balance_ada = total_lovelace / 1_000_000
                        raise ContractDeleteBlockedError(
                            f"Cannot delete '{contract.name}': active tokens exist on-chain "
                            f"at {addr} (balance: {balance_ada:.2f} ADA). "
                            f"Burn tokens first using POST /contracts/burn-protocol, "
                            f"then POST /contracts/invalidate."
                        )
                except ContractDeleteBlockedError:
                    raise
                except Exception:
                    pass  # If chain query fails, allow deletion

            # For protocol spending validator: check for dependent project contracts
            if registry_name == "protocol":
                # Find protocol_nfts that compiled this protocol (compilation_params[0] = protocol_nfts policy_id)
                minting_policy_id = None
                if contract.compilation_params and len(contract.compilation_params) > 0:
                    minting_policy_id = contract.compilation_params[0]

                if minting_policy_id:
                    # Find project_nfts contracts whose compilation_params[1] == this protocol_nfts policy_id
                    dependent_docs = await collection.find({
                        "registry_contract_name": "project_nfts",
                        "compilation_params.1": minting_policy_id,
                        "is_active": True,
                    }).to_list(100)

                    if dependent_docs:
                        dep_ids = [d["_id"] for d in dependent_docs]
                        raise ContractDeleteBlockedError(
                            f"Cannot delete '{contract.name}': {len(dependent_docs)} project contract(s) "
                            f"depend on this protocol (policy IDs: {dep_ids}). "
                            f"Delete dependent projects first."
                        )

    async def compile_protocol_contracts(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        utxo_ref: Optional[str] = None,
        force: bool = False,
    ) -> dict:
        """
        Compile protocol contracts (protocol_nfts and protocol).

        This method replicates the CLI "Compile Protocol Contracts" functionality.
        It compiles protocol_nfts first (as a minting policy), then protocol
        (as a spending validator) using the protocol_nfts policy ID.

        Args:
            wallet_address: Address to query UTXOs from
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID compiling the contracts
            chain_context: CardanoChainContext instance for blockchain queries
            utxo_ref: Optional specific UTXO reference (tx_hash:index)
            force: Force recompilation

        Returns:
            Dictionary with compilation results including:
            - success: bool
            - message: str
            - protocol_nfts: ContractMongo or None
            - protocol: ContractMongo or None
            - compilation_utxo: dict with tx_id, index, amount
            - skipped: bool
            - error: str or None
        """
        from opshin.builder import PlutusContract, build
        from opshin.prelude import TxId, TxOutRef

        # Contract source paths
        base_path = pathlib.Path("src/terrasacha_contracts")
        protocol_nfts_path = base_path / "minting_policies" / "protocol_nfts.py"
        protocol_path = base_path / "validators" / "protocol.py"

        # Verify contract files exist
        if not protocol_nfts_path.exists():
            raise ContractCompilationError(f"Contract source file not found: {protocol_nfts_path}")
        if not protocol_path.exists():
            raise ContractCompilationError(f"Contract source file not found: {protocol_path}")

        try:
            # Get address object
            address = pc.Address.from_primitive(wallet_address)

            # Find suitable UTXO
            utxo_to_use = None
            compilation_utxo_info = None

            if utxo_ref:
                # User specified a specific UTXO
                try:
                    tx_hash, index_str = utxo_ref.split(":")
                    target_index = int(index_str)
                except ValueError:
                    raise InvalidContractParametersError(
                        f"Invalid UTXO reference format: {utxo_ref}. Expected tx_hash:index"
                    )

                # Find the specific UTXO
                utxos = chain_context.context.utxos(address)
                for utxo in utxos:
                    if (utxo.input.transaction_id.payload.hex() == tx_hash and
                        utxo.input.index == target_index):
                        utxo_to_use = utxo
                        break

                if not utxo_to_use:
                    raise InvalidContractParametersError(
                        f"Specified UTXO {utxo_ref} not found at address {wallet_address}"
                    )
            else:
                # Auto-select UTXO with >3 ADA, excluding reserved compilation UTXOs
                utxos = chain_context.context.utxos(address)
                used_utxo_refs = await self.get_reserved_compilation_utxos()
                for utxo in utxos:
                    if utxo.output.amount.coin > 3_000_000:
                        ref = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
                        if ref not in used_utxo_refs:
                            utxo_to_use = utxo
                            break

            if not utxo_to_use:
                raise InvalidContractParametersError(
                    "No suitable UTXO found for protocol compilation (need >3 ADA)"
                )

            # Store compilation UTXO info
            compilation_utxo_info = {
                "tx_id": utxo_to_use.input.transaction_id.payload.hex(),
                "index": utxo_to_use.input.index,
                "amount_lovelace": utxo_to_use.output.amount.coin,
                "amount_ada": utxo_to_use.output.amount.coin / 1_000_000,
            }

            # Create TxOutRef for compilation parameter
            protocol_oref = TxOutRef(
                id=TxId(utxo_to_use.input.transaction_id.payload),
                idx=utxo_to_use.input.index
            )

            # Compile protocol_nfts minting policy
            protocol_nfts_compiled = build(str(protocol_nfts_path), protocol_oref)
            protocol_nfts_plutus = PlutusContract(protocol_nfts_compiled)

            # Check if contract with this policy_id already exists
            if self.database is not None and not force:
                collection = self._get_contract_collection()
                existing_nfts = await collection.find_one({"_id": protocol_nfts_plutus.policy_id})
                if existing_nfts:
                    # Contract with same policy_id exists, check for protocol too
                    # The protocol policy_id depends on protocol_nfts, so we need to compile to check
                    protocol_nfts_policy_id_bytes = bytes.fromhex(protocol_nfts_plutus.policy_id)
                    protocol_compiled = build(str(protocol_path), protocol_nfts_policy_id_bytes)
                    protocol_plutus = PlutusContract(protocol_compiled)

                    existing_protocol = await collection.find_one({"_id": protocol_plutus.policy_id})
                    if existing_protocol:
                        # Both contracts exist with same policy_ids - return existing
                        existing_nfts["policy_id"] = existing_nfts.pop("_id")
                        existing_protocol["policy_id"] = existing_protocol.pop("_id")
                        return {
                            "success": True,
                            "message": "Protocol contracts already exist with same policy IDs (use force=true to recompile)",
                            "protocol_nfts": ContractMongo.model_validate(existing_nfts),
                            "protocol": ContractMongo.model_validate(existing_protocol),
                            "compilation_utxo": compilation_utxo_info,
                            "skipped": True,
                            "error": None,
                        }

            # Read source for hash
            with open(protocol_nfts_path, 'r') as f:
                protocol_nfts_source = f.read()
            protocol_nfts_source_hash = hashlib.sha256(protocol_nfts_source.encode()).hexdigest()

            # Create protocol_nfts contract record
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Check for existing version (by policy_id for proper versioning)
            protocol_nfts_version = 1
            if self.database is not None:
                collection = self._get_contract_collection()
                existing = await collection.find_one({"_id": protocol_nfts_plutus.policy_id})
                if existing:
                    protocol_nfts_version = existing.get("version", 0) + 1

            protocol_nfts_contract = ContractMongo(
                policy_id=protocol_nfts_plutus.policy_id,
                name="protocol_nfts",
                contract_type="minting",
                cbor_hex=protocol_nfts_plutus.cbor.hex(),
                testnet_addr=None,
                mainnet_addr=None,
                source_file=str(protocol_nfts_path),
                source_hash=protocol_nfts_source_hash,
                compilation_params=[f"{compilation_utxo_info['tx_id']}:{compilation_utxo_info['index']}"],
                version=protocol_nfts_version,
                network=network,
                wallet_id=wallet_id,
                description="Protocol NFTs minting policy for authentication",
                is_custom_contract=False,
                registry_contract_name="protocol_nfts",
                category="core_protocol",
                compiled_at=now,
                created_at=now,
                updated_at=now,
            )

            # Compile protocol spending validator using protocol_nfts policy ID
            protocol_nfts_policy_id_bytes = bytes.fromhex(protocol_nfts_plutus.policy_id)
            protocol_compiled = build(str(protocol_path), protocol_nfts_policy_id_bytes)
            protocol_plutus = PlutusContract(protocol_compiled)

            # Read source for hash
            with open(protocol_path, 'r') as f:
                protocol_source = f.read()
            protocol_source_hash = hashlib.sha256(protocol_source.encode()).hexdigest()

            # Check for existing version (by policy_id for proper versioning)
            protocol_version = 1
            if self.database is not None:
                existing = await collection.find_one({"_id": protocol_plutus.policy_id})
                if existing:
                    protocol_version = existing.get("version", 0) + 1

            protocol_contract = ContractMongo(
                policy_id=protocol_plutus.policy_id,
                name="protocol",
                contract_type="spending",
                cbor_hex=protocol_plutus.cbor.hex(),
                testnet_addr=str(protocol_plutus.testnet_addr) if protocol_plutus.testnet_addr else None,
                mainnet_addr=str(protocol_plutus.mainnet_addr) if protocol_plutus.mainnet_addr else None,
                source_file=str(protocol_path),
                source_hash=protocol_source_hash,
                compilation_params=[protocol_nfts_plutus.policy_id],
                version=protocol_version,
                network=network,
                wallet_id=wallet_id,
                description="Protocol spending validator for managing projects",
                is_custom_contract=False,
                registry_contract_name="protocol",
                category="core_protocol",
                compiled_at=now,
                created_at=now,
                updated_at=now,
            )

            # Save contracts to MongoDB
            if self.database is not None:
                collection = self._get_contract_collection()

                # Save protocol_nfts (keep policy_id field for the unique index)
                contract_dict = protocol_nfts_contract.model_dump(by_alias=True, exclude={"id"})
                contract_dict["_id"] = protocol_nfts_contract.policy_id
                # Keep policy_id in the document for the unique index
                await collection.replace_one(
                    {"_id": protocol_nfts_contract.policy_id},
                    contract_dict,
                    upsert=True
                )

                # Save protocol (keep policy_id field for the unique index)
                contract_dict = protocol_contract.model_dump(by_alias=True, exclude={"id"})
                contract_dict["_id"] = protocol_contract.policy_id
                # Keep policy_id in the document for the unique index
                await collection.replace_one(
                    {"_id": protocol_contract.policy_id},
                    contract_dict,
                    upsert=True
                )

            return {
                "success": True,
                "message": "Successfully compiled 2 protocol contracts (protocol_nfts, protocol)",
                "protocol_nfts": protocol_nfts_contract,
                "protocol": protocol_contract,
                "compilation_utxo": compilation_utxo_info,
                "skipped": False,
                "error": None,
            }

        except (ContractCompilationError, InvalidContractParametersError):
            raise
        except Exception as e:
            raise ContractCompilationError(f"Protocol compilation failed: {str(e)}")

    async def build_mint_protocol_transaction(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        protocol_nfts_policy_id: str,
        destination_address: Optional[str] = None,
        protocol_admins: Optional[list[str]] = None,
        protocol_fee: int = 1_000_000,
        oracle_id: str = "",
        projects: Optional[list[str]] = None,
    ) -> dict:
        """
        Build an unsigned minting transaction for protocol NFTs.

        Creates REF and USER protocol NFT tokens. The REF token goes to the
        protocol contract address with a DatumProtocol; the USER token goes
        to the destination address (or wallet address).

        No password required — only builds the unsigned transaction.
        Signing is done via POST /transactions/sign.

        Args:
            wallet_address: Wallet enterprise address
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID
            chain_context: CardanoChainContext instance
            protocol_nfts_policy_id: Policy ID of the compiled protocol_nfts to mint
            destination_address: Where to send USER token (default: wallet_address)
            protocol_admins: List of admin PKH hex strings (default: [])
            protocol_fee: Protocol fee in lovelace (default: 1_000_000)
            oracle_id: Oracle policy ID hex string (default: "" for none)
            projects: List of project ID hashes hex (default: [])

        Returns:
            Dictionary with transaction details for the endpoint response
        """
        from opshin.prelude import TxId, TxOutRef
        from terrasacha_contracts.minting_policies.protocol_nfts import Mint
        from terrasacha_contracts.util import (
            PREFIX_REFERENCE_NFT,
            PREFIX_USER_NFT,
            DatumProtocol,
            unique_token_name,
        )
        from api.services.transaction_service_mongo import _extract_amount_from_value

        if self.database is None:
            raise ContractCompilationError("Database context required for mint operations")

        collection = self._get_contract_collection()

        # 1. Find protocol_nfts contract by policy_id
        nfts_doc = await collection.find_one({"_id": protocol_nfts_policy_id})
        if not nfts_doc:
            raise ContractNotFoundError(
                f"protocol_nfts contract with policy_id '{protocol_nfts_policy_id}' not found. "
                "Use GET /contracts/ to list available compiled contracts."
            )

        nfts_doc["policy_id"] = nfts_doc.pop("_id")
        protocol_nfts_contract = ContractMongo.model_validate(nfts_doc)

        # 2. Find protocol spending validator (by its compilation param = protocol_nfts policy_id)
        protocol_docs = await collection.find({
            "registry_contract_name": "protocol",
            "category": "core_protocol",
            "compilation_params": [protocol_nfts_contract.policy_id],
        }).sort("compiled_at", -1).limit(1).to_list(1)

        if not protocol_docs:
            raise ContractNotFoundError(
                "protocol spending validator not found. Run POST /compile-protocol first."
            )

        protocol_doc = protocol_docs[0]
        protocol_doc["policy_id"] = protocol_doc.pop("_id")
        protocol_contract = ContractMongo.model_validate(protocol_doc)

        # 3. Get compilation UTXO from protocol_nfts compilation_params
        if not protocol_nfts_contract.compilation_params:
            raise InvalidContractParametersError(
                "protocol_nfts contract missing compilation_params"
            )

        utxo_ref_str = protocol_nfts_contract.compilation_params[0]
        try:
            comp_tx_hash, comp_index_str = utxo_ref_str.split(":")
            comp_index = int(comp_index_str)
        except ValueError:
            raise InvalidContractParametersError(
                f"Invalid compilation UTXO reference: {utxo_ref_str}"
            )

        # 4. Find the UTXO on-chain at the wallet address
        address = pc.Address.from_primitive(wallet_address)
        utxos = chain_context.context.utxos(address)

        utxo_to_spend = None
        for utxo in utxos:
            if (utxo.input.transaction_id.payload.hex() == comp_tx_hash and
                    utxo.input.index == comp_index):
                utxo_to_spend = utxo
                break

        if not utxo_to_spend:
            raise InvalidContractParametersError(
                f"Compilation UTXO {utxo_ref_str} not found at address {wallet_address}. "
                "It may have already been consumed. Recompile with a new UTXO."
            )

        # 5. Reconstruct script and build transaction
        minting_script = pc.PlutusV2Script(bytes.fromhex(protocol_nfts_contract.cbor_hex))
        minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))

        # Determine protocol contract address
        if network == "testnet":
            protocol_address = pc.Address.from_primitive(protocol_contract.testnet_addr)
        else:
            protocol_address = pc.Address.from_primitive(protocol_contract.mainnet_addr)

        # Determine destination for USER token
        if destination_address:
            dest_addr = pc.Address.from_primitive(destination_address)
        else:
            dest_addr = address

        # Create UTXO reference for token name generation
        oref = TxOutRef(
            id=TxId(utxo_to_spend.input.transaction_id.payload),
            idx=utxo_to_spend.input.index
        )

        # Generate token names
        protocol_token_name = unique_token_name(oref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # Create assets to mint
        protocol_nft_asset = pc.MultiAsset(
            {minting_policy_id: pc.Asset({pc.AssetName(protocol_token_name): 1})}
        )
        user_nft_asset = pc.MultiAsset(
            {minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})}
        )

        total_mint = protocol_nft_asset.union(user_nft_asset)

        # Exclude reserved compilation UTXOs from coin selection so PyCardano
        # doesn't accidentally spend another contract's compilation UTXO for fees
        reserved_utxos = await self.get_reserved_compilation_utxos()
        comp_utxo_ref = f"{comp_tx_hash}:{comp_index}"

        # Build transaction
        builder = pc.TransactionBuilder(chain_context.context)
        builder.add_input(utxo_to_spend)

        # Add remaining non-reserved UTXOs as explicit inputs for fee coverage
        for u in utxos:
            ref = f"{u.input.transaction_id.payload.hex()}:{u.input.index}"
            if ref != comp_utxo_ref and ref not in reserved_utxos:
                builder.add_input(u)
        builder.mint = total_mint
        builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Mint()))

        # Validate datum parameters
        admins_list = protocol_admins or []
        projects_list = projects or []
        if len(admins_list) > 10:
            raise InvalidContractParametersError(
                f"protocol_admins cannot exceed 10 entries (got {len(admins_list)})"
            )
        if protocol_fee < 0:
            raise InvalidContractParametersError(
                f"protocol_fee must be >= 0 (got {protocol_fee})"
            )

        # Convert hex strings to bytes for datum
        admins_bytes = [bytes.fromhex(a) for a in admins_list]
        projects_bytes = [bytes.fromhex(p) for p in projects_list]
        oracle_bytes = bytes.fromhex(oracle_id) if oracle_id else b""

        # Create protocol datum
        protocol_datum = DatumProtocol(
            project_admins=admins_bytes,
            protocol_fee=protocol_fee,
            oracle_id=oracle_bytes,
            projects=projects_bytes,
        )

        # Add protocol output (REF token -> protocol contract address)
        # NOTE: Opshin PlutusData serializes with indefinite-length CBOR lists
        # (9f...ff) but Cardano node uses canonical definite-length (84...) for
        # min_lovelace size calculation. This causes a 1-byte undercount, so we
        # add coins_per_utxo_byte to compensate.
        protocol_value = pc.Value(0, protocol_nft_asset)
        min_val_protocol = pc.min_lovelace(
            chain_context.context,
            output=pc.TransactionOutput(protocol_address, protocol_value, datum=protocol_datum)
        ) + chain_context.context.protocol_param.coins_per_utxo_byte
        protocol_output = pc.TransactionOutput(
            address=protocol_address,
            amount=pc.Value(coin=min_val_protocol, multi_asset=protocol_nft_asset),
            datum=protocol_datum,
        )
        builder.add_output(protocol_output)

        # Add user output (USER token -> destination address)
        user_value = pc.Value(0, user_nft_asset)
        min_val_user = pc.min_lovelace(
            chain_context.context,
            output=pc.TransactionOutput(dest_addr, user_value)
        )
        user_output = pc.TransactionOutput(
            address=dest_addr,
            amount=pc.Value(coin=min_val_user, multi_asset=user_nft_asset),
            datum=None,
        )
        builder.add_output(user_output)

        # 6. Build unsigned transaction (no signing key needed)
        tx_body = builder.build(change_address=address)

        # Extract partial witness set (scripts + redeemers, no vkeys)
        # PyCardano's build_witness_set() returns everything except vkey witnesses
        partial_witness = builder.build_witness_set()

        unsigned_cbor = tx_body.to_cbor_hex()
        witness_cbor = partial_witness.to_cbor_hex()
        tx_hash = tx_body.hash().hex()

        # 7. Extract inputs/outputs for response
        utxo_map = {}
        for utxo in utxos:
            key = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            utxo_map[key] = utxo

        inputs = []
        for tx_input in tx_body.inputs:
            tx_hash_hex = tx_input.transaction_id.payload.hex()
            idx = tx_input.index
            utxo = utxo_map.get(f"{tx_hash_hex}:{idx}")
            if utxo:
                amount = _extract_amount_from_value(utxo.output.amount)
                inputs.append({
                    "address": str(utxo.output.address),
                    "tx_hash": tx_hash_hex,
                    "output_index": idx,
                    "amount": amount,
                })

        outputs = []
        for idx, tx_output in enumerate(tx_body.outputs):
            amount = _extract_amount_from_value(tx_output.amount)
            outputs.append({
                "address": str(tx_output.address),
                "amount": amount,
                "output_index": idx,
            })

        # 8. Save TransactionMongo
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        transaction = TransactionMongo(
            tx_hash=tx_hash,
            wallet_id=wallet_id,
            contract_policy_id=protocol_nfts_contract.policy_id,
            status=TransactionStatus.BUILT.value,
            operation="mint_protocol",
            description="Mint protocol NFTs (REF + USER tokens)",
            unsigned_cbor=unsigned_cbor,
            witness_cbor=witness_cbor,
            from_address=wallet_address,
            from_address_index=0,
            to_address=str(protocol_address),
            fee_lovelace=int(tx_body.fee),
            estimated_fee=int(tx_body.fee),
            inputs=inputs,
            outputs=outputs,
            created_at=now,
            updated_at=now,
        )

        tx_collection = self.database.get_collection("transactions")
        tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
        if "id" in tx_dict:
            tx_dict.pop("id")
        tx_dict["_id"] = transaction.tx_hash
        await tx_collection.insert_one(tx_dict)

        return {
            "success": True,
            "transaction_id": tx_hash,
            "tx_cbor": unsigned_cbor,
            "protocol_token_name": protocol_token_name.hex(),
            "user_token_name": user_token_name.hex(),
            "minting_policy_id": protocol_nfts_contract.policy_id,
            "protocol_contract_address": str(protocol_address),
            "compilation_utxo": {
                "tx_id": comp_tx_hash,
                "index": comp_index,
                "amount_lovelace": utxo_to_spend.output.amount.coin,
                "amount_ada": utxo_to_spend.output.amount.coin / 1_000_000,
            },
            "fee_lovelace": int(tx_body.fee),
            "inputs": inputs,
            "outputs": outputs,
        }

    async def build_burn_protocol_transaction(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        protocol_nfts_policy_id: str,
    ) -> dict:
        """
        Build an unsigned burn transaction for protocol NFTs.

        Destroys both the REF token (at the protocol contract address) and the
        USER token (at the wallet address). Requires two scripts: the minting
        policy with Burn() redeemer and the protocol spending validator with
        EndProtocol() redeemer.

        Args:
            wallet_address: Wallet enterprise address (holds USER token)
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID
            chain_context: CardanoChainContext instance
            protocol_nfts_policy_id: Policy ID of the protocol_nfts to burn

        Returns:
            Dictionary with transaction details for the endpoint response
        """
        from terrasacha_contracts.minting_policies.protocol_nfts import Burn
        from terrasacha_contracts.util import EndProtocol
        from api.services.transaction_service_mongo import _extract_amount_from_value

        if self.database is None:
            raise ContractCompilationError("Database context required for burn operations")

        collection = self._get_contract_collection()

        # 1. Find protocol_nfts contract by policy_id
        nfts_doc = await collection.find_one({"_id": protocol_nfts_policy_id})
        if not nfts_doc:
            raise ContractNotFoundError(
                f"protocol_nfts contract with policy_id '{protocol_nfts_policy_id}' not found. "
                "Use GET /contracts/ to list available compiled contracts."
            )

        nfts_doc["policy_id"] = nfts_doc.pop("_id")
        protocol_nfts_contract = ContractMongo.model_validate(nfts_doc)

        # 2. Find protocol spending validator (by its compilation param = protocol_nfts policy_id)
        protocol_docs = await collection.find({
            "registry_contract_name": "protocol",
            "category": "core_protocol",
            "compilation_params": [protocol_nfts_contract.policy_id],
        }).sort("compiled_at", -1).limit(1).to_list(1)

        if not protocol_docs:
            raise ContractNotFoundError(
                "protocol spending validator not found. Run POST /compile-protocol first."
            )

        protocol_doc = protocol_docs[0]
        protocol_doc["policy_id"] = protocol_doc.pop("_id")
        protocol_contract = ContractMongo.model_validate(protocol_doc)

        # 3. Reconstruct scripts
        minting_script = pc.PlutusV2Script(bytes.fromhex(protocol_nfts_contract.cbor_hex))
        minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))
        protocol_script = pc.PlutusV2Script(bytes.fromhex(protocol_contract.cbor_hex))

        # Determine protocol contract address
        if network == "testnet":
            protocol_address = pc.Address.from_primitive(protocol_contract.testnet_addr)
        else:
            protocol_address = pc.Address.from_primitive(protocol_contract.mainnet_addr)

        address = pc.Address.from_primitive(wallet_address)

        # 4. Find protocol UTXO on-chain (REF token at protocol contract address)
        protocol_utxos = chain_context.context.utxos(protocol_address)
        if not protocol_utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at protocol address {protocol_address}"
            )

        protocol_utxo = None
        for utxo in protocol_utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == minting_policy_id:
                        protocol_utxo = utxo
                        break
            if protocol_utxo:
                break

        if not protocol_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with policy {protocol_nfts_policy_id} found at protocol address"
            )

        # 5. Find user UTXO on-chain (USER token at wallet address)
        user_utxos = chain_context.context.utxos(address)
        if not user_utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at wallet address {wallet_address}"
            )

        # Exclude compilation UTXOs reserved for unminted contracts
        reserved_utxos = await self.get_reserved_compilation_utxos()
        if reserved_utxos:
            user_utxos = [
                u for u in user_utxos
                if f"{u.input.transaction_id.payload.hex()}:{u.input.index}" not in reserved_utxos
            ]

        user_utxo = None
        for utxo in user_utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == minting_policy_id:
                        user_utxo = utxo
                        break
            if user_utxo:
                break

        if not user_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with policy {protocol_nfts_policy_id} found at wallet address"
            )

        # 6. Calculate sorted input indices for EndProtocol redeemer
        all_inputs = sorted(
            user_utxos + [protocol_utxo],
            key=lambda u: (u.input.transaction_id.payload, u.input.index),
        )
        protocol_input_index = all_inputs.index(protocol_utxo)
        user_input_index = all_inputs.index(user_utxo)

        # 7. Build transaction
        builder = pc.TransactionBuilder(chain_context.context)

        # Add all user UTXOs as regular inputs
        for u in user_utxos:
            builder.add_input(u)

        # Add minting script with Burn redeemer
        builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Burn()))

        # Add protocol UTXO as script input with EndProtocol redeemer
        builder.add_script_input(
            protocol_utxo,
            script=protocol_script,
            redeemer=pc.Redeemer(EndProtocol(
                protocol_input_index=protocol_input_index,
                user_input_index=user_input_index,
            )),
        )

        # Extract token names from UTXOs for burn amounts
        protocol_asset = protocol_utxo.output.amount.multi_asset[minting_policy_id]
        user_asset = user_utxo.output.amount.multi_asset[minting_policy_id]
        protocol_token_name = list(protocol_asset.data.keys())[0]
        user_token_name = list(user_asset.data.keys())[0]

        # Set burn amounts (negative = burn)
        builder.mint = pc.MultiAsset({
            minting_policy_id: pc.Asset({
                protocol_token_name: -1,
                user_token_name: -1,
            })
        })

        # Fee coverage
        builder.add_input_address(address)

        # 8. Build unsigned transaction
        tx_body = builder.build(change_address=address)
        partial_witness = builder.build_witness_set()

        unsigned_cbor = tx_body.to_cbor_hex()
        witness_cbor = partial_witness.to_cbor_hex()
        tx_hash = tx_body.hash().hex()

        # 9. Extract inputs/outputs for response
        utxo_map = {}
        for utxo in user_utxos:
            key = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            utxo_map[key] = utxo
        # Also add protocol UTXO to the map
        pkey = f"{protocol_utxo.input.transaction_id.payload.hex()}:{protocol_utxo.input.index}"
        utxo_map[pkey] = protocol_utxo

        inputs = []
        for tx_input in tx_body.inputs:
            tx_hash_hex = tx_input.transaction_id.payload.hex()
            idx = tx_input.index
            utxo = utxo_map.get(f"{tx_hash_hex}:{idx}")
            if utxo:
                amount = _extract_amount_from_value(utxo.output.amount)
                inputs.append({
                    "address": str(utxo.output.address),
                    "tx_hash": tx_hash_hex,
                    "output_index": idx,
                    "amount": amount,
                })

        outputs = []
        for idx, tx_output in enumerate(tx_body.outputs):
            amount = _extract_amount_from_value(tx_output.amount)
            outputs.append({
                "address": str(tx_output.address),
                "amount": amount,
                "output_index": idx,
            })

        # 10. Save TransactionMongo
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        transaction = TransactionMongo(
            tx_hash=tx_hash,
            wallet_id=wallet_id,
            contract_policy_id=protocol_nfts_contract.policy_id,
            status=TransactionStatus.BUILT.value,
            operation="burn_protocol",
            description="Burn protocol NFTs (REF + USER tokens)",
            unsigned_cbor=unsigned_cbor,
            witness_cbor=witness_cbor,
            from_address=wallet_address,
            from_address_index=0,
            to_address=None,
            fee_lovelace=int(tx_body.fee),
            estimated_fee=int(tx_body.fee),
            inputs=inputs,
            outputs=outputs,
            created_at=now,
            updated_at=now,
        )

        tx_collection = self.database.get_collection("transactions")
        tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
        if "id" in tx_dict:
            tx_dict.pop("id")
        tx_dict["_id"] = transaction.tx_hash
        await tx_collection.insert_one(tx_dict)

        return {
            "success": True,
            "transaction_id": tx_hash,
            "tx_cbor": unsigned_cbor,
            "protocol_token_name": protocol_token_name.payload.hex(),
            "user_token_name": user_token_name.payload.hex(),
            "minting_policy_id": protocol_nfts_contract.policy_id,
            "protocol_contract_address": str(protocol_address),
            "fee_lovelace": int(tx_body.fee),
            "inputs": inputs,
            "outputs": outputs,
        }

    async def build_update_protocol_transaction(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        protocol_nfts_policy_id: str,
        protocol_admins: Optional[list[str]] = None,
        protocol_fee: Optional[int] = None,
        oracle_id: Optional[str] = None,
        projects: Optional[list[str]] = None,
    ) -> dict:
        """
        Build an unsigned transaction to update the protocol datum.

        Finds the protocol UTXO on-chain, extracts the current datum, merges
        with the provided values, and builds a transaction that spends the
        protocol UTXO and recreates it with the new datum.

        Args:
            wallet_address: Wallet enterprise address (holds USER token)
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID
            chain_context: CardanoChainContext instance
            protocol_nfts_policy_id: Policy ID of the protocol_nfts
            protocol_admins: New admin list (None = keep current). Max 10.
            protocol_fee: New fee in lovelace (None = keep current)
            oracle_id: New oracle ID hex (None = keep current, "" = clear)
            projects: New projects list (None = keep current)

        Returns:
            Dictionary with transaction details including old_datum and new_datum
        """
        from terrasacha_contracts.util import DatumProtocol, UpdateProtocol
        from api.services.transaction_service_mongo import _extract_amount_from_value

        if self.database is None:
            raise ContractCompilationError("Database context required for update operations")

        collection = self._get_contract_collection()

        # 1. Find protocol_nfts contract by policy_id
        nfts_doc = await collection.find_one({"_id": protocol_nfts_policy_id})
        if not nfts_doc:
            raise ContractNotFoundError(
                f"protocol_nfts contract with policy_id '{protocol_nfts_policy_id}' not found. "
                "Use GET /contracts/ to list available compiled contracts."
            )

        nfts_doc["policy_id"] = nfts_doc.pop("_id")
        protocol_nfts_contract = ContractMongo.model_validate(nfts_doc)

        # 2. Find protocol spending validator
        protocol_docs = await collection.find({
            "registry_contract_name": "protocol",
            "category": "core_protocol",
            "compilation_params": [protocol_nfts_contract.policy_id],
        }).sort("compiled_at", -1).limit(1).to_list(1)

        if not protocol_docs:
            raise ContractNotFoundError(
                "protocol spending validator not found. Run POST /compile-protocol first."
            )

        protocol_doc = protocol_docs[0]
        protocol_doc["policy_id"] = protocol_doc.pop("_id")
        protocol_contract = ContractMongo.model_validate(protocol_doc)

        # 3. Reconstruct scripts
        protocol_script = pc.PlutusV2Script(bytes.fromhex(protocol_contract.cbor_hex))
        minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_contract.policy_id))

        # Determine protocol contract address
        if network == "testnet":
            protocol_address = pc.Address.from_primitive(protocol_contract.testnet_addr)
        else:
            protocol_address = pc.Address.from_primitive(protocol_contract.mainnet_addr)

        address = pc.Address.from_primitive(wallet_address)

        # 4. Find protocol UTXO on-chain (REF token at protocol contract address)
        protocol_utxos = chain_context.context.utxos(protocol_address)
        if not protocol_utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at protocol address {protocol_address}"
            )

        protocol_utxo = None
        for utxo in protocol_utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == minting_policy_id:
                        protocol_utxo = utxo
                        break
            if protocol_utxo:
                break

        if not protocol_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with policy {protocol_nfts_policy_id} found at protocol address"
            )

        # 5. Find user UTXO on-chain (USER token at wallet address)
        user_utxos = chain_context.context.utxos(address)
        if not user_utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at wallet address {wallet_address}"
            )

        # Exclude compilation UTXOs reserved for unminted contracts
        reserved_utxos = await self.get_reserved_compilation_utxos()
        if reserved_utxos:
            user_utxos = [
                u for u in user_utxos
                if f"{u.input.transaction_id.payload.hex()}:{u.input.index}" not in reserved_utxos
            ]

        user_utxo = None
        for utxo in user_utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == minting_policy_id:
                        user_utxo = utxo
                        break
            if user_utxo:
                break

        if not user_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with policy {protocol_nfts_policy_id} found at wallet address"
            )

        # 6. Extract current datum
        old_datum = DatumProtocol.from_cbor(protocol_utxo.output.datum.cbor)

        # Convert old datum to display dict
        old_datum_dict = {
            "project_admins": [a.hex() for a in old_datum.project_admins],
            "protocol_fee": old_datum.protocol_fee,
            "oracle_id": old_datum.oracle_id.hex() if old_datum.oracle_id else "",
            "projects": [p.hex() for p in old_datum.projects],
        }

        # 7. Build new datum — merge request values with current
        new_admins = (
            [bytes.fromhex(a) for a in protocol_admins]
            if protocol_admins is not None
            else old_datum.project_admins
        )
        new_fee = protocol_fee if protocol_fee is not None else old_datum.protocol_fee
        if oracle_id is not None:
            new_oracle = bytes.fromhex(oracle_id) if oracle_id else b""
        else:
            new_oracle = old_datum.oracle_id
        new_projects = (
            [bytes.fromhex(p) for p in projects]
            if projects is not None
            else old_datum.projects
        )

        # 8. Validate new datum
        if len(new_admins) > 10:
            raise InvalidContractParametersError(
                f"protocol_admins cannot exceed 10 entries (got {len(new_admins)})"
            )
        if new_fee < 0:
            raise InvalidContractParametersError(
                f"protocol_fee must be >= 0 (got {new_fee})"
            )

        new_datum = DatumProtocol(
            project_admins=new_admins,
            protocol_fee=new_fee,
            oracle_id=new_oracle,
            projects=new_projects,
        )

        new_datum_dict = {
            "project_admins": [a.hex() for a in new_admins],
            "protocol_fee": new_fee,
            "oracle_id": new_oracle.hex() if new_oracle else "",
            "projects": [p.hex() for p in new_projects],
        }

        # 9. Calculate sorted input indices for UpdateProtocol redeemer
        all_inputs = sorted(
            user_utxos + [protocol_utxo],
            key=lambda u: (u.input.transaction_id.payload, u.input.index),
        )
        protocol_input_index = all_inputs.index(protocol_utxo)
        user_input_index = all_inputs.index(user_utxo)

        # 10. Build transaction
        builder = pc.TransactionBuilder(chain_context.context)

        # Add all user UTXOs as regular inputs
        for u in user_utxos:
            builder.add_input(u)

        # Add protocol UTXO as script input with UpdateProtocol redeemer
        builder.add_script_input(
            protocol_utxo,
            script=protocol_script,
            redeemer=pc.Redeemer(UpdateProtocol(
                protocol_input_index=protocol_input_index,
                user_input_index=user_input_index,
                protocol_output_index=0,
            )),
        )

        # Add protocol output with new datum
        protocol_asset = protocol_utxo.output.amount.multi_asset[minting_policy_id]
        protocol_multi_asset = pc.MultiAsset({minting_policy_id: protocol_asset})
        min_val = pc.min_lovelace(
            chain_context.context,
            output=pc.TransactionOutput(
                protocol_address, pc.Value(0, protocol_multi_asset), datum=new_datum
            ),
        )
        # Opshin PlutusData serializes with indefinite-length CBOR lists (9f...ff)
        # but the Cardano node uses canonical definite-length encoding for
        # min_lovelace size calculation, causing a 1-byte undercount per list.
        # Adding coins_per_utxo_byte compensates for this discrepancy.
        min_val += chain_context.context.protocol_param.coins_per_utxo_byte
        protocol_output = pc.TransactionOutput(
            address=protocol_address,
            amount=pc.Value(coin=min_val, multi_asset=protocol_multi_asset),
            datum=new_datum,
        )
        builder.add_output(protocol_output)

        # 11. Build unsigned transaction
        tx_body = builder.build(change_address=address)
        partial_witness = builder.build_witness_set()

        unsigned_cbor = tx_body.to_cbor_hex()
        witness_cbor = partial_witness.to_cbor_hex()
        tx_hash = tx_body.hash().hex()

        # 12. Extract inputs/outputs for response
        utxo_map = {}
        for utxo in user_utxos:
            key = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            utxo_map[key] = utxo
        pkey = f"{protocol_utxo.input.transaction_id.payload.hex()}:{protocol_utxo.input.index}"
        utxo_map[pkey] = protocol_utxo

        inputs = []
        for tx_input in tx_body.inputs:
            tx_hash_hex = tx_input.transaction_id.payload.hex()
            idx = tx_input.index
            utxo = utxo_map.get(f"{tx_hash_hex}:{idx}")
            if utxo:
                amount = _extract_amount_from_value(utxo.output.amount)
                inputs.append({
                    "address": str(utxo.output.address),
                    "tx_hash": tx_hash_hex,
                    "output_index": idx,
                    "amount": amount,
                })

        outputs = []
        for idx, tx_output in enumerate(tx_body.outputs):
            amount = _extract_amount_from_value(tx_output.amount)
            outputs.append({
                "address": str(tx_output.address),
                "amount": amount,
                "output_index": idx,
            })

        # 13. Save TransactionMongo
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        transaction = TransactionMongo(
            tx_hash=tx_hash,
            wallet_id=wallet_id,
            contract_policy_id=protocol_nfts_contract.policy_id,
            status=TransactionStatus.BUILT.value,
            operation="update_protocol",
            description="Update protocol datum",
            unsigned_cbor=unsigned_cbor,
            witness_cbor=witness_cbor,
            from_address=wallet_address,
            from_address_index=0,
            to_address=str(protocol_address),
            fee_lovelace=int(tx_body.fee),
            estimated_fee=int(tx_body.fee),
            inputs=inputs,
            outputs=outputs,
            created_at=now,
            updated_at=now,
        )

        tx_collection = self.database.get_collection("transactions")
        tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
        if "id" in tx_dict:
            tx_dict.pop("id")
        tx_dict["_id"] = transaction.tx_hash
        await tx_collection.insert_one(tx_dict)

        # 14. Return response
        return {
            "success": True,
            "transaction_id": tx_hash,
            "tx_cbor": unsigned_cbor,
            "protocol_contract_address": str(protocol_address),
            "old_datum": old_datum_dict,
            "new_datum": new_datum_dict,
            "fee_lovelace": int(tx_body.fee),
            "inputs": inputs,
            "outputs": outputs,
        }

    async def build_mint_project_transaction(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        project_nfts_policy_id: str,
        project_id: str,
        destination_address: Optional[str] = None,
        project_metadata: str = "",
        stakeholders: Optional[list[dict]] = None,
        certifications: Optional[list[dict]] = None,
        investment_tokens: int = 0,
    ) -> dict:
        """
        Build an unsigned minting transaction for project NFTs.

        Creates REF and USER project NFT tokens. The REF token goes to the
        project contract address with a DatumProject; the USER token goes
        to the destination address (or wallet address).

        The project_nfts minting policy requires the protocol UTXO as a
        reference input (to validate admin signature).

        Args:
            wallet_address: Wallet enterprise address
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID
            chain_context: CardanoChainContext instance
            project_nfts_policy_id: Policy ID of the compiled project_nfts to mint
            project_id: Project identifier hex string
            destination_address: Where to send USER token (default: wallet_address)
            project_metadata: Project metadata hex string (default: "")
            stakeholders: List of dicts with stakeholder, pkh, participation keys
            certifications: List of dicts with certification fields (None = default empty cert)
            investment_tokens: Grey tokens for investment pool (default: 0)

        Returns:
            Dictionary with transaction details for the endpoint response
        """
        from opshin.prelude import TxId, TxOutRef, FalseData
        from terrasacha_contracts.minting_policies.project_nfts import MintProject
        from terrasacha_contracts.util import (
            PREFIX_REFERENCE_NFT,
            PREFIX_USER_NFT,
            DatumProject,
            DatumProjectParams,
            TokenProject,
            StakeHolderParticipation,
            Certification,
            unique_token_name,
        )
        from api.services.transaction_service_mongo import _extract_amount_from_value

        if self.database is None:
            raise ContractCompilationError("Database context required for mint operations")

        collection = self._get_contract_collection()

        # 1. Find project_nfts contract by policy_id
        nfts_doc = await collection.find_one({"_id": project_nfts_policy_id})
        if not nfts_doc:
            raise ContractNotFoundError(
                f"project_nfts contract with policy_id '{project_nfts_policy_id}' not found. "
                "Use GET /contracts/ to list available compiled contracts."
            )

        nfts_doc["policy_id"] = nfts_doc.pop("_id")
        project_nfts_contract = ContractMongo.model_validate(nfts_doc)

        # 2. Find project spending validator (by compilation_params containing project_nfts policy_id)
        project_docs = await collection.find({
            "registry_contract_name": "project",
            "compilation_params": [project_nfts_contract.policy_id],
        }).sort("compiled_at", -1).limit(1).to_list(1)

        if not project_docs:
            raise ContractNotFoundError(
                "project spending validator not found. Run POST /compile-project first."
            )

        project_doc = project_docs[0]
        project_doc["policy_id"] = project_doc.pop("_id")
        project_contract = ContractMongo.model_validate(project_doc)

        # 3. Derive protocol_nfts_policy_id from project_nfts compilation_params[1]
        if not project_nfts_contract.compilation_params or len(project_nfts_contract.compilation_params) < 2:
            raise InvalidContractParametersError(
                "project_nfts contract missing compilation_params (need utxo_ref and protocol_nfts_policy_id)"
            )

        utxo_ref_str = project_nfts_contract.compilation_params[0]
        protocol_nfts_policy_id = project_nfts_contract.compilation_params[1]

        # 4. Find protocol spending validator to get protocol address
        protocol_docs = await collection.find({
            "registry_contract_name": "protocol",
            "compilation_params": [protocol_nfts_policy_id],
        }).sort("compiled_at", -1).limit(1).to_list(1)

        if not protocol_docs:
            raise ContractNotFoundError(
                "protocol spending validator not found. Ensure protocol contracts are compiled."
            )

        protocol_doc = protocol_docs[0]
        protocol_doc["policy_id"] = protocol_doc.pop("_id")
        protocol_contract = ContractMongo.model_validate(protocol_doc)

        # 5. Get protocol address and find protocol UTXO on-chain (for reference input)
        if network == "testnet":
            protocol_address = pc.Address.from_primitive(protocol_contract.testnet_addr)
        else:
            protocol_address = pc.Address.from_primitive(protocol_contract.mainnet_addr)

        protocol_minting_policy_id = pc.ScriptHash(bytes.fromhex(protocol_nfts_policy_id))
        protocol_utxos = chain_context.context.utxos(protocol_address)
        if not protocol_utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at protocol address {protocol_address}. "
                "Protocol NFTs must be minted first."
            )

        protocol_utxo = None
        for utxo in protocol_utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == protocol_minting_policy_id:
                        protocol_utxo = utxo
                        break
            if protocol_utxo:
                break

        if not protocol_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with protocol policy {protocol_nfts_policy_id} found at protocol address. "
                "Protocol NFTs must be minted first."
            )

        # 6. Parse compilation UTXO reference
        try:
            comp_tx_hash, comp_index_str = utxo_ref_str.split(":")
            comp_index = int(comp_index_str)
        except ValueError:
            raise InvalidContractParametersError(
                f"Invalid compilation UTXO reference: {utxo_ref_str}"
            )

        # 7. Find the compilation UTXO on-chain at the wallet address
        address = pc.Address.from_primitive(wallet_address)
        utxos = chain_context.context.utxos(address)

        utxo_to_spend = None
        for utxo in utxos:
            if (utxo.input.transaction_id.payload.hex() == comp_tx_hash and
                    utxo.input.index == comp_index):
                utxo_to_spend = utxo
                break

        if not utxo_to_spend:
            raise InvalidContractParametersError(
                f"Compilation UTXO {utxo_ref_str} not found at address {wallet_address}. "
                "It may have already been consumed. Recompile with a new UTXO."
            )

        # 8. Reconstruct minting script
        minting_script = pc.PlutusV2Script(bytes.fromhex(project_nfts_contract.cbor_hex))
        minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))

        # Determine project contract address
        if network == "testnet":
            project_address = pc.Address.from_primitive(project_contract.testnet_addr)
        else:
            project_address = pc.Address.from_primitive(project_contract.mainnet_addr)

        # Determine destination for USER token
        if destination_address:
            dest_addr = pc.Address.from_primitive(destination_address)
        else:
            dest_addr = address

        # 9. Create UTXO reference for token name generation
        oref = TxOutRef(
            id=TxId(utxo_to_spend.input.transaction_id.payload),
            idx=utxo_to_spend.input.index
        )

        # Generate token names
        project_token_name = unique_token_name(oref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # Create assets to mint
        project_nft_asset = pc.MultiAsset(
            {minting_policy_id: pc.Asset({pc.AssetName(project_token_name): 1})}
        )
        user_nft_asset = pc.MultiAsset(
            {minting_policy_id: pc.Asset({pc.AssetName(user_token_name): 1})}
        )
        total_mint = project_nft_asset.union(user_nft_asset)

        # 10. Build datum
        stakeholder_list_raw = stakeholders or []
        stakeholder_data = []
        total_supply = 0
        for s in stakeholder_list_raw:
            stakeholder_data.append(
                StakeHolderParticipation(
                    stakeholder=bytes.fromhex(s["stakeholder"]),
                    pkh=bytes.fromhex(s["pkh"]),
                    participation=s["participation"],
                    claimed=FalseData(),
                )
            )
            total_supply += s["participation"]

        total_supply += investment_tokens

        project_params = DatumProjectParams(
            project_id=bytes.fromhex(project_id),
            project_metadata=bytes.fromhex(project_metadata) if project_metadata else b"",
            project_state=0,
        )

        project_token_info = TokenProject(
            policy_id=b"",
            token_name=b"",
            total_supply=total_supply,
        )

        if certifications and len(certifications) > 0:
            certification_list = [
                Certification(
                    certification_date=c["certification_date"],
                    quantity=c["quantity"],
                    real_certification_date=c.get("real_certification_date", 0),
                    real_quantity=c.get("real_quantity", 0),
                )
                for c in certifications
            ]
        else:
            certification_list = [
                Certification(certification_date=0, quantity=0, real_certification_date=0, real_quantity=0)
            ]

        project_datum = DatumProject(
            params=project_params,
            project_token=project_token_info,
            stakeholders=stakeholder_data,
            certifications=certification_list,
        )

        # 11. Build transaction
        # Exclude reserved compilation UTXOs from coin selection so PyCardano
        # doesn't accidentally spend another contract's compilation UTXO for fees
        reserved_utxos = await self.get_reserved_compilation_utxos()
        comp_utxo_ref = f"{comp_tx_hash}:{comp_index}"

        builder = pc.TransactionBuilder(chain_context.context)
        builder.add_input(utxo_to_spend)

        # Add remaining non-reserved UTXOs as explicit inputs for fee coverage
        for u in utxos:
            ref = f"{u.input.transaction_id.payload.hex()}:{u.input.index}"
            if ref != comp_utxo_ref and ref not in reserved_utxos:
                builder.add_input(u)

        builder.mint = total_mint

        # MintProject redeemer — protocol_input_index = 0 (first reference input)
        builder.add_minting_script(
            script=minting_script,
            redeemer=pc.Redeemer(MintProject(protocol_input_index=0)),
        )

        # Add protocol UTXO as reference input
        builder.reference_inputs.add(protocol_utxo)

        # Add project output (REF token -> project contract address with datum)
        # NOTE: Opshin PlutusData serializes with indefinite-length CBOR lists
        # (9f...ff) but Cardano node uses canonical definite-length (84...) for
        # min_lovelace size calculation. This causes a 1-byte undercount, so we
        # add coins_per_utxo_byte to compensate.
        project_value = pc.Value(0, project_nft_asset)
        min_val_project = pc.min_lovelace(
            chain_context.context,
            output=pc.TransactionOutput(project_address, project_value, datum=project_datum),
        ) + chain_context.context.protocol_param.coins_per_utxo_byte
        project_output = pc.TransactionOutput(
            address=project_address,
            amount=pc.Value(coin=min_val_project, multi_asset=project_nft_asset),
            datum=project_datum,
        )
        builder.add_output(project_output)

        # Add user output (USER token -> destination address)
        user_value = pc.Value(0, user_nft_asset)
        min_val_user = pc.min_lovelace(
            chain_context.context,
            output=pc.TransactionOutput(dest_addr, user_value),
        )
        user_output = pc.TransactionOutput(
            address=dest_addr,
            amount=pc.Value(coin=min_val_user, multi_asset=user_nft_asset),
            datum=None,
        )
        builder.add_output(user_output)

        # 12. Build unsigned transaction
        tx_body = builder.build(change_address=address)
        partial_witness = builder.build_witness_set()

        unsigned_cbor = tx_body.to_cbor_hex()
        witness_cbor = partial_witness.to_cbor_hex()
        tx_hash = tx_body.hash().hex()

        # 13. Extract inputs/outputs for response
        utxo_map = {}
        for utxo in utxos:
            key = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            utxo_map[key] = utxo

        inputs = []
        for tx_input in tx_body.inputs:
            tx_hash_hex = tx_input.transaction_id.payload.hex()
            idx = tx_input.index
            utxo = utxo_map.get(f"{tx_hash_hex}:{idx}")
            if utxo:
                amount = _extract_amount_from_value(utxo.output.amount)
                inputs.append({
                    "address": str(utxo.output.address),
                    "tx_hash": tx_hash_hex,
                    "output_index": idx,
                    "amount": amount,
                })

        outputs = []
        for idx, tx_output in enumerate(tx_body.outputs):
            amount = _extract_amount_from_value(tx_output.amount)
            outputs.append({
                "address": str(tx_output.address),
                "amount": amount,
                "output_index": idx,
            })

        # 14. Save TransactionMongo
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        transaction = TransactionMongo(
            tx_hash=tx_hash,
            wallet_id=wallet_id,
            contract_policy_id=project_nfts_contract.policy_id,
            status=TransactionStatus.BUILT.value,
            operation="mint_project",
            description="Mint project NFTs (REF + USER tokens)",
            unsigned_cbor=unsigned_cbor,
            witness_cbor=witness_cbor,
            from_address=wallet_address,
            from_address_index=0,
            to_address=str(project_address),
            fee_lovelace=int(tx_body.fee),
            estimated_fee=int(tx_body.fee),
            inputs=inputs,
            outputs=outputs,
            created_at=now,
            updated_at=now,
        )

        tx_collection = self.database.get_collection("transactions")
        tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
        if "id" in tx_dict:
            tx_dict.pop("id")
        tx_dict["_id"] = transaction.tx_hash
        await tx_collection.insert_one(tx_dict)

        return {
            "success": True,
            "transaction_id": tx_hash,
            "tx_cbor": unsigned_cbor,
            "project_token_name": project_token_name.hex(),
            "user_token_name": user_token_name.hex(),
            "minting_policy_id": project_nfts_contract.policy_id,
            "project_contract_address": str(project_address),
            "compilation_utxo": {
                "tx_id": comp_tx_hash,
                "index": comp_index,
                "amount_lovelace": utxo_to_spend.output.amount.coin,
                "amount_ada": utxo_to_spend.output.amount.coin / 1_000_000,
            },
            "fee_lovelace": int(tx_body.fee),
            "inputs": inputs,
            "outputs": outputs,
        }

    async def build_update_project_transaction(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        project_nfts_policy_id: str,
        project_id: Optional[str] = None,
        project_metadata: Optional[str] = None,
        project_state: Optional[int] = None,
        project_token_policy_id: Optional[str] = None,
        project_token_name: Optional[str] = None,
        total_supply: Optional[int] = None,
        stakeholders: Optional[list[dict]] = None,
        certifications: Optional[list[dict]] = None,
    ) -> dict:
        """
        Build an unsigned transaction to update the project datum.

        Finds the project UTXO on-chain, extracts the current datum, merges
        with the provided values, and builds a transaction that spends the
        project UTXO and recreates it with the new datum.

        Args:
            wallet_address: Wallet enterprise address (holds USER token)
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID
            chain_context: CardanoChainContext instance
            project_nfts_policy_id: Policy ID of the project_nfts
            project_id: New project ID hex (None = keep current)
            project_metadata: New metadata hex (None = keep current)
            project_state: New state 0-3 (None = keep current)
            project_token_policy_id: New token policy ID hex (None = keep current)
            project_token_name: New token name hex (None = keep current)
            total_supply: New total supply (None = keep current)
            stakeholders: New stakeholders list of dicts (None = keep current)
            certifications: New certifications list of dicts (None = keep current)

        Returns:
            Dictionary with transaction details including old_datum and new_datum
        """
        from opshin.prelude import FalseData
        from terrasacha_contracts.util import (
            DatumProject,
            DatumProjectParams,
            TokenProject,
            StakeHolderParticipation,
            Certification,
            UpdateProject,
        )
        from api.services.transaction_service_mongo import _extract_amount_from_value

        if self.database is None:
            raise ContractCompilationError("Database context required for update operations")

        collection = self._get_contract_collection()

        # 1. Find project_nfts contract by policy_id
        nfts_doc = await collection.find_one({"_id": project_nfts_policy_id})
        if not nfts_doc:
            raise ContractNotFoundError(
                f"project_nfts contract with policy_id '{project_nfts_policy_id}' not found. "
                "Use GET /contracts/ to list available compiled contracts."
            )

        nfts_doc["policy_id"] = nfts_doc.pop("_id")
        project_nfts_contract = ContractMongo.model_validate(nfts_doc)

        # 2. Find project spending validator
        project_docs = await collection.find({
            "registry_contract_name": "project",
            "compilation_params": [project_nfts_contract.policy_id],
        }).sort("compiled_at", -1).limit(1).to_list(1)

        if not project_docs:
            raise ContractNotFoundError(
                "project spending validator not found. Run POST /compile-project first."
            )

        project_doc = project_docs[0]
        project_doc["policy_id"] = project_doc.pop("_id")
        project_contract = ContractMongo.model_validate(project_doc)

        # 3. Reconstruct script
        project_script = pc.PlutusV2Script(bytes.fromhex(project_contract.cbor_hex))
        minting_policy_id = pc.ScriptHash(bytes.fromhex(project_nfts_contract.policy_id))

        # Determine project contract address
        if network == "testnet":
            project_address = pc.Address.from_primitive(project_contract.testnet_addr)
        else:
            project_address = pc.Address.from_primitive(project_contract.mainnet_addr)

        address = pc.Address.from_primitive(wallet_address)

        # 4. Find project UTXO on-chain (REF token at project contract address)
        project_utxos = chain_context.context.utxos(project_address)
        if not project_utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at project address {project_address}"
            )

        project_utxo = None
        for utxo in project_utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == minting_policy_id:
                        project_utxo = utxo
                        break
            if project_utxo:
                break

        if not project_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with policy {project_nfts_policy_id} found at project address"
            )

        # 5. Find user UTXO on-chain (USER token at wallet address)
        user_utxos = chain_context.context.utxos(address)
        if not user_utxos:
            raise InvalidContractParametersError(
                f"No UTXOs found at wallet address {wallet_address}"
            )

        # Exclude compilation UTXOs reserved for unminted contracts
        reserved_utxos = await self.get_reserved_compilation_utxos()
        if reserved_utxos:
            user_utxos = [
                u for u in user_utxos
                if f"{u.input.transaction_id.payload.hex()}:{u.input.index}" not in reserved_utxos
            ]

        user_utxo = None
        for utxo in user_utxos:
            if utxo.output.amount.multi_asset:
                for pi in utxo.output.amount.multi_asset.data:
                    if pi == minting_policy_id:
                        user_utxo = utxo
                        break
            if user_utxo:
                break

        if not user_utxo:
            raise InvalidContractParametersError(
                f"No UTXO with policy {project_nfts_policy_id} found at wallet address"
            )

        # 6. Extract current datum
        old_datum = DatumProject.from_cbor(project_utxo.output.datum.cbor)

        # Helper to convert BoolData to string
        def _bool_data_to_str(bd) -> str:
            return "True" if bd.CONSTR_ID == 1 else "False"

        # Convert old datum to display dict
        old_datum_dict = {
            "params": {
                "project_id": old_datum.params.project_id.hex(),
                "project_metadata": old_datum.params.project_metadata.hex() if old_datum.params.project_metadata else "",
                "project_state": old_datum.params.project_state,
            },
            "project_token": {
                "policy_id": old_datum.project_token.policy_id.hex() if old_datum.project_token.policy_id else "",
                "token_name": old_datum.project_token.token_name.hex() if old_datum.project_token.token_name else "",
                "total_supply": old_datum.project_token.total_supply,
            },
            "stakeholders": [
                {
                    "stakeholder": s.stakeholder.hex(),
                    "pkh": s.pkh.hex(),
                    "participation": s.participation,
                    "claimed": _bool_data_to_str(s.claimed),
                }
                for s in old_datum.stakeholders
            ],
            "certifications": [
                {
                    "certification_date": c.certification_date,
                    "quantity": c.quantity,
                    "real_certification_date": c.real_certification_date,
                    "real_quantity": c.real_quantity,
                }
                for c in old_datum.certifications
            ],
        }

        # 7. Build new datum — merge request values with current
        new_params = DatumProjectParams(
            project_id=(
                bytes.fromhex(project_id) if project_id is not None
                else old_datum.params.project_id
            ),
            project_metadata=(
                bytes.fromhex(project_metadata) if project_metadata is not None
                else old_datum.params.project_metadata
            ),
            project_state=(
                project_state if project_state is not None
                else old_datum.params.project_state
            ),
        )

        new_token = TokenProject(
            policy_id=(
                bytes.fromhex(project_token_policy_id) if project_token_policy_id is not None
                else old_datum.project_token.policy_id
            ),
            token_name=(
                bytes.fromhex(project_token_name) if project_token_name is not None
                else old_datum.project_token.token_name
            ),
            total_supply=(
                total_supply if total_supply is not None
                else old_datum.project_token.total_supply
            ),
        )

        if stakeholders is not None:
            new_stakeholders = [
                StakeHolderParticipation(
                    stakeholder=bytes.fromhex(s["stakeholder"]),
                    pkh=bytes.fromhex(s["pkh"]),
                    participation=s["participation"],
                    claimed=FalseData(),
                )
                for s in stakeholders
            ]
        else:
            new_stakeholders = old_datum.stakeholders

        if certifications is not None:
            new_certifications = [
                Certification(
                    certification_date=c["certification_date"],
                    quantity=c["quantity"],
                    real_certification_date=c.get("real_certification_date", 0),
                    real_quantity=c.get("real_quantity", 0),
                )
                for c in certifications
            ]
        else:
            new_certifications = old_datum.certifications

        # 8. Validate new state
        if new_params.project_state is not None and new_params.project_state not in (0, 1, 2, 3):
            raise InvalidContractParametersError(
                f"project_state must be 0-3 (got {new_params.project_state})"
            )

        new_datum = DatumProject(
            params=new_params,
            project_token=new_token,
            stakeholders=new_stakeholders,
            certifications=new_certifications,
        )

        new_datum_dict = {
            "params": {
                "project_id": new_params.project_id.hex(),
                "project_metadata": new_params.project_metadata.hex() if new_params.project_metadata else "",
                "project_state": new_params.project_state,
            },
            "project_token": {
                "policy_id": new_token.policy_id.hex() if new_token.policy_id else "",
                "token_name": new_token.token_name.hex() if new_token.token_name else "",
                "total_supply": new_token.total_supply,
            },
            "stakeholders": [
                {
                    "stakeholder": s.stakeholder.hex(),
                    "pkh": s.pkh.hex(),
                    "participation": s.participation,
                    "claimed": _bool_data_to_str(s.claimed),
                }
                for s in new_stakeholders
            ],
            "certifications": [
                {
                    "certification_date": c.certification_date,
                    "quantity": c.quantity,
                    "real_certification_date": c.real_certification_date,
                    "real_quantity": c.real_quantity,
                }
                for c in new_certifications
            ],
        }

        # 9. Calculate sorted input indices for UpdateProject redeemer
        all_inputs = sorted(
            user_utxos + [project_utxo],
            key=lambda u: (u.input.transaction_id.payload, u.input.index),
        )
        project_input_index = all_inputs.index(project_utxo)
        user_input_index = all_inputs.index(user_utxo)

        # 10. Build transaction
        builder = pc.TransactionBuilder(chain_context.context)

        # Add all user UTXOs as regular inputs
        for u in user_utxos:
            builder.add_input(u)

        # Add project UTXO as script input with UpdateProject redeemer
        builder.add_script_input(
            project_utxo,
            script=project_script,
            redeemer=pc.Redeemer(UpdateProject(
                project_input_index=project_input_index,
                user_input_index=user_input_index,
                project_output_index=0,
            )),
        )

        # Add project output with new datum
        project_asset = project_utxo.output.amount.multi_asset[minting_policy_id]
        project_multi_asset = pc.MultiAsset({minting_policy_id: project_asset})
        min_val = pc.min_lovelace(
            chain_context.context,
            output=pc.TransactionOutput(
                project_address, pc.Value(0, project_multi_asset), datum=new_datum
            ),
        )
        # Opshin PlutusData serializes with indefinite-length CBOR lists (9f...ff)
        # but the Cardano node uses canonical definite-length encoding for
        # min_lovelace size calculation, causing a 1-byte undercount per list.
        # Adding coins_per_utxo_byte compensates for this discrepancy.
        min_val += chain_context.context.protocol_param.coins_per_utxo_byte
        project_output = pc.TransactionOutput(
            address=project_address,
            amount=pc.Value(coin=min_val, multi_asset=project_multi_asset),
            datum=new_datum,
        )
        builder.add_output(project_output)

        # 11. Build unsigned transaction
        tx_body = builder.build(change_address=address)
        partial_witness = builder.build_witness_set()

        unsigned_cbor = tx_body.to_cbor_hex()
        witness_cbor = partial_witness.to_cbor_hex()
        tx_hash = tx_body.hash().hex()

        # 12. Extract inputs/outputs for response
        utxo_map = {}
        for utxo in user_utxos:
            key = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            utxo_map[key] = utxo
        pkey = f"{project_utxo.input.transaction_id.payload.hex()}:{project_utxo.input.index}"
        utxo_map[pkey] = project_utxo

        inputs = []
        for tx_input in tx_body.inputs:
            tx_hash_hex = tx_input.transaction_id.payload.hex()
            idx = tx_input.index
            utxo = utxo_map.get(f"{tx_hash_hex}:{idx}")
            if utxo:
                amount = _extract_amount_from_value(utxo.output.amount)
                inputs.append({
                    "address": str(utxo.output.address),
                    "tx_hash": tx_hash_hex,
                    "output_index": idx,
                    "amount": amount,
                })

        outputs = []
        for idx, tx_output in enumerate(tx_body.outputs):
            amount = _extract_amount_from_value(tx_output.amount)
            outputs.append({
                "address": str(tx_output.address),
                "amount": amount,
                "output_index": idx,
            })

        # 13. Save TransactionMongo
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        transaction = TransactionMongo(
            tx_hash=tx_hash,
            wallet_id=wallet_id,
            contract_policy_id=project_nfts_contract.policy_id,
            status=TransactionStatus.BUILT.value,
            operation="update_project",
            description="Update project datum",
            unsigned_cbor=unsigned_cbor,
            witness_cbor=witness_cbor,
            from_address=wallet_address,
            from_address_index=0,
            to_address=str(project_address),
            fee_lovelace=int(tx_body.fee),
            estimated_fee=int(tx_body.fee),
            inputs=inputs,
            outputs=outputs,
            created_at=now,
            updated_at=now,
        )

        tx_collection = self.database.get_collection("transactions")
        tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
        if "id" in tx_dict:
            tx_dict.pop("id")
        tx_dict["_id"] = transaction.tx_hash
        await tx_collection.insert_one(tx_dict)

        # 14. Return response
        return {
            "success": True,
            "transaction_id": tx_hash,
            "tx_cbor": unsigned_cbor,
            "project_contract_address": str(project_address),
            "old_datum": old_datum_dict,
            "new_datum": new_datum_dict,
            "fee_lovelace": int(tx_body.fee),
            "inputs": inputs,
            "outputs": outputs,
        }

    async def invalidate_contracts(
        self,
        policy_id: str,
    ) -> dict:
        """
        Invalidate a contract and its dependents after confirming a burn transaction.

        Works for any contract type (protocol, project, etc.). Finds the target
        contract, any contracts compiled with its policy_id as a parameter, and
        marks them all as inactive.

        Args:
            policy_id: Policy ID of the contract to invalidate (typically a minting policy)

        Returns:
            Dictionary with invalidation results

        Raises:
            ContractNotFoundError: If contract not found
            ContractInvalidationError: If already invalidated or no burn tx found
        """
        if self.database is None:
            raise ContractInvalidationError("Database context required for invalidation")

        collection = self._get_contract_collection()

        # 1. Find target contract
        contract_doc = await collection.find_one({"_id": policy_id})
        if not contract_doc:
            raise ContractNotFoundError(
                f"Contract with policy_id '{policy_id}' not found"
            )

        # 2. Check if already invalidated
        if not contract_doc.get("is_active", True):
            raise ContractInvalidationError(
                f"Contract '{policy_id}' is already invalidated "
                f"(invalidated_at: {contract_doc.get('invalidated_at')})"
            )

        # 3. Find dependent contracts (compiled with this policy_id as a parameter)
        dependent_docs = await collection.find({
            "compilation_params": policy_id,
            "is_active": {"$ne": False},
        }).to_list(None)

        # 4. Verify a burn transaction exists in SUBMITTED or CONFIRMED state
        tx_collection = self.database.get_collection("transactions")
        burn_tx = await tx_collection.find_one({
            "contract_policy_id": policy_id,
            "operation": {"$regex": "^burn_"},
            "status": {"$in": [
                TransactionStatus.SUBMITTED.value,
                TransactionStatus.CONFIRMED.value,
            ]},
        })

        if not burn_tx:
            raise ContractInvalidationError(
                f"No burn transaction in SUBMITTED or CONFIRMED state found "
                f"for policy '{policy_id}'. "
                "Burn and submit the transaction before invalidating."
            )

        # 5. Invalidate target + all dependents
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        update_fields = {
            "is_active": False,
            "invalidated_at": now,
            "updated_at": now,
        }

        all_policy_ids = [policy_id] + [doc["_id"] for doc in dependent_docs]
        await collection.update_many(
            {"_id": {"$in": all_policy_ids}},
            {"$set": update_fields},
        )

        invalidated_contracts = [{
            "policy_id": policy_id,
            "name": contract_doc.get("name", "unknown"),
            "contract_type": contract_doc.get("contract_type", "unknown"),
        }]
        for doc in dependent_docs:
            invalidated_contracts.append({
                "policy_id": doc["_id"],
                "name": doc.get("name", "unknown"),
                "contract_type": doc.get("contract_type", "unknown"),
            })

        # 6. Return results
        return {
            "success": True,
            "message": f"Successfully invalidated {len(invalidated_contracts)} contract(s)",
            "invalidated_contracts": invalidated_contracts,
            "burn_tx_hash": burn_tx["_id"],
            "burn_tx_status": burn_tx["status"],
            "invalidated_at": now,
        }

    async def compile_project_contracts(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        project_name: str,
        protocol_nfts_policy_id: str,
        utxo_ref: Optional[str] = None,
        force: bool = False,
    ) -> dict:
        """
        Compile project contracts (project_nfts and project).

        Mirrors compile_protocol_contracts() but for project-level contracts.
        Requires an existing protocol_nfts contract to be compiled first.

        Args:
            wallet_address: Address to query UTXOs from
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID compiling the contracts
            chain_context: CardanoChainContext instance for blockchain queries
            project_name: User-provided project name (e.g. "reforestation_guaviare")
            protocol_nfts_policy_id: Policy ID of the compiled protocol_nfts
            utxo_ref: Optional specific UTXO reference (tx_hash:index)
            force: Force recompilation

        Returns:
            Dictionary with compilation results
        """
        from opshin.builder import PlutusContract, build
        from opshin.prelude import TxId, TxOutRef

        if self.database is None:
            raise ContractCompilationError("Database context required for project compilation")

        collection = self._get_contract_collection()

        # 1. Validate protocol_nfts exists and is active
        nfts_doc = await collection.find_one({"_id": protocol_nfts_policy_id})
        if not nfts_doc:
            raise ContractNotFoundError(
                f"protocol_nfts contract with policy_id '{protocol_nfts_policy_id}' not found. "
                "Compile protocol contracts first with POST /compile-protocol."
            )

        if not nfts_doc.get("is_active", True):
            raise InvalidContractParametersError(
                f"protocol_nfts contract '{protocol_nfts_policy_id}' is invalidated "
                f"(invalidated_at: {nfts_doc.get('invalidated_at')}). "
                "Compile new protocol contracts before creating project contracts."
            )

        # 2. Validate name uniqueness
        project_nfts_name = f"{project_name}_nfts"
        if not force:
            existing_name = await collection.find_one({"name": project_name, "is_active": {"$ne": False}})
            if existing_name:
                raise ContractAlreadyExistsError(
                    f"Contract with name '{project_name}' already exists (policy_id: {existing_name['_id']}). "
                    "Use a different project_name or force=true to recompile."
                )
            existing_nfts_name = await collection.find_one({"name": project_nfts_name, "is_active": {"$ne": False}})
            if existing_nfts_name:
                raise ContractAlreadyExistsError(
                    f"Contract with name '{project_nfts_name}' already exists (policy_id: {existing_nfts_name['_id']}). "
                    "Use a different project_name or force=true to recompile."
                )

        # 3. Resolve source paths
        base_path = pathlib.Path("src/terrasacha_contracts")
        project_nfts_path = base_path / "minting_policies" / "project_nfts.py"
        project_path = base_path / "validators" / "project.py"

        if not project_nfts_path.exists():
            raise ContractCompilationError(f"Contract source file not found: {project_nfts_path}")
        if not project_path.exists():
            raise ContractCompilationError(f"Contract source file not found: {project_path}")

        try:
            # 4. Select UTXO
            address = pc.Address.from_primitive(wallet_address)
            utxo_to_use = None

            if utxo_ref:
                try:
                    tx_hash, index_str = utxo_ref.split(":")
                    target_index = int(index_str)
                except ValueError:
                    raise InvalidContractParametersError(
                        f"Invalid UTXO reference format: {utxo_ref}. Expected tx_hash:index"
                    )

                utxos = chain_context.context.utxos(address)
                for utxo in utxos:
                    if (utxo.input.transaction_id.payload.hex() == tx_hash and
                        utxo.input.index == target_index):
                        utxo_to_use = utxo
                        break

                if not utxo_to_use:
                    raise InvalidContractParametersError(
                        f"Specified UTXO {utxo_ref} not found at address {wallet_address}"
                    )
            else:
                utxos = chain_context.context.utxos(address)

                # Exclude UTXOs reserved for other compilations
                used_utxo_refs = await self.get_reserved_compilation_utxos()

                for utxo in utxos:
                    if utxo.output.amount.coin > 3_000_000:
                        ref = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
                        if ref not in used_utxo_refs:
                            utxo_to_use = utxo
                            break

                # Fallback: use any UTXO with >3 ADA
                if not utxo_to_use:
                    for utxo in utxos:
                        if utxo.output.amount.coin > 3_000_000:
                            utxo_to_use = utxo
                            break

            if not utxo_to_use:
                raise InvalidContractParametersError(
                    "No suitable UTXO found for project compilation (need >3 ADA)"
                )

            compilation_utxo_info = {
                "tx_id": utxo_to_use.input.transaction_id.payload.hex(),
                "index": utxo_to_use.input.index,
                "amount_lovelace": utxo_to_use.output.amount.coin,
                "amount_ada": utxo_to_use.output.amount.coin / 1_000_000,
            }

            # 5. Compile project_nfts with build(path, utxo_oref, protocol_nfts_policy_id_bytes)
            oref = TxOutRef(
                id=TxId(utxo_to_use.input.transaction_id.payload),
                idx=utxo_to_use.input.index
            )
            protocol_nfts_policy_id_bytes = bytes.fromhex(protocol_nfts_policy_id)

            project_nfts_compiled = build(str(project_nfts_path), oref, protocol_nfts_policy_id_bytes)
            project_nfts_plutus = PlutusContract(project_nfts_compiled)

            # Check if contracts already exist with same policy_id
            if not force:
                existing = await collection.find_one({"_id": project_nfts_plutus.policy_id})
                if existing:
                    project_nfts_policy_id_bytes_new = bytes.fromhex(project_nfts_plutus.policy_id)
                    old_recursion_limit = sys.getrecursionlimit()
                    sys.setrecursionlimit(2000)
                    try:
                        project_compiled = build(str(project_path), project_nfts_policy_id_bytes_new)
                    finally:
                        sys.setrecursionlimit(old_recursion_limit)
                    project_plutus = PlutusContract(project_compiled)

                    existing_project = await collection.find_one({"_id": project_plutus.policy_id})
                    if existing_project:
                        existing["policy_id"] = existing.pop("_id")
                        existing_project["policy_id"] = existing_project.pop("_id")
                        return {
                            "success": True,
                            "message": "Project contracts already exist with same policy IDs (use force=true to recompile)",
                            "project_nfts": ContractMongo.model_validate(existing),
                            "project": ContractMongo.model_validate(existing_project),
                            "compilation_utxo": compilation_utxo_info,
                            "protocol_nfts_policy_id": protocol_nfts_policy_id,
                            "project_name": project_name,
                            "skipped": True,
                            "error": None,
                        }

            # 6. Compile project with build(path, project_nfts_policy_id_bytes)
            project_nfts_policy_id_bytes_new = bytes.fromhex(project_nfts_plutus.policy_id)
            old_recursion_limit = sys.getrecursionlimit()
            sys.setrecursionlimit(2000)
            try:
                project_compiled = build(str(project_path), project_nfts_policy_id_bytes_new)
            finally:
                sys.setrecursionlimit(old_recursion_limit)
            project_plutus = PlutusContract(project_compiled)

            # 7. Read sources for hashes
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            with open(project_nfts_path, 'r') as f:
                project_nfts_source = f.read()
            project_nfts_source_hash = hashlib.sha256(project_nfts_source.encode()).hexdigest()

            with open(project_path, 'r') as f:
                project_source = f.read()
            project_source_hash = hashlib.sha256(project_source.encode()).hexdigest()

            # 8. Version management
            project_nfts_version = 1
            existing = await collection.find_one({"_id": project_nfts_plutus.policy_id})
            if existing:
                project_nfts_version = existing.get("version", 0) + 1

            project_version = 1
            existing = await collection.find_one({"_id": project_plutus.policy_id})
            if existing:
                project_version = existing.get("version", 0) + 1

            utxo_ref_str = f"{compilation_utxo_info['tx_id']}:{compilation_utxo_info['index']}"

            # 9. Create contract records
            project_nfts_contract = ContractMongo(
                policy_id=project_nfts_plutus.policy_id,
                name=project_nfts_name,
                contract_type="minting",
                cbor_hex=project_nfts_plutus.cbor.hex(),
                testnet_addr=None,
                mainnet_addr=None,
                source_file=str(project_nfts_path),
                source_hash=project_nfts_source_hash,
                compilation_params=[utxo_ref_str, protocol_nfts_policy_id],
                version=project_nfts_version,
                network=network,
                wallet_id=wallet_id,
                description=f"Project NFTs minting policy for {project_name}",
                is_custom_contract=False,
                registry_contract_name="project_nfts",
                category="project_management",
                compiled_at=now,
                created_at=now,
                updated_at=now,
            )

            project_contract = ContractMongo(
                policy_id=project_plutus.policy_id,
                name=project_name,
                contract_type="spending",
                cbor_hex=project_plutus.cbor.hex(),
                testnet_addr=str(project_plutus.testnet_addr) if project_plutus.testnet_addr else None,
                mainnet_addr=str(project_plutus.mainnet_addr) if project_plutus.mainnet_addr else None,
                source_file=str(project_path),
                source_hash=project_source_hash,
                compilation_params=[project_nfts_plutus.policy_id],
                version=project_version,
                network=network,
                wallet_id=wallet_id,
                description=f"Project spending validator for {project_name}",
                is_custom_contract=False,
                registry_contract_name="project",
                category="project_management",
                compiled_at=now,
                created_at=now,
                updated_at=now,
            )

            # 10. Save to MongoDB
            contract_dict = project_nfts_contract.model_dump(by_alias=True, exclude={"id"})
            contract_dict["_id"] = project_nfts_contract.policy_id
            await collection.replace_one(
                {"_id": project_nfts_contract.policy_id},
                contract_dict,
                upsert=True
            )

            contract_dict = project_contract.model_dump(by_alias=True, exclude={"id"})
            contract_dict["_id"] = project_contract.policy_id
            await collection.replace_one(
                {"_id": project_contract.policy_id},
                contract_dict,
                upsert=True
            )

            return {
                "success": True,
                "message": f"Successfully compiled 2 project contracts ({project_nfts_name}, {project_name})",
                "project_nfts": project_nfts_contract,
                "project": project_contract,
                "compilation_utxo": compilation_utxo_info,
                "protocol_nfts_policy_id": protocol_nfts_policy_id,
                "project_name": project_name,
                "skipped": False,
                "error": None,
            }

        except (ContractCompilationError, InvalidContractParametersError, ContractAlreadyExistsError):
            raise
        except Exception as e:
            raise ContractCompilationError(f"Project compilation failed: {str(e)}")

    async def build_deploy_reference_script_transaction(
        self,
        wallet_address: str,
        network: str,
        wallet_id: str,
        chain_context,
        policy_id: str,
        destination_address: Optional[str] = None,
    ) -> dict:
        """
        Build an unsigned transaction to deploy a compiled contract as an on-chain reference script.

        Args:
            wallet_address: Wallet enterprise address
            network: Network (testnet/mainnet)
            wallet_id: CORE wallet ID
            chain_context: CardanoChainContext instance
            policy_id: Policy ID of the compiled contract to deploy
            destination_address: Where to store the reference script UTXO (default: wallet_address)

        Returns:
            Dictionary with transaction details for the endpoint response
        """
        from api.services.transaction_service_mongo import _extract_amount_from_value

        if self.database is None:
            raise ContractCompilationError("Database context required for reference script deployment")

        collection = self._get_contract_collection()

        # 1. Look up contract
        contract_doc = await collection.find_one({"_id": policy_id})
        if not contract_doc:
            raise ContractNotFoundError(
                f"Contract with policy_id '{policy_id}' not found."
            )

        contract_doc["policy_id"] = contract_doc.pop("_id")
        contract = ContractMongo.model_validate(contract_doc)

        if not contract.is_active:
            raise InvalidContractParametersError(
                f"Contract '{contract.name}' is invalidated and cannot be deployed as a reference script."
            )

        if not contract.cbor_hex:
            raise InvalidContractParametersError(
                f"Contract '{contract.name}' has no compiled CBOR data."
            )

        # 2. Check not already a reference script
        if contract.reference_utxo is not None:
            raise InvalidContractParametersError(
                f"Contract '{contract.name}' is already deployed as a reference script "
                f"(reference_utxo: {contract.reference_utxo})."
            )

        # 3. Reconstruct script
        script = pc.PlutusV2Script(bytes.fromhex(contract.cbor_hex))

        # 4. Resolve destination address
        address = pc.Address.from_primitive(wallet_address)
        if destination_address:
            dest_addr = pc.Address.from_primitive(destination_address)
        else:
            dest_addr = address

        # 5. Calculate min_lovelace for reference script output
        ref_output = pc.TransactionOutput(dest_addr, pc.Value(0), script=script)
        min_lovelace = pc.min_lovelace(chain_context.context, output=ref_output)

        # 6. Find suitable UTXO (need min_lovelace + fee buffer)
        utxos = chain_context.context.utxos(address)
        required = min_lovelace + 2_000_000  # fee buffer

        # Exclude UTXOs reserved for contract compilation
        reserved_utxos = await self.get_reserved_compilation_utxos()

        suitable_utxo = None
        for utxo in utxos:
            ref = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            if ref in reserved_utxos:
                continue
            if utxo.output.amount.coin > required:
                suitable_utxo = utxo
                break

        if not suitable_utxo:
            raise InvalidContractParametersError(
                f"No suitable UTXO found for reference script deployment "
                f"(need >{required / 1_000_000:.1f} ADA = {min_lovelace / 1_000_000:.1f} ADA min_lovelace + 2 ADA fee buffer)"
            )

        # 7. Build transaction
        builder = pc.TransactionBuilder(chain_context.context)
        builder.add_input(suitable_utxo)

        ref_script_output = pc.TransactionOutput(dest_addr, min_lovelace, script=script)
        builder.add_output(ref_script_output)

        tx_body = builder.build(change_address=address)
        unsigned_cbor = tx_body.to_cbor_hex()
        tx_hash = tx_body.hash().hex()

        # 8. Find reference output index
        ref_output_index = None
        for i, output in enumerate(tx_body.outputs):
            if output.script is not None:
                ref_output_index = i
                break

        if ref_output_index is None:
            raise ContractCompilationError("Reference script output not found in built transaction")

        # 9. Extract inputs/outputs
        utxo_map = {}
        for utxo in utxos:
            key = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            utxo_map[key] = utxo

        inputs = []
        for tx_input in tx_body.inputs:
            tx_hash_hex = tx_input.transaction_id.payload.hex()
            idx = tx_input.index
            utxo = utxo_map.get(f"{tx_hash_hex}:{idx}")
            if utxo:
                amount = _extract_amount_from_value(utxo.output.amount)
                inputs.append({
                    "address": str(utxo.output.address),
                    "tx_hash": tx_hash_hex,
                    "output_index": idx,
                    "amount": amount,
                })

        outputs = []
        for idx, tx_output in enumerate(tx_body.outputs):
            amount = _extract_amount_from_value(tx_output.amount)
            outputs.append({
                "address": str(tx_output.address),
                "amount": amount,
                "output_index": idx,
            })

        # 10. Save TransactionMongo
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        transaction = TransactionMongo(
            tx_hash=tx_hash,
            wallet_id=wallet_id,
            contract_policy_id=policy_id,
            status=TransactionStatus.BUILT.value,
            operation="deploy_reference_script",
            description=f"Deploy '{contract.name}' as on-chain reference script",
            unsigned_cbor=unsigned_cbor,
            from_address=wallet_address,
            from_address_index=0,
            to_address=str(dest_addr),
            fee_lovelace=int(tx_body.fee),
            estimated_fee=int(tx_body.fee),
            inputs=inputs,
            outputs=outputs,
            created_at=now,
            updated_at=now,
        )

        tx_collection = self.database.get_collection("transactions")
        tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
        if "id" in tx_dict:
            tx_dict.pop("id")
        tx_dict["_id"] = transaction.tx_hash
        await tx_collection.insert_one(tx_dict)

        return {
            "success": True,
            "transaction_id": tx_hash,
            "tx_cbor": unsigned_cbor,
            "contract_policy_id": policy_id,
            "contract_name": contract.name,
            "destination_address": str(dest_addr),
            "min_lovelace": min_lovelace,
            "reference_output_index": ref_output_index,
            "fee_lovelace": int(tx_body.fee),
            "inputs": inputs,
            "outputs": outputs,
        }

    async def confirm_reference_script_deployment(
        self,
        transaction_id: str,
    ) -> dict:
        """
        Confirm a reference script deployment by updating the contract record.

        After the deploy transaction is signed and submitted, this method updates
        the contract with the reference UTXO information.

        Args:
            transaction_id: Transaction hash of the deploy-reference-script transaction

        Returns:
            Dictionary with confirmation details
        """
        if self.database is None:
            raise ContractCompilationError("Database context required for confirmation")

        tx_collection = self.database.get_collection("transactions")
        collection = self._get_contract_collection()

        # 1. Find the transaction
        tx_doc = await tx_collection.find_one({"_id": transaction_id})
        if not tx_doc:
            raise ContractNotFoundError(
                f"Transaction '{transaction_id}' not found."
            )

        # 2. Verify it's a deploy_reference_script operation
        if tx_doc.get("operation") != "deploy_reference_script":
            raise InvalidContractParametersError(
                f"Transaction '{transaction_id}' is not a deploy_reference_script operation "
                f"(found: {tx_doc.get('operation')})."
            )

        # 3. Verify status is SUBMITTED or CONFIRMED
        status = tx_doc.get("status")
        if status not in [TransactionStatus.SUBMITTED.value, TransactionStatus.CONFIRMED.value]:
            raise InvalidContractParametersError(
                f"Transaction must be SUBMITTED or CONFIRMED to confirm deployment "
                f"(current status: {status}). Sign and submit the transaction first."
            )

        # 4. Get contract_policy_id from transaction field and find the reference output index from CBOR
        contract_policy_id = tx_doc.get("contract_policy_id")
        if not contract_policy_id:
            raise InvalidContractParametersError(
                "Transaction missing contract_policy_id field."
            )

        # Parse unsigned CBOR to find the reference script output index
        unsigned_cbor = tx_doc.get("unsigned_cbor")
        if not unsigned_cbor:
            raise InvalidContractParametersError(
                "Transaction missing unsigned CBOR data."
            )

        tx_body = pc.TransactionBody.from_cbor(unsigned_cbor)
        reference_output_index = None
        for i, output in enumerate(tx_body.outputs):
            if output.script is not None:
                reference_output_index = i
                break

        if reference_output_index is None:
            raise InvalidContractParametersError(
                "No reference script output found in the transaction."
            )

        # 5. Find the contract
        contract_doc = await collection.find_one({"_id": contract_policy_id})
        if not contract_doc:
            raise ContractNotFoundError(
                f"Contract with policy_id '{contract_policy_id}' not found."
            )

        # 6. Update contract with reference script info
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        reference_utxo = f"{transaction_id}:{reference_output_index}"

        await collection.update_one(
            {"_id": contract_policy_id},
            {"$set": {
                "reference_utxo": reference_utxo,
                "reference_tx_hash": transaction_id,
                "storage_type": "reference_script",
                "updated_at": now,
            }},
        )

        return {
            "success": True,
            "message": "Reference script deployment confirmed",
            "policy_id": contract_policy_id,
            "contract_name": contract_doc.get("name", "unknown"),
            "reference_utxo": reference_utxo,
            "reference_tx_hash": transaction_id,
        }
