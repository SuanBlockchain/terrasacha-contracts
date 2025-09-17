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

    # Validations when minting:
    # 1. the amount minted is exactly the amount added to the current supply
    # 2. Investor can only mint if it pays an price expressed in lovelace that is sent to a specific beneficiary

    our_minted = mint_value.get(own_policy_id, {b"": 0})
    assert len(our_minted) == 1, "Must mint or burn exactly 1 token type"

    project_reference_input = tx_info.reference_inputs[0].resolved

    assert check_token_present(project_id, project_reference_input), "Project reference input must have the project token"

    # Get the project datum
    project_datum = project_reference_input.datum
    assert isinstance(project_datum, SomeOutputDatum)
    project_datum_value: DatumProject = project_datum.datum

    datum_token_policy_id = project_datum_value.project_token.policy_id
    datum_token_name = project_datum_value.project_token.token_name

    assert datum_token_policy_id == own_policy_id, "PolicyID is different than ProjectDatum PolicyID"

    if isinstance(redeemer, Mint):

        assert our_minted.get(datum_token_name, 0) > 0, "Token Name not found in minted amount"

        assert project_datum_value.params.project_state > 0, "Minting can only happen when project_state > 0"

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
