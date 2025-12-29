"""
Wallet Service - MongoDB/Beanie Version

Business logic layer for wallet operations using MongoDB.
Handles wallet creation, encryption, unlocking, and management.
"""

from datetime import datetime, timezone
from typing import Any

import pycardano as pc
from blockfrost import ApiError, BlockFrostApi
from cryptography.fernet import InvalidToken

from api.database.models import WalletMongo, WalletSessionMongo
from api.enums import NetworkType, WalletRole
from api.utils.encryption import decrypt_mnemonic, encrypt_mnemonic
from api.utils.password import hash_password, needs_rehash, validate_password_strength, verify_password
from cardano_offchain.wallet import CardanoWallet


class WalletServiceError(Exception):
    """Base exception for wallet service errors"""
    pass


class WalletNotFoundError(WalletServiceError):
    """Wallet not found"""
    pass


class InvalidPasswordError(WalletServiceError):
    """Invalid password"""
    pass


class WalletAlreadyExistsError(WalletServiceError):
    """Wallet with this name already exists"""
    pass


class InvalidMnemonicError(WalletServiceError):
    """Invalid or corrupted mnemonic"""
    pass


class PermissionDeniedError(WalletServiceError):
    """Insufficient permissions for operation"""
    pass


class MongoWalletService:
    """
    Service for wallet management operations using MongoDB/Beanie

    Handles wallet lifecycle including creation, import, unlock, lock, and deletion.
    """

    def __init__(self, database=None):
        """
        Initialize wallet service with optional database context.

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

    def _get_session_collection(self):
        """Get the wallet_sessions collection from the tenant database."""
        if self.database is not None:
            return self.database.get_collection("wallet_sessions")
        return None

    async def _find_wallet_by_id(self, payment_key_hash: str) -> WalletMongo | None:
        """Find wallet by payment key hash using tenant database."""
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallet_dict = await collection.find_one({"_id": payment_key_hash})
            if wallet_dict:
                # Convert MongoDB document to WalletMongo
                wallet_dict["id"] = wallet_dict.pop("_id")
                # Use model_validate to properly handle the document
                return WalletMongo.model_validate(wallet_dict)
            return None
        else:
            return await WalletMongo.get(payment_key_hash)

    async def _find_wallet_by_name(self, name: str) -> WalletMongo | None:
        """Find wallet by name using tenant database."""
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallet_dict = await collection.find_one({"name": name})
            if wallet_dict:
                # Convert MongoDB document to WalletMongo
                wallet_dict["id"] = wallet_dict.pop("_id")
                # Use model_validate to properly handle the document
                return WalletMongo.model_validate(wallet_dict)
            return None
        else:
            query = WalletMongo.find_one(WalletMongo.name == name)
            return await query

    async def _save_wallet(self, wallet: WalletMongo) -> None:
        """Save wallet to tenant database."""
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallet_dict = wallet.model_dump(by_alias=True, exclude_unset=False)
            # Handle id -> _id conversion (Beanie uses id, MongoDB uses _id)
            if "id" in wallet_dict:
                wallet_dict["_id"] = wallet_dict.pop("id")
            elif "_id" not in wallet_dict:
                wallet_dict["_id"] = wallet.id
            await collection.replace_one({"_id": wallet_dict["_id"]}, wallet_dict)
        else:
            await wallet.save()

    async def _delete_wallet(self, wallet: WalletMongo) -> None:
        """Delete wallet from tenant database."""
        if self.database is not None:
            collection = self._get_wallet_collection()
            await collection.delete_one({"_id": wallet.id})
        else:
            await wallet.delete()

    async def _is_first_wallet(self) -> bool:
        """
        Check if this is the first wallet for the current tenant.

        Returns:
            True if no wallets exist, False otherwise
        """
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallet_count = await collection.count_documents({})
            return wallet_count == 0
        else:
            # For non-tenant mode, count all wallets
            wallet_count = await WalletMongo.find_all().count()
            return wallet_count == 0

    async def create_wallet(
        self, name: str, password: str, network: NetworkType = NetworkType.TESTNET, role: WalletRole = WalletRole.USER
    ) -> tuple[WalletMongo, str]:
        """
        Create a new wallet with generated mnemonic.

        Generates a 24-word BIP39 mnemonic, encrypts it with the password,
        and stores it in MongoDB.

        Args:
            name: Unique wallet name
            password: Password for encrypting the mnemonic
            network: Blockchain network (testnet or mainnet)
            role: Wallet role (user or core)

        Returns:
            Tuple of (wallet, mnemonic) - mnemonic is returned ONCE for user to backup

        Raises:
            WalletAlreadyExistsError: If wallet name already exists
            ValueError: If password doesn't meet strength requirements
        """
        # Check if wallet already exists
        existing_wallet = await self._find_wallet_by_name(name)
        if existing_wallet:
            raise WalletAlreadyExistsError(f"Wallet '{name}' already exists")

        # Validate password strength
        validate_password_strength(password)

        # Check if this is the first wallet for auto-promotion to CORE
        is_first_wallet = await self._is_first_wallet()
        if is_first_wallet:
            role = WalletRole.CORE
            import logging
            logging.info(f"Auto-promoting first wallet '{name}' to CORE role for tenant")

        # Generate 24-word mnemonic (256-bit entropy)
        mnemonic = pc.HDWallet.generate_mnemonic(strength=256)

        # Create CardanoWallet to get addresses
        cardano_wallet = CardanoWallet(mnemonic, network.value)

        # Encrypt mnemonic with password
        encrypted_mnemonic, salt = encrypt_mnemonic(mnemonic, password)

        # Hash password
        password_hash_str = hash_password(password)

        # Get payment key hash as hex string
        payment_key_hash = cardano_wallet.get_payment_verification_key_hash().hex()

        # Create wallet record
        wallet = WalletMongo(
            name=name,
            network=network.value,
            mnemonic_encrypted=encrypted_mnemonic,
            encryption_salt=salt,
            password_hash=password_hash_str,
            enterprise_address=str(cardano_wallet.enterprise_address),
            staking_address=str(cardano_wallet.staking_address),
            id=payment_key_hash,  # Payment key hash is the wallet ID
            wallet_role=role.value,
            is_locked=True,  # Locked by default
            is_default=False,
        )

        # Save to MongoDB (use explicit database for tenant isolation)
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallet_dict = wallet.model_dump(by_alias=True, exclude_unset=False)
            # Handle id -> _id conversion (Beanie uses id, MongoDB uses _id)
            if "id" in wallet_dict:
                wallet_dict["_id"] = wallet_dict.pop("id")
            elif "_id" not in wallet_dict:
                wallet_dict["_id"] = wallet.id
            await collection.insert_one(wallet_dict)
        else:
            await wallet.insert()

        # Return wallet and mnemonic (user must save mnemonic!)
        return wallet, mnemonic

    async def import_wallet(
        self,
        name: str,
        mnemonic: str,
        password: str,
        network: NetworkType = NetworkType.TESTNET,
        wallet_role: WalletRole = WalletRole.USER
    ) -> WalletMongo:
        """
        Import an existing wallet from mnemonic.

        Args:
            name: Unique wallet name
            mnemonic: BIP39 mnemonic phrase (12-24 words)
            password: Password for encrypting the mnemonic
            network: Blockchain network (testnet or mainnet)
            wallet_role: Wallet role (USER or CORE), defaults to USER

        Returns:
            Created wallet

        Raises:
            WalletAlreadyExistsError: If wallet name already exists
            InvalidMnemonicError: If mnemonic is invalid
            ValueError: If password doesn't meet strength requirements
        """
        # Check if wallet already exists
        existing_wallet = await self._find_wallet_by_name(name)
        if existing_wallet:
            raise WalletAlreadyExistsError(f"Wallet '{name}' already exists")

        # Validate password strength
        validate_password_strength(password)

        # Check if this is the first wallet for auto-promotion to CORE
        is_first_wallet = await self._is_first_wallet()
        if is_first_wallet:
            wallet_role = WalletRole.CORE
            import logging
            logging.info(f"Auto-promoting first imported wallet '{name}' to CORE role for tenant")

        # Validate mnemonic by trying to create a wallet
        try:
            cardano_wallet = CardanoWallet(mnemonic, network.value)
        except Exception as e:
            raise InvalidMnemonicError(f"Invalid mnemonic: {e}") from e

        # Encrypt mnemonic with password
        encrypted_mnemonic, salt = encrypt_mnemonic(mnemonic, password)

        # Hash password
        password_hash_str = hash_password(password)

        # Get payment key hash as hex string
        payment_key_hash = cardano_wallet.get_payment_verification_key_hash().hex()

        # Create wallet record
        wallet = WalletMongo(
            name=name,
            network=network.value,
            mnemonic_encrypted=encrypted_mnemonic,
            encryption_salt=salt,
            password_hash=password_hash_str,
            enterprise_address=str(cardano_wallet.enterprise_address),
            staking_address=str(cardano_wallet.staking_address),
            id=payment_key_hash,  # Payment key hash is the wallet ID
            wallet_role=wallet_role.value,  # Use provided role (defaults to USER)
            is_locked=True,
            is_default=False,
        )

        # Save to MongoDB (use explicit database for tenant isolation)
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallet_dict = wallet.model_dump(by_alias=True, exclude_unset=False)
            # Handle id -> _id conversion (Beanie uses id, MongoDB uses _id)
            if "id" in wallet_dict:
                wallet_dict["_id"] = wallet_dict.pop("id")
            elif "_id" not in wallet_dict:
                wallet_dict["_id"] = wallet.id
            await collection.insert_one(wallet_dict)
        else:
            await wallet.insert()

        return wallet

    async def is_wallet_locked(self, payment_key_hash: str) -> bool:
        """
        Check if wallet is locked based on active sessions.

        A wallet is considered locked if it has NO valid (non-revoked, non-expired) sessions.
        This replaces the old is_locked field approach with session-based implicit locking.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            True if wallet is locked (no active sessions), False otherwise
        """
        if self.database is not None:
            collection = self._get_session_collection()
            active_sessions_count = await collection.count_documents({
                "wallet_id": payment_key_hash,
                "revoked": False,
                "expires_at": {"$gt": datetime.now(timezone.utc).replace(tzinfo=None)}
            })
        else:
            active_sessions_count = await WalletSessionMongo.find(
                WalletSessionMongo.wallet_id == payment_key_hash,
                WalletSessionMongo.revoked == False,
                WalletSessionMongo.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
            ).count()

        return active_sessions_count == 0

    async def get_active_sessions_count(self, payment_key_hash: str) -> int:
        """
        Get count of active sessions for a wallet.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Number of active sessions
        """
        if self.database is not None:
            collection = self._get_session_collection()
            return await collection.count_documents({
                "wallet_id": payment_key_hash,
                "revoked": False,
                "expires_at": {"$gt": datetime.now(timezone.utc).replace(tzinfo=None)}
            })
        else:
            return await WalletSessionMongo.find(
                WalletSessionMongo.wallet_id == payment_key_hash,
                WalletSessionMongo.revoked == False,
                WalletSessionMongo.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
            ).count()

    async def unlock_wallet(self, payment_key_hash: str, password: str) -> tuple[WalletMongo, CardanoWallet]:
        """
        Unlock a wallet by decrypting its mnemonic.

        NOTE: This method ALWAYS allows unlock if password is correct, even if wallet
        already has active sessions. This enables multiple concurrent sessions and
        prevents client token loss from causing deadlocks.

        Args:
            payment_key_hash: Payment key hash (wallet ID)
            password: User's password

        Returns:
            Tuple of (wallet, cardano_wallet)

        Raises:
            WalletNotFoundError: If wallet doesn't exist
            InvalidPasswordError: If password is incorrect
        """
        # Get wallet from MongoDB
        wallet = await self._find_wallet_by_id(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect password")

        # Check if password hash needs rehashing (security upgrade)
        if needs_rehash(wallet.password_hash):
            # Rehash password with updated parameters
            wallet.password_hash = hash_password(password)
            await self._save_wallet(wallet)

        # Decrypt mnemonic
        try:
            mnemonic = decrypt_mnemonic(wallet.mnemonic_encrypted, password, wallet.encryption_salt)
        except (ValueError, InvalidToken) as e:
            raise InvalidPasswordError("Failed to decrypt mnemonic") from e

        # Create CardanoWallet instance
        try:
            cardano_wallet = CardanoWallet(mnemonic, wallet.network)
        except Exception as e:
            raise InvalidMnemonicError(f"Failed to create wallet from stored mnemonic: {e}") from e

        # Update wallet tracking (keep is_locked for backward compatibility during migration)
        wallet.is_locked = False
        wallet.last_unlocked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._save_wallet(wallet)

        return wallet, cardano_wallet

    async def get_active_sessions(self, payment_key_hash: str) -> list[WalletSessionMongo]:
        """
        Get all active sessions for a wallet.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            List of active (non-revoked, non-expired) sessions
        """
        if self.database is not None:
            collection = self._get_session_collection()
            sessions_data = await collection.find({
                "wallet_id": payment_key_hash,
                "revoked": False,
                "expires_at": {"$gt": datetime.now(timezone.utc).replace(tzinfo=None)}
            }).sort("created_at", -1).to_list(None)
            return [WalletSessionMongo(**session) for session in sessions_data]
        else:
            return await WalletSessionMongo.find(
                WalletSessionMongo.wallet_id == payment_key_hash,
                WalletSessionMongo.revoked == False,
                WalletSessionMongo.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
            ).sort(-WalletSessionMongo.created_at).to_list()

    async def lock_wallet(self, payment_key_hash: str) -> WalletMongo:
        """
        Lock a wallet by revoking all active sessions.

        NOTE: This method sets is_locked for backward compatibility, but the actual
        locking is done via session revocation. The wallet is truly locked when
        all sessions are revoked.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
        """
        wallet = await self._find_wallet_by_id(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Update is_locked field (backward compatibility during migration)
        wallet.is_locked = True
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._save_wallet(wallet)

        return wallet

    async def get_wallet(self, payment_key_hash: str) -> WalletMongo | None:
        """
        Get wallet by payment key hash.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Wallet or None if not found
        """
        return await self._find_wallet_by_id(payment_key_hash)

    async def get_wallet_by_name(self, name: str) -> WalletMongo | None:
        """
        Get wallet by name.

        Args:
            name: Wallet name

        Returns:
            Wallet or None if not found
        """
        return await self._find_wallet_by_name(name)

    async def list_wallets(self, skip: int = 0, limit: int = 100) -> list[WalletMongo]:
        """
        Get all wallets for current tenant.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of wallets
        """
        if self.database is not None:
            collection = self._get_wallet_collection()
            wallets_data = await collection.find().skip(skip).limit(limit).to_list(None)
            # Convert MongoDB documents to WalletMongo objects
            wallets = []
            for w in wallets_data:
                w["id"] = w.pop("_id")
                wallets.append(WalletMongo.model_validate(w))
            return wallets
        else:
            return await WalletMongo.find_all().skip(skip).limit(limit).to_list()

    async def delete_wallet(self, payment_key_hash: str, password: str, requesting_wallet_role: WalletRole) -> bool:
        """
        Delete a wallet after password verification.

        Args:
            payment_key_hash: Payment key hash (wallet ID)
            password: User's password for verification
            requesting_wallet_role: Role of wallet making the request

        Returns:
            True if deleted, False if not found

        Raises:
            InvalidPasswordError: If password is incorrect
            PermissionDeniedError: If user role tries to delete core wallet
        """
        wallet = await self._find_wallet_by_id(payment_key_hash)
        if not wallet:
            return False

        # Permission check: USER role cannot delete CORE wallets
        if requesting_wallet_role == WalletRole.USER and wallet.wallet_role == WalletRole.CORE.value:
            raise PermissionDeniedError("User wallets cannot delete core wallets")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect password")

        # Delete wallet
        await self._delete_wallet(wallet)

        return True

    async def change_password(self, payment_key_hash: str, current_password: str, new_password: str) -> WalletMongo:
        """
        Change wallet password (re-encrypts mnemonic).

        Args:
            payment_key_hash: Payment key hash (wallet ID)
            current_password: Current password
            new_password: New password

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
            InvalidPasswordError: If current password is incorrect
            ValueError: If new password doesn't meet strength requirements
        """
        wallet = await self._find_wallet_by_id(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Verify current password
        if not verify_password(current_password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect current password")

        # Validate new password strength
        validate_password_strength(new_password)

        # Decrypt with current password
        try:
            mnemonic = decrypt_mnemonic(wallet.mnemonic_encrypted, current_password, wallet.encryption_salt)
        except (ValueError, InvalidToken) as e:
            raise InvalidPasswordError("Failed to decrypt mnemonic") from e

        # Re-encrypt with new password
        encrypted_mnemonic, salt = encrypt_mnemonic(mnemonic, new_password)

        # Hash new password
        password_hash_str = hash_password(new_password)

        # Update wallet
        wallet.mnemonic_encrypted = encrypted_mnemonic
        wallet.encryption_salt = salt
        wallet.password_hash = password_hash_str
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._save_wallet(wallet)

        return wallet

    async def set_default_wallet(self, payment_key_hash: str) -> WalletMongo:
        """
        Set a wallet as the default wallet (unsets previous default).

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
        """
        wallet = await self._find_wallet_by_id(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Unset previous default
        if self.database is not None:
            collection = self._get_wallet_collection()
            previous_default_dict = await collection.find_one({"is_default": True})
            if previous_default_dict:
                previous_default_dict["id"] = previous_default_dict.pop("_id")
                previous_default = WalletMongo.model_validate(previous_default_dict)
                previous_default.is_default = False
                await self._save_wallet(previous_default)
        else:
            previous_default = await WalletMongo.find_one(WalletMongo.is_default == True)
            if previous_default:
                previous_default.is_default = False
                await previous_default.save()

        # Set new default
        wallet.is_default = True
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._save_wallet(wallet)

        return wallet

    async def promote_wallet(self, payment_key_hash: str) -> WalletMongo:
        """
        Promote a user wallet to core wallet.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
        """
        wallet = await self._find_wallet_by_id(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        wallet.wallet_role = WalletRole.CORE.value
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._save_wallet(wallet)

        return wallet

    async def unpromote_wallet(self, payment_key_hash: str) -> WalletMongo:
        """
        Unpromote a CORE wallet to USER wallet.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
            PermissionDeniedError: If this is the last CORE wallet
        """
        wallet = await self._find_wallet_by_id(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Check if this is the last CORE wallet
        if self.database is not None:
            collection = self._get_wallet_collection()
            core_wallets_data = await collection.find({"wallet_role": WalletRole.CORE.value}).to_list(None)
            core_wallets = []
            for w in core_wallets_data:
                w["id"] = w.pop("_id")
                core_wallets.append(WalletMongo.model_validate(w))
        else:
            core_wallets = await WalletMongo.find(WalletMongo.wallet_role == WalletRole.CORE.value).to_list()

        if len(core_wallets) <= 1 and wallet.wallet_role == WalletRole.CORE.value:
            raise PermissionDeniedError(
                "Cannot unpromote the last CORE wallet. At least one CORE wallet must exist."
            )

        wallet.wallet_role = WalletRole.USER.value
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._save_wallet(wallet)

        return wallet

    # ============================================================================
    # Wallet Query Methods (Balance, Addresses, UTXOs, Export)
    # ============================================================================

    async def get_wallet_balance(
        self,
        cardano_wallet: CardanoWallet,
        blockfrost_api: BlockFrostApi,
        limit_addresses: int = 5,
    ) -> dict[str, Any]:
        """
        Get balance for wallet addresses.

        Args:
            cardano_wallet: Unlocked CardanoWallet instance
            blockfrost_api: BlockFrost API instance
            limit_addresses: Number of derived addresses to check

        Returns:
            Balance information dictionary with structure:
            {
                "main_addresses": {"enterprise": {...}, "staking": {...}},
                "derived_addresses": [...],
                "total_balance": int (lovelace)
            }
        """
        return cardano_wallet.check_balances(blockfrost_api, limit_addresses)

    async def get_wallet_addresses(
        self,
        cardano_wallet: CardanoWallet,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Generate wallet addresses (deterministic HD wallet).

        Args:
            cardano_wallet: Unlocked CardanoWallet instance
            count: Number of addresses to generate

        Returns:
            List of address dictionaries with index, derivation_path,
            enterprise_address, staking_address
        """
        return cardano_wallet.generate_addresses(count)

    async def get_wallet_utxos(
        self,
        cardano_wallet: CardanoWallet,
        blockfrost_api: BlockFrostApi,
        address_index: int | None = None,
        min_ada: float | None = None,
    ) -> dict[str, Any]:
        """
        Get unspent transaction outputs for wallet.

        Args:
            cardano_wallet: Unlocked CardanoWallet instance
            blockfrost_api: BlockFrost API instance
            address_index: Specific address index (None = all addresses)
            min_ada: Minimum ADA filter

        Returns:
            UTXO information with structure:
            {
                "utxos": [...],
                "total_lovelace": int,
                "total_ada": float
            }
        """
        utxos_list = []
        total_lovelace = 0

        # Determine which addresses to check
        addresses_to_check = []
        if address_index is not None:
            # Check specific address
            if address_index == 0:
                addresses_to_check = [
                    ("enterprise", str(cardano_wallet.enterprise_address)),
                    ("staking", str(cardano_wallet.staking_address)),
                ]
            else:
                # Generate the specific derived address
                addr_info = cardano_wallet.generate_addresses(address_index)
                if addr_info:
                    addr = addr_info[-1]  # Get the last generated address
                    addresses_to_check = [
                        ("enterprise", str(addr["enterprise_address"])),
                        ("staking", str(addr["staking_address"])),
                    ]
        else:
            # Check all main addresses
            addresses_to_check = [
                ("enterprise", str(cardano_wallet.enterprise_address)),
                ("staking", str(cardano_wallet.staking_address)),
            ]

        # Query UTXOs for each address
        for addr_type, address in addresses_to_check:
            try:
                utxos = blockfrost_api.address_utxos(address)
                for utxo in utxos:
                    # Extract lovelace amount
                    lovelace_amount = 0
                    tokens = []

                    for amount in utxo.amount:
                        if amount.unit == "lovelace":
                            lovelace_amount = int(amount.quantity)
                        else:
                            tokens.append({
                                "unit": amount.unit,
                                "quantity": amount.quantity
                            })

                    ada_amount = lovelace_amount / 1_000_000

                    # Apply min_ada filter
                    if min_ada is not None and ada_amount < min_ada:
                        continue

                    utxos_list.append({
                        "tx_hash": utxo.tx_hash,
                        "output_index": utxo.output_index,
                        "address": address,
                        "amount_lovelace": lovelace_amount,
                        "amount_ada": ada_amount,
                        "tokens": tokens if tokens else None,
                    })

                    total_lovelace += lovelace_amount

            except ApiError:
                # Address might not exist on chain yet or have no UTXOs
                continue

        return {
            "utxos": utxos_list,
            "total_lovelace": total_lovelace,
            "total_ada": total_lovelace / 1_000_000,
        }

