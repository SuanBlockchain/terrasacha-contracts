"""
Mock objects and comprehensive test cases for the OpShin project validator
"""

from typing import Dict, List, Optional

import pytest
from opshin.ledger.api_v2 import *
from opshin.prelude import *
from opshin.std.builtins import *

from src.terrasacha_contracts.util import *
from src.terrasacha_contracts.validators.project import (
    Certification,
    DatumProject,
    DatumProjectParams,
    EndProject,
    StakeHolderParticipation,
    TokenProject,
    UpdateProject,
    validate_datum_update,
    validate_signatories,
)
from src.terrasacha_contracts.validators.project import validator as project_validator


class MockCommonProject:
    """Common Mock class used in project validator tests"""

    def setup_method(self):
        """Setup method called before each test"""
        self.sample_tx_id = TxId(bytes.fromhex("a" * 64))
        self.sample_policy_id = bytes.fromhex("b" * 56)
        self.protocol_policy_id = bytes.fromhex("c" * 56)
        self.project_token_policy_id = bytes.fromhex("d" * 56)

        self.sample_address = Address(
            PubKeyCredential(bytes.fromhex("e" * 56)), NoStakingCredential()
        )
        self.project_script_address = Address(
            ScriptCredential(self.sample_policy_id), NoStakingCredential()
        )
        self.protocol_script_address = Address(
            ScriptCredential(self.protocol_policy_id), NoStakingCredential()
        )

    def create_mock_oref(self, tx_id_bytes: bytes = None, idx: int = 0) -> TxOutRef:
        """Create a mock transaction output reference"""
        if tx_id_bytes is None:
            tx_id = TxId(bytes.fromhex("a" * 64))
        else:
            tx_id = TxId(tx_id_bytes)
        return TxOutRef(tx_id, idx)

    def create_mock_stakeholder_participation(
        self, stakeholder_name: str = "stakeholder1", participation: int = 1000000
    ) -> StakeHolderParticipation:
        """Create a mock stakeholder participation"""
        return StakeHolderParticipation(
            stakeholder=stakeholder_name.encode(), participation=participation
        )

    def create_mock_certification(
        self,
        cert_date: int = 1640995200,  # 2022-01-01
        quantity: int = 1000,
        real_cert_date: int = None,
        real_quantity: int = None,
    ) -> Certification:
        """Create a mock certification"""
        if real_cert_date is None:
            real_cert_date = cert_date
        if real_quantity is None:
            real_quantity = quantity

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
        current_supply: int = 2500000,
    ) -> TokenProject:
        """Create a mock token project"""
        if policy_id is None:
            policy_id = self.project_token_policy_id

        return TokenProject(
            policy_id=policy_id,
            token_name=token_name,
            total_supply=total_supply,
            current_supply=current_supply,
        )

    def create_mock_datum_project_params(
        self,
        owner: bytes = None,
        project_id: bytes = None,
        project_metadata: bytes = b"https://example.com/project.json",
        project_state: int = 1,
    ) -> DatumProjectParams:
        """Create mock project parameters"""
        if owner is None:
            owner = bytes.fromhex("f" * 56)
        if project_id is None:
            project_id = bytes.fromhex("1234567890abcdef" * 4)  # 32 bytes

        return DatumProjectParams(
            owner=owner,
            project_id=project_id,
            project_metadata=project_metadata,
            project_state=project_state,
        )

    def create_mock_datum_project(
        self,
        valid: bool = True,
        protocol_policy_id: bytes = None,
        params: DatumProjectParams = None,
        project_token: TokenProject = None,
        stakeholders: List[StakeHolderParticipation] = None,
        certifications: List[Certification] = None,
    ) -> DatumProject:
        """Create a mock project datum"""
        if protocol_policy_id is None:
            protocol_policy_id = self.protocol_policy_id

        if params is None:
            params = self.create_mock_datum_project_params()

        if project_token is None:
            if stakeholders is not None:
                # Calculate total supply from stakeholders
                total_supply = sum([s.participation for s in stakeholders])
                project_token = self.create_mock_token_project(
                    total_supply=total_supply, current_supply=total_supply // 2
                )
            else:
                project_token = self.create_mock_token_project()

        if stakeholders is None:
            if valid:
                # Create stakeholders that match token total supply
                stakeholders = [
                    self.create_mock_stakeholder_participation(
                        "stakeholder1", project_token.total_supply // 2
                    ),
                    self.create_mock_stakeholder_participation(
                        "stakeholder2", project_token.total_supply // 2
                    ),
                ]
            else:
                # Create mismatched stakeholders for invalid case
                stakeholders = [
                    self.create_mock_stakeholder_participation(
                        "stakeholder1", project_token.total_supply + 1000000  # Mismatch
                    )
                ]

        if certifications is None:
            certifications = [self.create_mock_certification()]

        return DatumProject(
            protocol_policy_id=protocol_policy_id,
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
            value = {b"": 2000000}  # 2 ADA

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
        mint: Dict[bytes, Dict[bytes, int]] = None,
        purpose_oref: TxOutRef = None,
        signatories: List[bytes] = None,
    ) -> TxInfo:
        """Create a mock transaction info"""
        if inputs is None:
            if purpose_oref:
                consumed_output = self.create_mock_tx_out(self.sample_address)
                inputs = [self.create_mock_tx_in_info(purpose_oref, consumed_output)]
            else:
                inputs = []

        if outputs is None:
            outputs = []

        if mint is None:
            mint = {}

        if signatories is None:
            signatories = [bytes.fromhex("f" * 56)]  # Default project owner

        return TxInfo(
            inputs=inputs,
            reference_inputs=[],
            outputs=outputs,
            fee={b"": 200000},  # 0.2 ADA fee
            mint=mint,
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

    def create_mock_protocol_datum(
        self,
        protocol_admin: List[bytes] = None,
        protocol_fee: int = 100000,
        oracle_id: bytes = None,
        projects: List[bytes] = None,
    ):
        """Create a mock protocol datum from the protocol validator"""
        from src.terrasacha_contracts.validators.project import DatumProtocol
        
        if protocol_admin is None:
            protocol_admin = [bytes.fromhex("a" * 56)]
        
        if oracle_id is None:
            oracle_id = bytes.fromhex("b" * 56)
        
        if projects is None:
            projects = []
            
        return DatumProtocol(
            protocol_admin=protocol_admin,
            protocol_fee=protocol_fee,
            oracle_id=oracle_id,
            projects=projects,
        )


class TestProjectValidationFunctions(MockCommonProject):
    """Test standalone project validation functions"""

    def test_validate_datum_update_success_basic(self):
        """Test successful basic datum update validation"""
        old_datum = self.create_mock_datum_project()

        # Create new datum with only metadata change
        new_params = DatumProjectParams(
            owner=old_datum.params.owner,
            project_id=old_datum.params.project_id,
            project_metadata=b"https://updated-metadata.com/project.json",  # Changed
            project_state=old_datum.params.project_state,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_success_state_progression(self):
        """Test successful state progression"""
        old_datum = self.create_mock_datum_project()

        # Progress state from 1 to 2
        new_params = DatumProjectParams(
            owner=old_datum.params.owner,
            project_id=old_datum.params.project_id,
            project_metadata=old_datum.params.project_metadata,
            project_state=2,  # Progressed from 1 to 2
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_success_current_supply_increase(self):
        """Test successful current supply increase"""
        old_datum = self.create_mock_datum_project()

        # Increase current supply
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=old_datum.project_token.token_name,
            total_supply=old_datum.project_token.total_supply,
            current_supply=old_datum.project_token.current_supply + 500000,  # Increased
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_success_add_certification(self):
        """Test successful addition of new certification"""
        old_datum = self.create_mock_datum_project()

        # Add new certification
        new_certifications = old_datum.certifications + [
            self.create_mock_certification(cert_date=1672531200, quantity=500)
        ]

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=new_certifications,
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_success_update_real_certification(self):
        """Test successful update of real certification values"""
        old_datum = self.create_mock_datum_project()

        # Update real certification values (increase)
        updated_cert = Certification(
            certification_date=old_datum.certifications[0].certification_date,
            quantity=old_datum.certifications[0].quantity,
            real_certification_date=old_datum.certifications[0].real_certification_date
            + 86400,  # +1 day
            real_quantity=old_datum.certifications[0].real_quantity + 100,  # +100 quantity
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=[updated_cert],
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    # Immutability Failure Tests

    def test_validate_datum_update_owner_change_fails(self):
        """Test datum update fails when owner changes"""
        old_datum = self.create_mock_datum_project()

        new_params = DatumProjectParams(
            owner=bytes.fromhex(
                "1111111111111111111111111111111111111111111111111111111111"
            ),  # Changed
            project_id=old_datum.params.project_id,
            project_metadata=old_datum.params.project_metadata,
            project_state=old_datum.params.project_state,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Project owner cannot be changed"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_project_id_change_fails(self):
        """Test datum update fails when project ID changes"""
        old_datum = self.create_mock_datum_project()

        new_params = DatumProjectParams(
            owner=old_datum.params.owner,
            project_id=bytes.fromhex("fedcba0987654321" * 4),  # Changed
            project_metadata=old_datum.params.project_metadata,
            project_state=old_datum.params.project_state,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Project ID cannot be changed"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_protocol_policy_id_change_fails(self):
        """Test datum update fails when protocol policy ID changes"""
        old_datum = self.create_mock_datum_project()

        new_datum = DatumProject(
            protocol_policy_id=bytes.fromhex("1" * 56),  # Changed
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Protocol policy ID cannot be changed"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_token_name_change_fails(self):
        """Test datum update fails when token name changes"""
        old_datum = self.create_mock_datum_project()

        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=b"DIFFERENT_TOKEN",  # Changed
            total_supply=old_datum.project_token.total_supply,
            current_supply=old_datum.project_token.current_supply,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Token name cannot be changed"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_token_policy_change_fails(self):
        """Test datum update fails when token policy ID changes"""
        old_datum = self.create_mock_datum_project()

        new_token = TokenProject(
            policy_id=bytes.fromhex("2" * 56),  # Changed
            token_name=old_datum.project_token.token_name,
            total_supply=old_datum.project_token.total_supply,
            current_supply=old_datum.project_token.current_supply,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Project token policy ID cannot be changed"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_stakeholders_length_change_fails(self):
        """Test datum update fails when stakeholders list length changes"""
        old_datum = self.create_mock_datum_project()

        # Add extra stakeholder
        new_stakeholders = old_datum.stakeholders + [
            self.create_mock_stakeholder_participation("new_stakeholder", 1000000)
        ]

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=new_stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Stakeholders list length cannot change"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_stakeholder_identity_change_fails(self):
        """Test datum update fails when stakeholder identity changes"""
        old_datum = self.create_mock_datum_project()

        # Change stakeholder identity
        new_stakeholder = StakeHolderParticipation(
            stakeholder=b"different_stakeholder",  # Changed
            participation=old_datum.stakeholders[0].participation,
        )

        new_stakeholders = [new_stakeholder] + old_datum.stakeholders[1:]

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=new_stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Stakeholder identity cannot change"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_stakeholder_participation_change_fails(self):
        """Test datum update fails when stakeholder participation changes"""
        old_datum = self.create_mock_datum_project()

        # Change stakeholder participation
        new_stakeholder = StakeHolderParticipation(
            stakeholder=old_datum.stakeholders[0].stakeholder,
            participation=old_datum.stakeholders[0].participation + 500000,  # Changed
        )

        new_stakeholders = [new_stakeholder] + old_datum.stakeholders[1:]

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=new_stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Stakeholder participation cannot change"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_certification_removed_fails(self):
        """Test datum update fails when certification is removed"""
        old_datum = self.create_mock_datum_project()

        # Remove certification (empty list)
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=[],  # Removed
        )

        with pytest.raises(AssertionError, match="Certifications can only be added, not removed"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_certification_date_change_fails(self):
        """Test datum update fails when existing certification date changes"""
        old_datum = self.create_mock_datum_project()

        # Change certification date
        modified_cert = Certification(
            certification_date=old_datum.certifications[0].certification_date + 86400,  # Changed
            quantity=old_datum.certifications[0].quantity,
            real_certification_date=old_datum.certifications[0].real_certification_date,
            real_quantity=old_datum.certifications[0].real_quantity,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=[modified_cert],
        )

        with pytest.raises(AssertionError, match="Existing certification date cannot change"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_certification_quantity_change_fails(self):
        """Test datum update fails when existing certification quantity changes"""
        old_datum = self.create_mock_datum_project()

        # Change certification quantity
        modified_cert = Certification(
            certification_date=old_datum.certifications[0].certification_date,
            quantity=old_datum.certifications[0].quantity + 100,  # Changed
            real_certification_date=old_datum.certifications[0].real_certification_date,
            real_quantity=old_datum.certifications[0].real_quantity,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=[modified_cert],
        )

        with pytest.raises(AssertionError, match="Existing certification quantity cannot change"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_real_certification_date_decrease_fails(self):
        """Test datum update fails when real certification date decreases"""
        old_datum = self.create_mock_datum_project()

        # Decrease real certification date
        modified_cert = Certification(
            certification_date=old_datum.certifications[0].certification_date,
            quantity=old_datum.certifications[0].quantity,
            real_certification_date=old_datum.certifications[0].real_certification_date
            - 86400,  # Decreased
            real_quantity=old_datum.certifications[0].real_quantity,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=[modified_cert],
        )

        with pytest.raises(AssertionError, match="Real certification date can only increase"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_real_certification_quantity_decrease_fails(self):
        """Test datum update fails when real certification quantity decreases"""
        old_datum = self.create_mock_datum_project()

        # Decrease real certification quantity
        modified_cert = Certification(
            certification_date=old_datum.certifications[0].certification_date,
            quantity=old_datum.certifications[0].quantity,
            real_certification_date=old_datum.certifications[0].real_certification_date,
            real_quantity=old_datum.certifications[0].real_quantity - 100,  # Decreased
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=[modified_cert],
        )

        with pytest.raises(AssertionError, match="Real certification quantity can only increase"):
            validate_datum_update(old_datum, new_datum)

    # Business Logic Failure Tests

    def test_validate_datum_update_participation_supply_mismatch_fails(self):
        """Test datum update fails when participation sum doesn't equal total supply"""
        # Create datum with mismatched participation
        old_datum = self.create_mock_datum_project(valid=False)

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Sum of participation must equal total supply"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_current_supply_decrease_fails(self):
        """Test datum update fails when current supply decreases"""
        old_datum = self.create_mock_datum_project()

        # Decrease current supply
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=old_datum.project_token.token_name,
            total_supply=old_datum.project_token.total_supply,
            current_supply=old_datum.project_token.current_supply - 500000,  # Decreased
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Current supply can only increase"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_current_supply_exceeds_total_fails(self):
        """Test datum update fails when current supply exceeds total supply"""
        old_datum = self.create_mock_datum_project()

        # Set current supply greater than total
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=old_datum.project_token.token_name,
            total_supply=old_datum.project_token.total_supply,
            current_supply=old_datum.project_token.total_supply + 1000000,  # Exceeds total
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Current supply cannot exceed total supply"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_zero_total_supply_fails(self):
        """Test datum update fails when total supply is zero"""
        # Create project with zero total supply from the start
        stakeholders_zero = [
            self.create_mock_stakeholder_participation("stakeholder1", 0),
            self.create_mock_stakeholder_participation("stakeholder2", 0),
        ]
        token_zero = self.create_mock_token_project(total_supply=0, current_supply=0)

        old_datum = self.create_mock_datum_project(
            stakeholders=stakeholders_zero, project_token=token_zero
        )

        # Create new datum with same zero total supply
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=old_datum.project_token.token_name,
            total_supply=0,  # Still zero
            current_supply=0,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,  # Same stakeholders
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Total supply must be greater than zero"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_zero_current_supply_fails(self):
        """Test datum update fails when current supply is zero"""
        # Create project with zero current supply from the start
        token_zero_current = self.create_mock_token_project(current_supply=0)
        old_datum = self.create_mock_datum_project(project_token=token_zero_current)

        # Keep current supply at zero
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=old_datum.project_token.token_name,
            total_supply=old_datum.project_token.total_supply,
            current_supply=0,  # Still zero
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Current supply must be greater than zero"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_state_regression_fails(self):
        """Test datum update fails when project state goes backward"""
        old_datum = self.create_mock_datum_project()

        # Regress state from 1 to 0
        new_params = DatumProjectParams(
            owner=old_datum.params.owner,
            project_id=old_datum.params.project_id,
            project_metadata=old_datum.params.project_metadata,
            project_state=0,  # Regressed from 1 to 0
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Project state can only move forward"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_invalid_state_fails(self):
        """Test datum update fails with invalid project state"""
        old_datum = self.create_mock_datum_project()

        # Set invalid state (> 3)
        new_params = DatumProjectParams(
            owner=old_datum.params.owner,
            project_id=old_datum.params.project_id,
            project_metadata=old_datum.params.project_metadata,
            project_state=4,  # Invalid state
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(
            AssertionError, match="Invalid project state \\(must be 0, 1, 2, or 3\\)"
        ):
            validate_datum_update(old_datum, new_datum)

    # Signatory Validation Tests

    def test_validate_signatories_success(self):
        """Test successful signature validation"""
        project_owner = bytes.fromhex("abc123" + "0" * 50)
        datum = self.create_mock_datum_project()

        # Update owner to specific value
        datum.params.owner = project_owner

        tx_info = self.create_mock_tx_info(signatories=[project_owner])

        # Should not raise any exception
        validate_signatories(datum, tx_info)

    def test_validate_signatories_multiple_signatures_success(self):
        """Test signature validation succeeds with multiple signatories including owner"""
        project_owner = bytes.fromhex("abc123" + "0" * 50)
        other_signer = bytes.fromhex("def456" + "0" * 50)
        datum = self.create_mock_datum_project()

        # Update owner to specific value
        datum.params.owner = project_owner

        tx_info = self.create_mock_tx_info(signatories=[other_signer, project_owner])

        # Should not raise any exception
        validate_signatories(datum, tx_info)

    def test_validate_signatories_missing_owner_fails(self):
        """Test signature validation fails when project owner hasn't signed"""
        project_owner = bytes.fromhex("abc123" + "0" * 50)
        wrong_signer = bytes.fromhex("def456" + "0" * 50)
        datum = self.create_mock_datum_project()

        # Update owner to specific value
        datum.params.owner = project_owner

        tx_info = self.create_mock_tx_info(signatories=[wrong_signer])

        with pytest.raises(
            AssertionError, match="EndProject requires signature from project owner"
        ):
            validate_signatories(datum, tx_info)

    def test_validate_signatories_empty_signatures_fails(self):
        """Test signature validation fails with empty signature list"""
        project_owner = bytes.fromhex("abc123" + "0" * 50)
        datum = self.create_mock_datum_project()

        # Update owner to specific value
        datum.params.owner = project_owner

        tx_info = self.create_mock_tx_info(signatories=[])

        with pytest.raises(
            AssertionError, match="EndProject requires signature from project owner"
        ):
            validate_signatories(datum, tx_info)


class TestProjectValidator(MockCommonProject):
    """Test full project validator integration"""

    def test_validator_protocol_policy_id_mismatch_fails(self):
        """Test validator fails when protocol policy ID parameter doesn't match datum"""
        datum = self.create_mock_datum_project()
        wrong_protocol_policy = bytes.fromhex("9" * 56)  # Different from datum

        redeemer = UpdateProject(
            protocol_input_index=0,
            project_input_index=0,
            user_input_index=1,
            project_output_index=0,
        )

        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(Spending(self.create_mock_oref()), tx_info)

        with pytest.raises(
            AssertionError, match="Project datum protocol policy ID must match validator parameter"
        ):
            project_validator(wrong_protocol_policy, datum, redeemer, context)

    def test_validator_update_project_success(self):
        """Test successful UpdateProject validation"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        # Create old datum
        old_datum = self.create_mock_datum_project()

        # Create new datum (only metadata changed)
        new_params = DatumProjectParams(
            owner=old_datum.params.owner,
            project_id=old_datum.params.project_id,
            project_metadata=b"https://updated.com/project.json",  # Changed
            project_state=old_datum.params.project_state,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create protocol datum WITH the project ID
        protocol_datum = self.create_mock_protocol_datum(
            projects=[old_datum.params.project_id]  # Include the project ID
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.protocol_script_address,
            value={b"": 5000000, self.protocol_policy_id: {b"PROTO_NFT": 1}},
            datum=SomeOutputDatum(protocol_datum),
        )

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {user_token_name: 1},  # Project token
                self.protocol_policy_id: {b"PROTO_USER": 1},  # Protocol token
            },
        )

        # Create transaction inputs
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        # Create transaction info
        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input, project_input, user_input],  # protocol at 0, project at 1, user at 2
            outputs=[project_output_utxo],
        )

        # Create script context
        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Create redeemer
        redeemer = UpdateProject(
            protocol_input_index=0,
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        # Should not raise any exception
        project_validator(self.protocol_policy_id, old_datum, redeemer, context)

    def test_validator_update_project_missing_user_token_fails(self):
        """Test UpdateProject fails when user doesn't have required project token"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"

        old_datum = self.create_mock_datum_project()
        new_datum = old_datum  # Same datum for simplicity

        # Create protocol datum with the project ID
        protocol_datum = self.create_mock_protocol_datum(
            projects=[old_datum.params.project_id]
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.protocol_script_address,
            value={b"": 5000000, self.protocol_policy_id: {b"PROTO_NFT": 1}},
            datum=SomeOutputDatum(protocol_datum),
        )

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        # User has NO project tokens
        user_input_utxo = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000}  # Only ADA
        )

        # Create transaction
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input, project_input, user_input], outputs=[project_output_utxo]
        )

        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProject(
            protocol_input_index=0,
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        with pytest.raises(AssertionError, match="User does not have required token"):
            project_validator(self.protocol_policy_id, old_datum, redeemer, context)

    def test_validator_update_project_missing_protocol_token_fails(self):
        """Test UpdateProject fails when user doesn't have protocol token"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        old_datum = self.create_mock_datum_project()
        new_datum = old_datum

        # Create protocol datum with the project ID
        protocol_datum = self.create_mock_protocol_datum(
            projects=[old_datum.params.project_id]
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.protocol_script_address,
            value={b"": 5000000, self.protocol_policy_id: {b"PROTO_NFT": 1}},
            datum=SomeOutputDatum(protocol_datum),
        )

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        # User has project token but NO protocol token
        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {user_token_name: 1},  # Project token only
                # Missing protocol token
            },
        )

        # Create transaction
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input, project_input, user_input], outputs=[project_output_utxo]
        )

        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProject(
            protocol_input_index=0,
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        # Since protocol token validation is disabled, this should now pass
        # No exception expected
        project_validator(self.protocol_policy_id, old_datum, redeemer, context)

    def test_validator_update_project_invalid_datum_update_fails(self):
        """Test UpdateProject fails with invalid datum update (owner change)"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        old_datum = self.create_mock_datum_project()

        # Create invalid new datum (owner change)
        new_params = DatumProjectParams(
            owner=bytes.fromhex(
                "1111111111111111111111111111111111111111111111111111111111"
            ),  # Changed owner
            project_id=old_datum.params.project_id,
            project_metadata=old_datum.params.project_metadata,
            project_state=old_datum.params.project_state,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create protocol datum with the project ID
        protocol_datum = self.create_mock_protocol_datum(
            projects=[old_datum.params.project_id]
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.protocol_script_address,
            value={b"": 5000000, self.protocol_policy_id: {b"PROTO_NFT": 1}},
            datum=SomeOutputDatum(protocol_datum),
        )

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {user_token_name: 1},
                self.protocol_policy_id: {b"PROTO_USER": 1},
            },
        )

        # Create transaction
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input, project_input, user_input], outputs=[project_output_utxo]
        )

        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProject(
            protocol_input_index=0,
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        with pytest.raises(AssertionError, match="Project owner cannot be changed"):
            project_validator(self.protocol_policy_id, old_datum, redeemer, context)

    def test_validator_end_project_success(self):
        """Test successful EndProject validation"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create project datum with owner
        project_owner = bytes.fromhex("abc123" + "0" * 50)
        project_datum = self.create_mock_datum_project()
        project_datum.params.owner = project_owner

        # Create project input with datum
        project_output = self.create_mock_tx_out(
            self.project_script_address, datum=SomeOutputDatum(project_datum)
        )
        project_input = self.create_mock_tx_in_info(oref_project, project_output)

        redeemer = EndProject(project_input_index=0)

        # Create tx_info with owner signature
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=[project_input], signatories=[project_owner])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should not raise any exception
        project_validator(self.protocol_policy_id, project_datum, redeemer, context)

    def test_validator_end_project_missing_signature_fails(self):
        """Test EndProject fails when project owner hasn't signed"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create project datum with owner
        project_owner = bytes.fromhex("abc123" + "0" * 50)
        wrong_signer = bytes.fromhex("def456" + "0" * 50)
        project_datum = self.create_mock_datum_project()
        project_datum.params.owner = project_owner

        # Create project input with datum
        project_output = self.create_mock_tx_out(
            self.project_script_address, datum=SomeOutputDatum(project_datum)
        )
        project_input = self.create_mock_tx_in_info(oref_project, project_output)

        redeemer = EndProject(project_input_index=0)

        # Create tx_info with wrong signature
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=[project_input], signatories=[wrong_signer])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        with pytest.raises(
            AssertionError, match="EndProject requires signature from project owner"
        ):
            project_validator(self.protocol_policy_id, project_datum, redeemer, context)

    def test_validator_update_project_not_listed_in_protocol_fails(self):
        """Test UpdateProject fails when project ID is not listed in protocol datum"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        old_datum = self.create_mock_datum_project()
        new_datum = old_datum  # Same datum for simplicity

        # Create protocol datum WITHOUT the project ID
        different_project_id = bytes.fromhex("abcdef123456789a" * 4)  # 64 hex chars = 32 bytes
        protocol_datum = self.create_mock_protocol_datum(
            projects=[different_project_id]  # Different project ID
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.protocol_script_address,
            value={b"": 5000000, self.protocol_policy_id: {b"PROTO_NFT": 1}},
            datum=SomeOutputDatum(protocol_datum),
        )

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {user_token_name: 1},
                self.protocol_policy_id: {b"USER_NFT": 1},
            },
        )

        # Create transaction inputs
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        # Create transaction info
        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input, project_input, user_input],  # protocol at 0, project at 1, user at 2
            outputs=[project_output_utxo],
        )

        # Create script context
        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Create redeemer
        redeemer = UpdateProject(
            protocol_input_index=0,
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        with pytest.raises(AssertionError, match="Project must be listed in protocol datum"):
            project_validator(self.protocol_policy_id, old_datum, redeemer, context)

    def test_validator_update_project_listed_in_protocol_succeeds(self):
        """Test UpdateProject succeeds when project ID is properly listed in protocol datum"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        old_datum = self.create_mock_datum_project()

        # Create new datum with metadata change
        new_params = DatumProjectParams(
            owner=old_datum.params.owner,
            project_id=old_datum.params.project_id,
            project_metadata=b"https://updated-metadata.com/project.json",  # Changed
            project_state=old_datum.params.project_state,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create protocol datum WITH the project ID
        protocol_datum = self.create_mock_protocol_datum(
            projects=[old_datum.params.project_id]  # Include the project ID
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.protocol_script_address,
            value={b"": 5000000, self.protocol_policy_id: {b"PROTO_NFT": 1}},
            datum=SomeOutputDatum(protocol_datum),
        )

        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {user_token_name: 1},
                self.protocol_policy_id: {b"USER_NFT": 1},
            },
        )

        # Create transaction inputs
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        # Create transaction info
        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input, project_input, user_input],  # protocol at 0, project at 1, user at 2
            outputs=[project_output_utxo],
        )

        # Create script context
        spending_purpose = Spending(oref_project)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Create redeemer
        redeemer = UpdateProject(
            protocol_input_index=0,
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        # Should not raise any exception
        project_validator(self.protocol_policy_id, old_datum, redeemer, context)

    def test_validator_invalid_redeemer_type(self):
        """Test validator fails with invalid redeemer type"""
        project_datum = self.create_mock_datum_project()
        invalid_redeemer = PlutusData()  # Invalid redeemer type

        spending_purpose = Spending(self.create_mock_oref())
        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(spending_purpose, tx_info)

        with pytest.raises(AssertionError, match="Invalid redeemer type"):
            project_validator(self.protocol_policy_id, project_datum, invalid_redeemer, context)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
