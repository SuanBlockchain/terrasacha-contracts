"""
Token Service

JWT token generation and validation for wallet session management.
Provides access tokens (short-lived) and refresh tokens (long-lived).
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from api.enums import WalletRole


# Token configuration from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "default_secret_key_change_in_production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
WALLET_SESSION_TIMEOUT_MINUTES = int(os.getenv("WALLET_SESSION_TIMEOUT_MINUTES", "30"))
WALLET_REFRESH_TOKEN_DAYS = int(os.getenv("WALLET_REFRESH_TOKEN_DAYS", "7"))


class TokenServiceError(Exception):
    """Base exception for token service errors"""

    pass


class InvalidTokenError(TokenServiceError):
    """Invalid or expired token"""

    pass


class TokenService:
    """
    Service for JWT token management

    Handles creation and validation of access and refresh tokens for wallet sessions.
    """

    @staticmethod
    def create_wallet_token(
        payment_key_hash: str,
        wallet_name: str,
        wallet_role: WalletRole,
        expires_minutes: int | None = None
    ) -> tuple[str, str, datetime]:
        """
        Create a wallet access token (JWT).

        Args:
            payment_key_hash: Payment key hash (wallet ID)
            wallet_name: Wallet name
            wallet_role: Wallet role (USER or CORE)
            expires_minutes: Token expiration in minutes (default: from env)

        Returns:
            Tuple of (token, jti, expires_at)
            - token: JWT token string
            - jti: JWT ID (for revocation tracking)
            - expires_at: Token expiration datetime

        Example:
            >>> token, jti, expires_at = TokenService.create_wallet_token("abc123...", "my_wallet", WalletRole.USER)
            >>> # Use token in Authorization header
        """
        if expires_minutes is None:
            expires_minutes = WALLET_SESSION_TIMEOUT_MINUTES

        # Generate unique JWT ID for revocation tracking
        jti = secrets.token_urlsafe(32)

        # Calculate expiration
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_minutes)

        # Create JWT payload
        payload = {
            "sub": payment_key_hash,  # Subject: wallet payment key hash
            "wallet_id": payment_key_hash,  # For backward compatibility, renamed from int to PKH
            "wallet_name": wallet_name,
            "wallet_role": wallet_role.value,
            "jti": jti,  # JWT ID
            "iat": now,  # Issued at
            "exp": expires_at,  # Expiration
            "type": "access"  # Token type
        }

        # Generate JWT
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        return token, jti, expires_at

    @staticmethod
    def create_refresh_token(
        payment_key_hash: str,
        wallet_name: str,
        expires_days: int | None = None
    ) -> tuple[str, str, datetime]:
        """
        Create a refresh token for extending wallet sessions.

        Args:
            payment_key_hash: Payment key hash (wallet ID)
            wallet_name: Wallet name
            expires_days: Token expiration in days (default: from env)

        Returns:
            Tuple of (refresh_token, jti, expires_at)

        Example:
            >>> refresh_token, jti, expires_at = TokenService.create_refresh_token("abc123...", "my_wallet")
            >>> # Store jti and use refresh_token to get new access tokens
        """
        if expires_days is None:
            expires_days = WALLET_REFRESH_TOKEN_DAYS

        # Generate unique JWT ID
        jti = secrets.token_urlsafe(32)

        # Calculate expiration
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_days)

        # Create JWT payload
        payload = {
            "sub": payment_key_hash,
            "wallet_id": payment_key_hash,  # For backward compatibility, renamed from int to PKH
            "wallet_name": wallet_name,
            "jti": jti,
            "iat": now,
            "exp": expires_at,
            "type": "refresh"  # Token type
        }

        # Generate JWT
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        return token, jti, expires_at

    @staticmethod
    def verify_token(token: str, expected_type: str = "access") -> dict:
        """
        Verify and decode a JWT token.

        Args:
            token: JWT token string
            expected_type: Expected token type ("access" or "refresh")

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is invalid, expired, or wrong type

        Example:
            >>> payload = TokenService.verify_token(token)
            >>> wallet_id = payload["wallet_id"]
            >>> jti = payload["jti"]
        """
        try:
            # Decode and verify JWT
            payload = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM]
            )

            # Verify token type
            if payload.get("type") != expected_type:
                raise InvalidTokenError(
                    f"Invalid token type. Expected '{expected_type}', got '{payload.get('type')}'"
                )

            return payload

        except ExpiredSignatureError:
            raise InvalidTokenError("Token has expired")
        except DecodeError:
            raise InvalidTokenError("Invalid token format")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Token validation failed: {str(e)}")

    @staticmethod
    def decode_token_without_verification(token: str) -> dict | None:
        """
        Decode a token without verifying signature (for inspection only).

        Useful for extracting JTI from expired tokens for cleanup.

        Args:
            token: JWT token string

        Returns:
            Decoded payload or None if invalid

        Example:
            >>> payload = TokenService.decode_token_without_verification(token)
            >>> if payload:
            ...     jti = payload.get("jti")
        """
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False}
            )
            return payload
        except Exception:
            return None

    @staticmethod
    def get_token_expiration(token: str) -> datetime | None:
        """
        Get token expiration time without full validation.

        Args:
            token: JWT token string

        Returns:
            Expiration datetime or None if invalid

        Example:
            >>> expires_at = TokenService.get_token_expiration(token)
            >>> if expires_at and expires_at < datetime.now(timezone.utc):
            ...     print("Token has expired")
        """
        payload = TokenService.decode_token_without_verification(token)
        if payload and "exp" in payload:
            return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        return None

    @staticmethod
    def extract_jti(token: str) -> str | None:
        """
        Extract JWT ID (jti) from token without verification.

        Args:
            token: JWT token string

        Returns:
            JTI string or None if invalid

        Example:
            >>> jti = TokenService.extract_jti(token)
            >>> # Use jti for session lookup or revocation
        """
        payload = TokenService.decode_token_without_verification(token)
        if payload:
            return payload.get("jti")
        return None
