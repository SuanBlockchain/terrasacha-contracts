from opshin.prelude import *

from terrasacha_contracts.util import *

def validate_stakeholder_authorization(datum: DatumProject, tx_info: TxInfo) -> None:
    """
    Validate stakeholder authorization for token operations.
    - If there are non-investor stakeholders, at least one must sign the transaction
    - If there are only investor stakeholders, no signature is required (public access)
    """
    signatories = tx_info.signatories
    
    # Check if there are any non-investor stakeholders
    has_non_investor_stakeholders = False
    found_authorized_signer = False
    
    for stakeholder in datum.stakeholders:
        if stakeholder.stakeholder != b"investor":
            has_non_investor_stakeholders = True
            for signer in signatories:
                if stakeholder.pkh == signer:
                    found_authorized_signer = True
    
    # If there are non-investor stakeholders, at least one must sign
    # If there are only investor stakeholders, no signature required (public access)
    if has_non_investor_stakeholders:
        assert found_authorized_signer, "Transaction must be signed by a non-investor stakeholder"

def validate_update_token_changes(old_datum: DatumProject, new_datum: DatumProject, mint_delta: int, tx_info: TxInfo) -> None:
    """Consolidated validation for UpdateToken operations"""
    signatories = tx_info.signatories
    expected_new_supply = old_datum.project_token.current_supply + mint_delta

    # Supply validation
    assert new_datum.project_token.current_supply == expected_new_supply, "Current supply must be updated by exactly the delta amount"
    assert new_datum.project_token.current_supply <= new_datum.project_token.total_supply, "Current supply cannot exceed total supply"
    assert new_datum.project_token.current_supply >= 0, "Current supply must be non-negative"

    # Immutable fields
    assert old_datum.protocol_policy_id == new_datum.protocol_policy_id, "Protocol policy ID cannot change"
    assert old_datum.params.project_id == new_datum.params.project_id, "Project ID cannot change"
    assert old_datum.params.project_state == new_datum.params.project_state, "Project state cannot change"
    assert old_datum.project_token.policy_id == new_datum.project_token.policy_id, "Token policy ID cannot change"
    assert old_datum.project_token.token_name == new_datum.project_token.token_name, "Token name cannot change"
    assert old_datum.project_token.total_supply == new_datum.project_token.total_supply, "Total supply cannot change"
    assert len(old_datum.stakeholders) == len(new_datum.stakeholders), "Stakeholders count cannot change"
    assert len(old_datum.certifications) == len(new_datum.certifications), "Certifications count cannot change"

    # Stakeholder validation
    for i in range(len(old_datum.stakeholders)):
        old_stakeholder = old_datum.stakeholders[i]
        new_stakeholder = new_datum.stakeholders[i]

        # Immutable stakeholder fields
        assert old_stakeholder.stakeholder == new_stakeholder.stakeholder, "Stakeholder identity cannot change"
        assert old_stakeholder.pkh == new_stakeholder.pkh, "Stakeholder PKH cannot change"
        assert old_stakeholder.participation == new_stakeholder.participation, "Stakeholder participation cannot change"

        # Amount claimed validation
        if mint_delta > 0:
            assert new_stakeholder.amount_claimed >= old_stakeholder.amount_claimed, "Amount claimed can only increase during minting"
        else:
            assert new_stakeholder.amount_claimed <= old_stakeholder.amount_claimed, "Amount claimed can only decrease during burning"

        assert new_stakeholder.amount_claimed >= 0, "Amount claimed must be non-negative"
        assert new_stakeholder.amount_claimed <= new_stakeholder.participation, "Amount claimed cannot exceed participation"

        # Authorization for claim changes
        if new_stakeholder.amount_claimed != old_stakeholder.amount_claimed:
            if old_stakeholder.stakeholder != b"investor":
                assert old_stakeholder.pkh in signatories, "Stakeholder must sign to claim tokens"

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
    assert (
        new_datum.params.project_state >= old_datum.params.project_state
    ), "Project state can only move forward"
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
        # assert (
        #     old_datum.params.project_state == new_datum.params.project_state
        # ), "Project state cannot be changed after project lock (state >= 1)"
        
        # Protocol policy ID must be identical
        assert (
            old_datum.protocol_policy_id == new_datum.protocol_policy_id
        ), "Protocol policy ID cannot be changed after project lock (state >= 1)"
        
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
        assert (
            old_datum.project_token.current_supply == new_datum.project_token.current_supply
        ), "Current supply cannot be changed after project lock (state >= 1)"
        
        # All stakeholder data must be identical
        assert len(old_datum.stakeholders) == len(new_datum.stakeholders), "Stakeholders count cannot change after project lock (state >= 1)"
        for i in range(len(old_datum.stakeholders)):
            old_stakeholder = old_datum.stakeholders[i]
            new_stakeholder = new_datum.stakeholders[i]
            assert old_stakeholder.stakeholder == new_stakeholder.stakeholder, "Stakeholder identity cannot change after project lock (state >= 1)"
            assert old_stakeholder.pkh == new_stakeholder.pkh, "Stakeholder PKH cannot change after project lock (state >= 1)"
            assert old_stakeholder.participation == new_stakeholder.participation, "Stakeholder participation cannot change after project lock (state >= 1)"
            assert old_stakeholder.amount_claimed == new_stakeholder.amount_claimed, "Stakeholder amount claimed cannot change after project lock (state >= 1)"
        
        # All certification data must be identical
        assert len(old_datum.certifications) == len(new_datum.certifications), "Certifications count cannot change after project lock (state >= 1)"
        for i in range(len(old_datum.certifications)):
            old_cert = old_datum.certifications[i]
            new_cert = new_datum.certifications[i]
            assert old_cert.certification_date == new_cert.certification_date, "Certification date cannot change after project lock (state >= 1)"
            assert old_cert.quantity == new_cert.quantity, "Certification quantity cannot change after project lock (state >= 1)"
            assert old_cert.real_certification_date == new_cert.real_certification_date, "Real certification date cannot change after project lock (state >= 1)"
            assert old_cert.real_quantity == new_cert.real_quantity, "Real certification quantity cannot change after project lock (state >= 1)"
            
    else:
        ##################################################################################################
        # project_state == 0: Allow changes with business logic validation only
        ##################################################################################################
        
        # Business validations for token economics
        assert (
            new_datum.project_token.current_supply >= old_datum.project_token.current_supply
        ), "Current supply can only increase"
        assert (
            new_datum.project_token.current_supply <= new_datum.project_token.total_supply
        ), "Current supply cannot exceed total supply"
        assert new_datum.project_token.total_supply > 0, "Total supply must be greater than zero"
        assert new_datum.project_token.current_supply >= 0, "Current supply must be non-negative"
        
        # Stakeholder participation must equal total supply
        total_participation = sum([stakeholder.participation for stakeholder in new_datum.stakeholders])
        assert (
            total_participation == new_datum.project_token.total_supply
        ), "Sum of stakeholder participation must equal total supply"
        
        # Certification business logic (can add new, modify existing when state == 0)
        assert len(new_datum.certifications) >= len(old_datum.certifications), "Certifications can only be added, not removed"
        for i in range(len(old_datum.certifications)):
            old_cert = old_datum.certifications[i]
            new_cert = new_datum.certifications[i]
            # Real certification values can only increase
            assert (
                new_cert.real_certification_date >= old_cert.real_certification_date
            ), "Real certification date can only increase"
            assert (
                new_cert.real_quantity >= old_cert.real_quantity
            ), "Real certification quantity can only increase"


