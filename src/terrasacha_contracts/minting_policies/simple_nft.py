#!opshin
from opshin.prelude import *


@dataclass
class MintAction(PlutusData):
    CONSTR_ID = 0


@dataclass
class BurnAction(PlutusData):
    CONSTR_ID = 1


def assert_minting_purpose(context: ScriptContext) -> None:
    """Check that this is being used as a minting policy"""
    purpose = context.purpose
    if isinstance(purpose, Minting):
        is_minting = True
    else:
        is_minting = False
    assert is_minting, "not minting purpose"


def check_minted_amount(
    tn: TokenName, context: ScriptContext, expected_amount: int
) -> bool:
    """Check that exactly the expected amount of tokens with given name is minted"""
    mint_value = context.tx_info.mint
    valid = False
    count = 0
    for policy_id in mint_value.keys():
        v = mint_value.get(policy_id, {b"": 0})
        if len(v.keys()) == 1:
            for token_name in v.keys():
                amount = v.get(token_name, 0)
                valid = token_name == tn and amount == expected_amount
                if amount != 0:
                    count += 1
    return valid and count == 1


def validator(
    token_name: TokenName,
    redeemer: Union[MintAction, BurnAction],
    context: ScriptContext,
) -> None:
    """
    NFT minting policy that allows minting exactly one token or burning
    """
    assert_minting_purpose(context)

    if isinstance(redeemer, MintAction):
        # Mint exactly 1 token
        assert check_minted_amount(token_name, context, 1), "wrong amount minted"
    elif isinstance(redeemer, BurnAction):
        # Burn exactly 1 token
        assert check_minted_amount(token_name, context, -1), "wrong amount burned"
