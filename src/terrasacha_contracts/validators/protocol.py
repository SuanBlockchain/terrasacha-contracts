from opshin.prelude import *

from terrasacha_contracts.util import *


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


def derive_user_token_from_protocol_token(protocol_token: TokenName) -> TokenName:
    """
    Derive the corresponding user NFT token name from a protocol NFT token name.
    Both tokens share the same unique suffix (txid_hash + output_index).

    Args:
        protocol_token: The protocol NFT token name

    Returns:
        TokenName: The corresponding user NFT token name

    Raises:
        AssertionError: If user token doesn't have expected format
    """

    # Extract the unique suffix (everything after the prefix)
    unique_suffix = protocol_token[len(PREFIX_REFERENCE_NFT) :]

    # Create user token with same suffix
    user_token_name = PREFIX_USER_NFT + unique_suffix

    return user_token_name


def validate_datum_update(old_datum: DatumProtocol, new_datum: DatumProtocol) -> None:
    """
    Validate the update of a datum.
    Now allows updates to protocol_admin, oracle_id, and protocol_fee with proper validations.
    """
    # Validate protocol_fee
    assert new_datum.protocol_fee >= 0, "Protocol fee must be non-negative"

    # Validate project list updates
    assert len(new_datum.projects) <= 10, "Protocol cannot have more than 10 projects"

    # Validate no duplicate project IDs within the new projects list
    projects_len = len(new_datum.projects)
    for i in range(projects_len):
        for j in range(projects_len):
            if j > i:  # Only check pairs once, avoid self-comparison
                assert (
                    new_datum.projects[i] != new_datum.projects[j]
                ), "Duplicate project IDs not allowed in protocol datum"


def validator(
    oref: TxOutRef,
    datum_protocol: DatumProtocol,
    redeemer: RedeemerProtocol,
    context: ScriptContext,
) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)

    if isinstance(redeemer, UpdateProtocol):
        protocol_input = resolve_linear_input(tx_info, redeemer.protocol_input_index, purpose)
        protocol_output = resolve_linear_output(
            protocol_input, tx_info, redeemer.protocol_output_index
        )

        protocol_token = extract_token_from_input(protocol_input)
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(
            protocol_token.policy_id, user_input
        ), "User does not have required token"

        validate_nft_continues(protocol_output, protocol_token)

        protocol_datum = protocol_output.datum
        assert isinstance(protocol_datum, SomeOutputDatum)
        new_datum: DatumProtocol = protocol_datum.datum
        validate_datum_update(datum_protocol, new_datum)

    elif isinstance(redeemer, EndProtocol):
        protocol_input = resolve_linear_input(tx_info, redeemer.protocol_input_index, purpose)

        protocol_token = extract_token_from_input(protocol_input)
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(
            protocol_token.policy_id, user_input
        ), "User does not have required token"

    else:
        assert False, "Invalid redeemer type"
