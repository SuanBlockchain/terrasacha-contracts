#!opshin
from opshin.prelude import *

from terrasacha_contracts.util import *


@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0


@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1

def validate_project_reference(project_id: PolicyId, tx_info: TxInfo, own_policy_id: PolicyId) -> DatumProject:
    """
    Validate that the project reference input is valid and return the project datum.
    - Reference input must contain the project NFT
    - Project token policy must match our minting policy
    - Project must be in active state (> 0) for minting/burning
    """
    assert len(tx_info.reference_inputs) > 0, "Transaction must have reference inputs"

    project_reference_input = tx_info.reference_inputs[0].resolved
    assert check_token_present(project_id, project_reference_input), "Project reference input must have the project token"

    # Get the project datum
    project_datum = project_reference_input.datum
    assert isinstance(project_datum, SomeOutputDatum)
    project_datum_value: DatumProject = project_datum.datum

    # Validate project token configuration
    datum_token_policy_id = project_datum_value.project_token.policy_id
    assert datum_token_policy_id == own_policy_id, "Token policy ID mismatch with project datum"

    # Project must be active for token operations
    assert project_datum_value.params.project_state > 0, "Token operations can only happen when project_state > 0"

    return project_datum_value

def validate_mint_operation(our_minted: Dict[bytes, int], project_datum: DatumProject, tx_info: TxInfo) -> None:
    """
    Validate token minting operation.
    - Minted amount must be positive
    - Token name must match project datum
    """

    datum_token_name = project_datum.project_token.token_name
    minted_amount = our_minted.get(datum_token_name, 0)

    assert minted_amount > 0, "Must mint positive amount of tokens"

    # Additional validation: minted amount should not exceed remaining mintable supply
    remaining_supply = project_datum.project_token.total_supply - project_datum.project_token.current_supply
    assert minted_amount <= remaining_supply, "Cannot mint more than remaining supply"

def validate_burn_operation(our_minted: Dict[bytes, int], project_datum: DatumProject, tx_info: TxInfo, own_policy_id: PolicyId) -> None:
    """
    Validate token burning operation.
    - Burned amount must be negative (in mint value)
    - Token name must match project datum
    - Cannot send tokens to outputs when burning
    """

    datum_token_name = project_datum.project_token.token_name
    burned_amount = our_minted.get(datum_token_name, 0)

    assert burned_amount < 0, "Must burn tokens with negative mint amount"

    # Ensure burned amount doesn't exceed current supply
    assert abs(burned_amount) <= project_datum.project_token.current_supply, "Cannot burn more than current supply"

    # Ensure no tokens are sent to any output with this policy when burning
    for output in tx_info.outputs:
        token_amount = sum(output.value.get(own_policy_id, {b"": 0}).values())
        assert token_amount == 0, "Cannot send tokens to outputs when burning"

def validator(
    project_id: PolicyId,
    redeemer: Union[Mint, Burn],
    context: ScriptContext,
) -> None:
    """
    Grey token minting policy validator.

    Responsibilities:
    - Validate project reference input is correct
    - Ensure minting/burning amounts are valid
    - Verify token operations match project constraints
    - Coordinate with project contract for datum updates

    Args:
        project_id: The PolicyId of the associated project contract NFT
        redeemer: Either Mint or Burn operation
        context: Script execution context
    """
    purpose = get_minting_purpose(context)
    own_policy_id = purpose.policy_id
    tx_info = context.tx_info
    mint_value = tx_info.mint

    # Get our minted/burned tokens
    our_minted = mint_value.get(own_policy_id, {b"": 0})
    assert len(our_minted) == 1, "Must mint or burn exactly 1 token type"

    # Validate project reference and get datum
    project_datum = validate_project_reference(project_id, tx_info, own_policy_id)

    if isinstance(redeemer, Mint):
        validate_mint_operation(our_minted, project_datum, tx_info)

    elif isinstance(redeemer, Burn):
        validate_burn_operation(our_minted, project_datum, tx_info, own_policy_id)

    else:
        assert False, "Invalid redeemer type"

