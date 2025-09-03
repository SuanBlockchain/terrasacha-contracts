#!opshin
from opshin.prelude import *
from terrasacha_contracts.util import *
from terrasacha_contracts.types import *

def validator(
    oref: TxOutRef,
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

    our_minted = mint_value.get(own_policy_id, {b"": 0})

    # Check redeemer type using constructor ID
    if isinstance(redeemer, Mint):
        # 1. Validate that the specified UTXO is consumed
        # oref_input = context.tx_info.inputs[unique_utxo_index].out_ref
        assert has_utxo(context, oref), "UTxO not consumed"

        # Validate exactly 2 tokens are minted (1 protocol + 1 user)
        assert len(our_minted) == 2, "Must mint exactly 2 tokens"
        
        # Generate unique token names based on UTXO reference
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        assert (
            our_minted.get(protocol_token_name, 0) == 1
        ), "Must mint exactly 1 protocol token"
        assert our_minted.get(user_token_name, 0) == 1, "Must mint exactly 1 user token"

    elif isinstance(redeemer, Burn):

        # Must burn exactly 2 tokens (protocol + user pair)
        assert len(our_minted) == 2, "Must burn exactly 2 tokens (protocol + user pair)"

        # Ensure no tokens are sent to any output with this policy
        for output in tx_info.outputs:
            token_amount = sum(output.value.get(own_policy_id, {b"": 0}).values())
            assert token_amount == 0, "Cannot send tokens to outputs when burning"

    else:
        assert False, "Invalid redeemer type"