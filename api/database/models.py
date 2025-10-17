"""
Database Models for Terrasacha Contracts

SQLModel models for storing contract information, transaction history,
and wallet management in PostgreSQL.
"""

from datetime import datetime, timezone

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from api.enums import ContractStorageType, ContractType, NetworkType, ProjectState, TransactionStatus


# ============================================================================
# Base Model
# ============================================================================


class TimestampMixin(SQLModel):
    """Mixin for timestamp fields"""

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )


# ============================================================================
# Wallet Models
# ============================================================================


class Wallet(TimestampMixin, table=True):
    """
    Wallet management table

    Stores wallet information with encrypted mnemonics and role-based organization.
    """

    __tablename__ = "wallets"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, nullable=False)
    network: NetworkType = Field(nullable=False)
    mnemonic_encrypted: str = Field(nullable=False)  # Encrypted BIP39 mnemonic
    enterprise_address: str = Field(index=True, nullable=False)
    staking_address: str = Field(index=True, nullable=False)
    payment_key_hash: str = Field(nullable=False)
    is_default: bool = Field(default=False, nullable=False)
    extra_data: dict = Field(default={}, sa_column=Column(JSON))

    # Relationships
    transactions: list["Transaction"] = Relationship(back_populates="wallet")
    protocols: list["Protocol"] = Relationship(back_populates="wallet")


# ============================================================================
# Contract Models
# ============================================================================


class Contract(TimestampMixin, table=True):
    """
    Generic contract registry

    Stores all compiled contracts with metadata about compilation and deployment.
    """

    __tablename__ = "contracts"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    network: NetworkType = Field(nullable=False)
    contract_type: ContractType = Field(nullable=False)
    storage_type: ContractStorageType = Field(default=ContractStorageType.LOCAL, nullable=False)

    # Contract identifiers
    policy_id: str = Field(index=True, unique=True, nullable=False)
    testnet_address: str | None = Field(default=None)
    mainnet_address: str | None = Field(default=None)

    # Script storage
    cbor_hex: str | None = Field(default=None)  # For local contracts

    # Reference script info (if storage_type == REFERENCE_SCRIPT)
    reference_tx_id: str | None = Field(default=None)
    reference_output_index: int | None = Field(default=None)
    reference_address: str | None = Field(default=None)

    # Compilation metadata
    compilation_timestamp: datetime | None = Field(default=None)
    compilation_utxo_tx_id: str | None = Field(default=None)
    compilation_utxo_index: int | None = Field(default=None)

    # Additional metadata
    extra_data: dict = Field(default={}, sa_column=Column(JSON))

    # Relationships
    protocols: list["Protocol"] = Relationship(back_populates="contract")
    projects: list["Project"] = Relationship(back_populates="contract")
    transactions: list["Transaction"] = Relationship(back_populates="contract")


# ============================================================================
# Protocol Models
# ============================================================================


class Protocol(TimestampMixin, table=True):
    """
    Protocol contract instances

    Tracks protocol state and configuration on-chain.
    """

    __tablename__ = "protocols"

    id: int | None = Field(default=None, primary_key=True)
    contract_id: int = Field(foreign_key="contracts.id", nullable=False)
    wallet_id: int = Field(foreign_key="wallets.id", nullable=False)

    # Protocol NFT information
    protocol_nft_policy_id: str = Field(index=True, nullable=False)
    protocol_nft_token_name: str = Field(nullable=False)
    user_nft_token_name: str = Field(nullable=False)

    # Protocol state (from on-chain datum)
    project_admins: list[str] = Field(default=[], sa_column=Column(JSON))  # List of PKH hex strings
    protocol_fee: int = Field(nullable=False)  # Fee in lovelace
    oracle_id: str = Field(nullable=False)  # Oracle policy ID
    projects: list[str] = Field(default=[], sa_column=Column(JSON))  # List of project ID hashes

    # UTXO tracking
    current_utxo_tx_id: str | None = Field(default=None, index=True)
    current_utxo_index: int | None = Field(default=None)
    balance_lovelace: int = Field(default=0)

    # Status
    is_active: bool = Field(default=True, nullable=False)

    # Relationships
    contract: Contract = Relationship(back_populates="protocols")
    wallet: Wallet = Relationship(back_populates="protocols")
    project_instances: list["Project"] = Relationship(back_populates="protocol")


