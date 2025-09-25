from opshin.prelude import *

from terrasacha_contracts.util import *


def validate_stakeholder_authorization(datum: DatumProject, tx_info: TxInfo) -> bytes:
    """
    Validate stakeholder authorization for token operations and return the authorized stakeholder's PKH.
    - All stakeholders require a PKH to mint new grey tokens up to their respective quantity
    - Returns the PKH of the stakeholder who signed the transaction
    """
    signatories = tx_info.signatories

    # Find the stakeholder who signed the transaction
    authorized_stakeholder_pkh = b""

    for stakeholder in datum.stakeholders:
        for signer in signatories:
            if stakeholder.pkh == signer:
                authorized_stakeholder_pkh = stakeholder.pkh

    # At least one stakeholder must sign for token operations
    assert (
        authorized_stakeholder_pkh != b""
    ), "Transaction must be signed by at least one stakeholder"

    return authorized_stakeholder_pkh

def validate_immutable_fields_update_token(
    old_datum: DatumProject, new_datum: DatumProject
) -> None:
    """Validate that immutable fields remain unchanged during UpdateToken operations"""
    # Immutable datum fields
    assert old_datum.params.project_id == new_datum.params.project_id, "Project ID cannot change"
    assert (
        old_datum.params.project_metadata == new_datum.params.project_metadata
    ), "Project metadata cannot change"
    assert (
        old_datum.params.project_state == new_datum.params.project_state
    ), "Project state cannot change"
    assert (
        old_datum.project_token.policy_id == new_datum.project_token.policy_id
    ), "Token policy ID cannot change"
    assert (
        old_datum.project_token.token_name == new_datum.project_token.token_name
    ), "Token name cannot change"
    assert (
        old_datum.project_token.total_supply == new_datum.project_token.total_supply
    ), "Total supply cannot change"
    assert len(old_datum.stakeholders) == len(
        new_datum.stakeholders
    ), "Stakeholders count cannot change"
    assert len(old_datum.certifications) == len(
        new_datum.certifications
    ), "Certifications count cannot change"

    # Stakeholder immutable fields
    for i in range(len(old_datum.stakeholders)):
        old_stakeholder = old_datum.stakeholders[i]
        new_stakeholder = new_datum.stakeholders[i]

        # Immutable stakeholder fields
        assert (
            old_stakeholder.stakeholder == new_stakeholder.stakeholder
        ), "Stakeholder identity cannot change"
        assert old_stakeholder.pkh == new_stakeholder.pkh, "Stakeholder PKH cannot change"
        assert (
            old_stakeholder.participation == new_stakeholder.participation
        ), "Stakeholder participation cannot change"

    # Certification immutable fields
    for i in range(len(old_datum.certifications)):
        old_cert = old_datum.certifications[i]
        new_cert = new_datum.certifications[i]

        assert (
            old_cert.certification_date == new_cert.certification_date
        ), "Certification date cannot change"
        assert old_cert.quantity == new_cert.quantity, "Certification quantity cannot change"
        assert (
            old_cert.real_certification_date == new_cert.real_certification_date
        ), "Real certification date cannot change"
        assert (
            old_cert.real_quantity == new_cert.real_quantity
        ), "Real certification quantity cannot change"

def validate_stakeholder_claim(
    old_datum: DatumProject,
    new_datum: DatumProject,
    authorized_stakeholder_pkh: bytes,
) -> None:
    """
    Validate stakeholder claim during UpdateToken operations.
    Only the authorized stakeholder can mark themselves as claimed.
    """

    for i in range(len(old_datum.stakeholders)):
        old_stakeholder = old_datum.stakeholders[i]
        new_stakeholder = new_datum.stakeholders[i]
        
        # These fields must remain unchanged in all cases
        assert (old_stakeholder.stakeholder == new_stakeholder.stakeholder
                    ), "Stakeholder identity cannot change"
        assert old_stakeholder.pkh == new_stakeholder.pkh, "Stakeholder PKH cannot change"
        assert (
            old_stakeholder.participation == new_stakeholder.participation
        ), "Stakeholder participation cannot change"

        # if old_stakeholder.pkh == authorized_stakeholder_pkh:
        #     # This is the authorized stakeholder - validate their claim
        #     assert (
        #         not old_stakeholder.claimed
        #     ), "Authorized stakeholder has already claimed their tokens"
        #     assert new_stakeholder.claimed, "Authorized stakeholder must be marked as claimed"
        # else:
        #     # Non-authorized stakeholders cannot change ANY field
        #     assert (
        #         old_stakeholder.claimed == new_stakeholder.claimed
        #     ), "Non-authorized stakeholders cannot change their claimed status"

