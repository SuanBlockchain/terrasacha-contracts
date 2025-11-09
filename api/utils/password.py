"""
Password Utilities

Provides secure password hashing and verification using Argon2id.
Argon2id is the recommended password hashing algorithm (winner of the Password Hashing Competition).
"""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


# Initialize Argon2 password hasher with secure defaults
# Using Argon2id variant (hybrid of Argon2i and Argon2d)
_password_hasher = PasswordHasher(
    time_cost=3,  # Number of iterations (OWASP minimum: 2)
    memory_cost=65536,  # Memory usage in KiB (64 MB, OWASP minimum: 47104)
    parallelism=4,  # Number of parallel threads
    hash_len=32,  # Length of the hash in bytes
    salt_len=16,  # Length of the salt in bytes
)


# Password requirements
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.

    Args:
        password: Plain text password to hash

    Returns:
        Argon2 hash string (includes algorithm, parameters, salt, and hash)

    Raises:
        ValueError: If password doesn't meet requirements

    Example:
        >>> password_hash = hash_password("my_secure_password")
        >>> # password_hash = "$argon2id$v=19$m=65536,t=3,p=4$..."
    """
    # Validate password
    validate_password_strength(password)

    # Hash the password
    password_hash = _password_hasher.hash(password)

    return password_hash


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        password: Plain text password to verify
        password_hash: Argon2 hash string to verify against

    Returns:
        True if password matches, False otherwise

    Example:
        >>> is_valid = verify_password("my_secure_password", stored_hash)
        >>> if is_valid:
        ...     # Password is correct
    """
    if not password or not password_hash:
        return False

    try:
        # Verify the password
        _password_hasher.verify(password_hash, password)

        # Check if hash needs rehashing (e.g., parameters changed)
        if _password_hasher.check_needs_rehash(password_hash):
            # Note: Caller should rehash the password with new parameters
            # This is not done automatically to avoid database updates during verification
            pass

        return True

    except (VerifyMismatchError, VerificationError, InvalidHashError):
        # Password doesn't match or hash is invalid
        return False
    except Exception:
        # Any other error (shouldn't happen, but be safe)
        return False


def validate_password_strength(password: str) -> None:
    """
    Validate password meets minimum strength requirements.

    Requirements:
    - Minimum 8 characters
    - Maximum 128 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Raises:
        ValueError: If password doesn't meet requirements

    Example:
        >>> validate_password_strength("MyP@ssw0rd")  # Valid
        >>> validate_password_strength("weak")  # Raises ValueError
    """
    if not password:
        raise ValueError("Password cannot be empty")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")

    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_LENGTH} characters")

    # Check for at least one uppercase letter
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")

    # Check for at least one lowercase letter
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")

    # Check for at least one digit
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")

    # Check for at least one special character
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", password):
        raise ValueError("Password must contain at least one special character (!@#$%^&*...)")


def needs_rehash(password_hash: str) -> bool:
    """
    Check if a password hash needs to be rehashed with updated parameters.

    This should be called after successful password verification.
    If True, the password should be rehashed and updated in the database.

    Args:
        password_hash: Argon2 hash string to check

    Returns:
        True if hash should be updated, False otherwise

    Example:
        >>> if verify_password(password, stored_hash) and needs_rehash(stored_hash):
        ...     new_hash = hash_password(password)
        ...     # Update database with new_hash
    """
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except Exception:
        # If we can't check, assume it needs rehashing
        return True
