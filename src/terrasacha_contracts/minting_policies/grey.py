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
    project_reference_index: int


def validate_mint_operation(
    project_datum_value: DatumProject, own_policy_id: PolicyId, our_minted: Dict[TokenName, int]
) -> None:
    """
    Validate that the project input is valid for minting.
    - Project input must contain the project NFT
    - Project token policy must match our minting policy
    - Project must be in appropriate state for token operations
    """

    # Validate project token configuration
    datum_token_policy_id = project_datum_value.project_token.policy_id
    assert datum_token_policy_id == own_policy_id, "Token policy ID mismatch with project datum"

    datum_token_name = project_datum_value.project_token.token_name
    assert our_minted.get(datum_token_name, 0) > 0, "Must mint the correct token"


def validate_project_state_for_mint(
    project_input_datum_value: DatumProject,
    project_output_datum_value: DatumProject,
    our_minted: Dict[TokenName, int],
    signatories: List[PubKeyHash],
) -> None:
    # Check if this is the "free minting" period (state 0→1 transition)
    project_input_state = project_input_datum_value.params.project_state
    project_output_state = project_output_datum_value.params.project_state

    is_free_minting_period = project_input_state == 0 and project_output_state == 1
    minted_quantity = our_minted.get(project_input_datum_value.project_token.token_name, 0)
    if is_free_minting_period:
        #         # During free minting period (state 0→1), any amount can be minted
        #         # No additional validations required - this is the initial token distribution
        total_supply = project_input_datum_value.project_token.total_supply
        total_participation = get_total_participation(project_input_datum_value.stakeholders)
        assert minted_quantity + total_participation == total_supply, (
            "Minted quantity plus stakeholder participation cannot exceed total supply"
        )
    else:
        assert project_input_datum_value.params.project_state == 1, (
            "Can only mint during free minting period (input state must be 0)"
        )
        assert len(signatories) > 0, "Transaction must be signed by a stakeholder"
        assert len(project_input_datum_value.stakeholders) > 0, "Project must have stakeholders for token operations"

        # Find the authorized stakeholder
        found_authorized_stakeholder = False
        # authorized_stakeholder = project_input_datum_value.stakeholders[0]  # Default to avoid None type

        for signer_pkh in signatories:
            for stakeholder in project_input_datum_value.stakeholders:
                if stakeholder.pkh == signer_pkh:
                    # authorized_stakeholder = stakeholder
                    assert stakeholder.claimed == FalseData(), "Stakeholder has already claimed their tokens"
                    assert minted_quantity == stakeholder.participation, (
                        "Must mint exactly the stakeholder's full participation amount"
                    )
                    found_authorized_stakeholder = True

        assert found_authorized_stakeholder, "Transaction must be signed by a registered stakeholder"


def validate_burn_operation(
    our_minted: Dict[bytes, int], project_datum: DatumProject, tx_info: TxInfo, own_policy_id: PolicyId
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


def validator(project_id: PolicyId, redeemer: Union[MintGrey, BurnGrey], context: ScriptContext) -> None:
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

        # Validate project reference and get datum
        project_reference_input = tx_info.inputs[redeemer.project_input_index].resolved
        project_datum = project_reference_input.datum
        assert isinstance(project_datum, SomeOutputDatum), "Project input must have a datum"
        project_input_datum_value: DatumProject = project_datum.datum
        
        assert check_token_present(project_id, project_reference_input), "Project input must have the project token"

        validate_mint_operation(project_input_datum_value, own_policy_id, our_minted)

        project_output = resolve_linear_output(project_reference_input, tx_info, redeemer.project_output_index)

        project_output_datum = project_output.datum
        assert isinstance(project_output_datum, SomeOutputDatum), "Project output must have a datum"
        project_output_datum_value: DatumProject = project_output_datum.datum

        signatories = tx_info.signatories

        validate_project_state_for_mint(project_input_datum_value, project_output_datum_value, our_minted, signatories)

    elif isinstance(redeemer, BurnGrey):
        project_reference_input = tx_info.reference_inputs[redeemer.project_reference_index].resolved
        project_datum = project_reference_input.datum
        assert isinstance(project_datum, SomeOutputDatum), "Project input must have a datum"
        project_input_datum_value: DatumProject = project_datum.datum

        validate_burn_operation(our_minted, project_input_datum_value, tx_info, own_policy_id)

    else:
        assert False, "Invalid redeemer type"
