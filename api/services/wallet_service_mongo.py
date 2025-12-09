"""
Wallet Service - MongoDB/Beanie Version

Business logic layer for wallet operations using MongoDB.
Handles wallet creation, encryption, unlocking, and management.
"""

from datetime import datetime, timezone

import pycardano as pc
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
        existing_wallet = await WalletMongo.find_one(WalletMongo.name == name)
        if existing_wallet:
            raise WalletAlreadyExistsError(f"Wallet '{name}' already exists")

        # Validate password strength
        validate_password_strength(password)

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

        # Save to MongoDB
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
        existing_wallet = await WalletMongo.find_one(WalletMongo.name == name)
        if existing_wallet:
            raise WalletAlreadyExistsError(f"Wallet '{name}' already exists")

        # Validate password strength
        validate_password_strength(password)

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

        # Save to MongoDB
        await wallet.insert()

        return wallet

    async def unlock_wallet(self, payment_key_hash: str, password: str) -> tuple[WalletMongo, CardanoWallet]:
        """
        Unlock a wallet by decrypting its mnemonic.

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
        wallet = await WalletMongo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect password")

        # Check if password hash needs rehashing (security upgrade)
        if needs_rehash(wallet.password_hash):
            # Rehash password with updated parameters
            wallet.password_hash = hash_password(password)
            await wallet.save()

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

        # Update wallet state
        wallet.is_locked = False
        wallet.last_unlocked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await wallet.save()

        return wallet, cardano_wallet

    async def lock_wallet(self, payment_key_hash: str) -> WalletMongo:
        """
        Lock a wallet (marks as locked, doesn't affect stored data).

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
        """
        wallet = await WalletMongo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        wallet.is_locked = True
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await wallet.save()

        return wallet

    async def get_wallet(self, payment_key_hash: str) -> WalletMongo | None:
        """
        Get wallet by payment key hash.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Wallet or None if not found
        """
        return await WalletMongo.get(payment_key_hash)

    async def get_wallet_by_name(self, name: str) -> WalletMongo | None:
        """
        Get wallet by name.

        Args:
            name: Wallet name

        Returns:
            Wallet or None if not found
        """
        return await WalletMongo.find_one(WalletMongo.name == name)

    async def list_wallets(self, skip: int = 0, limit: int = 100) -> list[WalletMongo]:
        """
        Get all wallets for current tenant.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of wallets
        """
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
        wallet = await WalletMongo.get(payment_key_hash)
        if not wallet:
            return False

        # Permission check: USER role cannot delete CORE wallets
        if requesting_wallet_role == WalletRole.USER and wallet.wallet_role == WalletRole.CORE.value:
            raise PermissionDeniedError("User wallets cannot delete core wallets")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect password")

        # Delete wallet
        await wallet.delete()

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
        wallet = await WalletMongo.get(payment_key_hash)
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
        await wallet.save()

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
        wallet = await WalletMongo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Unset previous default
        previous_default = await WalletMongo.find_one(WalletMongo.is_default == True)
        if previous_default:
            previous_default.is_default = False
            await previous_default.save()

        # Set new default
        wallet.is_default = True
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await wallet.save()

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
        wallet = await WalletMongo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        wallet.wallet_role = WalletRole.CORE.value
        wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await wallet.save()

        return wallet