# ============================================================================
# Project Models
# ============================================================================


class Project(TimestampMixin, table=True):
    """
    Project contract instances

    Manages individual carbon credit projects.
    """

    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    contract_id: int = Field(foreign_key="contracts.id", nullable=False)
    protocol_id: int = Field(foreign_key="protocols.id", nullable=False)

    # Project identification
    name: str = Field(index=True, nullable=False)  # Friendly name (e.g., "project_1")
    project_id: str = Field(index=True, nullable=False)  # On-chain project ID hash
    project_metadata: str = Field(nullable=False)  # Metadata URI or hash

    # Project NFT information
    project_nft_policy_id: str = Field(index=True, nullable=False)
    project_nft_token_name: str = Field(nullable=False)

    # Grey token information
    grey_token_policy_id: str | None = Field(default=None, index=True)
    grey_token_name: str | None = Field(default=None)
    total_supply: int = Field(default=0)

    # Project state
    project_state: ProjectState = Field(default=ProjectState.INITIALIZED, nullable=False)

    # UTXO tracking
    current_utxo_tx_id: str | None = Field(default=None, index=True)
    current_utxo_index: int | None = Field(default=None)
    balance_lovelace: int = Field(default=0)

    # Status
    is_active: bool = Field(default=True, nullable=False)

    # Compilation tracking
    compilation_utxo_tx_id: str | None = Field(default=None)
    compilation_utxo_index: int | None = Field(default=None)

    # Relationships
    contract: Contract = Relationship(back_populates="projects")
    protocol: Protocol = Relationship(back_populates="project_instances")
    stakeholders: list["Stakeholder"] = Relationship(back_populates="project")
    certifications: list["Certification"] = Relationship(back_populates="project")
    tokens: list["Token"] = Relationship(back_populates="project")
    sales: list["InvestorSale"] = Relationship(back_populates="project")


# ============================================================================
# Stakeholder Models
# ============================================================================


class Stakeholder(TimestampMixin, table=True):
    """
    Project stakeholders

    Tracks participation in carbon credit projects.
    """

    __tablename__ = "stakeholders"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False)

    # Stakeholder info
    stakeholder_name: str = Field(nullable=False)  # Role name (investor, landowner, etc.)
    pkh: str = Field(index=True, nullable=False)  # Public key hash
    participation: int = Field(nullable=False)  # Amount of grey tokens allocated
    claimed: bool = Field(default=False, nullable=False)

    # Relationships
    project: Project = Relationship(back_populates="stakeholders")


# ============================================================================
# Certification Models
# ============================================================================


class Certification(TimestampMixin, table=True):
    """
    Carbon credit certifications

    Tracks certification events for projects.
    """

    __tablename__ = "certifications"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False)

    # Certification data
    certification_date: int = Field(nullable=False)  # POSIX timestamp
    quantity: int = Field(nullable=False)  # Promised carbon credits
    real_certification_date: int = Field(default=0)  # Actual certification date
    real_quantity: int = Field(default=0)  # Actual verified carbon credits

    # Relationships
    project: Project = Relationship(back_populates="certifications")


# ============================================================================
# Token Models
# ============================================================================


class Token(TimestampMixin, table=True):
    """
    Token tracking

    Manages NFTs, grey tokens, and protocol tokens.
    """

    __tablename__ = "tokens"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id")

    # Token identification
    policy_id: str = Field(index=True, nullable=False)
    token_name: str = Field(index=True, nullable=False)
    token_type: str = Field(nullable=False)  # "protocol_nft", "user_nft", "project_nft", "grey_token"

    # Token details
    quantity: int = Field(default=1)
    owner_address: str | None = Field(default=None, index=True)
    owner_pkh: str | None = Field(default=None)

    # Token metadata
    token_metadata: dict = Field(default={}, sa_column=Column(JSON))

    # Relationships
    project: Project | None = Relationship(back_populates="tokens")


