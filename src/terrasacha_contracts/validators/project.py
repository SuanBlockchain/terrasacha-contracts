from opshin.prelude import *

from terrasacha_contracts.util import *

@dataclass()
class DatumProjectParams(PlutusData):
    CONSTR_ID = 1
    owner: bytes  # Project owner public key hash
    project_id: bytes  # Project Identifier
    project_metadata: bytes  # Metadata URI or hash
    project_state: int  # 0=initialized, 1=distributed, 2=certified 3=closed


@dataclass()
class TokenProject(PlutusData):
    CONSTR_ID = 2
    policy_id: bytes  # Minting policy ID for the project tokens
    token_name: bytes  # Token name for the project tokens
    total_supply: int  # Total supply of tokens for the project (Grey tokens representing carbon credits promises)
    current_supply: int  # Current supply of tokens minted (Grey tokens)


@dataclass()
class StakeHolderParticipation(PlutusData):
    CONSTR_ID = 3
    stakeholder: bytes  # Stakeholder public name
    participation: int  # Participation amount in lovelace


@dataclass()
class Certification(PlutusData):
    CONSTR_ID = 4
    certification_date: int  # Certification date as POSIX timestamp
    quantity: int  # Quantity of carbon credits certified
    real_certification_date: int  # Real certification date as POSIX timestamp (after verification)
    real_quantity: int  # Real quantity of carbon credits certified (after verification)


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
    # protocol_input_index: int
    project_input_index: int
    user_input_index: int
    project_output_index: int


@dataclass()
class EndProject(PlutusData):
    CONSTR_ID = 2
    project_input_index: int

RedeemerProject = Union[UpdateProject, EndProject]

def validate_datum_update(old_datum: DatumProject, new_datum: DatumProject) -> None:
    """
    Validate the update of a project datum.
    Enforces immutability rules and business logic constraints.
    """
    ##################################################################################################
    # Parameters that always should remain the same (immutable):
    ##################################################################################################

    # 1. Ensure that the project owner remains the same
    assert old_datum.params.owner == new_datum.params.owner, "Project owner cannot be changed"

    # 2. Ensure that the project ID remains the same
    assert (
        old_datum.params.project_id == new_datum.params.project_id
    ), "Project ID cannot be changed"

    # 3. Ensure that the protocol policy ID remains the same
    assert (
        old_datum.protocol_policy_id == new_datum.protocol_policy_id
    ), "Protocol policy ID cannot be changed"

    # 4. Ensure that the token name remains the same
    assert (
        old_datum.project_token.token_name == new_datum.project_token.token_name
    ), "Token name cannot be changed"

    # 5. Ensure that the project token policy ID remains the same
    assert (
        old_datum.project_token.policy_id == new_datum.project_token.policy_id
    ), "Project token policy ID cannot be changed"

    # 6. StakeHolders participation list remains the same
    assert len(old_datum.stakeholders) == len(
        new_datum.stakeholders
    ), "Stakeholders list length cannot change"
    for i in range(len(old_datum.stakeholders)):
        old_stakeholder = old_datum.stakeholders[i]
        new_stakeholder = new_datum.stakeholders[i]
        assert (
            old_stakeholder.stakeholder == new_stakeholder.stakeholder
        ), "Stakeholder identity cannot change"
        assert (
            old_stakeholder.participation == new_stakeholder.participation
        ), "Stakeholder participation cannot change"

    # 7. Existing certification dates and quantities remain the same
    assert len(new_datum.certifications) >= len(
        old_datum.certifications
    ), "Certifications can only be added, not removed"
    for i in range(len(old_datum.certifications)):
        old_cert = old_datum.certifications[i]
        new_cert = new_datum.certifications[i]
        assert (
            old_cert.certification_date == new_cert.certification_date
        ), "Existing certification date cannot change"
        assert (
            old_cert.quantity == new_cert.quantity
        ), "Existing certification quantity cannot change"
        # Real certification dates and quantities can only be added/updated, not removed
        assert (
            new_cert.real_certification_date >= old_cert.real_certification_date
        ), "Real certification date can only increase"
        assert (
            new_cert.real_quantity >= old_cert.real_quantity
        ), "Real certification quantity can only increase"

    ##################################################################################################
    # Business Logic Validations:
    ##################################################################################################

    # 1. Sum of participation must always be equal to total supply
    total_participation = sum([stakeholder.participation for stakeholder in new_datum.stakeholders])
    assert (
        total_participation == new_datum.project_token.total_supply
    ), "Sum of participation must equal total supply"

    # 2. Current supply can only increase, and must always be <= total supply
    assert (
        new_datum.project_token.current_supply >= old_datum.project_token.current_supply
    ), "Current supply can only increase"
    assert (
        new_datum.project_token.current_supply <= new_datum.project_token.total_supply
    ), "Current supply cannot exceed total supply"

    # 3. Total supply and current supply must be > 0
    assert new_datum.project_token.total_supply > 0, "Total supply must be greater than zero"
    assert new_datum.project_token.current_supply >= 0, "Current supply must be greater than zero"

    # 4. Project state can only move forward (0->1->2->3)
    assert (
        new_datum.params.project_state >= old_datum.params.project_state
    ), "Project state can only move forward"
    assert new_datum.params.project_state <= 3, "Invalid project state (must be 0, 1, 2, or 3)"

def validate_signatories(input_datum: DatumProject, tx_info: TxInfo) -> None:
    """
    Validate that the project owner has signed the transaction.
    Required for EndProject operations.
    """
    signatories = tx_info.signatories
    project_owner = input_datum.params.owner

    assert project_owner in signatories, "EndProject requires signature from project owner"

def validator(
    protocol_policy_id: PolicyId,
    datum_project: DatumProject,
    redeemer: RedeemerProject,
    context: ScriptContext,
) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)

    # Validate that the project datum's protocol policy ID matches the validator parameter
    assert (
        datum_project.protocol_policy_id == protocol_policy_id
    ), "Project datum protocol policy ID must match validator parameter"

    if isinstance(redeemer, UpdateProject):
        project_input = resolve_linear_input(tx_info, redeemer.project_input_index, purpose)
        project_output = resolve_linear_output(
            project_input, tx_info, redeemer.project_output_index
        )

        project_token = extract_token_from_input(project_input)
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(
            project_token.policy_id, user_input
        ), "User does not have required token"

        validate_nft_continues(project_output, project_token)

        protocol_reference_input = tx_info.reference_inputs[0].resolved
        protocol_datum = protocol_reference_input.datum
        assert isinstance(protocol_datum, SomeOutputDatum)
        protocol_datum_value: DatumProtocol = protocol_datum.datum
        assert any([project == datum_project.params.project_id for project in protocol_datum_value.projects]), "Project must be listed in protocol datum"

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
    else:
        assert False, "Invalid redeemer type"
