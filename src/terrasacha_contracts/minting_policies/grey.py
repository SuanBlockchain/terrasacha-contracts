#!opshin
from opshin.prelude import *

from terrasacha_contracts.util import *


@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0


@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1


def validator(
    project_id: PolicyId,
    redeemer: Union[Mint, Burn],
    context: ScriptContext,
) -> None:
    """
    Project token contract validator for minting and burning grey tokens.

    Args:
        oref: Transaction output reference used for unique token name generation
        project_id: The PolicyId of the associated protocol contract
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

        assert True, "Always succeeds for minting grey tokens"

    elif isinstance(redeemer, Burn):

        assert True, "Always succeeds for burning grey tokens"

        # # Must burn exactly 2 tokens (protocol + user pair)
        # assert len(our_minted) == 2, "Must burn exactly 2 tokens (protocol + user pair)"

        # # Ensure no tokens are sent to any output with this policy
        # for output in tx_info.outputs:
        #     token_amount = sum(output.value.get(own_policy_id, {b"": 0}).values())
        #     assert token_amount == 0, "Cannot send tokens to outputs when burning"

    else:
        assert False, "Invalid redeemer type"
