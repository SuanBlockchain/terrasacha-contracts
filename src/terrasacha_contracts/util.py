from opshin.prelude import *
from opshin.std.builtins import *

################################################
# Constants
################################################
PREFIX_REFERENCE_NFT = b"REF_"
PREFIX_USER_NFT = b"USER_"

################################################
# Protocol Data Types
################################################
@dataclass()
class DatumProtocol(PlutusData):
    CONSTR_ID = 0
    project_admins: List[bytes]  # List of admin public key hashes to allow project auth minting nfts
    protocol_fee: int  # Protocol fee in lovelace
    oracle_id: PolicyId  # Oracle identifier

@dataclass()
class UpdateProtocol(PlutusData):
    CONSTR_ID = 1
    protocol_input_index: int
    user_input_index: int
    protocol_output_index: int


@dataclass()
class EndProtocol(PlutusData):
    CONSTR_ID = 2
    protocol_input_index: int
    user_input_index: int

RedeemerProtocol = Union[UpdateProtocol, EndProtocol]

################################################
# Project Data Types
################################################

@dataclass()
class DatumProjectParams(PlutusData):
    CONSTR_ID = 1
    project_id: bytes  # Project Identifier
    project_metadata: bytes  # Metadata URI or hash
    project_state: int  # 0=initialized, 1=distributed, 2=certified 3=closed


@dataclass()
class TokenProject(PlutusData):
    CONSTR_ID = 2
    policy_id: bytes  # Minting policy ID for the project tokens
    token_name: bytes  # Token name for the project tokens
    total_supply: int  # Total supply of tokens for the project (Grey tokens representing carbon credits promises)
    current_supply: int  # Current supply of tokens minted (Grey tokens)

@dataclass()
class StakeHolderParticipation(PlutusData):
    CONSTR_ID = 3
    stakeholder: bytes  # Stakeholder public name (investor, landowner, verifier, etc.) Investor is a keyword that do not require pkh)
    pkh: bytes  # Stakeholder public key hash
    participation: int  # Participation amount in lovelace
    amount_claimed: int  # Amount already claimed in lovelace


@dataclass()
class Certification(PlutusData):
    CONSTR_ID = 4
    certification_date: int  # Certification date as POSIX timestamp
    quantity: int  # Quantity of carbon credits certified
    real_certification_date: int  # Real certification date as POSIX timestamp (after verification)
    real_quantity: int  # Real quantity of carbon credits certified (after verification)

@dataclass()
class DatumProject(PlutusData):
    CONSTR_ID = 0
    protocol_policy_id: bytes  # Protocol policy ID
    params: DatumProjectParams
    project_token: TokenProject
    stakeholders: List[StakeHolderParticipation]  # List of stakeholders and their participation
    certifications: List[Certification]  # List of certification info for the project

@dataclass()
class UpdateProject(PlutusData):
    CONSTR_ID = 1
    project_input_index: int
    user_input_index: int
    project_output_index: int

@dataclass()
class UpdateToken(PlutusData):
    CONSTR_ID = 3
    project_input_index: int
    user_input_index: int
    project_output_index: int
    new_supply: int

@dataclass()
class EndProject(PlutusData):
    CONSTR_ID = 2
    project_input_index: int
    user_input_index: int

RedeemerProject = Union[UpdateProject, UpdateToken, EndProject]

################################################
# Generic functions
################################################
def get_minting_purpose(context: ScriptContext) -> Minting:
    purpose = context.purpose
    assert isinstance(purpose, Minting)
    return purpose


def get_spending_purpose(context: ScriptContext) -> Spending:
    purpose = context.purpose
    assert isinstance(purpose, Spending)
    return purpose


def has_utxo(context: ScriptContext, oref: TxOutRef) -> bool:
    """Check if specified UTXO is consumed in transaction"""
    tx_info = context.tx_info
    for input_utxo in tx_info.inputs:
        if input_utxo.out_ref == oref:
            return True
    return False


