"""
Contract Definitions

Structured contract definitions with enums and dataclasses.
Provides type-safe contract names, categories, and parameter specifications.
"""

from dataclasses import dataclass, field
from enum import Enum


class ContractName(str, Enum):
    """Type-safe contract names"""

    # Minting Policies
    MY_USD_FREE = "myUSDFree"
    PROJECT_NFTS = "project_nfts"
    PROTOCOL_NFTS = "protocol_nfts"
    GREY = "grey"

    # Spending Validators
    INVESTOR = "investor"
    PROJECT = "project"
    PROTOCOL = "protocol"


class ContractCategory(str, Enum):
    """Contract categories for grouping and filtering"""

    CORE_PROTOCOL = "core_protocol"
    PROJECT_MANAGEMENT = "project_management"
    TOKEN_MANAGEMENT = "token_management"
    TESTING = "testing"


@dataclass(frozen=True)
class ParameterSpec:
    """Compilation parameter specification"""

    name: str
    type: str  # "bytes", "policy_id", "TxOutRef", etc.
    description: str
    example: str | None = None


@dataclass(frozen=True)
class ContractDefinition:
    """
    Immutable contract definition.

    Defines all metadata for a contract including file path,
    compilation parameters, category, and tags.
    """

    name: ContractName
    contract_type: str  # "minting" or "spending"
    file_path: str  # Relative to src/terrasacha_contracts/
    description: str
    category: ContractCategory
    requires_params: bool
    parameters: list[ParameterSpec] | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate that parameters are defined if required"""
        if self.requires_params and not self.parameters:
            raise ValueError(
                f"Contract {self.name.value} requires parameters but none are defined"
            )


# ============================================================================
# Contract Definitions
# ============================================================================

CONTRACTS: list[ContractDefinition] = [
    # Minting Policies
    ContractDefinition(
        name=ContractName.MY_USD_FREE,
        contract_type="minting",
        file_path="minting_policies/myUSDFree.py",
        description="USDA faucet minting policy - free minting for testing",
        category=ContractCategory.TESTING,
        requires_params=False,
        parameters=None,
        tags=["testing", "faucet", "simple"]
    ),

    ContractDefinition(
        name=ContractName.PROJECT_NFTS,
        contract_type="minting",
        file_path="minting_policies/project_nfts.py",
        description="Project NFTs minting policy - requires UTXO reference and protocol policy ID",
        category=ContractCategory.PROJECT_MANAGEMENT,
        requires_params=True,
        parameters=[
            ParameterSpec(
                name="utxo_ref",
                type="TxOutRef",
                description="UTXO reference for one-time minting",
                example="a1b2c3d4e5f6...#0"
            ),
            ParameterSpec(
                name="protocol_policy_id_bytes",
                type="bytes",
                description="Protocol NFT policy ID as bytes",
                example="0x1234abcd..."
            )
        ],
        tags=["nft", "project", "parameterized"]
    ),

    ContractDefinition(
        name=ContractName.PROTOCOL_NFTS,
        contract_type="minting",
        file_path="minting_policies/protocol_nfts.py",
        description="Protocol NFTs minting policy - requires UTXO reference",
        category=ContractCategory.CORE_PROTOCOL,
        requires_params=True,
        parameters=[
            ParameterSpec(
                name="utxo_ref",
                type="TxOutRef",
                description="UTXO reference for one-time minting",
                example="a1b2c3d4e5f6...#0"
            )
        ],
        tags=["nft", "core", "protocol", "parameterized"]
    ),

    ContractDefinition(
        name=ContractName.GREY,
        contract_type="minting",
        file_path="minting_policies/grey.py",
        description="Grey token minting policy - requires project NFTs policy ID",
        category=ContractCategory.TOKEN_MANAGEMENT,
        requires_params=True,
        parameters=[
            ParameterSpec(
                name="project_nfts_policy_id_bytes",
                type="bytes",
                description="Project NFTs policy ID as bytes",
                example="0x1234abcd..."
            )
        ],
        tags=["token", "grey", "carbon-credits", "parameterized"]
    ),

    # Spending Validators
    ContractDefinition(
        name=ContractName.INVESTOR,
        contract_type="spending",
        file_path="validators/investor.py",
        description="Investor contract - manages grey token sales",
        category=ContractCategory.TOKEN_MANAGEMENT,
        requires_params=True,
        parameters=[
            ParameterSpec(
                name="protocol_policy_id_bytes",
                type="bytes",
                description="Protocol NFT policy ID as bytes",
                example="0x1234abcd..."
            ),
            ParameterSpec(
                name="grey_policy_id_bytes",
                type="bytes",
                description="Grey token policy ID as bytes",
                example="0x5678ef90..."
            ),
            ParameterSpec(
                name="grey_token_name_bytes",
                type="bytes",
                description="Grey token name as bytes",
                example="0x67726579"
            )
        ],
        tags=["investor", "grey", "sales", "parameterized"]
    ),

    ContractDefinition(
        name=ContractName.PROJECT,
        contract_type="spending",
        file_path="validators/project.py",
        description="Project contract - manages project state and carbon credits",
        category=ContractCategory.PROJECT_MANAGEMENT,
        requires_params=True,
        parameters=[
            ParameterSpec(
                name="project_nfts_policy_id_bytes",
                type="bytes",
                description="Project NFTs policy ID as bytes",
                example="0x1234abcd..."
            )
        ],
        tags=["project", "carbon-credits", "state-management", "parameterized"]
    ),

    ContractDefinition(
        name=ContractName.PROTOCOL,
        contract_type="spending",
        file_path="validators/protocol.py",
        description="Protocol contract - manages global protocol state",
        category=ContractCategory.CORE_PROTOCOL,
        requires_params=True,
        parameters=[
            ParameterSpec(
                name="protocol_nfts_policy_id_bytes",
                type="bytes",
                description="Protocol NFTs policy ID as bytes",
                example="0x1234abcd..."
            )
        ],
        tags=["protocol", "core", "state-management", "parameterized"]
    ),
]


# ============================================================================
# Utility Functions
# ============================================================================

def get_contracts_by_category() -> dict[ContractCategory, list[ContractDefinition]]:
    """Group contracts by category"""
    from collections import defaultdict
    grouped = defaultdict(list)
    for contract in CONTRACTS:
        grouped[contract.category].append(contract)
    return dict(grouped)


def get_contracts_by_tag(tag: str) -> list[ContractDefinition]:
    """Get all contracts with a specific tag"""
    return [c for c in CONTRACTS if tag in c.tags]
