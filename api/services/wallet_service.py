"""
Wallet Service

Business logic layer for wallet operations.
Handles wallet creation, encryption, unlocking, and management.
"""

from datetime import datetime, timezone

import pycardano as pc
from cryptography.fernet import InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.models import Wallet, WalletSession
from api.database.repositories.wallet import WalletRepository
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


class WalletService:
    """
    Service for wallet management operations

    Handles wallet lifecycle including creation, import, unlock, lock, and deletion.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize wallet service

        Args:
            session: Async database session
        """
        self.session = session
        self.wallet_repo = WalletRepository(session)

    async def create_wallet(
        self, name: str, password: str, network: NetworkType = NetworkType.TESTNET, role: WalletRole = WalletRole.USER
    ) -> tuple[Wallet, str]:
        """
        Create a new wallet with generated mnemonic.

        Generates a 24-word BIP39 mnemonic, encrypts it with the password,
        and stores it in the database.

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
        existing_wallet = await self.wallet_repo.get_by_name(name)
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
        wallet = Wallet(
            name=name,
            network=network,
            mnemonic_encrypted=encrypted_mnemonic,
            encryption_salt=salt,
            password_hash=password_hash_str,
            enterprise_address=str(cardano_wallet.enterprise_address),
            staking_address=str(cardano_wallet.staking_address),
            payment_key_hash=payment_key_hash,
            wallet_role=role,
            is_locked=True,  # Locked by default
            is_default=False,
        )

        # Save to database
        wallet = await self.wallet_repo.create(wallet)

        # Return wallet and mnemonic (user must save mnemonic!)
        return wallet, mnemonic

    async def import_wallet(
        self,
        name: str,
        mnemonic: str,
        password: str,
        network: NetworkType = NetworkType.TESTNET,
        wallet_role: WalletRole = WalletRole.USER
    ) -> Wallet:
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
        existing_wallet = await self.wallet_repo.get_by_name(name)
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
        wallet = Wallet(
            name=name,
            network=network,
            mnemonic_encrypted=encrypted_mnemonic,
            encryption_salt=salt,
            password_hash=password_hash_str,
            enterprise_address=str(cardano_wallet.enterprise_address),
            staking_address=str(cardano_wallet.staking_address),
            payment_key_hash=payment_key_hash,
            wallet_role=wallet_role,  # Use provided role (defaults to USER)
            is_locked=True,
            is_default=False,
        )

        # Save to database
        wallet = await self.wallet_repo.create(wallet)

        return wallet

    async def unlock_wallet(self, payment_key_hash: str, password: str) -> tuple[Wallet, CardanoWallet]:
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
        # Get wallet from database
        wallet = await self.wallet_repo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect password")

        # Check if password hash needs rehashing (security upgrade)
        if needs_rehash(wallet.password_hash):
            # Rehash password with updated parameters
            new_hash = hash_password(password)
            await self.wallet_repo.update(payment_key_hash, password_hash=new_hash)

        # Decrypt mnemonic
        try:
            mnemonic = decrypt_mnemonic(wallet.mnemonic_encrypted, password, wallet.encryption_salt)
        except (ValueError, InvalidToken) as e:
            raise InvalidPasswordError("Failed to decrypt mnemonic") from e

        # Create CardanoWallet instance
        try:
            cardano_wallet = CardanoWallet(mnemonic, wallet.network.value)
        except Exception as e:
            raise InvalidMnemonicError(f"Failed to create wallet from mnemonic: {e}") from e

        # Update unlock timestamp
        await self.wallet_repo.update(
            payment_key_hash, is_locked=False, last_unlocked_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )

        return wallet, cardano_wallet

    async def lock_wallet(self, payment_key_hash: str) -> Wallet:
        """
        Lock a wallet.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
        """
        wallet = await self.wallet_repo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Update lock status
        updated_wallet = await self.wallet_repo.update(payment_key_hash, is_locked=True)

        return updated_wallet  # type: ignore

    async def change_password(self, payment_key_hash: str, old_password: str, new_password: str) -> Wallet:
        """
        Change wallet password and re-encrypt mnemonic.

        Args:
            payment_key_hash: Payment key hash (wallet ID)
            old_password: Current password
            new_password: New password

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
            InvalidPasswordError: If old password is incorrect
            ValueError: If new password doesn't meet strength requirements
        """
        # Get wallet
        wallet = await self.wallet_repo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Verify old password
        if not verify_password(old_password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect current password")

        # Validate new password strength
        validate_password_strength(new_password)

        # Decrypt mnemonic with old password
        try:
            mnemonic = decrypt_mnemonic(wallet.mnemonic_encrypted, old_password, wallet.encryption_salt)
        except (ValueError, InvalidToken) as e:
            raise InvalidPasswordError("Failed to decrypt mnemonic with current password") from e

        # Re-encrypt mnemonic with new password
        new_encrypted_mnemonic, new_salt = encrypt_mnemonic(mnemonic, new_password)

        # Hash new password
        new_password_hash = hash_password(new_password)

        # Update wallet
        updated_wallet = await self.wallet_repo.update(
            payment_key_hash,
            mnemonic_encrypted=new_encrypted_mnemonic,
            encryption_salt=new_salt,
            password_hash=new_password_hash,
            is_locked=True,  # Lock after password change for security
        )

        return updated_wallet  # type: ignore

    async def promote_to_core(self, payment_key_hash: str, promoted_by_pkh: str) -> Wallet:
        """
        Promote a wallet to CORE role.

        Only existing CORE wallets can promote other wallets.

        Args:
            payment_key_hash: PKH of wallet to promote
            promoted_by_pkh: PKH of core wallet performing the promotion

        Returns:
            Updated wallet

        Raises:
            WalletNotFoundError: If either wallet doesn't exist
            PermissionDeniedError: If promoting wallet is not CORE
        """
        # Get both wallets
        wallet = await self.wallet_repo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        promoting_wallet = await self.wallet_repo.get(promoted_by_pkh)
        if not promoting_wallet:
            raise WalletNotFoundError(f"Promoting wallet with PKH {promoted_by_pkh} not found")

        # Check if promoting wallet has CORE role
        if promoting_wallet.wallet_role != WalletRole.CORE:
            raise PermissionDeniedError("Only CORE wallets can promote other wallets")

        # Promote wallet
        updated_wallet = await self.wallet_repo.update(payment_key_hash, wallet_role=WalletRole.CORE)

        return updated_wallet  # type: ignore

    async def delete_wallet(self, payment_key_hash: str, password: str) -> bool:
        """
        Delete a wallet (with password confirmation).

        Args:
            payment_key_hash: Payment key hash (wallet ID)
            password: Password for confirmation

        Returns:
            True if deleted successfully

        Raises:
            WalletNotFoundError: If wallet doesn't exist
            InvalidPasswordError: If password is incorrect
            PermissionDeniedError: If attempting to delete the last CORE wallet
        """
        # Get wallet
        wallet = await self.wallet_repo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        # Verify password
        if not verify_password(password, wallet.password_hash):
            raise InvalidPasswordError("Incorrect password")

        # Check if this is the last CORE wallet
        if wallet.wallet_role == WalletRole.CORE:
            # Count other CORE wallets
            # Note: This is a simplified check, you might want to use a repository method
            all_wallets = await self.wallet_repo.get_all()
            core_count = sum(1 for w in all_wallets if w.wallet_role == WalletRole.CORE)

            if core_count <= 1:
                raise PermissionDeniedError("Cannot delete the last CORE wallet")

        # Delete wallet (cascades to sessions)
        success = await self.wallet_repo.delete(payment_key_hash)

        return success

    async def get_wallet(self, payment_key_hash: str) -> Wallet:
        """
        Get wallet by payment key hash.

        Args:
            payment_key_hash: Payment key hash (wallet ID)

        Returns:
            Wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
        """
        wallet = await self.wallet_repo.get(payment_key_hash)
        if not wallet:
            raise WalletNotFoundError(f"Wallet with PKH {payment_key_hash} not found")

        return wallet

    async def get_wallet_by_name(self, name: str) -> Wallet:
        """
        Get wallet by name.

        Args:
            name: Wallet name

        Returns:
            Wallet

        Raises:
            WalletNotFoundError: If wallet doesn't exist
        """
        wallet = await self.wallet_repo.get_by_name(name)
        if not wallet:
            raise WalletNotFoundError(f"Wallet '{name}' not found")

        return wallet

    async def list_wallets(self, skip: int = 0, limit: int = 100) -> list[Wallet]:
        """
        List all wallets.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of wallets
        """
        return await self.wallet_repo.get_all(skip=skip, limit=limit)