def validator(
    oref: TxOutRef,
    datum_project: DatumProject,
    redeemer: RedeemerProject,
    context: ScriptContext,
) -> None:

    tx_info = context.tx_info
    purpose = get_spending_purpose(context)

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

        project_datum = project_output.datum
        assert isinstance(project_datum, SomeOutputDatum)
        new_datum: DatumProject = project_datum.datum
        validate_datum_update(datum_project, new_datum)

    elif isinstance(redeemer, UpdateToken):
        # UpdateToken can only be used when project is in active state (state > 0)
        # This path is for token operations after project initialization is complete
        assert datum_project.params.project_state > 0, "UpdateToken can only be used when project_state > 0"

        # Resolve input/output UTXOs
        project_input = resolve_linear_input(tx_info, redeemer.project_input_index, purpose)
        project_output = resolve_linear_output(
            project_input, tx_info, redeemer.project_output_index
        )

        project_token = extract_token_from_input(project_input)

        # Validate mint amount matches redeemer delta
        grey_token_policy = datum_project.project_token.policy_id
        grey_token_name = datum_project.project_token.token_name
        mint_value = tx_info.mint
        grey_minted = mint_value.get(grey_token_policy, {b"": 0})
        assert grey_minted.get(grey_token_name, 0) == redeemer.new_supply, "Mint amount must match redeemer delta"

        # Validate NFT continues
        validate_nft_continues(project_output, project_token)

        # Get new datum from output
        project_datum = project_output.datum
        assert isinstance(project_datum, SomeOutputDatum)
        new_datum: DatumProject = project_datum.datum

        # Validate all UpdateToken changes
        validate_stakeholder_authorization(datum_project, tx_info)
        validate_update_token_changes(datum_project, new_datum, redeemer.new_supply, tx_info)
        
    elif isinstance(redeemer, EndProject):
        project_input = resolve_linear_input(tx_info, redeemer.project_input_index, purpose)
        project_token = extract_token_from_input(project_input)
        user_input = tx_info.inputs[redeemer.user_input_index].resolved

        assert check_token_present(
            project_token.policy_id, user_input
        ), "User does not have required token"
    else:
        assert False, "Invalid redeemer type"

