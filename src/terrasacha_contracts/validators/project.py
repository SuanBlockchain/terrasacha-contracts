from opshin.prelude import *
from terrasacha_contracts.util import *


@dataclass()
class DatumProject(PlutusData):
    CONSTR_ID = 0
    project_admin: bytes       # Project admin public key hash
    project_fee: int           # Project fee in lovelace
    project_metadata: bytes    # Metadata URI or hash

@dataclass()
class UpdateProject(PlutusData):
    CONSTR_ID = 1
    project_input_index: int
    user_input_index: int
    project_output_index: int

@dataclass()
class EndProject(PlutusData):
    CONSTR_ID = 2
    project_input_index: int

RedeemerProject = Union[UpdateProject, EndProject]

def validator(oref: TxOutRef, datum_project: DatumProject, redeemer: RedeemerProject, context: ScriptContext) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)
    
    if isinstance(redeemer, UpdateProject):
        project_input = resolve_linear_input(tx_info, redeemer.project_input_index, purpose)
        project_output = resolve_linear_output(project_input, tx_info, redeemer.project_output_index)

        project_token = extract_project_token_from_input(project_input)
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(project_token.policy_id, user_input), "User does not have required token"

        validate_project_nft_continues(project_output, project_token)

        project_datum = project_output.datum
        assert isinstance(project_datum, SomeOutputDatum)
        new_datum: DatumProject = project_datum.datum
        validate_datum_update(datum_project, new_datum)

    elif isinstance(redeemer, EndProject):
        project_input = resolve_linear_input(tx_info, redeemer.project_input_index, purpose)
        project_datum = project_input.datum
        assert isinstance(project_datum, SomeOutputDatum)
        input_datum: DatumProject = project_datum.datum

        validate_signatories(input_datum, tx_info)