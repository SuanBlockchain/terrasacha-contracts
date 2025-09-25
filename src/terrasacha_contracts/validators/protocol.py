from opshin.prelude import *

from terrasacha_contracts.util import *

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


def validate_datum_update(new_datum: DatumProtocol) -> None:
    """
    Validate the update of a datum.
    Now allows updates to project_admins, oracle_id, and protocol_fee with proper validations.
    """
    # Validate protocol_fee
    assert new_datum.protocol_fee >= 0, "Protocol fee must be non-negative"

    # Validate admin list updates
    assert len(new_datum.project_admins) <= 10, "Protocol cannot have more than 10 admins"


def validator(
    token_policy_id: PolicyId,
    _: DatumProtocol,
    redeemer: RedeemerProtocol,
    context: ScriptContext,
) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)
    protocol_input = resolve_linear_input(tx_info, redeemer.protocol_input_index, purpose)
    protocol_token = extract_token_from_input(protocol_input)
    user_input = tx_info.inputs[redeemer.user_input_index].resolved

    # Primarly to validate that the user is giving the right input index to interact with the contract
    assert protocol_token.policy_id == token_policy_id, "Wrong token policy ID"

    assert check_token_present(
        protocol_token.policy_id, user_input
    ), "User does not have required token"

    for txi in tx_info.inputs:
        if txi.out_ref == purpose.tx_out_ref:
            own_txout = txi.resolved
            own_address = own_txout.address

    assert only_one_input_from_address(own_address, tx_info.inputs) == 1, "More than one input from the contract address"

    if isinstance(redeemer, UpdateProtocol):
        protocol_output = resolve_linear_output(
            protocol_input, tx_info, redeemer.protocol_output_index
        )

        validate_nft_continues(protocol_output, protocol_token)

        protocol_datum = protocol_output.datum
        assert isinstance(protocol_datum, SomeOutputDatum)
        new_datum: DatumProtocol = protocol_datum.datum
        validate_datum_update(new_datum)

    elif isinstance(redeemer, EndProtocol):

        # Ensure no tokens are sent to any output with the token policy
        for output in tx_info.outputs:
            token_amount = sum(output.value.get(protocol_token.policy_id, {b"": 0}).values())
            assert token_amount == 0, "Cannot send tokens to outputs when burning"

    else:
        assert False, "Invalid redeemer type"