# ============================================================================
# UTXO Models
# ============================================================================


class UTXO(TimestampMixin, table=True):
    """
    UTXO tracking

    Tracks compilation UTXOs and contract state UTXOs.
    """

    __tablename__ = "utxos"

    id: int | None = Field(default=None, primary_key=True)

    # UTXO identification
    tx_id: str = Field(index=True, nullable=False)
    output_index: int = Field(nullable=False)

    # UTXO details
    address: str = Field(index=True, nullable=False)
    amount_lovelace: int = Field(nullable=False)

    # Purpose tracking
    purpose: str = Field(nullable=False)  # "compilation", "protocol_state", "project_state", "investor_contract"
    is_spent: bool = Field(default=False, nullable=False, index=True)
    spent_at: datetime | None = Field(default=None)

    # References
    contract_id: int | None = Field(default=None, foreign_key="contracts.id")
    project_id: int | None = Field(default=None, foreign_key="projects.id")

    # UTXO metadata
    extra_data: dict = Field(default={}, sa_column=Column(JSON))


# ============================================================================
# Transaction Models
# ============================================================================


class Transaction(TimestampMixin, table=True):
    """
    Transaction history

    Comprehensive tracking of all blockchain transactions.
    """

    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int | None = Field(default=None, foreign_key="wallets.id")
    contract_id: int | None = Field(default=None, foreign_key="contracts.id")

    # Transaction identification
    tx_hash: str = Field(index=True, unique=True, nullable=False)

    # Transaction details
    status: TransactionStatus = Field(default=TransactionStatus.PENDING, nullable=False, index=True)
    operation: str = Field(nullable=False)  # "mint_protocol", "create_project", "buy_grey", etc.
    description: str | None = Field(default=None)

    # Amounts
    fee_lovelace: int | None = Field(default=None)
    total_output_lovelace: int | None = Field(default=None)

    # Inputs/Outputs
    inputs: list[dict] = Field(default=[], sa_column=Column(JSON))
    outputs: list[dict] = Field(default=[], sa_column=Column(JSON))

    # Transaction metadata
    tx_metadata: dict = Field(default={}, sa_column=Column(JSON))

    # Confirmation tracking
    submitted_at: datetime | None = Field(default=None)
    confirmed_at: datetime | None = Field(default=None)
    block_height: int | None = Field(default=None)

    # Error tracking
    error_message: str | None = Field(default=None)

    # Relationships
    wallet: Wallet | None = Relationship(back_populates="transactions")
    contract: Contract | None = Relationship(back_populates="transactions")


# ============================================================================
# Investor Sale Models
# ============================================================================


class InvestorSale(TimestampMixin, table=True):
    """
    Investor contract sales tracking

    Manages grey token sales through investor contracts.
    """

    __tablename__ = "investor_sales"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False)

    # Investor contract identification
    contract_name: str = Field(index=True, nullable=False)  # e.g., "project_1_investor"
    contract_address: str = Field(index=True, nullable=False)

    # Seller information
    seller_pkh: str = Field(index=True, nullable=False)

    # Sale details
    grey_token_amount: int = Field(nullable=False)
    price_per_token: int = Field(nullable=False)  # With precision
    price_precision: int = Field(default=6, nullable=False)
    min_purchase_amount: int = Field(nullable=False)

    # UTXO tracking
    current_utxo_tx_id: str | None = Field(default=None, index=True)
    current_utxo_index: int | None = Field(default=None)

    # Status
    is_active: bool = Field(default=True, nullable=False)
    remaining_tokens: int = Field(nullable=False)

    # Sales history
    total_sales: int = Field(default=0)
    total_revenue: int = Field(default=0)  # In USDA with precision

    # Relationships
    project: Project = Relationship(back_populates="sales")
