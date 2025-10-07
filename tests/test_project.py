"""
Minimal functional test suite for OpShin project validator
Tests updated to match current contract design
"""

from typing import Dict, List, Optional

import pytest
from opshin.ledger.api_v2 import *
from opshin.prelude import *
from opshin.std.builtins import *

from terrasacha_contracts.util import *
from terrasacha_contracts.validators.project import (
    validate_datum_update,
    validate_stakeholder_authorization,
    validate_immutable_fields_update_token,
    validate_stakeholder_claim,
    validator as project_validator,
)


class MockCommonProject:
    """Common Mock class used in project validator tests"""

    def setup_method(self):
        """Setup method called before each test"""
        self.sample_tx_id = TxId(bytes.fromhex("a" * 64))
        self.sample_policy_id = bytes.fromhex("b" * 56)
        self.project_token_policy_id = bytes.fromhex("d" * 56)

        self.sample_address = Address(
            PubKeyCredential(bytes.fromhex("e" * 56)), NoStakingCredential()
        )
        self.project_script_address = Address(
            ScriptCredential(self.sample_policy_id), NoStakingCredential()
        )

    def create_mock_oref(self, tx_id_bytes: bytes = None, idx: int = 0) -> TxOutRef:
        """Create a mock transaction output reference"""
        if tx_id_bytes is None:
            tx_id = TxId(bytes.fromhex("a" * 64))
        else:
            tx_id = TxId(tx_id_bytes)
        return TxOutRef(tx_id, idx)

    def create_mock_stakeholder_participation(
        self, stakeholder_name: str = "stakeholder1", participation: int = 1000000,
        pkh: bytes = None, claimed: BoolData = None
    ) -> StakeHolderParticipation:
        """Create a mock stakeholder participation"""
        if pkh is None:
            pkh = bytes.fromhex("a" * 56)
        if claimed is None:
            claimed = FalseData()

        return StakeHolderParticipation(
            stakeholder=stakeholder_name.encode(),
            pkh=pkh,
            participation=participation,
            claimed=claimed
        )

    def create_mock_certification(
        self,
        cert_date: int = 1640995200,
        quantity: int = 1000,
        real_cert_date: int = 0,
        real_quantity: int = 0,
    ) -> Certification:
        """Create a mock certification"""
        return Certification(
            certification_date=cert_date,
            quantity=quantity,
            real_certification_date=real_cert_date,
            real_quantity=real_quantity,
        )

    def create_mock_token_project(
        self,
        policy_id: bytes = None,
        token_name: bytes = b"PROJECT_TOKEN",
        total_supply: int = 5000000,
    ) -> TokenProject:
        """Create a mock token project"""
        if policy_id is None:
            policy_id = self.project_token_policy_id

        return TokenProject(
            policy_id=policy_id,
            token_name=token_name,
            total_supply=total_supply,
        )

    def create_mock_datum_project_params(
        self,
        project_id: bytes = None,
        project_metadata: bytes = b"https://example.com/project.json",
        project_state: int = 0,
    ) -> DatumProjectParams:
        """Create mock project parameters"""
        if project_id is None:
            project_id = bytes.fromhex("1234567890abcdef" * 4)

        return DatumProjectParams(
            project_id=project_id,
            project_metadata=project_metadata,
            project_state=project_state,
        )

    def create_mock_datum_project(
        self,
        params: DatumProjectParams = None,
        project_token: TokenProject = None,
        stakeholders: List[StakeHolderParticipation] = None,
        certifications: List[Certification] = None,
    ) -> DatumProject:
        """Create a mock project datum"""
        if params is None:
            params = self.create_mock_datum_project_params()

        if project_token is None:
            if stakeholders is not None:
                total_supply = sum([s.participation for s in stakeholders])
                project_token = self.create_mock_token_project(total_supply=total_supply)
            else:
                project_token = self.create_mock_token_project()

        if stakeholders is None:
            stakeholders = [
                self.create_mock_stakeholder_participation("stakeholder1", project_token.total_supply // 2),
                self.create_mock_stakeholder_participation("stakeholder2", project_token.total_supply // 2),
            ]

        if certifications is None:
            certifications = [self.create_mock_certification(quantity=project_token.total_supply)]

        return DatumProject(
            params=params,
            project_token=project_token,
            stakeholders=stakeholders,
            certifications=certifications,
        )

    def create_mock_tx_out(
        self,
        address: Address,
        value: Dict[bytes, Dict[bytes, int]] = None,
        datum: Optional[OutputDatum] = None,
    ) -> TxOut:
        """Create a mock transaction output"""
        if value is None:
            value = {b"": 2000000}

        return TxOut(
            address=address,
            value=value,
            datum=datum or NoOutputDatum(),
            reference_script=NoScriptHash(),
        )

    def create_mock_tx_in_info(self, oref: TxOutRef, resolved: TxOut) -> TxInInfo:
        """Create a mock transaction input info"""
        return TxInInfo(out_ref=oref, resolved=resolved)

    def create_mock_tx_info(
        self,
        inputs: List[TxInInfo] = None,
        outputs: List[TxOut] = None,
        signatories: List[bytes] = None,
    ) -> TxInfo:
        """Create a mock transaction info"""
        if inputs is None:
            inputs = []
        if outputs is None:
            outputs = []
        if signatories is None:
            signatories = []

        return TxInfo(
            inputs=inputs,
            reference_inputs=[],
            outputs=outputs,
            fee={b"": 200000},
            mint={},
            dcert=[],
            wdrl={},
            valid_range=POSIXTimeRange(
                LowerBoundPOSIXTime(FinitePOSIXTime(1672531200), TrueData()),
                UpperBoundPOSIXTime(FinitePOSIXTime(1672534800), TrueData()),
            ),
            signatories=signatories,
            redeemers={},
            data={},
            id=self.sample_tx_id,
        )

    def create_mock_script_context(
        self, purpose: ScriptPurpose, tx_info: TxInfo = None
    ) -> ScriptContext:
        """Create a mock script context"""
        if tx_info is None:
            tx_info = self.create_mock_tx_info()

        return ScriptContext(tx_info=tx_info, purpose=purpose)


class TestValidateDatumUpdate(MockCommonProject):
    """Tests for validate_datum_update function"""

    def test_validate_datum_update_state_0_success(self):
        """Test datum update succeeds in state 0 with valid changes"""
        old_datum = self.create_mock_datum_project()

        # Modify some fields - allowed in state 0
        new_params = DatumProjectParams(
            project_id=old_datum.params.project_id,
            project_metadata=b"https://example.com/updated.json",
            project_state=0
        )

        new_datum = DatumProject(
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_state_progression_success(self):
        """Test state can progress forward"""
        old_datum = self.create_mock_datum_project()

        new_params = DatumProjectParams(
            project_id=old_datum.params.project_id,
            project_metadata=old_datum.params.project_metadata,
            project_state=1  # Progress to state 1
        )

        new_datum = DatumProject(
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_negative_fee_fails(self):
        """Test datum update fails with negative protocol fee"""
        # Note: protocol_fee is in DatumProtocol, not DatumProject
        # This test is for project datum, so we test negative participation
        old_datum = self.create_mock_datum_project()

        bad_stakeholders = [
            self.create_mock_stakeholder_participation("bad", -1000),  # Negative!
        ]

        new_datum = DatumProject(
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=bad_stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Stakeholder participation must be non-negative"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_participation_exceeds_supply_fails(self):
        """Test datum update fails when stakeholder participation exceeds total supply"""
        old_datum = self.create_mock_datum_project()

        # Create stakeholders with total > supply
        bad_stakeholders = [
            self.create_mock_stakeholder_participation("s1", old_datum.project_token.total_supply),
            self.create_mock_stakeholder_participation("s2", 1000),  # Exceeds!
        ]

        new_datum = DatumProject(
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=bad_stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Sum of stakeholder participation cannot exceed total supply"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_certification_quantity_mismatch_fails(self):
        """Test datum update fails when certification quantities don't match total supply"""
        old_datum = self.create_mock_datum_project()

        # Certification quantity doesn't match total supply
        bad_certs = [
            self.create_mock_certification(quantity=old_datum.project_token.total_supply - 1000)
        ]

        new_datum = DatumProject(
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=bad_certs,
        )

        with pytest.raises(AssertionError, match="Sum of certification quantities must equal total supply"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_locked_state_immutable_fields(self):
        """Test that fields become immutable after state >= 1"""
        # Create datum in state 1
        params_state_1 = self.create_mock_datum_project_params(project_state=1)
        old_datum = self.create_mock_datum_project(params=params_state_1)

        # Try to change project_id (should fail)
        new_params = DatumProjectParams(
            project_id=bytes.fromhex("ffffffff" * 8),  # Different ID
            project_metadata=old_datum.params.project_metadata,
            project_state=1
        )

        new_datum = DatumProject(
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Project ID cannot be changed after project lock"):
            validate_datum_update(old_datum, new_datum)


class TestProjectValidator(MockCommonProject):
    """Tests for main project validator"""

    def test_validator_update_project_success(self):
        """Test successful UpdateProject with valid user token"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        project_token_name = unique_token_name(oref_project, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref_project, PREFIX_USER_NFT)

        old_datum = self.create_mock_datum_project()

        # Create new datum with state progression
        new_params = DatumProjectParams(
            project_id=old_datum.params.project_id,
            project_metadata=old_datum.params.project_metadata,
            project_state=1
        )
        new_datum = DatumProject(
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create inputs/outputs
        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, policy_id: {project_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, policy_id: {project_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, policy_id: {user_token_name: 1}}
        )

        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[user_input, project_input],
            outputs=[project_output_utxo],
        )

        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProject(
            project_input_index=1,
            user_input_index=0,
            project_output_index=0
        )

        # Should not raise
        project_validator(policy_id, old_datum, redeemer, context)

    def test_validator_update_project_missing_user_token_fails(self):
        """Test UpdateProject fails without user token"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        project_token_name = unique_token_name(oref_project, PREFIX_REFERENCE_NFT)

        old_datum = self.create_mock_datum_project()
        new_datum = self.create_mock_datum_project()

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, policy_id: {project_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, policy_id: {project_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        # User has NO token
        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000}
        )

        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[user_input, project_input],
            outputs=[project_output_utxo],
        )

        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProject(
            project_input_index=1,
            user_input_index=0,
            project_output_index=0
        )

        with pytest.raises(AssertionError, match="User does not have required token"):
            project_validator(policy_id, old_datum, redeemer, context)

    def test_validator_end_project_success(self):
        """Test EndProject with valid user token"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        project_token_name = unique_token_name(oref_project, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref_project, PREFIX_USER_NFT)

        project_datum = self.create_mock_datum_project()

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, policy_id: {project_token_name: 1}},
            datum=SomeOutputDatum(project_datum)
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, policy_id: {user_token_name: 1}}
        )

        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[project_input, user_input],
        )

        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = EndProject(
            project_input_index=0,
            user_input_index=1
        )

        # Should not raise
        project_validator(policy_id, project_datum, redeemer, context)


class TestUpdateTokenValidation(MockCommonProject):
    """Tests for UpdateToken redeemer validation"""

    def test_validate_stakeholder_authorization_success(self):
        """Test successful stakeholder authorization"""
        stakeholder_pkh = bytes.fromhex("abc123" + "0" * 50)

        stakeholders = [
            self.create_mock_stakeholder_participation("landowner", 1000000, stakeholder_pkh),
        ]

        datum = self.create_mock_datum_project(stakeholders=stakeholders)
        tx_info = self.create_mock_tx_info(signatories=[stakeholder_pkh])

        # Should return the authorized PKH
        result = validate_stakeholder_authorization(datum, tx_info)
        assert result == stakeholder_pkh

    def test_validate_stakeholder_authorization_no_signature_fails(self):
        """Test stakeholder authorization fails without signature"""
        stakeholder_pkh = bytes.fromhex("abc123" + "0" * 50)
        other_pkh = bytes.fromhex("def456" + "0" * 50)

        stakeholders = [
            self.create_mock_stakeholder_participation("landowner", 1000000, stakeholder_pkh),
        ]

        datum = self.create_mock_datum_project(stakeholders=stakeholders)
        tx_info = self.create_mock_tx_info(signatories=[other_pkh])  # Wrong signer

        with pytest.raises(AssertionError, match="Transaction must be signed by at least one stakeholder"):
            validate_stakeholder_authorization(datum, tx_info)

    def test_validate_immutable_fields_update_token_success(self):
        """Test immutable fields validation passes when nothing changes"""
        old_datum = self.create_mock_datum_project()

        # Clone datum with same fields
        new_datum = DatumProject(
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise
        validate_immutable_fields_update_token(old_datum, new_datum)

    def test_validate_stakeholder_claim_success(self):
        """Test stakeholder claim validation succeeds"""
        stakeholder_pkh = bytes.fromhex("abc123" + "0" * 50)

        old_stakeholders = [
            self.create_mock_stakeholder_participation(
                "landowner", 1000000, stakeholder_pkh, claimed=FalseData()
            ),
        ]

        old_datum = self.create_mock_datum_project(stakeholders=old_stakeholders)

        # Mark as claimed
        new_stakeholders = [
            self.create_mock_stakeholder_participation(
                "landowner", 1000000, stakeholder_pkh, claimed=TrueData()
            ),
        ]

        new_datum = DatumProject(
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=new_stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise
        validate_stakeholder_claim(old_datum, new_datum, stakeholder_pkh)

    def test_validate_stakeholder_claim_already_claimed_fails(self):
        """Test stakeholder claim fails if already claimed"""
        stakeholder_pkh = bytes.fromhex("abc123" + "0" * 50)

        # Already claimed
        old_stakeholders = [
            self.create_mock_stakeholder_participation(
                "landowner", 1000000, stakeholder_pkh, claimed=TrueData()
            ),
        ]

        old_datum = self.create_mock_datum_project(stakeholders=old_stakeholders)

        new_stakeholders = [
            self.create_mock_stakeholder_participation(
                "landowner", 1000000, stakeholder_pkh, claimed=TrueData()
            ),
        ]

        new_datum = DatumProject(
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=new_stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Authorized stakeholder has already claimed their tokens"):
            validate_stakeholder_claim(old_datum, new_datum, stakeholder_pkh)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
