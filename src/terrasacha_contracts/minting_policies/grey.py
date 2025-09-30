#!opshin
from opshin.prelude import *

from terrasacha_contracts.util import *

@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0

@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1

def validate_project_reference(
    project_id: PolicyId, tx_info: TxInfo, own_policy_id: PolicyId
) -> DatumProject:
    """
    Validate that the project reference input is valid and return the project datum.
    - Reference input must contain the project NFT
    - Project token policy must match our minting policy
    - Project must be in appropriate state for token operations
    """
    assert len(tx_info.reference_inputs) > 0, "Transaction must have reference inputs"

    project_reference_input = tx_info.reference_inputs[0].resolved
    assert check_token_present(
        project_id, project_reference_input
    ), "Project reference input must have the project token"

    # Get the project datum
    project_datum = project_reference_input.datum
    assert isinstance(project_datum, SomeOutputDatum)
    project_datum_value: DatumProject = project_datum.datum

    # Validate project token configuration
    datum_token_policy_id = project_datum_value.project_token.policy_id
    assert datum_token_policy_id == own_policy_id, "Token policy ID mismatch with project datum"

    # Project state validation will be done in specific mint/burn functions
    assert project_datum_value.params.project_state >= 0, "Invalid project state"

    return project_datum_value

def validate_mint_operation(
    our_minted: Dict[bytes, int], project_datum: DatumProject, tx_info: TxInfo
) -> None:
    """
    Validate token minting operation based on project state:
    - State 0→1 transition: "Free minting" period - any amount allowed
    - State >= 1: Only authorized stakeholders can mint their full allocation once
    """
    datum_token_name = project_datum.project_token.token_name
    minted_amount = our_minted.get(datum_token_name, 0)

    assert minted_amount > 0, "Must mint positive amount of tokens"

    # Check if this is the "free minting" period (state 0→1 transition)
    # We need to find the project input (state 0) and output (state 1) to detect the transition
    project_input_state = -1
    project_output_state = -1

    # Find project input state from spending inputs
    for input_info in tx_info.inputs:
        input_datum = input_info.resolved.datum
        if isinstance(input_datum, SomeOutputDatum):
            input_project_datum: DatumProject = input_datum.datum
            if input_project_datum.project_token.token_name == datum_token_name:
                project_input_state = input_project_datum.params.project_state

    # Find project output state from outputs
    for output in tx_info.outputs:
        output_datum = output.datum
        if isinstance(output_datum, SomeOutputDatum):
            output_project_datum: DatumProject = output_datum.datum
            if output_project_datum.project_token.token_name == datum_token_name:
                project_output_state = output_project_datum.params.project_state

    # Check if this is free minting period (0→1 transition)
    is_free_minting_period = project_input_state == 0 and project_output_state == 1

    if is_free_minting_period:
        # During free minting period (state 0→1), any amount can be minted
        # No additional validations required - this is the initial token distribution
        pass
    elif project_datum.params.project_state >= 1:
        # After free minting period, only authorized stakeholders can mint their allocation
        assert len(tx_info.signatories) > 0, "Transaction must be signed by a stakeholder"
        assert (
            len(project_datum.stakeholders) > 0
        ), "Project must have stakeholders for token operations"

        # Find the authorized stakeholder
        found_authorized_stakeholder = False
        authorized_stakeholder = project_datum.stakeholders[0]  # Default to avoid None type

        for signer_pkh in tx_info.signatories:
            for stakeholder in project_datum.stakeholders:
                if stakeholder.pkh == signer_pkh:
                    authorized_stakeholder = stakeholder
                    found_authorized_stakeholder = True

        assert (
            found_authorized_stakeholder
        ), "Transaction must be signed by a registered stakeholder"
        assert authorized_stakeholder.claimed == FalseData(), "Stakeholder has already claimed their tokens"
        assert (
            minted_amount == authorized_stakeholder.participation
        ), "Must mint exactly the stakeholder's full participation amount"
    else:
        assert False, "Invalid project state for minting"

def validate_burn_operation(
    our_minted: Dict[bytes, int],
    project_datum: DatumProject,
    tx_info: TxInfo,
    own_policy_id: PolicyId,
) -> None:
    """
    Validate token burning operation.
    - Burned amount must be negative (in mint value)
    - Token name must match project datum
    - Cannot send tokens to outputs when burning
    """

    datum_token_name = project_datum.project_token.token_name
    burned_amount = our_minted.get(datum_token_name, 0)

    assert burned_amount < 0, "Must burn tokens with negative mint amount"

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
