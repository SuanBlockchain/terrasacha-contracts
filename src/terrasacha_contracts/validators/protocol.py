from opshin.prelude import *

from utils.types import Burn, DatumProtocol, Mint
from utils.utils import (
    PREFIX_PROTOCOL_NFT,
    PREFIX_USER_NFT,
    find_script_address,
    find_token_output,
    has_utxo,
    unique_token_name,
)


def validate_protocol_datum(datum: DatumProtocol) -> None:
    """Validate protocol datum constraints"""
    assert len(datum.protocol_admin) > 0, "Protocol admin list cannot be empty"
    assert datum.protocol_fee > 0, "Protocol fee must be greater than zero"
    assert len(datum.oracle_id) > 0, "Oracle ID cannot be empty"
    assert len(datum.project_id) > 0, "Project ID cannot be empty"


def validate_minting_constraints(
    context: ScriptContext, protocol_token_name: TokenName, user_token_name: TokenName
) -> None:
    """Validate all minting constraints"""
    tx_info = context.tx_info
    purpose = context.purpose
    assert isinstance(purpose, Minting), f"Wrong script purpose: {purpose}"

    policy_id = purpose.policy_id

    script_address = find_script_address(policy_id)

    # Find protocol and user outputs
    protocol_output = find_token_output(
        tx_info.outputs, purpose.policy_id, protocol_token_name
    )
    assert protocol_output is not None, "Protocol NFT output not found"
    user_output = find_token_output(tx_info.outputs, purpose.policy_id, user_token_name)
    assert user_output is not None, "User NFT output not found"

    # Validate protocol output datum
    protocol_datum = protocol_output.datum
    assert isinstance(
        protocol_datum, SomeOutputDatum
    ), "Protocol output must have inlined datum"
    datum_data = protocol_datum.datum
    assert isinstance(
        datum_data, DatumProtocol
    ), "Protocol output datum must be DatumProtocol"
    validate_protocol_datum(datum_data)

    # Validate protocol output address (sent to script)
    assert (
        protocol_output.address == script_address
    ), "Protocol NFT not sent to correct script address"

    # # Validate protocol output contains exactly 1 token
    # protocol_tokens = protocol_output.value.get(purpose.policy_id, {b"": 0})
    # assert sum(protocol_tokens.values()) == 1, "Protocol output must contain exactly 1 token"
    # assert len(protocol_tokens.keys()) == 1, "Protocol output must contain only one token type"

    # # Validate user output contains exactly 1 token
    # user_tokens = user_output.value.get(purpose.policy_id, {b"": 0})
    # assert sum(user_tokens.values()) == 1, "User output must contain exactly 1 token"
    # assert len(user_tokens.keys()) == 1, "User output must contain only one token type"

    # Validate that outputs only contain ADA and the minted policy
    for output in [protocol_output, user_output]:
        value_policies = list(output.value.keys())
        valid_policies = [b"", purpose.policy_id]  # ADA (empty bytes) and own policy
        assert all(
            policy in valid_policies for policy in value_policies
        ), "Outputs contain unauthorized token policies"
        assert len(value_policies) <= 2, "Too many token policies in output"

    # Validate exactly 2 tokens are minted (1 protocol + 1 user)
    mint_value = tx_info.mint
    our_minted = mint_value.get(purpose.policy_id, {b"": 0})
    assert len(our_minted) == 2, "Must mint exactly 2 tokens"
    assert (
        our_minted.get(protocol_token_name, 0) == 1
    ), "Must mint exactly 1 protocol token"
    assert our_minted.get(user_token_name, 0) == 1, "Must mint exactly 1 user token"


# TODO: for being able to burn make sure to pass both tokens at the input and both tokens must be burned
def validate_burning_constraints(context: ScriptContext, policy_id: PolicyId) -> None:
    """Validate all burning constraints"""
    tx_info = context.tx_info

    # Check that tokens are being burned (negative amounts in mint)
    mint_value = tx_info.mint
    our_minted = mint_value.get(policy_id, {b"": 0})

    # All minted amounts should be negative (burning)
    for token_name, amount in our_minted.items():
        assert amount < 0, f"Token {token_name.hex()} must be burned (negative amount)"

    # Ensure no tokens are sent to any output with this policy
    for output in tx_info.outputs:
        token_amount = sum(output.value.get(policy_id, {b"": 0}).values())
        assert token_amount == 0, "Cannot send tokens to outputs when burning"


def validator(
    oref: TxOutRef,
    redeemer: Union[Mint, Burn],
    context: ScriptContext,
) -> None:
    """
    Protocol contract validator for minting and burning protocol NFTs.

    Args:
        oref: Transaction output reference used for unique token name generation
        redeemer: Either Mint or Burn operation
        context: Script execution context
    """
    purpose = context.purpose
    # tx_info = context.tx_info

    # Ensure this is a minting script
    assert isinstance(purpose, Minting), f"Wrong script purpose: {purpose}"

    if isinstance(redeemer, Mint):
        # 1. Validate that the specified UTXO is consumed
        assert has_utxo(context, oref), "UTxO not consumed"
        # Generate unique token names based on UTXO reference
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # 2-7. Validate all minting constraints
        validate_minting_constraints(context, protocol_token_name, user_token_name)

    elif isinstance(redeemer, Burn):
        # Validate burning constraints
        validate_burning_constraints(context, purpose.policy_id)

    else:
        assert False, "Invalid redeemer type"
