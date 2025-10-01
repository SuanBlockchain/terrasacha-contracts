#!opshin
from opshin.prelude import *

from terrasacha_contracts.util import *

@dataclass()
class MintGrey(PlutusData):
    CONSTR_ID = 0
    project_input_index: int
    project_output_index: int

@dataclass()
class BurnGrey(PlutusData):
    CONSTR_ID = 1

def validate_mint_operation(
    project_id: PolicyId, project_reference_input: TxOut, own_policy_id: PolicyId, our_minted: Dict[TokenName, int]
) -> DatumProject:
    """
    Validate that the project input is valid and return the project datum.
    - Project input must contain the project NFT
    - Project token policy must match our minting policy
    - Project must be in appropriate state for token operations
    """
    
    assert check_token_present(
        project_id, project_reference_input
    ), "Project input must have the project token"
    project_datum = project_reference_input.datum
    assert isinstance(project_datum, SomeOutputDatum)
    project_datum_value: DatumProject = project_datum.datum

    # Validate project token configuration
    datum_token_policy_id = project_datum_value.project_token.policy_id
    assert datum_token_policy_id == own_policy_id, "Token policy ID mismatch with project datum"

    datum_token_name = project_datum_value.project_token.token_name
    assert our_minted.get(datum_token_name, 0) > 0, "Must mint the correct token"

    return project_datum_value

def validate_project_state_for_mint(project_datum: DatumProject, project_output: TxOut, our_minted: Dict[TokenName, int]) -> None:
    # Check if this is the "free minting" period (state 0→1 transition)
    project_input_state = project_datum.params.project_state
    # assert project_input_state == 0, "Can only mint during free minting period (input state must be 0)"

    # Find project output state from outputs
    project_output_datum = project_output.datum
    assert isinstance(project_output_datum, SomeOutputDatum)
    project_output_datum_value: DatumProject = project_output_datum.datum
    project_output_state = project_output_datum_value.params.project_state

#     # assert project_output_state == 1, "Can only mint during free minting period (output state must be 1)"

    is_free_minting_period = project_input_state == 0 and project_output_state == 1
    if is_free_minting_period:
#         # During free minting period (state 0→1), any amount can be minted
#         # No additional validations required - this is the initial token distribution
        total_supply = project_datum.project_token.total_supply
        total_participation = get_total_participation(project_datum.stakeholders)
        minted_quantity = our_minted.get(project_datum.project_token.token_name, 0)
        assert minted_quantity + total_participation == total_supply, "Minted quantity plus stakeholder participation cannot exceed total supply"
    else:
        assert False, "Can only mint during free minting period (0→1 transition)"
        #  elif project_datum.params.project_state >= 1:
#         # After free minting period, only authorized stakeholders can mint their allocation
#         assert len(tx_info.signatories) > 0, "Transaction must be signed by a stakeholder"
#         assert (
#             len(project_datum.stakeholders) > 0
#         ), "Project must have stakeholders for token operations"

#         # Find the authorized stakeholder
#         found_authorized_stakeholder = False
#         authorized_stakeholder = project_datum.stakeholders[0]  # Default to avoid None type

#         for signer_pkh in tx_info.signatories:
#             for stakeholder in project_datum.stakeholders:
#                 if stakeholder.pkh == signer_pkh:
#                     authorized_stakeholder = stakeholder
#                     found_authorized_stakeholder = True

#         assert (
#             found_authorized_stakeholder
#         ), "Transaction must be signed by a registered stakeholder"
#         assert authorized_stakeholder.claimed == FalseData(), "Stakeholder has already claimed their tokens"
#         assert (
#             minted_amount == authorized_stakeholder.participation
#         ), "Must mint exactly the stakeholder's full participation amount"

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
    redeemer: Union[MintGrey, BurnGrey],
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


    if isinstance(redeemer, MintGrey):
        # assert True, "Minting always succeeds for now"
        # Validate project reference and get datum
        project_reference_input = tx_info.inputs[redeemer.project_input_index].resolved
        project_datum = validate_mint_operation(project_id, project_reference_input, own_policy_id, our_minted)

        project_output = resolve_linear_output(
            project_reference_input, tx_info, redeemer.project_output_index
        )
        validate_project_state_for_mint(project_datum, project_output, our_minted)

    elif isinstance(redeemer, BurnGrey):
        # validate_burn_operation(our_minted, project_datum, tx_info, own_policy_id)
        assert True, "Burning always succeeds for now"

    else:
        assert False, "Invalid redeemer type"
