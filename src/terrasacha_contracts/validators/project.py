from opshin.prelude import *
from terrasacha_contracts.util import *

@dataclass()
class DatumProjectParams(PlutusData):
    CONSTR_ID = 0
    owner: bytes       # Project owner public key hash
    project_id: bytes           # Project IDentifier
    project_metadata: bytes    # Metadata URI or hash
    project_state: int # 0=initialized, 1=distributed, 2=certified 3=closed

@dataclass()
class TokenProject(PlutusData):
    CONSTR_ID = 1
    policy_id: bytes         # Minting policy ID for the project tokens
    token_name: bytes        # Token name for the project tokens
    total_supply: int       # Total supply of tokens for the project (Grey tokens representing carbon credits promises)
    current_supply: int     # Current supply of tokens minted (Grey tokens)

@dataclass()
class StakeHolderParticipation(PlutusData):
    CONSTR_ID = 0
    stakeholder: bytes       # Stakeholder public name
    participation: int       # Participation amount in lovelace

@dataclass()
class Certification(PlutusData):
    CONSTR_ID = 0
    certification_date: int  # Certification date as POSIX timestamp
    quantity: int            # Quantity of carbon credits certified
    real_certification_date: int  # Real certification date as POSIX timestamp (after verification)
    real_quantity: int       # Real quantity of carbon credits certified (after verification)

@dataclass()
class DatumProject(PlutusData):
    CONSTR_ID = 0
    protocol_policy_id: bytes  # Protocol policy ID
    params: DatumProjectParams
    project_token: TokenProject
    stakeholders: List[StakeHolderParticipation]  # List of stakeholders and their participation
    certifications: List[Certification]  # List of certification info for the project

@dataclass()
class UpdateProject(PlutusData):
    CONSTR_ID = 1
    protocol_input_index: int
    project_input_index: int
    user_input_index: int
    project_output_index: int

@dataclass()
class EndProject(PlutusData):
    CONSTR_ID = 2
    project_input_index: int

RedeemerProject = Union[UpdateProject, EndProject]

def validator(protocol_policy_id: PolicyId, datum_project: DatumProject, redeemer: RedeemerProject, context: ScriptContext) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)
    
    if isinstance(redeemer, UpdateProject):
        project_input = resolve_linear_input(tx_info, redeemer.project_input_index, purpose)
        project_output = resolve_linear_output(project_input, tx_info, redeemer.project_output_index)

        project_token = extract_token_from_input(project_input)
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(project_token.policy_id, user_input), "User does not have required token"

        validate_nft_continues(project_output, project_token)

        ##################################################################################################
        # Validatios to make when updating a project datum
        # Project datum is normally updated when 
        ##################################################################################################
        # Parameters that always should remain the same:
        ##################################################################################################
        # 1. Ensure that the project owner remains the same
        # 2. Ensure that the project ID remains the same
        # 3. Ensure that the protocol policy ID remains the same
        # 4. Ensure that the token name remains the same
        # 5. Ensure that the project token policy ID remains the same
        # 6. StakeHolders participation list remains the same
        # 7. Certification date and quantity remain the same
        ##################################################################################################
        # 1. Sum of participation must always be equal to total supply
        # 2. Current supply can only increase, and must always be <= total supply
        # 3. Total supply and current supply must be > 0
        # 4. Project state can only move forward (0->1->2->3)
        # 5. Real certification dates and real quantities can only be added, not removed or modified
        ##################################################################################################
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