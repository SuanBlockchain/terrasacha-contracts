from opshin.prelude import *

from terrasacha_contracts.util import *


@dataclass()
class DatumProtocol(PlutusData):
    CONSTR_ID = 0
    protocol_admin: List[bytes]  # List of admin public key hashes
    protocol_fee: int  # Protocol fee in lovelace
    oracle_id: PolicyId  # Oracle identifier
    projects: List[bytes]  # List of project IDs registered


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

    # Validate protocol_admin updates
    assert len(new_datum.protocol_admin) > 0, "Protocol must have at least one admin"
    assert len(new_datum.protocol_admin) <= 3, "Protocol cannot have more than 10 admins"
    assert len(new_datum.projects) > 0, "Protocol must have at least one project"

    # Validate project list updates
    assert len(new_datum.projects) <= 10, "Protocol cannot have more than 10 projects"


def validate_signatories(input_datum: DatumProtocol, tx_info: TxInfo) -> None:
    """
    Validate that the signatories are authorized.
    """
    signatories = tx_info.signatories
    protocol_admins = input_datum.protocol_admin

    admin_signed = False
    for admin_pkh in protocol_admins:
        if admin_pkh in signatories:
            admin_signed = True

    assert admin_signed, "EndProtocol requires signature from protocol admin"


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
        protocol_datum = protocol_input.datum
        assert isinstance(protocol_datum, SomeOutputDatum)
        input_datum: DatumProtocol = protocol_datum.datum

        validate_signatories(input_datum, tx_info)
    else:
        assert False, "Invalid redeemer type"
