"""
Contract Service

Business logic for compiling Opshin smart contracts.
Follows cardano-cli workflow: compile → store → (later: deploy)
"""

import hashlib
import pathlib
from datetime import datetime, timezone

from opshin.builder import PlutusContract, build
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.database.models import Contract
from api.enums import NetworkType, ContractType


# Custom exceptions
class ContractCompilationError(Exception):
    """Contract compilation failed"""
    pass


class ContractNotFoundError(Exception):
    """Contract not found in database"""
    pass


class ContractService:
    """Service for managing smart contract compilation"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _normalize_contract_type(contract_type: str) -> ContractType:
        """
        Convert user-friendly contract type to database enum.

        Args:
            contract_type: "minting" or "spending"

        Returns:
            ContractType enum value

        Raises:
            ValueError: If invalid contract type
        """
        contract_type_lower = contract_type.lower()
        if contract_type_lower == "minting":
            return ContractType.MINTING_POLICY
        elif contract_type_lower == "spending":
            return ContractType.SPENDING_VALIDATOR
        else:
            raise ValueError(f"Invalid contract type: {contract_type}. Must be 'minting' or 'spending'")

    async def compile_contract_from_file(
        self,
        contract_path: str,
        contract_name: str,
        network: NetworkType,
        contract_type: str = "spending",
        compilation_params: list = None
    ) -> Contract:
        """
        Compile an Opshin contract from a file path.

        Args:
            contract_path: Path to the Opshin contract file (.py)
            contract_name: Name to store the contract under
            network: testnet or mainnet
            contract_type: "spending" or "minting"
            compilation_params: Optional list of compilation parameters

        Returns:
            Contract database record with compiled CBOR

        Raises:
            ContractCompilationError: If compilation fails
        """
        try:
            # Normalize contract type to enum
            contract_type_enum = self._normalize_contract_type(contract_type)

            # Validate file exists
            contract_file = pathlib.Path(contract_path)
            if not contract_file.exists():
                raise ContractCompilationError(f"Contract file not found: {contract_path}")

            # Read source code for storage
            with open(contract_file, 'r') as f:
                source_code = f.read()

            # Compile using Opshin
            if compilation_params:
                compiled = build(contract_file, *compilation_params)
            else:
                compiled = build(contract_file)

            plutus_contract = PlutusContract(compiled)

            # Extract contract information
            policy_id = plutus_contract.policy_id
            testnet_addr = str(plutus_contract.testnet_addr)
            mainnet_addr = str(plutus_contract.mainnet_addr)
            cbor_hex = plutus_contract.cbor.hex()

            # Calculate hash for versioning
            source_hash = hashlib.sha256(source_code.encode()).hexdigest()

            # Store in database
            contract = await self._store_contract(
                name=contract_name,
                policy_id=policy_id,
                cbor_hex=cbor_hex,
                testnet_addr=testnet_addr,
                mainnet_addr=mainnet_addr,
                source_code=source_code,
                source_hash=source_hash,
                contract_type=contract_type_enum,
                network=network,
                compilation_params=compilation_params
            )

            return contract

        except ContractCompilationError:
            raise
        except Exception as e:
            raise ContractCompilationError(f"Compilation failed: {str(e)}")

    async def compile_contract_from_source(
        self,
        source_code: str,
        contract_name: str,
        network: NetworkType,
        contract_type: str = "spending",
        compilation_params: list = None
    ) -> Contract:
        """
        Compile an Opshin contract from source code string.

        Args:
            source_code: Opshin contract source code
            contract_name: Name to store the contract under
            network: testnet or mainnet
            contract_type: "spending" or "minting"
            compilation_params: Optional list of compilation parameters

        Returns:
            Contract database record with compiled CBOR

        Raises:
            ContractCompilationError: If compilation fails
        """
        try:
            # Normalize contract type to enum
            contract_type_enum = self._normalize_contract_type(contract_type)

            # Create temporary file for compilation
            import tempfile
            import os

            # Create temp file with .py extension
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(source_code)
                temp_path = f.name

            try:
                # Compile using Opshin
                temp_file = pathlib.Path(temp_path)
                if compilation_params:
                    compiled = build(temp_file, *compilation_params)
                else:
                    compiled = build(temp_file)

                plutus_contract = PlutusContract(compiled)

                # Extract contract information
                policy_id = plutus_contract.policy_id
                testnet_addr = str(plutus_contract.testnet_addr)
                mainnet_addr = str(plutus_contract.mainnet_addr)
                cbor_hex = plutus_contract.cbor.hex()

                # Calculate hash for versioning
                source_hash = hashlib.sha256(source_code.encode()).hexdigest()

                # Store in database
                contract = await self._store_contract(
                    name=contract_name,
                    policy_id=policy_id,
                    cbor_hex=cbor_hex,
                    testnet_addr=testnet_addr,
                    mainnet_addr=mainnet_addr,
                    source_code=source_code,
                    source_hash=source_hash,
                    contract_type=contract_type_enum,
                    network=network,
                    compilation_params=compilation_params
                )

                return contract

            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except ContractCompilationError:
            raise
        except Exception as e:
            raise ContractCompilationError(f"Compilation failed: {str(e)}")

    async def _store_contract(
        self,
        name: str,
        policy_id: str,
        cbor_hex: str,
        testnet_addr: str,
        mainnet_addr: str,
        source_code: str,
        source_hash: str,
        contract_type: ContractType,
        network: NetworkType,
        compilation_params: list = None
    ) -> Contract:
        """
        Store compiled contract in database.

        Args:
            name: Contract name
            policy_id: Plutus policy ID
            cbor_hex: Compiled CBOR hex string
            testnet_addr: Testnet address
            mainnet_addr: Mainnet address
            source_code: Original source code
            source_hash: SHA256 hash of source code
            contract_type: ContractType enum (MINTING_POLICY or SPENDING_VALIDATOR)
            network: Network type
            compilation_params: Optional compilation parameters

        Returns:
            Contract database record
        """
        # Check if contract with same name already exists
        stmt = select(Contract).where(Contract.name == name, Contract.network == network)
        result = await self.session.execute(stmt)
        existing_contract = result.scalar_one_or_none()

        if existing_contract:
            # Update existing contract
            existing_contract.policy_id = policy_id
            existing_contract.cbor_hex = cbor_hex
            existing_contract.testnet_addr = testnet_addr
            existing_contract.mainnet_addr = mainnet_addr
            existing_contract.source_code = source_code
            existing_contract.source_hash = source_hash
            existing_contract.contract_type = contract_type
            existing_contract.compilation_params = compilation_params or []
            existing_contract.compiled_at = datetime.now(timezone.utc).replace(tzinfo=None)
            existing_contract.version = (existing_contract.version or 0) + 1

            await self.session.commit()
            await self.session.refresh(existing_contract)
            return existing_contract
        else:
            # Create new contract
            contract = Contract(
                name=name,
                policy_id=policy_id,
                cbor_hex=cbor_hex,
                testnet_addr=testnet_addr,
                mainnet_addr=mainnet_addr,
                source_code=source_code,
                source_hash=source_hash,
                contract_type=contract_type,
                network=network,
                compilation_params=compilation_params or [],
                compiled_at=datetime.now(timezone.utc).replace(tzinfo=None),
                version=1
            )

            self.session.add(contract)
            await self.session.commit()
            await self.session.refresh(contract)
            return contract

    async def get_contract(self, policy_id: str) -> Contract:
        """
        Get contract by policy ID.

        Args:
            policy_id: Contract policy ID (primary key)

        Returns:
            Contract record

        Raises:
            ContractNotFoundError: If contract not found
        """
        stmt = select(Contract).where(Contract.policy_id == policy_id)
        result = await self.session.execute(stmt)
        contract = result.scalar_one_or_none()

        if not contract:
            raise ContractNotFoundError(f"Contract {policy_id} not found")

        return contract

    async def get_contract_by_name(self, name: str, network: NetworkType) -> Contract | None:
        """
        Get contract by name and network.

        Args:
            name: Contract name
            network: Network type

        Returns:
            Contract record or None if not found
        """
        stmt = select(Contract).where(Contract.name == name, Contract.network == network)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_contracts(self, network: NetworkType | None = None) -> list[Contract]:
        """
        List all compiled contracts.

        Args:
            network: Optional network filter

        Returns:
            List of Contract records
        """
        if network:
            stmt = select(Contract).where(Contract.network == network).order_by(Contract.compiled_at.desc())
        else:
            stmt = select(Contract).order_by(Contract.compiled_at.desc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_contract(self, policy_id: str) -> bool:
        """
        Delete a contract.

        Args:
            policy_id: Contract policy ID (primary key)

        Returns:
            True if deleted successfully

        Raises:
            ContractNotFoundError: If contract not found
        """
        contract = await self.get_contract(policy_id)

        await self.session.delete(contract)
        await self.session.commit()

        return True
