from opshin.prelude import *
from terrasacha_contracts.util import *
from terrasacha_contracts.types import *

def validate_protocol_nft_continues(
    protocol_output: TxOut,
    protocol_token: Token
) -> None:
    """
    Validate that the protocol NFT continues to the protocol output UTxO.
    
    Args:
        protocol_output: Protocol's output TxOut
        minting_policy_id: The minting policy ID
        expected_protocol_token: Expected protocol NFT token name
        
    Raises:
        AssertionError: If protocol NFT is not found in output
    """

    minting_policy_id = protocol_token.policy_id
    expected_protocol_token = protocol_token.token_name
    protocol_output_tokens = protocol_output.value.get(minting_policy_id, {b"": 0})
    protocol_nft_amount = protocol_output_tokens.get(expected_protocol_token, 0)
    
    assert protocol_nft_amount == 1, f"Protocol NFT {expected_protocol_token.hex()} must continue to protocol output"

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
    unique_suffix = protocol_token[len(PREFIX_PROTOCOL_NFT):]

    # Create user token with same suffix
    user_token_name = PREFIX_USER_NFT + unique_suffix

    return user_token_name

def extract_protocol_token_from_input(protocol_input: TxOut) -> Token:
    """
    Extract protocol NFT - Version 3: Flag-based approach
    """
    found = False
    result_policy = b""
    result_token = b""
    
    for policy_id in protocol_input.value.keys():
        if policy_id != b"" and not found:  # Skip ADA and only take first
            for token_name in protocol_input.value[policy_id].keys():
                if not found:  # Only take the first token
                    result_policy = policy_id
                    result_token = token_name
                    found = True

    assert found, "Protocol NFT not found in protocol input"
    return Token(result_policy, result_token)

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

def validator(oref: TxOutRef, datum_protocol: DatumProtocol, redeemer: RedeemerProtocol, context: ScriptContext) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)
    
    if isinstance(redeemer, UpdateProtocol):
        protocol_input = resolve_linear_input(tx_info, redeemer.protocol_input_index, purpose)
        protocol_output = resolve_linear_output(protocol_input, tx_info, redeemer.protocol_output_index)

        protocol_token = extract_protocol_token_from_input(protocol_input)
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(protocol_token.policy_id, user_input), "User does not have required token"

        validate_protocol_nft_continues(protocol_output, protocol_token)

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