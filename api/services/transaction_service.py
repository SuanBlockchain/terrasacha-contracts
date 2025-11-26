"""
Transaction Service

Business logic for building, signing, and submitting blockchain transactions.
Supports two-stage flow: BUILD → SIGN → SUBMIT
"""

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.database.models import Transaction, Wallet
from api.database.repositories.transaction import TransactionRepository
from api.enums import TransactionStatus, NetworkType
from api.utils.encryption import decrypt_mnemonic
from api.utils.password import verify_password
from api.utils.metadata import prepare_metadata, validate_metadata_size
from cardano_offchain.wallet import CardanoWallet
from cardano_offchain.chain_context import CardanoChainContext
import pycardano as pc


# Custom exceptions
class TransactionNotFoundError(Exception):
    """Transaction not found in database"""
    pass


class TransactionNotOwnedError(Exception):
    """User doesn't own this transaction"""
    pass


class InvalidTransactionStateError(Exception):
    """Transaction is not in the correct state for this operation"""
    pass


class InsufficientFundsError(Exception):
    """Not enough funds to create transaction"""
    pass


class TransactionService:
    """Service for managing blockchain transactions"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tx_repo = TransactionRepository(session)

    async def build_transaction(
        self,
        wallet_id: str,
        from_address_index: int,
        to_address: str,
        amount_ada: float,
        network: NetworkType,
        metadata: dict | None = None
    ) -> Transaction:
        """
        Build an unsigned transaction.

        Args:
            wallet_id: Payment key hash (wallet ID)
            from_address_index: Index of source address (0 = main)
            to_address: Destination Cardano address
            amount_ada: Amount to send in ADA
            network: testnet or mainnet
            metadata: Optional transaction metadata (CIP-20 or custom format)

        Returns:
            Transaction record with unsigned CBOR

        Raises:
            InsufficientFundsError: Not enough funds
            Exception: Other blockchain errors
        """
        # Get wallet from database
        stmt = select(Wallet).where(Wallet.id == wallet_id)
        result = await self.session.execute(stmt)
        wallet = result.scalar_one_or_none()

        if not wallet:
            raise Exception(f"Wallet {wallet_id} not found")

        # Create chain context
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        if not blockfrost_api_key:
            raise Exception("Missing blockfrost_api_key environment variable")

        chain_context = CardanoChainContext(network=network.value, blockfrost_api_key=blockfrost_api_key)

        # Simplified: Use wallet.enterprise_address for index 0
        if from_address_index == 0:
            from_address = wallet.enterprise_address
        else:
            raise NotImplementedError(
                "Derived addresses (index > 0) not yet supported in build phase. "
                "Use index 0 (main address) or implement address storage."
            )

        # Convert ADA to lovelace
        amount_lovelace = int(amount_ada * 1_000_000)

        # Get UTXOs for the address
        context = chain_context.get_context()
        utxos = context.utxos(from_address)

        if not utxos:
            raise InsufficientFundsError(f"No UTXOs found at address {from_address}")

        # Build transaction
        builder = pc.TransactionBuilder(chain_context.context)

        # Add inputs (all available UTXOs)
        for utxo in utxos:
            builder.add_input(utxo)

        # Add output
        builder.add_output(
            pc.TransactionOutput(
                pc.Address.from_primitive(to_address),
                pc.Value(amount_lovelace)
            )
        )

        # Set fee buffer (will be calculated properly during build)
        builder.fee_buffer = 1_000_000  # 1 ADA fee buffer

        # Add metadata if provided
        if metadata:
            # Validate metadata size
            is_valid, error_message = validate_metadata_size(metadata)
            if not is_valid:
                raise Exception(f"Invalid metadata: {error_message}")

            # Prepare and attach metadata
            auxiliary_data = prepare_metadata(metadata)
            if auxiliary_data:
                builder.auxiliary_data = auxiliary_data

        # Build the transaction (WITHOUT signing)
        try:
            tx_body = builder.build(change_address=pc.Address.from_primitive(from_address))
        except Exception as e:
            if "insufficient" in str(e).lower():
                raise InsufficientFundsError(f"Insufficient funds: {str(e)}")
            raise

        # Get the unsigned transaction CBOR
        unsigned_cbor = tx_body.to_cbor_hex()

        # Calculate estimated fee
        estimated_fee = int(tx_body.fee) if hasattr(tx_body, 'fee') else 170000  # Default estimate

        # Calculate transaction hash from unsigned transaction
        # Create unsigned transaction to get the hash
        unsigned_tx = pc.Transaction(tx_body, pc.TransactionWitnessSet())
        tx_hash = str(unsigned_tx.id.payload.hex()) if unsigned_tx.id else None

        # Extract inputs and outputs for database storage
        inputs = []
        for tx_input in tx_body.inputs:
            inputs.append({
                "address": str(from_address),  # Simplified - all inputs from source address
                "tx_hash": str(tx_input.transaction_id.payload.hex()),
                "index": tx_input.index
            })

        outputs = []
        for tx_output in tx_body.outputs:
            outputs.append({
                "address": str(tx_output.address),
                "amount": int(tx_output.amount.coin)
            })

        # Check for FAILED transaction with same parameters - auto-reset to BUILT
        # This allows retrying failed transactions without manual intervention
        failed_stmt = select(Transaction).where(
            Transaction.wallet_id == wallet_id,
            Transaction.status == TransactionStatus.FAILED,
            Transaction.to_address == to_address,
            Transaction.amount_lovelace == amount_lovelace,
            Transaction.from_address_index == from_address_index
        ).order_by(Transaction.created_at.desc())
        failed_result = await self.session.execute(failed_stmt)
        failed_tx = failed_result.scalars().first()

        if failed_tx:
            # Reset the failed transaction to BUILT with new transaction data
            failed_tx.status = TransactionStatus.BUILT
            failed_tx.unsigned_cbor = unsigned_cbor
            failed_tx.tx_hash = tx_hash
            failed_tx.inputs = inputs
            failed_tx.outputs = outputs
            failed_tx.estimated_fee = estimated_fee
            failed_tx.tx_metadata = metadata if metadata else {}
            failed_tx.error_message = None
            failed_tx.signed_cbor = None
            failed_tx.submitted_at = None
            failed_tx.confirmed_at = None
            await self.session.commit()
            await self.session.refresh(failed_tx)
            return failed_tx

        # Check for duplicate transaction (same wallet, status BUILT, same to_address and amount)
        # This prevents abuse by repeatedly building the same transaction
        built_stmt = select(Transaction).where(
            Transaction.wallet_id == wallet_id,
            Transaction.status == TransactionStatus.BUILT,
            Transaction.to_address == to_address,
            Transaction.amount_lovelace == amount_lovelace,
            Transaction.from_address_index == from_address_index
        ).order_by(Transaction.created_at.desc())
        built_result = await self.session.execute(built_stmt)
        existing_tx = built_result.scalars().first()  # Get the most recent one if multiple exist

        if existing_tx:
            # Return the existing transaction instead of creating a duplicate
            return existing_tx

        # Create transaction record in database
        transaction = Transaction(
            wallet_id=wallet_id,
            tx_hash=tx_hash,
            status=TransactionStatus.BUILT,
            operation="send_ada",
            description=f"Send {amount_ada} ADA to {to_address}",  # Full address
            unsigned_cbor=unsigned_cbor,
            from_address_index=from_address_index,
            from_address=from_address,
            to_address=to_address,
            amount_lovelace=amount_lovelace,
            estimated_fee=estimated_fee,
            inputs=inputs,
            outputs=outputs,
            tx_metadata=metadata if metadata else {},
        )

        self.session.add(transaction)
        await self.session.commit()
        await self.session.refresh(transaction)

        return transaction

    async def sign_transaction(
        self,
        transaction_id: str,
        wallet_id: str,
        password: str,
        network: NetworkType
    ) -> Transaction:
        """
        Sign a built transaction with wallet password.

        Args:
            transaction_id: Database transaction ID
            wallet_id: Wallet ID (must own the transaction)
            password: Wallet password
            network: testnet or mainnet

        Returns:
            Transaction record with signed CBOR and tx_hash

        Raises:
            TransactionNotFoundError: Transaction doesn't exist
            TransactionNotOwnedError: Wallet doesn't own this transaction
            InvalidTransactionStateError: Transaction not in BUILT state
            InvalidPasswordError: Wrong password
        """
        # Get transaction
        transaction = await self.tx_repo.get(transaction_id)
        if not transaction:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found")

        # Verify ownership
        if transaction.wallet_id != wallet_id:
            raise TransactionNotOwnedError("You don't own this transaction")

        # Verify state
        if transaction.status != TransactionStatus.BUILT:
            raise InvalidTransactionStateError(
                f"Transaction must be in BUILT state, currently: {transaction.status.value}"
            )

        # Get wallet
        stmt = select(Wallet).where(Wallet.id == wallet_id)
        result = await self.session.execute(stmt)
        wallet = result.scalar_one_or_none()

        if not wallet:
            raise Exception(f"Wallet {wallet_id} not found")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            from api.services.wallet_service import InvalidPasswordError
            raise InvalidPasswordError("Incorrect password")

        # Decrypt mnemonic TEMPORARILY
        mnemonic = decrypt_mnemonic(
            wallet.mnemonic_encrypted,
            password,
            wallet.encryption_salt
        )

        # Create CardanoWallet instance
        cardano_wallet = CardanoWallet(mnemonic, network.value)

        # Get signing key for the address index
        signing_key = cardano_wallet.get_signing_key(transaction.from_address_index)

        # Parse unsigned CBOR back into transaction body
        unsigned_tx_body = pc.TransactionBody.from_cbor(transaction.unsigned_cbor)

        # Create verification key witness (signature)
        vkey_witness = pc.VerificationKeyWitness(signing_key.to_verification_key(), signing_key.sign(unsigned_tx_body.hash()))

        # Create witness set with the signature
        witness_set = pc.TransactionWitnessSet(vkey_witnesses=[vkey_witness])

        # Reconstruct auxiliary data if transaction has metadata
        auxiliary_data = None
        if transaction.tx_metadata:
            # Prepare auxiliary data from stored metadata
            auxiliary_data = prepare_metadata(transaction.tx_metadata)

        # Create signed transaction (including auxiliary data if present)
        # PyCardano Transaction signature: Transaction(body, witness_set, valid=True, auxiliary_data=None)
        signed_tx = pc.Transaction(unsigned_tx_body, witness_set, True, auxiliary_data)

        # Get signed CBOR and hash
        signed_cbor = signed_tx.to_cbor_hex()
        tx_hash = str(signed_tx.id.payload.hex())

        # Clear sensitive data immediately
        del mnemonic
        del cardano_wallet
        del signing_key

        # Update transaction in database
        transaction.signed_cbor = signed_cbor
        transaction.tx_hash = tx_hash
        transaction.status = TransactionStatus.SIGNED
        transaction.fee_lovelace = int(unsigned_tx_body.fee)

        await self.session.commit()
        await self.session.refresh(transaction)

        return transaction

    async def submit_transaction(
        self,
        transaction_id: str,
        wallet_id: str,
        network: NetworkType
    ) -> Transaction:
        """
        Submit a signed transaction to the blockchain.

        Args:
            transaction_id: Database transaction ID
            wallet_id: Wallet ID (must own the transaction)
            network: testnet or mainnet

        Returns:
            Transaction record with SUBMITTED status

        Raises:
            TransactionNotFoundError: Transaction doesn't exist
            TransactionNotOwnedError: Wallet doesn't own this transaction
            InvalidTransactionStateError: Transaction not in SIGNED state
        """
        # Get transaction
        transaction = await self.tx_repo.get(transaction_id)
        if not transaction:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found")

        # Verify ownership
        if transaction.wallet_id != wallet_id:
            raise TransactionNotOwnedError("You don't own this transaction")

        # Verify state
        if transaction.status != TransactionStatus.SIGNED:
            raise InvalidTransactionStateError(
                f"Transaction must be in SIGNED state, currently: {transaction.status.value}"
            )

        # Create chain context
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        if not blockfrost_api_key:
            raise Exception("Missing blockfrost_api_key environment variable")

        chain_context = CardanoChainContext(network=network.value, blockfrost_api_key=blockfrost_api_key)
        context = chain_context.get_context()

        # Parse signed transaction
        signed_tx = pc.Transaction.from_cbor(transaction.signed_cbor)

        # Submit to blockchain
        try:
            context.submit_tx(signed_tx)
        except Exception as e:
            # Update with error
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = str(e)
            await self.session.commit()
            raise Exception(f"Failed to submit transaction: {str(e)}")

        # Update transaction
        transaction.status = TransactionStatus.SUBMITTED
        transaction.submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)

        await self.session.commit()
        await self.session.refresh(transaction)

        return transaction

    async def sign_and_submit_transaction(
        self,
        transaction_id: str,
        wallet_id: str,
        password: str,
        network: NetworkType
    ) -> Transaction:
        """
        Sign and submit a transaction in one operation (convenience method).

        Args:
            transaction_id: Database transaction ID
            wallet_id: Wallet ID (must own the transaction)
            password: Wallet password
            network: testnet or mainnet

        Returns:
            Transaction record with SUBMITTED status

        Raises:
            Same as sign_transaction and submit_transaction
        """
        # Sign the transaction
        transaction = await self.sign_transaction(
            transaction_id=transaction_id,
            wallet_id=wallet_id,
            password=password,
            network=network
        )

        # Submit the transaction
        transaction = await self.submit_transaction(
            transaction_id=transaction_id,
            wallet_id=wallet_id,
            network=network
        )

        return transaction