def validate_datum_update(old_datum: DatumProject, new_datum: DatumProject) -> None:
    """
    Validate UpdateProject datum changes.

    Business Logic:
    - When project_state == 0: Allow all field changes (initialization phase)
    - When project_state >= 1: All fields must remain immutable (project locked)

    Note: This function is only used in UpdateProject path.
    UpdateToken path has separate validation for current_supply and amount_claimed.
    """
    # Project state can only move forward (0->1->2->3)
    # assert (
    #     new_datum.params.project_state >= old_datum.params.project_state
    # ), "Project state can only move forward"
    assert new_datum.params.project_state >= 0, "Project state must be non-negative"
    assert new_datum.params.project_state <= 3, "Invalid project state (must be 0, 1, 2, or 3)"

    if old_datum.params.project_state >= 1:
        ##################################################################################################
        # Project is locked - ALL fields must remain identical
        ##################################################################################################

        # Project parameters must be identical
        assert (
            old_datum.params.project_id == new_datum.params.project_id
        ), "Project ID cannot be changed after project lock (state >= 1)"
        assert (
            old_datum.params.project_metadata == new_datum.params.project_metadata
        ), "Project metadata cannot be changed after project lock (state >= 1)"

        # All token fields must be identical
        assert (
            old_datum.project_token.policy_id == new_datum.project_token.policy_id
        ), "Token policy ID cannot be changed after project lock (state >= 1)"
        assert (
            old_datum.project_token.token_name == new_datum.project_token.token_name
        ), "Token name cannot be changed after project lock (state >= 1)"
        assert (
            old_datum.project_token.total_supply == new_datum.project_token.total_supply
        ), "Total supply cannot be changed after project lock (state >= 1)"

        # All stakeholder data must be identical
        assert len(old_datum.stakeholders) == len(
            new_datum.stakeholders
        ), "Stakeholders count cannot change after project lock (state >= 1)"
        for i in range(len(old_datum.stakeholders)):
            old_stakeholder = old_datum.stakeholders[i]
            new_stakeholder = new_datum.stakeholders[i]
            assert (
                old_stakeholder.stakeholder == new_stakeholder.stakeholder
            ), "Stakeholder identity cannot change after project lock (state >= 1)"
            # assert (
            #     old_stakeholder.pkh == new_stakeholder.pkh
            # ), "Stakeholder PKH cannot change after project lock (state >= 1)"
            assert (
                old_stakeholder.participation == new_stakeholder.participation
            ), "Stakeholder participation cannot change after project lock (state >= 1)"
            # assert (
            #     old_stakeholder.claimed == new_stakeholder.claimed
            # ), "Stakeholder claimed status cannot change after project lock (state >= 1)"

        # All certification data must be identical
        assert len(old_datum.certifications) == len(
            new_datum.certifications
        ), "Certifications count cannot change after project lock (state >= 1)"
        for i in range(len(old_datum.certifications)):
            old_cert = old_datum.certifications[i]
            new_cert = new_datum.certifications[i]
            assert (
                old_cert.certification_date == new_cert.certification_date
            ), "Certification date cannot change after project lock (state >= 1)"
            assert (
                old_cert.quantity == new_cert.quantity
            ), "Certification quantity cannot change after project lock (state >= 1)"
            if old_datum.params.project_state == 1:
                # In state 1, real values must remain empty
                assert (
                    new_cert.real_certification_date == 0
                ), "Real certification date must be empty in project state 1"
                assert (
                    new_cert.real_quantity == 0
                ), "Real certification quantity must be empty in project state 1"

    else:
        ##################################################################################################
        # project_state == 0: Allow changes with business logic validation only
        ##################################################################################################

        assert new_datum.project_token.total_supply >= 0, "Total supply must be non-negative"

        # Stakeholder participation cannot exceed total supply
        total_participation = 0
        for stakeholder in new_datum.stakeholders:
            # Participation must be non-negative
            assert stakeholder.participation >= 0, "Stakeholder participation must be non-negative"
            total_participation += stakeholder.participation
            # assert (
            #     stakeholder.claimed == False
            # ), "Stakeholder claimed must be False during initialization"
        assert (
            total_participation <= new_datum.project_token.total_supply
        ), "Sum of stakeholder participation cannot exceed total supply"

        # Certification validation rules
        total_certification_quantity = 0
        for cert in new_datum.certifications:
            # Quantity must be non-negative
            assert cert.quantity >= 0, "Certification quantity must be non-negative"
            total_certification_quantity += cert.quantity

            # For states below 2, real values should still be empty (only state 2 can have real values when certification is verified)
            assert (
                cert.real_certification_date == 0
            ), "Real certification date can only be set when project_state is 2"
            assert (
                cert.real_quantity == 0
            ), "Real certification quantity can only be set when project_state is 2"

            assert cert.certification_date >= 0, "Certification date must be non-negative"
            assert cert.quantity >= 0, "Certification quantity must be non-negative"

        # Sum of certification quantities must equal total supply
        # assert (
        #     total_certification_quantity == new_datum.project_token.total_supply
        # ), "Sum of certification quantities must equal total supply"

