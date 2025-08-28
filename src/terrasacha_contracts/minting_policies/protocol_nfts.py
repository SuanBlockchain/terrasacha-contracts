#!opshin
from opshin.prelude import *
from terrasacha_contracts.util import *
from terrasacha_contracts.types import *

def validator(
    unique_utxo_index: int,
    redeemer: Union[Mint, Burn],
    context: ScriptContext,
) -> None:
    """
    Protocol contract validator for minting and burning protocol NFTs.

    Args:
        oref: Transaction output reference used for unique token name generation
        redeemer: Either Mint or Burn operation (as PlutusData)
        context: Script execution context
    """
    purpose = get_minting_purpose(context)
    own_policy_id = purpose.policy_id
    tx_info = context.tx_info
    mint_value = tx_info.mint

    # Check redeemer type using constructor ID
    if isinstance(redeemer, Mint):
        # 1. Validate that the specified UTXO is consumed
        oref_input = context.tx_info.inputs[unique_utxo_index].out_ref
        assert has_utxo(context, oref_input), "UTxO not consumed"
        
        # Generate unique token names based on UTXO reference
        protocol_token_name = unique_token_name(oref_input, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref_input, PREFIX_USER_NFT)


        # Validate exactly 2 tokens are minted (1 protocol + 1 user)
        our_minted = mint_value.get(own_policy_id, {b"": 0})
        assert len(our_minted) == 2, "Must mint exactly 2 tokens"

        assert (
            our_minted.get(protocol_token_name, 0) == 1
        ), "Must mint exactly 1 protocol token"
        assert our_minted.get(user_token_name, 0) == 1, "Must mint exactly 1 user token"

    elif isinstance(redeemer, Burn):

        # Check that tokens are being burned (negative amounts in mint)
        our_minted = mint_value.get(own_policy_id, {b"": 0})

        # All minted amounts should be negative (burning)
        for token_name, amount in our_minted.items():
            assert amount < 0, f"Token {token_name.hex()} must be burned (negative amount)"

        # Ensure no tokens are sent to any output with this policy
        for output in tx_info.outputs:
            token_amount = sum(output.value.get(own_policy_id, {b"": 0}).values())
            assert token_amount == 0, "Cannot send tokens to outputs when burning"

    else:
        assert False, "Invalid redeemer type"