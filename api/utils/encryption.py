"""
Encryption Utilities

Provides secure encryption/decryption for sensitive wallet data (mnemonics).
Uses AES-256 encryption via Fernet with password-derived keys.
"""

import base64
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# Constants
KEY_DERIVATION_ITERATIONS = 480_000  # OWASP recommended minimum for PBKDF2-HMAC-SHA256
SALT_BYTES = 32  # 256 bits


def generate_salt() -> str:
    """
    Generate a cryptographically secure random salt.

    Returns:
        Base64-encoded salt string
    """
    salt_bytes = secrets.token_bytes(SALT_BYTES)
    return base64.urlsafe_b64encode(salt_bytes).decode("utf-8")


def _derive_key_from_password(password: str, salt: str) -> bytes:
    """
    Derive an encryption key from a password using PBKDF2-HMAC-SHA256.

    Args:
        password: User's password
        salt: Base64-encoded salt

    Returns:
        32-byte encryption key suitable for Fernet
    """
    salt_bytes = base64.urlsafe_b64decode(salt.encode("utf-8"))

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits
        salt=salt_bytes,
        iterations=KEY_DERIVATION_ITERATIONS,
    )

    password_bytes = password.encode("utf-8")
    key = kdf.derive(password_bytes)

    # Fernet requires a base64-encoded 32-byte key
    return base64.urlsafe_b64encode(key)


def encrypt_mnemonic(mnemonic: str, password: str) -> tuple[str, str]:
    """
    Encrypt a mnemonic phrase using password-based encryption.

    Uses AES-256 encryption via Fernet with a password-derived key (PBKDF2-HMAC-SHA256).

    Args:
        mnemonic: BIP39 mnemonic phrase (space-separated words)
        password: User's password for encryption

    Returns:
        Tuple of (encrypted_mnemonic, salt) both as base64-encoded strings

    Raises:
        ValueError: If mnemonic or password is empty

    Example:
        >>> encrypted, salt = encrypt_mnemonic("word1 word2 ... word24", "my_secure_password")
        >>> # Store encrypted and salt in database
    """
    if not mnemonic or not mnemonic.strip():
        raise ValueError("Mnemonic cannot be empty")

    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    # Generate a new salt for this encryption
    salt = generate_salt()

    # Derive encryption key from password and salt
    encryption_key = _derive_key_from_password(password, salt)

    # Create Fernet cipher
    cipher = Fernet(encryption_key)

    # Encrypt the mnemonic
    mnemonic_bytes = mnemonic.encode("utf-8")
    encrypted_bytes = cipher.encrypt(mnemonic_bytes)

    # Return as base64-encoded string
    encrypted_mnemonic = encrypted_bytes.decode("utf-8")

    return encrypted_mnemonic, salt


def decrypt_mnemonic(encrypted_mnemonic: str, password: str, salt: str) -> str:
    """
    Decrypt an encrypted mnemonic phrase using the password and salt.

    Args:
        encrypted_mnemonic: Base64-encoded encrypted mnemonic
        password: User's password (must match the one used for encryption)
        salt: Base64-encoded salt (stored with encrypted mnemonic)

    Returns:
        Decrypted mnemonic phrase (space-separated words)

    Raises:
        ValueError: If any parameter is empty
        cryptography.fernet.InvalidToken: If password is wrong or data is corrupted

    Example:
        >>> mnemonic = decrypt_mnemonic(encrypted, password, salt)
        >>> # mnemonic = "word1 word2 ... word24"
    """
    if not encrypted_mnemonic or not encrypted_mnemonic.strip():
        raise ValueError("Encrypted mnemonic cannot be empty")

    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    if not salt or not salt.strip():
        raise ValueError("Salt cannot be empty")

    try:
        # Derive the same encryption key from password and salt
        encryption_key = _derive_key_from_password(password, salt)

        # Create Fernet cipher
        cipher = Fernet(encryption_key)

        # Decrypt the mnemonic
        encrypted_bytes = encrypted_mnemonic.encode("utf-8")
        decrypted_bytes = cipher.decrypt(encrypted_bytes)

        # Return as string
        return decrypted_bytes.decode("utf-8")

    except Exception as e:
        # Re-raise with more helpful message for wrong password
        if "Invalid" in str(e) or "token" in str(e).lower():
            raise ValueError("Invalid password or corrupted data") from e
        raise
