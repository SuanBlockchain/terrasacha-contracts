from opshin.prelude import *
from opshin.std.builtins import *

from terrasacha_contracts.types import *

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
    """Generate unique token name from UTXO reference and prefix"""
    txid_hash = sha3_256(oref.id.tx_id)
    prepend_index = cons_byte_string(oref.idx, txid_hash)
    token_name = append_byte_string(prefix, prepend_index)

    return token_name

def get_user_token_from_protocol_token(protocol_token: TokenName) -> TokenName:
    """
    Slice the token name into its prefix and unique suffix.
    """

    return slice_byte_string(len(PREFIX_PROTOCOL_NFT), len(protocol_token) - len(PREFIX_PROTOCOL_NFT), protocol_token)

def check_mint_exactly_n_with_name(
    mint: Value, n: int, policy_id: PolicyId, required_token_name: TokenName
) -> None:
    """
    Check that exactly n token with the given name is minted
    from the given policy
    """
    d = mint[policy_id]
    assert d[required_token_name] == n, "Exactly n token must be minted"
    assert len(d) == 1, "No other token must be minted"


def check_mint_exactly_one_with_name(
    mint: Value, policy_id: PolicyId, required_token_name: TokenName
) -> None:
    """
    Check that exactly one token with the given name is minted
    from the given policy
    """
    check_mint_exactly_n_with_name(mint, 1, policy_id, required_token_name)

def only_one_input_from_address(address: Address, inputs: List[TxInInfo]) -> bool:
    return sum([int(i.resolved.address == address) for i in inputs]) == 1

def only_one_output_to_address(address: Address, outputs: List[TxOut]) -> bool:
    return sum([int(i.address == address) for i in outputs]) == 1

def amount_of_token_in_output(token: Token, output: TxOut) -> int:
    return output.value.get(token.policy_id, {b"": 0}).get(token.token_name, 0)

def resolve_linear_input(tx_info: TxInfo, input_index: int, purpose: Spending) -> TxOut:
    """
    Resolve the input that is referenced by the redeemer.
    Also checks that the input is referenced correctly and that there is only one.
    """
    previous_state_input_unresolved = tx_info.inputs[input_index]
    assert (
        previous_state_input_unresolved.out_ref == purpose.tx_out_ref
    ), f"Referenced wrong input"
    previous_state_input = previous_state_input_unresolved.resolved
    assert only_one_input_from_address(
        previous_state_input.address, tx_info.inputs
    ), "More than one input from the contract address"
    return previous_state_input

def resolve_linear_output(
    previous_state_input: TxOut, tx_info: TxInfo, output_index: int
) -> TxOut:
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

def check_mint_exactly_one_to_output(mint: Value, token: Token, staking_output: TxOut):
    """
    Check that exactly one token is minted and sent to address
    Also ensures that no other token of this policy is minted
    """
    check_mint_exactly_one_with_name(mint, token.policy_id, token.token_name)
    assert (
        amount_of_token_in_output(token, staking_output) == 1
    ), "Exactly one token must be sent to staking address"

def check_token_present(token: Token, output: TxOut) -> bool:
    """
    Returns whether the given token is contained in the output
    """
    return output.value.get(token.policy_id, {b"": 0}).get(token.token_name, 0) > 0