def unique_token_name(oref: TxOutRef, prefix: bytes) -> TokenName:
    """Hash tx_id with index to ensure index affects the entire hash"""
    # Combine tx_id with index before hashing
    index_bytes = cons_byte_string(oref.idx, b"")
    combined_data = append_byte_string(oref.id.tx_id, index_bytes)

    # Hash the combined data
    combined_hash = sha3_256(combined_data)

    # Add prefix and truncate
    full_token = append_byte_string(prefix, combined_hash)

    if len(full_token) > 32:
        return slice_byte_string(0, 32, full_token)

    return full_token


def only_one_input_from_address(address: Address, inputs: List[TxInInfo]) -> bool:  # Not in Used
    """Check if there is only one input from the specified address"""
    return sum([int(i.resolved.address == address) for i in inputs]) == 1


def only_one_output_to_address(address: Address, outputs: List[TxOut]) -> bool:  # Not in Used
    """Check if there is only one output to the specified address"""
    return sum([int(i.address == address) for i in outputs]) == 1


def amount_of_token_in_output(token: Token, output: TxOut) -> int:  # Not in Used
    """Get the amount of a specific token in a transaction output"""
    return output.value.get(token.policy_id, {b"": 0}).get(token.token_name, 0)


def resolve_linear_input(tx_info: TxInfo, input_index: int, purpose: Spending) -> TxOut:  # In Use
    """
    Resolve the input that is referenced by the redeemer.
    Also checks that the input is referenced correctly and that there is only one.
    """
    previous_state_input_unresolved = tx_info.inputs[input_index]
    assert previous_state_input_unresolved.out_ref == purpose.tx_out_ref, f"Referenced wrong input"
    previous_state_input = previous_state_input_unresolved.resolved
    assert only_one_input_from_address(
        previous_state_input.address, tx_info.inputs
    ), "More than one input from the contract address"
    return previous_state_input


def resolve_linear_output(
    previous_state_input: TxOut, tx_info: TxInfo, output_index: int
) -> TxOut:  # In Use
    """
    Resolve the continuing output that is referenced by the redeemer. Checks that the output does not move funds to a different address.
    """
    outputs = tx_info.outputs
    next_state_output = outputs[output_index]
    assert (
        next_state_output.address == previous_state_input.address
    ), "Moved funds to different address"
    assert only_one_output_to_address(
        next_state_output.address, outputs
    ), "More than one output to the contract address"
    return next_state_output


def check_token_present(policy_id: PolicyId, output: TxOut) -> bool:
    """
    Returns whether the given token is contained in the output
    """
    default_tokens: Dict[bytes, int] = {b"": 0}
    policy_tokens = output.value.get(policy_id, default_tokens)

    # Use .keys() to iterate over dictionary keys
    for token_name in policy_tokens.keys():
        if policy_tokens[token_name] > 0:
            return True
    return False


def extract_token_from_input(tx_input: TxOut) -> Token:
    """
    Extract protocol NFT - Version 3: Flag-based approach
    """
    found = False
    result_policy = b""
    result_token = b""

    for policy_id in tx_input.value.keys():
        if policy_id != b"" and not found:  # Skip ADA and only take first
            for token_name in tx_input.value[policy_id].keys():
                if not found:  # Only take the first token
                    result_policy = policy_id
                    result_token = token_name
                    found = True

    assert found, "Token not found in transaction input"
    return Token(result_policy, result_token)


def validate_nft_continues(tx_output: TxOut, expected_token: Token) -> None:
    """
    Validate that the NFT continues to the output UTxO.

    Args:
        tx_output: Output TxOut
        expected_token: Expected NFT token name

    Raises:
        AssertionError: If NFT is not found in output
    """

    minting_policy_id = expected_token.policy_id
    expected_token_name = expected_token.token_name
    tx_output_tokens = tx_output.value.get(minting_policy_id, {b"": 0})
    token_amount = tx_output_tokens.get(expected_token_name, 0)

    assert token_amount == 1, f"NFT {expected_token_name.hex()} must continue to output"
