"""
MongoDB Transaction Service

Business logic for building, signing, and submitting blockchain transactions.
Supports two-stage flow: BUILD → SIGN → SUBMIT

MongoDB/Beanie version for multi-tenant architecture.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from api.database.models import TransactionMongo, WalletMongo
from api.enums import TransactionStatus, NetworkType
from api.utils.encryption import decrypt_mnemonic
from api.utils.password import verify_password
from api.utils.metadata import prepare_metadata, validate_metadata_size
from cardano_offchain.wallet import CardanoWallet
from cardano_offchain.chain_context import CardanoChainContext
import pycardano as pc
from bson import ObjectId


def _extract_amount_from_value(value: pc.Value) -> list[dict]:
    """
    Extract amounts from PyCardano Value in Blockfrost-compatible format.

    Returns a list of dicts with 'unit' and 'quantity' keys:
    - lovelace: {"unit": "lovelace", "quantity": "1000000"}
    - native assets: {"unit": "<policy_id><asset_name>", "quantity": "1"}
    """
    amounts = [{"unit": "lovelace", "quantity": str(value.coin)}]
    if value.multi_asset:
        for policy_id, assets in value.multi_asset.items():
            for asset_name, qty in assets.items():
                unit = policy_id.payload.hex() + asset_name.payload.hex()
                amounts.append({"unit": unit, "quantity": str(qty)})
    return amounts


def _prepare_tx_dict_for_validation(tx_dict: dict) -> dict:
    """
    Prepare a MongoDB transaction document for Pydantic model validation.

    Handles:
    - Converting _id to tx_hash (preserving existing tx_hash if present)
    - Converting ObjectId to string
    - Adding default values for required fields missing in legacy documents
    """
    # Handle _id field - but preserve existing tx_hash if it exists
    if "_id" in tx_dict:
        _id_value = tx_dict.pop("_id")
        # Only use _id as tx_hash if tx_hash is not already set
        if "tx_hash" not in tx_dict or not tx_dict["tx_hash"]:
            # Convert ObjectId to string if necessary
            if isinstance(_id_value, ObjectId):
                tx_dict["tx_hash"] = str(_id_value)
            else:
                tx_dict["tx_hash"] = _id_value

    # Ensure required fields have defaults for legacy documents
    if "operation" not in tx_dict or not tx_dict["operation"]:
        tx_dict["operation"] = "send_ada"

    return tx_dict


def _compute_assets_hash(assets: list[dict]) -> str:
    """
    Compute a deterministic SHA256 hash of an assets list for duplicate detection.

    Normalizes by sorting policy IDs and token names to ensure consistent hashing
    regardless of input ordering.
    """
    normalized = []
    for asset in sorted(assets, key=lambda a: a.get("policyid", "")):
        tokens = asset.get("tokens", {})
        sorted_tokens = dict(sorted(tokens.items()))
        normalized.append({"policyid": asset["policyid"], "tokens": sorted_tokens})
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def _build_multi_asset_from_items(assets: list[dict]) -> pc.MultiAsset:
    """
    Convert a list of asset dicts (MultiAssetItem format) into a PyCardano MultiAsset.

    Each dict has:
    - policyid: hex string
    - tokens: {token_name: quantity}

    Token names are parsed as hex first, falling back to UTF-8 encoding.
    """
    multi_asset_dict = {}
    for item in assets:
        policy_id = pc.ScriptHash.from_primitive(item["policyid"])
        assets_dict = {}
        for token_name, amount in item["tokens"].items():
            try:
                asset_name = pc.AssetName(bytes.fromhex(token_name))
            except ValueError:
                asset_name = pc.AssetName(token_name.encode("utf-8"))
            assets_dict[asset_name] = amount
        multi_asset_dict[policy_id] = pc.Asset(assets_dict)
    return pc.MultiAsset(multi_asset_dict)


def _validate_wallet_has_tokens(
    utxos: list, required_assets: list[dict]
) -> None:
    """
    Validate that UTXOs contain enough of each requested token.

    Aggregates token balances across all UTXOs and compares against required amounts.

    Raises:
        InsufficientFundsError: If the wallet lacks any of the requested tokens.
    """
    # Aggregate available token balances from UTXOs
    available: dict[str, dict[str, int]] = {}  # {policy_id: {asset_name_hex: qty}}
    for utxo in utxos:
        value = utxo.output.amount
        if isinstance(value, pc.Value) and value.multi_asset:
            for policy_id, assets in value.multi_asset.items():
                pid_hex = policy_id.payload.hex()
                if pid_hex not in available:
                    available[pid_hex] = {}
                for asset_name, qty in assets.items():
                    aname_hex = asset_name.payload.hex()
                    available[pid_hex][aname_hex] = available[pid_hex].get(aname_hex, 0) + qty

    # Check each required asset
    for item in required_assets:
        pid = item["policyid"]
        for token_name, required_qty in item["tokens"].items():
            # Normalize token name to hex for comparison
            try:
                token_hex = bytes.fromhex(token_name).hex()  # Already hex
            except ValueError:
                token_hex = token_name.encode("utf-8").hex()

            wallet_qty = available.get(pid, {}).get(token_hex, 0)
            if wallet_qty < required_qty:
                raise InsufficientFundsError(
                    f"Insufficient token balance for policy {pid}, "
                    f"token {token_name}: have {wallet_qty}, need {required_qty}"
                )


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


class MongoTransactionService:
    """Service for managing blockchain transactions (MongoDB version)"""

    def __init__(self, database=None):
        """
        Initialize transaction service with optional database context.

        Args:
            database: MongoDB database instance for tenant isolation.
                     If None, uses the globally initialized database (not recommended for multi-tenant).
        """
        self.database = database

    def _get_wallet_collection(self):
        """Get the wallets collection from the tenant database."""
        if self.database is not None:
            return self.database.get_collection("wallets")
        return None

    def _get_transaction_collection(self):
        """Get the transactions collection from the tenant database."""
        if self.database is not None:
            return self.database.get_collection("transactions")
        return None

    async def _find_wallet_by_id(self, wallet_id: str):
        """Find wallet by ID using tenant database."""
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallet_dict = await collection.find_one({"_id": wallet_id})
            if wallet_dict:
                wallet_dict["id"] = wallet_dict.pop("_id")
                return WalletMongo.model_validate(wallet_dict)
            return None
        else:
            return await WalletMongo.find_one(WalletMongo.id == wallet_id)

    async def _find_transaction_by_hash(self, tx_hash: str):
        """Find transaction by hash using tenant database."""
        import logging
        logger = logging.getLogger(__name__)

        if self.database is not None:
            collection = self._get_transaction_collection()
            # tx_hash is stored as _id in MongoDB
            logger.info(f"🔍 Searching for transaction {tx_hash} in MongoDB")
            tx_dict = await collection.find_one({"_id": tx_hash})
            if tx_dict:
                logger.info(f"✅ Found transaction {tx_hash} in MongoDB")
                tx_dict = _prepare_tx_dict_for_validation(tx_dict)
                return TransactionMongo.model_validate(tx_dict)
            else:
                logger.warning(f"❌ Transaction {tx_hash} NOT FOUND in MongoDB")
                # Debug: List all transactions in collection
                all_txs = await collection.find({}).to_list(length=10)
                logger.info(f"📋 Recent transactions in DB: {[tx.get('_id', 'no-id')[:16] + '...' for tx in all_txs]}")
            return None
        else:
            return await TransactionMongo.find_one(TransactionMongo.tx_hash == tx_hash)

    async def _save_transaction(self, transaction: TransactionMongo):
        """Save transaction to tenant database."""
        if self.database is not None:
            collection = self._get_transaction_collection()
            tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
            # Remove 'id' if present and use tx_hash as _id
            if "id" in tx_dict:
                tx_dict.pop("id")
            # Ensure _id is set to tx_hash for MongoDB
            tx_dict["_id"] = transaction.tx_hash
            await collection.replace_one(
                {"_id": transaction.tx_hash},
                tx_dict,
                upsert=True
            )
        else:
            await transaction.save()

    async def _insert_transaction(self, transaction: TransactionMongo):
        """Insert transaction to tenant database."""
        import logging
        logger = logging.getLogger(__name__)

        if self.database is not None:
            collection = self._get_transaction_collection()
            tx_dict = transaction.model_dump(by_alias=True, exclude_unset=False)
            # Remove 'id' if present and use tx_hash as _id
            if "id" in tx_dict:
                tx_dict.pop("id")
            # Set _id to tx_hash for MongoDB (primary key)
            tx_dict["_id"] = transaction.tx_hash
            await collection.insert_one(tx_dict)
            logger.info(f"✅ Inserted transaction {transaction.tx_hash} into MongoDB")
        else:
            await transaction.insert()
            logger.info(f"✅ Inserted transaction {transaction.tx_hash} using Beanie")

    async def build_transaction(
        self,
        wallet_id: str,
        to_address: str,
        amount_ada: float | None,
        network: str,  # NetworkType as string ("testnet" or "mainnet")
        metadata: dict | None = None,
        assets: list[dict] | None = None
    ) -> TransactionMongo:
        """
        Build an unsigned transaction.

        Args:
            wallet_id: Payment key hash (wallet ID)
            to_address: Destination Cardano address
            amount_ada: Amount to send in ADA (required for ADA-only, optional with assets)
            network: testnet or mainnet
            metadata: Optional transaction metadata (CIP-20 or custom format)
            assets: Optional list of native tokens/assets to send

        Returns:
            TransactionMongo record with unsigned CBOR

        Raises:
            InsufficientFundsError: Not enough funds or tokens
            Exception: Other blockchain errors
        """
        # Get wallet from MongoDB
        wallet = await self._find_wallet_by_id(wallet_id)

        if not wallet:
            raise Exception(f"Wallet {wallet_id} not found")

        # Create chain context
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        if not blockfrost_api_key:
            raise Exception("Missing blockfrost_api_key environment variable")

        chain_context = CardanoChainContext(network=network, blockfrost_api_key=blockfrost_api_key)

        # Use wallet's enterprise address as the source
        from_address = wallet.enterprise_address

        # Determine operation type
        operation = "send_tokens" if assets else "send_ada"

        # Get UTXOs for the address
        context = chain_context.get_context()
        utxos = context.utxos(from_address)

        if not utxos:
            raise InsufficientFundsError(f"No UTXOs found at address {from_address}")

        # Build transaction
        builder = pc.TransactionBuilder(chain_context.context)

        # Add inputs (all available UTXOs) and track in lookup map for later extraction
        utxo_map = {}  # tx_hash:index -> utxo
        for utxo in utxos:
            builder.add_input(utxo)
            key = f"{utxo.input.transaction_id.payload.hex()}:{utxo.input.index}"
            utxo_map[key] = utxo

        # Build the output (ADA-only or multi-asset)
        min_lovelace_calculated = None
        assets_hash = None

        if assets:
            # Validate wallet has the requested tokens
            _validate_wallet_has_tokens(utxos, assets)

            # Build PyCardano MultiAsset
            multi_asset = _build_multi_asset_from_items(assets)

            # Calculate min lovelace for this output
            test_output = pc.TransactionOutput(
                pc.Address.from_primitive(to_address),
                pc.Value(0, multi_asset)
            )
            min_lovelace_calculated = pc.min_lovelace(context, output=test_output)

            # Determine coin amount: max(requested, min_lovelace)
            if amount_ada is not None:
                requested_lovelace = int(amount_ada * 1_000_000)
                amount_lovelace = max(requested_lovelace, min_lovelace_calculated)
            else:
                amount_lovelace = min_lovelace_calculated

            # Create multi-asset output
            builder.add_output(
                pc.TransactionOutput(
                    pc.Address.from_primitive(to_address),
                    pc.Value(amount_lovelace, multi_asset)
                )
            )

            # Compute assets hash for duplicate detection
            assets_hash = _compute_assets_hash(assets)
        else:
            # ADA-only transfer (existing behavior)
            amount_lovelace = int(amount_ada * 1_000_000)
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

        # Calculate transaction hash from transaction body
        # For unsigned transactions, the hash is calculated from the transaction body
        try:
            tx_body_hash = tx_body.hash()
            if tx_body_hash is None:
                raise Exception("Transaction body hash is None")
            tx_hash = tx_body_hash.hex()
        except Exception as e:
            # Fallback: create a Transaction object to get the ID
            unsigned_tx = pc.Transaction(tx_body, pc.TransactionWitnessSet())
            if unsigned_tx.id and hasattr(unsigned_tx.id, 'payload'):
                tx_hash = unsigned_tx.id.payload.hex()
            else:
                raise Exception(f"Failed to calculate transaction hash: {str(e)}")

        # Extract detailed inputs with full UTXO amount data (Blockfrost-compatible format)
        inputs = []
        total_input_lovelace = 0
        for tx_input in tx_body.inputs:
            tx_hash_hex = tx_input.transaction_id.payload.hex()
            idx = tx_input.index
            utxo = utxo_map.get(f"{tx_hash_hex}:{idx}")
            if utxo:
                amount = _extract_amount_from_value(utxo.output.amount)
                total_input_lovelace += utxo.output.amount.coin
                inputs.append({
                    "address": str(utxo.output.address),
                    "tx_hash": tx_hash_hex,
                    "output_index": idx,
                    "amount": amount,
                    "collateral": False,
                    "data_hash": utxo.output.datum_hash.payload.hex() if utxo.output.datum_hash else None,
                    "inline_datum": None,
                    "reference_script_hash": None
                })

        # Extract detailed outputs with amounts and indexes (Blockfrost-compatible format)
        outputs = []
        total_output_lovelace = 0
        for idx, tx_output in enumerate(tx_body.outputs):
            amount = _extract_amount_from_value(tx_output.amount)
            total_output_lovelace += tx_output.amount.coin
            outputs.append({
                "address": str(tx_output.address),
                "amount": amount,
                "output_index": idx,
                "data_hash": tx_output.datum_hash.payload.hex() if hasattr(tx_output, 'datum_hash') and tx_output.datum_hash else None,
                "inline_datum": None,
                "collateral": False,
                "reference_script_hash": None
            })

        # Calculate transaction size in bytes
        tx_size = len(bytes.fromhex(unsigned_cbor))

        # Check for FAILED transaction with same parameters - auto-reset to BUILT
        failed_query = {
            "wallet_id": wallet_id,
            "status": TransactionStatus.FAILED.value,
            "to_address": to_address,
            "amount_lovelace": amount_lovelace,
        }
        if assets_hash:
            failed_query["assets_hash"] = assets_hash

        if self.database is not None:
            collection = self._get_transaction_collection()
            failed_tx_dict = await collection.find_one(failed_query)
            if failed_tx_dict:
                failed_tx_dict = _prepare_tx_dict_for_validation(failed_tx_dict)
                failed_tx = TransactionMongo.model_validate(failed_tx_dict)
            else:
                failed_tx = None
        else:
            failed_tx = await TransactionMongo.find_one(
                TransactionMongo.wallet_id == wallet_id,
                TransactionMongo.status == TransactionStatus.FAILED.value,
                TransactionMongo.to_address == to_address,
                TransactionMongo.amount_lovelace == amount_lovelace,
            )

        if failed_tx:
            # Delete the old failed transaction and create a new one
            # We can't just update because tx_hash (the primary key) changes when UTXOs change
            old_tx_hash = failed_tx.tx_hash
            if self.database is not None:
                collection = self._get_transaction_collection()
                await collection.delete_one({"_id": old_tx_hash})
            else:
                await TransactionMongo.find_one(
                    TransactionMongo.tx_hash == old_tx_hash
                ).delete()

            # Create new transaction with the new tx_hash
            new_transaction = TransactionMongo(
                tx_hash=tx_hash,
                wallet_id=wallet_id,
                from_address=from_address,
                to_address=to_address,
                amount_lovelace=amount_lovelace,
                estimated_fee=estimated_fee,
                fee_lovelace=int(tx_body.fee),
                total_output_lovelace=total_output_lovelace,
                inputs=inputs,
                outputs=outputs,
                unsigned_cbor=unsigned_cbor,
                signed_cbor=None,
                status=TransactionStatus.BUILT.value,
                operation=operation,
                description=failed_tx.description or (
                    f"Send tokens to {to_address}" if assets else f"Send {amount_ada} ADA to {to_address}"
                ),
                tx_metadata=metadata if metadata else {},
                assets_sent=assets,
                assets_hash=assets_hash,
                error_message=None,
                submitted_at=None,
                confirmed_at=None,
                created_at=failed_tx.created_at,  # Preserve original creation time
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            await self._insert_transaction(new_transaction)
            return new_transaction

        # Check for duplicate transaction (same wallet, status BUILT, same to_address and amount)
        built_query = {
            "wallet_id": wallet_id,
            "status": TransactionStatus.BUILT.value,
            "to_address": to_address,
            "amount_lovelace": amount_lovelace,
        }
        if assets_hash:
            built_query["assets_hash"] = assets_hash

        if self.database is not None:
            collection = self._get_transaction_collection()
            existing_tx_dict = await collection.find_one(built_query)
            if existing_tx_dict:
                existing_tx_dict = _prepare_tx_dict_for_validation(existing_tx_dict)
                existing_tx = TransactionMongo.model_validate(existing_tx_dict)
            else:
                existing_tx = None
        else:
            existing_tx = await TransactionMongo.find_one(
                TransactionMongo.wallet_id == wallet_id,
                TransactionMongo.status == TransactionStatus.BUILT.value,
                TransactionMongo.to_address == to_address,
                TransactionMongo.amount_lovelace == amount_lovelace,
            )

        if existing_tx:
            # Return the existing transaction instead of creating a duplicate
            return existing_tx

        # Validate tx_hash before creating transaction
        if not tx_hash or tx_hash is None:
            raise Exception(
                f"Transaction hash is None or empty. "
                f"tx_body type: {type(tx_body)}, "
                f"has hash method: {hasattr(tx_body, 'hash')}"
            )

        # Create transaction record in MongoDB
        description = (
            f"Send tokens to {to_address}" if assets
            else f"Send {amount_ada} ADA to {to_address}"
        )
        transaction = TransactionMongo(
            wallet_id=wallet_id,
            tx_hash=tx_hash,
            status=TransactionStatus.BUILT.value,
            operation=operation,
            description=description,
            unsigned_cbor=unsigned_cbor,
            from_address=from_address,
            to_address=to_address,
            amount_lovelace=amount_lovelace,
            estimated_fee=estimated_fee,
            fee_lovelace=int(tx_body.fee),
            total_output_lovelace=total_output_lovelace,
            inputs=inputs,
            outputs=outputs,
            tx_metadata=metadata if metadata else {},
            assets_sent=assets,
            assets_hash=assets_hash,
        )

        await self._insert_transaction(transaction)
        return transaction

    async def sign_transaction(
        self,
        transaction_id: str,
        wallet_id: str,
        password: str,
        network: str  # NetworkType as string from MongoDB
    ) -> TransactionMongo:
        """
        Sign a built transaction with wallet password.

        Args:
            transaction_id: Transaction hash (tx_hash)
            wallet_id: Wallet ID (must own the transaction)
            password: Wallet password
            network: testnet or mainnet

        Returns:
            TransactionMongo record with signed CBOR and tx_hash

        Raises:
            TransactionNotFoundError: Transaction doesn't exist
            TransactionNotOwnedError: Wallet doesn't own this transaction
            InvalidTransactionStateError: Transaction not in BUILT state
            InvalidPasswordError: Wrong password
        """
        # Get transaction
        transaction = await self._find_transaction_by_hash(transaction_id)

        if not transaction:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found")

        # Verify ownership
        if transaction.wallet_id != wallet_id:
            raise TransactionNotOwnedError("You don't own this transaction")

        # Verify state
        if transaction.status != TransactionStatus.BUILT.value:
            raise InvalidTransactionStateError(
                f"Transaction must be in BUILT state, currently: {transaction.status}"
            )

        # Get wallet
        wallet = await self._find_wallet_by_id(wallet_id)

        if not wallet:
            raise Exception(f"Wallet {wallet_id} not found")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            from api.services.wallet_service_mongo import InvalidPasswordError

            raise InvalidPasswordError("Incorrect password")

        # Decrypt mnemonic TEMPORARILY
        mnemonic = decrypt_mnemonic(
            wallet.mnemonic_encrypted,
            password,
            wallet.encryption_salt
        )

        # Create CardanoWallet instance (network is already a string)
        cardano_wallet = CardanoWallet(mnemonic, network)

        # Get signing key for the enterprise address (index 0)
        signing_key = cardano_wallet.get_signing_key(0)

        # Parse unsigned CBOR back into transaction body
        unsigned_tx_body = pc.TransactionBody.from_cbor(transaction.unsigned_cbor)

        # Create verification key witness (signature)
        vkey_witness = pc.VerificationKeyWitness(
            signing_key.to_verification_key(),
            signing_key.sign(unsigned_tx_body.hash())
        )

        # Handle Plutus transactions (have script witnesses stored separately)
        if transaction.witness_cbor:
            partial_witness = pc.TransactionWitnessSet.from_cbor(transaction.witness_cbor)
            witness_set = pc.TransactionWitnessSet(
                vkey_witnesses=[vkey_witness],
                plutus_v2_script=partial_witness.plutus_v2_script,
                redeemer=partial_witness.redeemer,
                plutus_data=partial_witness.plutus_data,
            )
        else:
            # Simple transactions (existing behavior)
            witness_set = pc.TransactionWitnessSet(vkey_witnesses=[vkey_witness])

        # Reconstruct auxiliary data if transaction has metadata
        auxiliary_data = None
        if transaction.tx_metadata:
            auxiliary_data = prepare_metadata(transaction.tx_metadata)

        # Create signed transaction
        signed_tx = pc.Transaction(unsigned_tx_body, witness_set, True, auxiliary_data)

        # Get signed CBOR
        signed_cbor = signed_tx.to_cbor_hex()

        # NOTE: Do NOT update tx_hash! The transaction ID must remain constant.
        # The unsigned transaction hash is used as the permanent identifier.
        # Cardano allows this because the transaction body (which determines the ID)
        # doesn't change when adding witnesses.

        # Clear sensitive data immediately
        del mnemonic
        del cardano_wallet
        del signing_key

        # Update transaction in MongoDB (keep original tx_hash!)
        transaction.signed_cbor = signed_cbor
        transaction.status = TransactionStatus.SIGNED.value
        transaction.fee_lovelace = int(unsigned_tx_body.fee)
        transaction.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        await self._save_transaction(transaction)
        return transaction

    async def submit_transaction(
        self,
        transaction_id: str,
        wallet_id: str,
        network: str  # NetworkType as string from MongoDB
    ) -> TransactionMongo:
        """
        Submit a signed transaction to the blockchain.

        Args:
            transaction_id: Transaction hash (tx_hash)
            wallet_id: Wallet ID (must own the transaction)
            network: testnet or mainnet

        Returns:
            TransactionMongo record with SUBMITTED status

        Raises:
            TransactionNotFoundError: Transaction doesn't exist
            TransactionNotOwnedError: Wallet doesn't own this transaction
            InvalidTransactionStateError: Transaction not in SIGNED state
        """
        # Get transaction
        transaction = await self._find_transaction_by_hash(transaction_id)

        if not transaction:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found")

        # Verify ownership
        if transaction.wallet_id != wallet_id:
            raise TransactionNotOwnedError("You don't own this transaction")

        # Verify state
        if transaction.status != TransactionStatus.SIGNED.value:
            raise InvalidTransactionStateError(
                f"Transaction must be in SIGNED state, currently: {transaction.status}"
            )

        # Create chain context
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        if not blockfrost_api_key:
            raise Exception("Missing blockfrost_api_key environment variable")

        chain_context = CardanoChainContext(network=network, blockfrost_api_key=blockfrost_api_key)
        context = chain_context.get_context()

        # Parse signed transaction
        signed_tx = pc.Transaction.from_cbor(transaction.signed_cbor)

        # Submit to blockchain
        try:
            context.submit_tx(signed_tx)
        except Exception as e:
            # Update with error
            transaction.status = TransactionStatus.FAILED.value
            transaction.error_message = str(e)
            transaction.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self._save_transaction(transaction)
            raise Exception(f"Failed to submit transaction: {str(e)}")

        # Update transaction
        transaction.status = TransactionStatus.SUBMITTED.value
        transaction.submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        transaction.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        await self._save_transaction(transaction)
        return transaction

    async def sign_and_submit_transaction(
        self,
        transaction_id: str,
        wallet_id: str,
        password: str,
        network: NetworkType
    ) -> TransactionMongo:
        """
        Sign and submit a transaction in one operation (convenience method).

        Args:
            transaction_id: Transaction hash (tx_hash)
            wallet_id: Wallet ID (must own the transaction)
            password: Wallet password
            network: testnet or mainnet

        Returns:
            TransactionMongo record with SUBMITTED status

        Raises:
            Same as sign_transaction and submit_transaction
        """
        # Sign the transaction
        transaction = await self.sign_transaction(transaction_id, wallet_id, password, network)

        # Submit the transaction
        transaction = await self.submit_transaction(transaction_id, wallet_id, network)

        return transaction
