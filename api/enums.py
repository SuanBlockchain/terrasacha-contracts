"""
Shared Enums

Single source of truth for enums used across database models, API schemas,
and business logic. This eliminates duplication and ensures consistency.
"""

from enum import Enum


# ============================================================================
# Blockchain Enums
# ============================================================================


class NetworkType(str, Enum):
    """Blockchain network types"""

    TESTNET = "testnet"
    MAINNET = "mainnet"


class WalletRole(str, Enum):
    """
    Wallet roles for access control

    - USER: Regular user wallet, can perform standard operations
    - CORE: Core/admin wallet, can compile smart contracts and promote other wallets
    """

    USER = "user"
    CORE = "core"


class TransactionStatus(str, Enum):
    """
    Transaction processing status

    Lifecycle:
    - BUILT: Transaction built (unsigned), ready for signing
    - SIGNED: Transaction signed, ready for submission
    - PENDING: Created but not yet submitted to blockchain (legacy)
    - SUBMITTED: Submitted to blockchain mempool
    - CONFIRMED: Included in a block on-chain
    - FAILED: Transaction rejected or failed
    """

    BUILT = "BUILT"
    SIGNED = "SIGNED"
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


# ============================================================================
# Contract Enums
# ============================================================================


class ContractType(str, Enum):
    """Smart contract types"""

    MINTING_POLICY = "minting_policy"
    SPENDING_VALIDATOR = "spending_validator"


class ContractStorageType(str, Enum):
    """How contract scripts are stored"""

    LOCAL = "local"
    REFERENCE_SCRIPT = "reference_script"


# ============================================================================
# Project Enums
# ============================================================================


class ProjectState(int, Enum):
    """
    Project contract states

    - INITIALIZED: Project created, tokens not yet distributed
    - DISTRIBUTED: Tokens distributed to stakeholders
    - CERTIFIED: Carbon credits certified
    - CLOSED: Project completed
    """

    INITIALIZED = 0
    DISTRIBUTED = 1
    CERTIFIED = 2
    CLOSED = 3
