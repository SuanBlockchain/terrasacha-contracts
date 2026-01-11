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

from api.database.models import ContractMongo


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