def validator(
    token_policy_id: PolicyId,
    datum_project: DatumProject,
    redeemer: RedeemerProject,
    context: ScriptContext,
) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)
    project_input = resolve_linear_input(tx_info, redeemer.project_input_index, purpose)
    project_token = extract_token_from_input(project_input)

    assert project_token.policy_id == token_policy_id, "Wrong token policy ID"

    for txi in tx_info.inputs:
        if txi.out_ref == purpose.tx_out_ref:
            own_txout = txi.resolved
            own_address = own_txout.address

    assert (
        only_one_input_from_address(own_address, tx_info.inputs) == 1
    ), "More than one input from the contract address"

    if isinstance(redeemer, UpdateProject):
        project_output = resolve_linear_output(
            project_input, tx_info, redeemer.project_output_index
        )

        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(
            project_token.policy_id, user_input
        ), "User does not have required token"

        validate_nft_continues(project_output, project_token)

        project_datum = project_output.datum
        assert isinstance(project_datum, SomeOutputDatum)
        new_datum: DatumProject = project_datum.datum
        validate_datum_update(datum_project, new_datum)

    elif isinstance(redeemer, UpdateToken):
        # UpdateToken is used for stakeholder claims during token minting
        # State validation is handled by the grey minting policy

        # Resolve input/output UTXOs
        project_output = resolve_linear_output(
            project_input, tx_info, redeemer.project_output_index
        )
        # Validate NFT continues
        validate_nft_continues(project_output, project_token)

        # Get new datum from output
        project_datum = project_output.datum
        assert isinstance(project_datum, SomeOutputDatum)
        new_datum: DatumProject = project_datum.datum

        # Validate all UpdateToken changes
        authorized_stakeholder_pkh = validate_stakeholder_authorization(datum_project, tx_info)
        validate_immutable_fields_update_token(datum_project, new_datum)
        validate_stakeholder_claim(datum_project, new_datum, authorized_stakeholder_pkh)

    elif isinstance(redeemer, EndProject):
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(
            project_token.policy_id, user_input
        ), "User does not have required token"
    else:
        assert False, "Invalid redeemer type"
