"""
MongoDB Contract Service

Business logic for compiling and managing smart contracts.
Supports Opshin contract compilation with versioning and multi-tenant isolation.

MongoDB/Beanie version for multi-tenant architecture.
"""

import hashlib
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

    async def delete_contract(self, policy_id: str) -> None:
        """
        Delete a contract by policy ID.

        Args:
            policy_id: The contract's policy ID (script hash)

        Raises:
            ContractNotFoundError: If contract not found
        """
        if self.database is not None:
            collection = self._get_contract_collection()
            result = await collection.delete_one({"_id": policy_id})
            if result.deleted_count == 0:
                raise ContractNotFoundError(f"Contract not found: {policy_id}")
        else:
            contract = await self._find_contract_by_policy_id(policy_id)
            if not contract:
                raise ContractNotFoundError(f"Contract not found: {policy_id}")
            await contract.delete()

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
                # Auto-select UTXO with >3 ADA
                utxos = chain_context.context.utxos(address)
                for utxo in utxos:
                    if utxo.output.amount.coin > 3_000_000:
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

        # Build transaction
        builder = pc.TransactionBuilder(chain_context.context)
        builder.add_input(utxo_to_spend)
        builder.mint = total_mint
        builder.add_minting_script(script=minting_script, redeemer=pc.Redeemer(Mint()))

        # Create protocol datum
        protocol_datum = DatumProtocol(
            project_admins=[],
            protocol_fee=1000000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[],
        )

        # Add protocol output (REF token -> protocol contract address)
        protocol_value = pc.Value(0, protocol_nft_asset)
        min_val_protocol = pc.min_lovelace(
            chain_context.context,
            output=pc.TransactionOutput(protocol_address, protocol_value, datum=protocol_datum)
        )
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
