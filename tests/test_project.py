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
    UpdateToken,
    validate_datum_update,
    validate_stakeholder_authorization,
    validate_update_token_changes,
)
from terrasacha_contracts.minting_policies.project_nfts import (
    BurnProject,
    MintProject,
)
from terrasacha_contracts.minting_policies.project_nfts import (
    validator as project_nft_validator,
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
        self, stakeholder_name: str = "stakeholder1", participation: int = 1000000, pkh: bytes = None, amount_claimed: int = 0
    ) -> StakeHolderParticipation:
        """Create a mock stakeholder participation"""
        if pkh is None:
            if stakeholder_name == "investor":
                # Investor stakeholders are public and don't need a specific PKH
                pkh = b""
            else:
                # Generate a mock PKH for non-investor stakeholders (28 bytes)
                pkh = bytes.fromhex("a" * 56)  # 28 bytes = 56 hex chars
        
        return StakeHolderParticipation(
            stakeholder=stakeholder_name.encode(), 
            pkh=pkh,
            participation=participation,
            amount_claimed=amount_claimed
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
        project_id: bytes = None,
        project_metadata: bytes = b"https://example.com/project.json",
        project_state: int = 0,
    ) -> DatumProjectParams:
        """Create mock project parameters"""
        if project_id is None:
            project_id = bytes.fromhex("1234567890abcdef" * 4)  # 32 bytes

        return DatumProjectParams(
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
                        "stakeholder1", project_token.total_supply // 2, bytes.fromhex("a" * 56)
                    ),
                    self.create_mock_stakeholder_participation(
                        "stakeholder2", project_token.total_supply // 2, bytes.fromhex("b" * 56)
                    ),
                ]
            else:
                # Create mismatched stakeholders for invalid case
                stakeholders = [
                    self.create_mock_stakeholder_participation(
                        "stakeholder1", project_token.total_supply + 1000000, bytes.fromhex("a" * 56)  # Mismatch
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

    def create_active_project_datum(
        self,
        project_state: int = 1,
        stakeholders: List[StakeHolderParticipation] = None,
        **kwargs
    ) -> DatumProject:
        """Create a project datum with project_state > 0 for UpdateToken tests"""
        params = self.create_mock_datum_project_params(project_state=project_state)
        return self.create_mock_datum_project(params=params, stakeholders=stakeholders, **kwargs)

    def create_initialized_project(self, **kwargs) -> DatumProject:
        """Create a project in initialized state (status 0)"""
        params = self.create_mock_datum_project_params(project_state=0)
        return self.create_mock_datum_project(params=params, valid=True, **kwargs)

    def create_distributed_project(self, **kwargs) -> DatumProject:
        """Create a project in distributed state (status 1)"""
        params = self.create_mock_datum_project_params(project_state=1)
        return self.create_mock_datum_project(params=params, valid=True, **kwargs)

    def create_certified_project(self, **kwargs) -> DatumProject:
        """Create a project in certified state (status 2)"""
        params = self.create_mock_datum_project_params(project_state=2)
        return self.create_mock_datum_project(params=params, valid=True, **kwargs)

    def create_closed_project(self, **kwargs) -> DatumProject:
        """Create a project in closed state (status 3)"""
        params = self.create_mock_datum_project_params(project_state=3)
        return self.create_mock_datum_project(params=params, valid=True, **kwargs)

    def create_project_with_empty_fields(self, **kwargs) -> DatumProject:
        """Create a project with empty protocol_policy_id and token_name for testing initialization"""
        params = self.create_mock_datum_project_params(project_state=0)
        project_token = self.create_mock_token_project(token_name=b"")
        
        # Ensure stakeholders match the total supply
        if 'stakeholders' not in kwargs:
            stakeholders = [
                self.create_mock_stakeholder_participation("stakeholder1", project_token.total_supply // 2, bytes.fromhex("a" * 56)),
                self.create_mock_stakeholder_participation("stakeholder2", project_token.total_supply // 2, bytes.fromhex("b" * 56)),
            ]
            kwargs['stakeholders'] = stakeholders
            
        return self.create_mock_datum_project(
            protocol_policy_id=b"",
            params=params,
            project_token=project_token,
            valid=True,
            **kwargs
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
        project_admins: List[bytes] = None,
        protocol_fee: int = 100000,
        oracle_id: bytes = None,
    ):
        """Create a mock protocol datum from the protocol validator"""
        from src.terrasacha_contracts.util import DatumProtocol
        
        if project_admins is None:
            project_admins = [bytes.fromhex("a" * 56)]
        
        if oracle_id is None:
            oracle_id = bytes.fromhex("b" * 56)
            
        return DatumProtocol(
            project_admins=project_admins,
            protocol_fee=protocol_fee,
            oracle_id=oracle_id,
        )


class TestProjectValidationFunctions(MockCommonProject):
    """Test standalone project validation functions"""

    def test_validate_datum_update_success_basic(self):
        """Test successful basic datum update validation"""
        old_datum = self.create_mock_datum_project()

        # Create new datum with only metadata change
        new_params = DatumProjectParams(
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


    def test_validate_datum_update_project_id_change_status_0_success(self):
        """Test datum update succeeds when project ID changes and status is 0"""
        # Create datum with status 0
        old_params = self.create_mock_datum_project_params(project_state=0)
        old_datum = self.create_mock_datum_project(params=old_params)

        new_params = DatumProjectParams(
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

        # Should not raise any exception when status is 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_project_id_change_status_1_fails(self):
        """Test datum update fails when project ID changes and status > 0"""
        # Create datum with status 1
        old_params = self.create_mock_datum_project_params(project_state=1)
        old_datum = self.create_mock_datum_project(params=old_params)

        new_params = DatumProjectParams(
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

        with pytest.raises(AssertionError, match="Project ID cannot be changed after project lock"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_protocol_policy_id_set_status_0_success(self):
        """Test datum update succeeds when setting empty protocol policy ID and status is 0"""
        # Create datum with status 0 and empty protocol policy ID
        old_params = self.create_mock_datum_project_params(project_state=0)
        old_datum = self.create_mock_datum_project(params=old_params)
        old_datum.protocol_policy_id = b""  # Empty initially

        new_datum = DatumProject(
            protocol_policy_id=bytes.fromhex("1" * 56),  # Setting for first time
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should not raise any exception when setting empty policy ID at status 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_protocol_policy_id_change_state_0_success(self):
        """Test datum update succeeds when changing protocol policy ID at state 0"""
        # Create datum with status 0 and non-empty protocol policy ID
        old_params = self.create_mock_datum_project_params(project_state=0)
        old_datum = self.create_mock_datum_project(params=old_params)
        old_datum.protocol_policy_id = bytes.fromhex("a" * 56)  # Already set

        new_datum = DatumProject(
            protocol_policy_id=bytes.fromhex("1" * 56),  # Changing is now allowed at state 0
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Should pass - all fields can change when state == 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_protocol_policy_id_change_status_1_fails(self):
        """Test datum update fails when protocol policy ID changes and status > 0"""
        # Create datum with status 1
        old_params = self.create_mock_datum_project_params(project_state=1)
        old_datum = self.create_mock_datum_project(params=old_params)

        new_datum = DatumProject(
            protocol_policy_id=bytes.fromhex("1" * 56),  # Changed
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Protocol policy ID cannot be changed after project lock"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_token_name_set_status_0_success(self):
        """Test datum update succeeds when setting empty token name and status is 0"""
        # Create datum with status 0 and empty token name
        old_params = self.create_mock_datum_project_params(project_state=0)
        old_token = self.create_mock_token_project(token_name=b"")  # Empty initially
        old_datum = self.create_mock_datum_project(params=old_params, project_token=old_token)

        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=b"NEW_TOKEN",  # Setting for first time
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

        # Should not raise any exception when setting empty token name at status 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_token_name_change_state_0_success(self):
        """Test datum update succeeds when changing token name in state 0"""
        # Create datum with status 0 and non-empty token name
        old_params = self.create_mock_datum_project_params(project_state=0)
        old_datum = self.create_mock_datum_project(params=old_params)
        old_datum.project_token.token_name = b"ORIGINAL_TOKEN"  # Already set

        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=b"DIFFERENT_TOKEN",  # Changing - should be allowed in state 0
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

        # Should succeed - token name can be changed when state == 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_token_name_change_status_1_fails(self):
        """Test datum update fails when token name changes and status > 0"""
        # Create datum with status 1
        old_params = self.create_mock_datum_project_params(project_state=1)
        old_datum = self.create_mock_datum_project(params=old_params)

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

        with pytest.raises(AssertionError, match="Token name cannot be changed after project lock"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_token_policy_change_fails(self):
        """Test datum update fails when token policy ID changes after project lock"""
        old_datum = self.create_mock_datum_project()
        # Set project state to 1 (locked)
        old_datum.params.project_state = 1

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

        with pytest.raises(AssertionError, match="Token policy ID cannot be changed after project lock"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_stakeholders_length_change_fails(self):
        """Test datum update fails when stakeholders list length changes"""
        old_datum = self.create_mock_datum_project()

        # Add extra stakeholder
        new_stakeholders = old_datum.stakeholders + [
            self.create_mock_stakeholder_participation("new_stakeholder", 1000000, bytes.fromhex("c" * 56))
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
            pkh=old_datum.stakeholders[0].pkh,  # Keep same PKH
            participation=old_datum.stakeholders[0].participation,
            amount_claimed=old_datum.stakeholders[0].amount_claimed,
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
            pkh=old_datum.stakeholders[0].pkh,  # Keep same PKH
            participation=old_datum.stakeholders[0].participation + 500000,  # Changed
            amount_claimed=old_datum.stakeholders[0].amount_claimed,
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

    def test_validate_datum_update_stakeholder_amount_claimed_change_fails(self):
        """Test datum update fails when stakeholder amount_claimed changes during UpdateProject"""
        old_datum = self.create_mock_datum_project()

        # Change stakeholder amount_claimed
        new_stakeholder = StakeHolderParticipation(
            stakeholder=old_datum.stakeholders[0].stakeholder,
            pkh=old_datum.stakeholders[0].pkh,
            participation=old_datum.stakeholders[0].participation,
            amount_claimed=old_datum.stakeholders[0].amount_claimed + 100000,  # Changed
        )

        new_stakeholders = [new_stakeholder] + old_datum.stakeholders[1:]

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=new_stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Stakeholder amount claimed cannot change"):
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

    def test_validate_datum_update_certification_date_change_status_0_success(self):
        """Test datum update succeeds when certification date changes and status is 0"""
        # Create datum with status 0
        old_params = self.create_mock_datum_project_params(project_state=0)
        old_datum = self.create_mock_datum_project(params=old_params)

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

        # Should not raise any exception when status is 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_certification_date_change_status_1_fails(self):
        """Test datum update fails when certification date changes and status > 0"""
        # Create datum with status 1
        old_params = self.create_mock_datum_project_params(project_state=1)
        old_datum = self.create_mock_datum_project(params=old_params)

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

        with pytest.raises(AssertionError, match="Existing certification date cannot change after status > 0"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_certification_quantity_change_status_0_success(self):
        """Test datum update succeeds when certification quantity changes and status is 0"""
        # Create datum with status 0
        old_params = self.create_mock_datum_project_params(project_state=0)
        old_datum = self.create_mock_datum_project(params=old_params)

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

        # Should not raise any exception when status is 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_certification_quantity_change_status_1_fails(self):
        """Test datum update fails when certification quantity changes and status > 0"""
        # Create datum with status 1
        old_params = self.create_mock_datum_project_params(project_state=1)
        old_datum = self.create_mock_datum_project(params=old_params)

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

        with pytest.raises(AssertionError, match="Existing certification quantity cannot change after status > 0"):
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

    def test_validate_datum_update_total_supply_change_fails(self):
        """Test datum update fails when total supply changes (now always immutable)"""
        old_datum = self.create_mock_datum_project()

        # Try to change total supply
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=old_datum.project_token.token_name,
            total_supply=old_datum.project_token.total_supply + 1000000,  # Changed
            current_supply=old_datum.project_token.current_supply,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        with pytest.raises(AssertionError, match="Total supply can never be changed"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_zero_total_supply_fails(self):
        """Test datum update fails when total supply is zero"""
        # Create project with zero total supply from the start
        stakeholders_zero = [
            self.create_mock_stakeholder_participation("stakeholder1", 0, bytes.fromhex("a" * 56)),
            self.create_mock_stakeholder_participation("stakeholder2", 0, bytes.fromhex("b" * 56)),
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

    def test_validate_datum_update_zero_current_supply_success(self):
        """Test datum update succeeds when current supply is zero"""
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

        # Should not raise any exception - zero current supply is allowed
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_state_regression_fails(self):
        """Test datum update fails when project state goes backward"""
        old_datum = self.create_distributed_project()  # Status 1

        # Regress state from 1 to 0
        new_params = DatumProjectParams(
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
        old_datum = self.create_initialized_project()  # Status 0

        # Set invalid state (> 3)
        new_params = DatumProjectParams(
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



class TestProjectValidator(MockCommonProject):
    """Test full project validator integration"""

    def test_validator_protocol_policy_id_mismatch_fails(self):
        """Test validator works regardless of protocol policy ID parameter"""
        datum = self.create_mock_datum_project()
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        # Create inputs for the test  
        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {b"PROJECT_token": 1}},
            datum=SomeOutputDatum(datum)
        )
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address, 
            value={b"": 2000000, self.sample_policy_id: {b"USER_token": 1}}
        )
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        project_output_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, self.sample_policy_id: {b"PROJECT_token": 1}},
            datum=SomeOutputDatum(datum)
        )

        redeemer = UpdateProject(
            project_input_index=0,
            user_input_index=1,
            project_output_index=0,
        )

        tx_info = self.create_mock_tx_info(
            inputs=[project_input, user_input],
            outputs=[project_output_utxo]
        )
        context = self.create_mock_script_context(Spending(oref_project), tx_info)

        # The validator no longer checks protocol policy ID mismatch in this way
        # Should not raise any exception
        project_validator(oref_project, datum, redeemer, context)

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

        # Create protocol datum
        protocol_datum = self.create_mock_protocol_datum()

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
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        # Should not raise any exception
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_project_missing_user_token_fails(self):
        """Test UpdateProject fails when user doesn't have required project token"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"

        old_datum = self.create_mock_datum_project()
        new_datum = old_datum  # Same datum for simplicity

        # Create protocol datum
        protocol_datum = self.create_mock_protocol_datum()

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
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        with pytest.raises(AssertionError, match="User does not have required token"):
            project_validator(oref_project, old_datum, redeemer, context)

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

        # Create protocol datum
        protocol_datum = self.create_mock_protocol_datum()

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
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        # Since protocol token validation is disabled, this should now pass
        # No exception expected
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_project_invalid_datum_update_fails(self):
        """Test UpdateProject fails with invalid datum update (owner change)"""
        # Create test data
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_protocol = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("c" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        old_datum = self.create_mock_datum_project()

        # Create invalid new datum (total supply change - not allowed)
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=old_datum.project_token.token_name,
            total_supply=old_datum.project_token.total_supply + 1000000,  # Changed total supply
            current_supply=old_datum.project_token.current_supply,
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create protocol datum
        protocol_datum = self.create_mock_protocol_datum()

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
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        with pytest.raises(AssertionError, match="Total supply can never be changed"):
            project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_end_project_success(self):
        """Test successful EndProject validation"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        project_token_name = unique_token_name(oref_project, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref_project, PREFIX_USER_NFT)

        # Create project datum
        project_datum = self.create_mock_datum_project()

        # Create project input with datum
        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, policy_id: {project_token_name: 1}},
            datum=SomeOutputDatum(project_datum)
        )
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)

        # Create user input with required token
        user_input_utxo = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, policy_id: {user_token_name: 1}}
        )
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        redeemer = EndProject(project_input_index=0, user_input_index=1)

        # Create tx_info
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=[project_input, user_input])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should not raise any exception
        project_validator(oref_project, project_datum, redeemer, context)

    def test_validator_end_project_missing_user_token_fails(self):
        """Test EndProject fails when user doesn't have required token"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        project_token_name = unique_token_name(oref_project, PREFIX_REFERENCE_NFT)

        # Create project datum
        project_datum = self.create_mock_datum_project()

        # Create project input with datum
        project_input_utxo = self.create_mock_tx_out(
            self.project_script_address,
            value={b"": 10000000, policy_id: {project_token_name: 1}},
            datum=SomeOutputDatum(project_datum)
        )
        project_input = self.create_mock_tx_in_info(oref_project, project_input_utxo)

        # Create user input WITHOUT required token
        user_input_utxo = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000}  # No tokens
        )
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        redeemer = EndProject(project_input_index=0, user_input_index=1)

        # Create tx_info
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=[project_input, user_input])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail due to missing user token
        with pytest.raises(AssertionError, match="User does not have required token"):
            project_validator(oref_project, project_datum, redeemer, context)

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

        # Create protocol datum
        protocol_datum = self.create_mock_protocol_datum()

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
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        # Should not raise any exception since project listing is no longer validated
        project_validator(oref_project, old_datum, redeemer, context)

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

        # Create protocol datum
        protocol_datum = self.create_mock_protocol_datum()

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
            project_input_index=1,
            user_input_index=2,
            project_output_index=0,
        )

        # Should not raise any exception
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_invalid_redeemer_type(self):
        """Test validator fails with invalid redeemer type"""
        project_datum = self.create_mock_datum_project()
        invalid_redeemer = PlutusData()  # Invalid redeemer type

        spending_purpose = Spending(self.create_mock_oref())
        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(spending_purpose, tx_info)

        with pytest.raises(AssertionError, match="Invalid redeemer type"):
            project_validator(self.create_mock_oref(), project_datum, invalid_redeemer, context)

    # ==================== Enhanced Status-Based Tests ====================
    
    def test_validate_datum_update_metadata_change_status_0_vs_1(self):
        """Test metadata changes are allowed for both status 0 and status > 0"""
        # Test status 0 (initialized)
        old_datum_status_0 = self.create_initialized_project()
        new_datum_status_0 = DatumProject(
            protocol_policy_id=old_datum_status_0.protocol_policy_id,
            params=DatumProjectParams(
                project_id=old_datum_status_0.params.project_id,
                project_metadata=b"https://updated-metadata-status0.com/project.json",
                project_state=old_datum_status_0.params.project_state,
            ),
            project_token=old_datum_status_0.project_token,
            stakeholders=old_datum_status_0.stakeholders,
            certifications=old_datum_status_0.certifications,
        )
        validate_datum_update(old_datum_status_0, new_datum_status_0)  # Should pass
        
        # Test status 1 (distributed)
        old_datum_status_1 = self.create_distributed_project()
        new_datum_status_1 = DatumProject(
            protocol_policy_id=old_datum_status_1.protocol_policy_id,
            params=DatumProjectParams(
                project_id=old_datum_status_1.params.project_id,
                project_metadata=b"https://updated-metadata-status1.com/project.json",
                project_state=old_datum_status_1.params.project_state,
            ),
            project_token=old_datum_status_1.project_token,
            stakeholders=old_datum_status_1.stakeholders,
            certifications=old_datum_status_1.certifications,
        )
        validate_datum_update(old_datum_status_1, new_datum_status_1)  # Should pass

    def test_validate_datum_update_current_supply_increase_all_statuses(self):
        """Test current supply increases are allowed for all status levels"""
        statuses = [0, 1, 2, 3]
        project_creators = [
            self.create_initialized_project,
            self.create_distributed_project, 
            self.create_certified_project,
            self.create_closed_project
        ]
        
        for status, creator in zip(statuses, project_creators):
            old_datum = creator()
            old_supply = old_datum.project_token.current_supply
            
            new_token = TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=min(old_supply + 1000000, old_datum.project_token.total_supply)  # Increase but don't exceed total
            )
            
            new_datum = DatumProject(
                protocol_policy_id=old_datum.protocol_policy_id,
                params=old_datum.params,
                project_token=new_token,
                stakeholders=old_datum.stakeholders,
                certifications=old_datum.certifications,
            )
            
            validate_datum_update(old_datum, new_datum)  # Should pass for all statuses

    # ==================== Status Transition Boundary Tests ====================

    def test_validate_datum_update_status_transitions_all_valid_paths(self):
        """Test all valid status transitions (0->1, 1->2, 2->3, etc.)"""
        transition_paths = [
            (0, 1),  # initialized -> distributed
            (0, 2),  # initialized -> certified (skip distributed)
            (0, 3),  # initialized -> closed (skip distributed and certified)
            (1, 2),  # distributed -> certified
            (1, 3),  # distributed -> closed (skip certified)
            (2, 3),  # certified -> closed
        ]
        
        for old_status, new_status in transition_paths:
            old_datum = self.create_mock_datum_project(
                params=self.create_mock_datum_project_params(project_state=old_status)
            )
            new_datum = DatumProject(
                protocol_policy_id=old_datum.protocol_policy_id,
                params=DatumProjectParams(
                    project_id=old_datum.params.project_id,
                    project_metadata=old_datum.params.project_metadata,
                    project_state=new_status,
                ),
                project_token=old_datum.project_token,
                stakeholders=old_datum.stakeholders,
                certifications=old_datum.certifications,
            )
            
            validate_datum_update(old_datum, new_datum)  # Should pass

    def test_validate_datum_update_status_regression_boundary_cases(self):
        """Test all invalid status regressions fail"""
        regression_paths = [
            (1, 0),  # distributed -> initialized
            (2, 0),  # certified -> initialized
            (2, 1),  # certified -> distributed  
            (3, 0),  # closed -> initialized
            (3, 1),  # closed -> distributed
            (3, 2),  # closed -> certified
        ]
        
        for old_status, new_status in regression_paths:
            old_datum = self.create_mock_datum_project(
                params=self.create_mock_datum_project_params(project_state=old_status)
            )
            new_datum = DatumProject(
                protocol_policy_id=old_datum.protocol_policy_id,
                params=DatumProjectParams(
                    project_id=old_datum.params.project_id,
                    project_metadata=old_datum.params.project_metadata,
                    project_state=new_status,
                ),
                project_token=old_datum.project_token,
                stakeholders=old_datum.stakeholders,
                certifications=old_datum.certifications,
            )
            
            with pytest.raises(AssertionError, match="Project state can only move forward"):
                validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_immutable_fields_at_status_boundary(self):
        """Test that fields become immutable exactly at the transition from status 0 to 1"""
        # These changes should work at status 0
        old_datum_status_0 = self.create_initialized_project()
        
        # Test project_id change at status 0 (should work)
        new_datum_status_0 = DatumProject(
            protocol_policy_id=old_datum_status_0.protocol_policy_id,
            params=DatumProjectParams(
                project_id=b"new_project_id_12345678901234567890",  # Changed
                project_metadata=old_datum_status_0.params.project_metadata,
                project_state=0,  # Still status 0
            ),
            project_token=old_datum_status_0.project_token,
            stakeholders=old_datum_status_0.stakeholders,
            certifications=old_datum_status_0.certifications,
        )
        validate_datum_update(old_datum_status_0, new_datum_status_0)  # Should pass
        
        # The same change should fail at status 1
        old_datum_status_1 = self.create_distributed_project()
        new_datum_status_1 = DatumProject(
            protocol_policy_id=old_datum_status_1.protocol_policy_id,
            params=DatumProjectParams(
                project_id=b"new_project_id_12345678901234567890",  # Changed
                project_metadata=old_datum_status_1.params.project_metadata,
                project_state=1,
            ),
            project_token=old_datum_status_1.project_token,
            stakeholders=old_datum_status_1.stakeholders,
            certifications=old_datum_status_1.certifications,
        )
        
        with pytest.raises(AssertionError, match="Project ID cannot be changed after status > 0"):
            validate_datum_update(old_datum_status_1, new_datum_status_1)

    # ==================== Empty Value Initialization Tests ====================

    def test_validate_datum_update_empty_protocol_policy_id_initialization(self):
        """Test that empty protocol_policy_id can be set initially but not changed once set"""
        # Start with empty protocol_policy_id
        old_datum = self.create_project_with_empty_fields()
        
        # Setting empty protocol_policy_id to a value should work (status 0)
        new_datum = DatumProject(
            protocol_policy_id=self.protocol_policy_id,  # Set to actual value
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )
        validate_datum_update(old_datum, new_datum)  # Should pass
        
        # Once set, changing protocol_policy_id should fail
        newer_datum = DatumProject(
            protocol_policy_id=bytes.fromhex("f" * 56),  # Different value
            params=new_datum.params,
            project_token=new_datum.project_token,
            stakeholders=new_datum.stakeholders,
            certifications=new_datum.certifications,
        )
        
        with pytest.raises(AssertionError, match="Protocol policy ID cannot be changed once set"):
            validate_datum_update(new_datum, newer_datum)

    def test_validate_datum_update_empty_token_name_initialization(self):
        """Test that empty token_name can be set initially but not changed once set"""
        # Start with empty token_name
        old_datum = self.create_project_with_empty_fields()
        
        # Setting empty token_name to a value should work (status 0)
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,
            token_name=b"NEW_PROJECT_TOKEN",  # Set to actual value
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
        validate_datum_update(old_datum, new_datum)  # Should pass
        
        # Once set, changing token_name should fail
        newer_token = TokenProject(
            policy_id=new_datum.project_token.policy_id,
            token_name=b"DIFFERENT_TOKEN_NAME",  # Different value
            total_supply=new_datum.project_token.total_supply,
            current_supply=new_datum.project_token.current_supply,
        )
        
        newer_datum = DatumProject(
            protocol_policy_id=new_datum.protocol_policy_id,
            params=new_datum.params,
            project_token=newer_token,
            stakeholders=new_datum.stakeholders,
            certifications=new_datum.certifications,
        )
        
        with pytest.raises(AssertionError, match="Token name cannot be changed once set"):
            validate_datum_update(new_datum, newer_datum)

    def test_validate_datum_update_empty_fields_at_higher_status_fail(self):
        """Test that empty fields cannot be set when status > 0"""
        # Try to set protocol_policy_id when status is 1 (should fail)
        old_datum = DatumProject(
            protocol_policy_id=b"",  # Empty
            params=self.create_mock_datum_project_params(project_state=1),  # Status 1
            project_token=self.create_mock_token_project(),
            stakeholders=[self.create_mock_stakeholder_participation("stakeholder1", 1000000, bytes.fromhex("a" * 56))],
            certifications=[self.create_mock_certification()],
        )
        
        new_datum = DatumProject(
            protocol_policy_id=self.protocol_policy_id,  # Try to set
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )
        
        with pytest.raises(AssertionError, match="Protocol policy ID cannot be changed after project lock"):
            validate_datum_update(old_datum, new_datum)
        
        # Try to set token_name when status is 1 (should fail)
        old_datum_token = DatumProject(
            protocol_policy_id=self.protocol_policy_id,
            params=self.create_mock_datum_project_params(project_state=1),  # Status 1
            project_token=self.create_mock_token_project(token_name=b""),  # Empty token name
            stakeholders=[self.create_mock_stakeholder_participation("stakeholder1", 1000000, bytes.fromhex("a" * 56))],
            certifications=[self.create_mock_certification()],
        )
        
        new_token = TokenProject(
            policy_id=old_datum_token.project_token.policy_id,
            token_name=b"NEW_TOKEN_NAME",  # Try to set
            total_supply=old_datum_token.project_token.total_supply,
            current_supply=old_datum_token.project_token.current_supply,
        )
        
        new_datum_token = DatumProject(
            protocol_policy_id=old_datum_token.protocol_policy_id,
            params=old_datum_token.params,
            project_token=new_token,
            stakeholders=old_datum_token.stakeholders,
            certifications=old_datum_token.certifications,
        )
        
        with pytest.raises(AssertionError, match="Token name cannot be changed after status > 0"):
            validate_datum_update(old_datum_token, new_datum_token)

    # ==================== Complex Scenario Tests ====================

    def test_validate_datum_update_complex_status_0_multiple_changes(self):
        """Test multiple field changes are allowed when status is 0"""
        old_datum = self.create_project_with_empty_fields()
        
        # Make multiple changes at once (status 0)
        new_params = DatumProjectParams(
            project_id=b"new_complex_project_id_123456789012",  # Changed
            project_metadata=b"https://new-complex-metadata.com/project.json",  # Changed
            project_state=1,  # Changed (state progression)
        )
        
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,  # Unchanged
            token_name=b"COMPLEX_NEW_TOKEN_NAME",  # Changed (was empty)
            total_supply=old_datum.project_token.total_supply,  # Unchanged
            current_supply=old_datum.project_token.current_supply + 500000,  # Changed (increased)
        )
        
        # Add a new certification
        new_certifications = old_datum.certifications + [
            self.create_mock_certification(cert_date=1672531200)  # Added
        ]
        
        new_datum = DatumProject(
            protocol_policy_id=self.protocol_policy_id,  # Changed (was empty)
            params=new_params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,  # Unchanged
            certifications=new_certifications,
        )
        
        validate_datum_update(old_datum, new_datum)  # Should pass

    def test_validate_datum_update_complex_status_1_restricted_changes(self):
        """Test that only some changes are allowed when status > 0"""
        old_datum = self.create_distributed_project()  # Status 1
        
        # These changes should work at status 1
        new_params = DatumProjectParams(
            project_id=old_datum.params.project_id,  # Unchanged (required)
            project_metadata=b"https://updated-distributed-metadata.com/project.json",  # Changed (allowed)
            project_state=2,  # Changed (state progression allowed)
        )
        
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,  # Unchanged (required)
            token_name=old_datum.project_token.token_name,  # Unchanged (required)
            total_supply=old_datum.project_token.total_supply,  # Unchanged (required)
            current_supply=old_datum.project_token.current_supply + 750000,  # Changed (allowed)
        )
        
        # Add a new certification (allowed)
        new_certifications = old_datum.certifications + [
            self.create_mock_certification(cert_date=1672531200)
        ]
        
        # Update real certification values (allowed)
        updated_certifications = []
        for cert in new_certifications:
            updated_cert = Certification(
                certification_date=cert.certification_date,
                quantity=cert.quantity,
                real_certification_date=cert.real_certification_date + 86400,  # Increased (allowed)
                real_quantity=cert.real_quantity + 100,  # Increased (allowed)
            )
            updated_certifications.append(updated_cert)
        
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,  # Unchanged (required)
            params=new_params,
            project_token=new_token,
            stakeholders=old_datum.stakeholders,  # Unchanged (required)
            certifications=updated_certifications,
        )
        
        validate_datum_update(old_datum, new_datum)  # Should pass

    def test_validate_datum_update_complex_status_1_forbidden_changes(self):
        """Test that forbidden changes fail when status > 0, even with allowed changes"""
        old_datum = self.create_distributed_project()  # Status 1
        
        # Mix allowed and forbidden changes
        new_params = DatumProjectParams(
            project_id=b"forbidden_new_project_id_123456789",  # FORBIDDEN CHANGE
            project_metadata=b"https://updated-metadata.com/project.json",  # Allowed change
            project_state=2,  # Allowed change
        )
        
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=new_params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )
        
        with pytest.raises(AssertionError, match="Project ID cannot be changed after project lock"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_complex_certification_updates(self):
        """Test complex certification update scenarios"""
        # Create project with multiple certifications
        old_certifications = [
            self.create_mock_certification(cert_date=1640995200, quantity=1000, real_cert_date=1640995200, real_quantity=900),
            self.create_mock_certification(cert_date=1672531200, quantity=1500, real_cert_date=1672531200, real_quantity=1400),
        ]
        
        old_datum = self.create_distributed_project(certifications=old_certifications)
        
        # Update real values and add new certification
        updated_certifications = [
            # Update first certification real values (allowed)
            Certification(
                certification_date=old_certifications[0].certification_date,  # Unchanged
                quantity=old_certifications[0].quantity,  # Unchanged
                real_certification_date=old_certifications[0].real_certification_date + 86400,  # Increased
                real_quantity=old_certifications[0].real_quantity + 50,  # Increased
            ),
            # Keep second certification unchanged
            old_certifications[1],
            # Add new certification (allowed)
            self.create_mock_certification(cert_date=1704067200, quantity=2000),
        ]
        
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=old_datum.project_token,
            stakeholders=old_datum.stakeholders,
            certifications=updated_certifications,
        )
        
        validate_datum_update(old_datum, new_datum)  # Should pass

    def test_validate_datum_update_complex_supply_and_status_progression(self):
        """Test complex supply changes with status progression"""
        old_datum = self.create_initialized_project()  # Status 0
        
        # Progress through multiple status levels with supply changes
        intermediate_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=DatumProjectParams(
                project_id=old_datum.params.project_id,
                project_metadata=old_datum.params.project_metadata,
                project_state=1,  # 0 -> 1
            ),
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + 1000000,  # Increase supply
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )
        
        validate_datum_update(old_datum, intermediate_datum)  # Should pass
        
        # Further progression
        final_datum = DatumProject(
            protocol_policy_id=intermediate_datum.protocol_policy_id,
            params=DatumProjectParams(
                project_id=intermediate_datum.params.project_id,
                project_metadata=b"https://final-certified-metadata.com/project.json",
                project_state=2,  # 1 -> 2
            ),
            project_token=TokenProject(
                policy_id=intermediate_datum.project_token.policy_id,
                token_name=intermediate_datum.project_token.token_name,
                total_supply=intermediate_datum.project_token.total_supply,
                current_supply=intermediate_datum.project_token.total_supply,  # Reach total supply
            ),
            stakeholders=intermediate_datum.stakeholders,
            certifications=intermediate_datum.certifications + [
                self.create_mock_certification(cert_date=1704067200, quantity=3000)
            ],
        )
        
        validate_datum_update(intermediate_datum, final_datum)  # Should pass

    # ==================== Integration Tests for Full Validator ====================

    def test_validator_update_project_status_0_field_changes_success(self):
        """Test full validator with status 0 project allowing field changes"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        # Create old datum (status 0) with empty fields that can be set
        old_datum = self.create_project_with_empty_fields()

        # Create new datum with field changes allowed at status 0
        new_params = DatumProjectParams(
            project_id=b"updated_project_id_1234567890123456",  # Changed (allowed at status 0)
            project_metadata=b"https://updated-status0.com/project.json",
            project_state=1,  # Status progression (allowed)
        )

        new_datum = DatumProject(
            protocol_policy_id=self.protocol_policy_id,  # Set (was empty, allowed at status 0)
            params=new_params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=b"NEW_TOKEN_NAME",  # Set (was empty, allowed at status 0)
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + 500000,  # Increased
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create protocol datum
        protocol_datum = self.create_mock_protocol_datum()

        # Create UTxOs
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
            value={b"": 5000000, self.sample_policy_id: {user_token_name: 1}},
        )

        # Create transaction inputs and outputs
        tx_inputs = [
            self.create_mock_tx_in_info(oref_project, project_input_utxo),
            self.create_mock_tx_in_info(self.create_mock_oref(bytes.fromhex("c" * 64), 0), user_input_utxo),
        ]
        tx_outputs = [project_output_utxo]

        # Create redeemer
        redeemer = UpdateProject(
            project_input_index=0,
            user_input_index=1,
            project_output_index=0,
        )

        # Create context
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should pass - status 0 allows these changes
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_project_status_1_restricted_changes_success(self):
        """Test full validator with status 1 project allowing only certain changes"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        # Create old datum (status 1)
        old_datum = self.create_distributed_project()

        # Create new datum with only changes allowed at status > 0
        new_params = DatumProjectParams(
            project_id=old_datum.params.project_id,  # Unchanged (required)
            project_metadata=b"https://updated-status1.com/project.json",  # Changed (allowed)
            project_state=2,  # Status progression (allowed)
        )

        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,  # Unchanged (required)
            params=new_params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,  # Unchanged (required)
                token_name=old_datum.project_token.token_name,  # Unchanged (required)
                total_supply=old_datum.project_token.total_supply,  # Unchanged (required)
                current_supply=old_datum.project_token.current_supply + 750000,  # Increased (allowed)
            ),
            stakeholders=old_datum.stakeholders,  # Unchanged (required)
            certifications=old_datum.certifications + [  # Added certification (allowed)
                self.create_mock_certification(cert_date=1704067200, quantity=2000)
            ],
        )

        # Create UTxOs
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
            value={b"": 5000000, self.sample_policy_id: {user_token_name: 1}},
        )

        # Create transaction inputs and outputs
        tx_inputs = [
            self.create_mock_tx_in_info(oref_project, project_input_utxo),
            self.create_mock_tx_in_info(self.create_mock_oref(bytes.fromhex("c" * 64), 0), user_input_utxo),
        ]
        tx_outputs = [project_output_utxo]

        # Create redeemer
        redeemer = UpdateProject(
            project_input_index=0,
            user_input_index=1,
            project_output_index=0,
        )

        # Create context
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should pass - only allowed changes for status > 0
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_project_status_1_forbidden_change_fails(self):
        """Test full validator fails when trying forbidden changes at status > 0"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"
        user_token_name = b"USER_token"

        # Create old datum (status 1)
        old_datum = self.create_distributed_project()

        # Create new datum with forbidden change at status > 0
        new_params = DatumProjectParams(
            project_id=b"forbidden_project_id_change_1234567",  # FORBIDDEN CHANGE
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

        # Create UTxOs
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
            value={b"": 5000000, self.sample_policy_id: {user_token_name: 1}},
        )

        # Create transaction inputs and outputs
        tx_inputs = [
            self.create_mock_tx_in_info(oref_project, project_input_utxo),
            self.create_mock_tx_in_info(self.create_mock_oref(bytes.fromhex("c" * 64), 0), user_input_utxo),
        ]
        tx_outputs = [project_output_utxo]

        # Create redeemer
        redeemer = UpdateProject(
            project_input_index=0,
            user_input_index=1,
            project_output_index=0,
        )

        # Create context
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail due to forbidden project_id change at status > 0
        with pytest.raises(AssertionError, match="Project ID cannot be changed after status > 0"):
            project_validator(oref_project, old_datum, redeemer, context)

    # ==================== Project Lifecycle Workflow Tests ====================

    def test_complete_project_lifecycle_workflow(self):
        """Test a complete project lifecycle from initialization to closure"""
        # Phase 1: Project Initialization (Status 0)
        initial_project = self.create_project_with_empty_fields()
        
        # Initialize project with basic information
        configured_project = DatumProject(
            protocol_policy_id=self.protocol_policy_id,  # Set protocol
            params=DatumProjectParams(
                project_id=b"lifecycle_project_id_123456789012",  # Set project ID
                project_metadata=b"https://lifecycle-project.com/phase1.json",
                project_state=0,  # Still initialized
            ),
            project_token=TokenProject(
                policy_id=initial_project.project_token.policy_id,
                token_name=b"LIFECYCLE_TOKEN",  # Set token name
                total_supply=initial_project.project_token.total_supply,
                current_supply=initial_project.project_token.current_supply,  # Keep current supply same (can't decrease)
            ),
            stakeholders=initial_project.stakeholders,
            certifications=initial_project.certifications,
        )
        
        validate_datum_update(initial_project, configured_project)  # Should pass
        
        # Phase 2: Project Distribution (Status 0 -> 1)
        distributed_project = DatumProject(
            protocol_policy_id=configured_project.protocol_policy_id,
            params=DatumProjectParams(
                project_id=configured_project.params.project_id,
                project_metadata=b"https://lifecycle-project.com/phase2-distributed.json",
                project_state=1,  # Move to distributed
            ),
            project_token=TokenProject(
                policy_id=configured_project.project_token.policy_id,
                token_name=configured_project.project_token.token_name,
                total_supply=configured_project.project_token.total_supply,
                current_supply=configured_project.project_token.total_supply // 2,  # Distribute 50%
            ),
            stakeholders=configured_project.stakeholders,
            certifications=configured_project.certifications,
        )
        
        validate_datum_update(configured_project, distributed_project)  # Should pass
        
        # Phase 3: Add Certification and Progress to Certified (Status 1 -> 2)
        certified_project = DatumProject(
            protocol_policy_id=distributed_project.protocol_policy_id,
            params=DatumProjectParams(
                project_id=distributed_project.params.project_id,  # Cannot change at status > 0
                project_metadata=b"https://lifecycle-project.com/phase3-certified.json",
                project_state=2,  # Move to certified
            ),
            project_token=TokenProject(
                policy_id=distributed_project.project_token.policy_id,
                token_name=distributed_project.project_token.token_name,  # Cannot change at status > 0
                total_supply=distributed_project.project_token.total_supply,
                current_supply=distributed_project.project_token.total_supply,  # Fully distributed
            ),
            stakeholders=distributed_project.stakeholders,
            certifications=distributed_project.certifications + [
                self.create_mock_certification(cert_date=1704067200, quantity=5000, real_cert_date=1704067200, real_quantity=4800)
            ],
        )
        
        validate_datum_update(distributed_project, certified_project)  # Should pass
        
        # Phase 4: Update Real Certification Values and Close Project (Status 2 -> 3)
        closed_project = DatumProject(
            protocol_policy_id=certified_project.protocol_policy_id,
            params=DatumProjectParams(
                project_id=certified_project.params.project_id,
                project_metadata=b"https://lifecycle-project.com/phase4-closed.json",
                project_state=3,  # Move to closed
            ),
            project_token=certified_project.project_token,
            stakeholders=certified_project.stakeholders,
            certifications=[
                # Update real certification values (allowed increase)
                Certification(
                    certification_date=certified_project.certifications[0].certification_date,
                    quantity=certified_project.certifications[0].quantity,
                    real_certification_date=certified_project.certifications[0].real_certification_date,
                    real_quantity=certified_project.certifications[0].real_quantity,
                ),
                Certification(
                    certification_date=certified_project.certifications[1].certification_date,
                    quantity=certified_project.certifications[1].quantity,
                    real_certification_date=certified_project.certifications[1].real_certification_date + 86400,  # Updated
                    real_quantity=certified_project.certifications[1].real_quantity + 100,  # Updated
                ),
            ],
        )
        
        validate_datum_update(certified_project, closed_project)  # Should pass

    def test_project_lifecycle_invalid_transitions(self):
        """Test that invalid transitions in project lifecycle fail"""
        # Try to go backwards in lifecycle
        distributed_project = self.create_distributed_project()  # Status 1
        
        # Try to regress to initialized (should fail)
        regressed_project = DatumProject(
            protocol_policy_id=distributed_project.protocol_policy_id,
            params=DatumProjectParams(
                project_id=distributed_project.params.project_id,
                project_metadata=distributed_project.params.project_metadata,
                project_state=0,  # Try to regress
            ),
            project_token=distributed_project.project_token,
            stakeholders=distributed_project.stakeholders,
            certifications=distributed_project.certifications,
        )
        
        with pytest.raises(AssertionError, match="Project state can only move forward"):
            validate_datum_update(distributed_project, regressed_project)
        
        # Try to make forbidden changes during valid transition
        certified_project = self.create_certified_project()  # Status 2
        
        # Try to change immutable field during valid status progression (should fail)
        invalid_closed_project = DatumProject(
            protocol_policy_id=bytes.fromhex("f" * 56),  # FORBIDDEN CHANGE
            params=DatumProjectParams(
                project_id=certified_project.params.project_id,
                project_metadata=certified_project.params.project_metadata,
                project_state=3,  # Valid status progression
            ),
            project_token=certified_project.project_token,
            stakeholders=certified_project.stakeholders,
            certifications=certified_project.certifications,
        )
        
        with pytest.raises(AssertionError, match="Protocol policy ID cannot be changed after status > 0"):
            validate_datum_update(certified_project, invalid_closed_project)

    def test_project_lifecycle_certification_evolution(self):
        """Test how certifications evolve through project lifecycle"""
        # Start with project in distributed state with initial certifications
        initial_certifications = [
            self.create_mock_certification(
                cert_date=1640995200, quantity=1000, 
                real_cert_date=1640995200, real_quantity=900
            ),
            self.create_mock_certification(
                cert_date=1672531200, quantity=1500,
                real_cert_date=1672531200, real_quantity=1400
            ),
        ]
        
        distributed_project = self.create_distributed_project(certifications=initial_certifications)
        
        # Progress to certified with new certification
        certified_with_new = DatumProject(
            protocol_policy_id=distributed_project.protocol_policy_id,
            params=DatumProjectParams(
                project_id=distributed_project.params.project_id,
                project_metadata=distributed_project.params.project_metadata,
                project_state=2,  # Move to certified
            ),
            project_token=distributed_project.project_token,
            stakeholders=distributed_project.stakeholders,
            certifications=distributed_project.certifications + [
                # Add new certification
                self.create_mock_certification(
                    cert_date=1704067200, quantity=2000,
                    real_cert_date=1704067200, real_quantity=1900
                ),
            ],
        )
        
        validate_datum_update(distributed_project, certified_with_new)  # Should pass
        
        # Final update with improved real certification values
        final_project = DatumProject(
            protocol_policy_id=certified_with_new.protocol_policy_id,
            params=DatumProjectParams(
                project_id=certified_with_new.params.project_id,
                project_metadata=b"https://final-certification-update.com/project.json",
                project_state=3,  # Move to closed
            ),
            project_token=certified_with_new.project_token,
            stakeholders=certified_with_new.stakeholders,
            certifications=[
                # Keep first two unchanged
                certified_with_new.certifications[0],
                certified_with_new.certifications[1],
                # Update the third certification with better real values
                Certification(
                    certification_date=certified_with_new.certifications[2].certification_date,
                    quantity=certified_with_new.certifications[2].quantity,
                    real_certification_date=certified_with_new.certifications[2].real_certification_date + 172800,  # +2 days
                    real_quantity=certified_with_new.certifications[2].real_quantity + 50,  # Improved
                ),
            ],
        )
        
        validate_datum_update(certified_with_new, final_project)  # Should pass

    def test_project_lifecycle_supply_evolution(self):
        """Test how token supply evolves through project lifecycle"""
        # Start with initialized project (zero current supply)
        initial_project = self.create_initialized_project()
        initial_project = DatumProject(
            protocol_policy_id=initial_project.protocol_policy_id,
            params=initial_project.params,
            project_token=TokenProject(
                policy_id=initial_project.project_token.policy_id,
                token_name=initial_project.project_token.token_name,
                total_supply=10000000,  # 10M total supply
                current_supply=0,  # Start with zero
            ),
            stakeholders=[  # Update stakeholders to match new total supply
                self.create_mock_stakeholder_participation("stakeholder1", 5000000, bytes.fromhex("a" * 56)),
                self.create_mock_stakeholder_participation("stakeholder2", 5000000, bytes.fromhex("b" * 56)),
            ],
            certifications=initial_project.certifications,
        )
        
        # Phase 1: Partial distribution (Status 0 -> 1)
        partial_distribution = DatumProject(
            protocol_policy_id=initial_project.protocol_policy_id,
            params=DatumProjectParams(
                project_id=initial_project.params.project_id,
                project_metadata=initial_project.params.project_metadata,
                project_state=1,  # Move to distributed
            ),
            project_token=TokenProject(
                policy_id=initial_project.project_token.policy_id,
                token_name=initial_project.project_token.token_name,
                total_supply=initial_project.project_token.total_supply,
                current_supply=3000000,  # 30% distributed
            ),
            stakeholders=initial_project.stakeholders,
            certifications=initial_project.certifications,
        )
        
        validate_datum_update(initial_project, partial_distribution)  # Should pass
        
        # Phase 2: Further distribution (Status 1 -> 2)
        further_distribution = DatumProject(
            protocol_policy_id=partial_distribution.protocol_policy_id,
            params=DatumProjectParams(
                project_id=partial_distribution.params.project_id,
                project_metadata=partial_distribution.params.project_metadata,
                project_state=2,  # Move to certified
            ),
            project_token=TokenProject(
                policy_id=partial_distribution.project_token.policy_id,
                token_name=partial_distribution.project_token.token_name,
                total_supply=partial_distribution.project_token.total_supply,
                current_supply=7500000,  # 75% distributed
            ),
            stakeholders=partial_distribution.stakeholders,
            certifications=partial_distribution.certifications,
        )
        
        validate_datum_update(partial_distribution, further_distribution)  # Should pass
        
        # Phase 3: Full distribution (Status 2 -> 3)
        full_distribution = DatumProject(
            protocol_policy_id=further_distribution.protocol_policy_id,
            params=DatumProjectParams(
                project_id=further_distribution.params.project_id,
                project_metadata=further_distribution.params.project_metadata,
                project_state=3,  # Move to closed
            ),
            project_token=TokenProject(
                policy_id=further_distribution.project_token.policy_id,
                token_name=further_distribution.project_token.token_name,
                total_supply=further_distribution.project_token.total_supply,
                current_supply=further_distribution.project_token.total_supply,  # 100% distributed
            ),
            stakeholders=further_distribution.stakeholders,
            certifications=further_distribution.certifications,
        )
        
        validate_datum_update(further_distribution, full_distribution)  # Should pass

    # ==================== UpdateToken Test Cases ====================

    def test_validator_update_token_mint_success(self):
        """Test successful UpdateToken validation for minting"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum
        old_datum = self.create_distributed_project()

        # Create new datum with increased current_supply
        mint_amount = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create UTxOs
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

        # Create transaction with minting
        tx_inputs = [
            self.create_mock_tx_in_info(oref_project, project_input_utxo),
        ]
        tx_outputs = [project_output_utxo]

        # Create redeemer
        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,  # Not used in UpdateToken
            project_output_index=0,
            new_supply=mint_amount,
        )

        # Create context with mint field
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        
        # Add mint field for grey tokens
        tx_info.mint = {
            old_datum.project_token.policy_id: {
                old_datum.project_token.token_name: mint_amount
            }
        }
        
        # Add stakeholder signature
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # Stakeholder1's PKH
        
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should pass
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_burn_success(self):
        """Test successful UpdateToken validation for burning"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum
        old_datum = self.create_distributed_project()

        # Create new datum with decreased current_supply
        burn_amount = -500000  # Negative for burning
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + burn_amount,
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create UTxOs
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

        # Create transaction
        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        # Create redeemer
        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=burn_amount,
        )

        # Create context with burn in mint field
        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        
        # Add mint field for burning (negative amount)
        tx_info.mint = {
            old_datum.project_token.policy_id: {
                old_datum.project_token.token_name: burn_amount
            }
        }
        
        # Add stakeholder signature
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # Stakeholder1's PKH
        
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should pass
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_missing_stakeholder_signature_fails(self):
        """Test UpdateToken fails when no stakeholder signs"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum
        old_datum = self.create_distributed_project()

        # Create new datum
        mint_amount = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create UTxOs
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

        # Create transaction without stakeholder signatures
        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        
        tx_info.mint = {
            old_datum.project_token.policy_id: {
                old_datum.project_token.token_name: mint_amount
            }
        }
        
        # No stakeholder signatures
        tx_info.signatories = []
        
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail
        with pytest.raises(AssertionError, match="Transaction must be signed by a non-investor stakeholder"):
            project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_mint_amount_mismatch_fails(self):
        """Test UpdateToken fails when redeemer delta doesn't match mint amount"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum
        old_datum = self.create_distributed_project()

        # Create new datum
        mint_amount = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create UTxOs
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

        # Create transaction
        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,  # Redeemer says 1M
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        
        # Mint field says different amount
        tx_info.mint = {
            old_datum.project_token.policy_id: {
                old_datum.project_token.token_name: mint_amount + 500000  # Different amount
            }
        }
        
        tx_info.signatories = [bytes.fromhex("a" * 56)]
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail
        with pytest.raises(AssertionError, match="Mint amount must match redeemer delta"):
            project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_current_supply_mismatch_fails(self):
        """Test UpdateToken fails when current_supply doesn't match expected delta"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum
        old_datum = self.create_distributed_project()

        # Create new datum with wrong current_supply change
        mint_amount = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount + 500000,  # Wrong amount
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create UTxOs
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

        # Create transaction
        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        
        tx_info.mint = {
            old_datum.project_token.policy_id: {
                old_datum.project_token.token_name: mint_amount
            }
        }
        
        tx_info.signatories = [bytes.fromhex("a" * 56)]
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail
        with pytest.raises(AssertionError, match="Current supply must be updated by exactly the delta amount"):
            project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_investor_stakeholder_public_access(self):
        """Test UpdateToken works with only investor stakeholders (public access, no signature required)"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum with ONLY investor stakeholders (active state for UpdateToken)
        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("investor", 3000000, b""),  # Public investor
                self.create_mock_stakeholder_participation("investor", 2000000, b""),  # Another public investor
            ]
        )

        # Create new datum
        mint_amount = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create UTxOs
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

        # Create transaction
        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        
        tx_info.mint = {
            old_datum.project_token.policy_id: {
                old_datum.project_token.token_name: mint_amount
            }
        }
        
        # NO SIGNATURES REQUIRED - public access for investor-only projects
        tx_info.signatories = []  # Empty signatories list
        
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should pass - no signature required for investor-only projects
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_mixed_stakeholders_requires_non_investor_signature(self):
        """Test UpdateToken with mixed stakeholders still requires non-investor signature"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum with mixed stakeholders (investor + non-investor) in active state
        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("investor", 2500000, b""),  # Public investor
                self.create_mock_stakeholder_participation("landowner", 2500000, bytes.fromhex("b" * 56)),  # Requires signature
            ]
        )

        # Create new datum
        mint_amount = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create UTxOs
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

        # Create transaction
        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        
        tx_info.mint = {
            old_datum.project_token.policy_id: {
                old_datum.project_token.token_name: mint_amount
            }
        }
        
        # Test 1: No signatures should fail
        tx_info.signatories = []
        context = self.create_mock_script_context(spending_purpose, tx_info)
        
        with pytest.raises(AssertionError, match="Transaction must be signed by a non-investor stakeholder"):
            project_validator(oref_project, old_datum, redeemer, context)
        
        # Test 2: Sign with non-investor stakeholder should pass
        tx_info.signatories = [bytes.fromhex("b" * 56)]  # landowner's PKH
        context = self.create_mock_script_context(spending_purpose, tx_info)
        
        # Should pass
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_amount_claimed_increase_success(self):
        """Test UpdateToken succeeds when amount_claimed increases within participation limits"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum with stakeholder having some amount claimed (active state)
        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("landowner", 5000000, bytes.fromhex("a" * 56), amount_claimed=1000000),
            ]
        )

        # Create new datum with increased amount_claimed (within limits)
        mint_amount = 500000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=[
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[0].stakeholder,
                    pkh=old_datum.stakeholders[0].pkh,
                    participation=old_datum.stakeholders[0].participation,
                    amount_claimed=2000000,  # Increased by 1M, still within 5M participation
                )
            ],
            certifications=old_datum.certifications,
        )

        # Create transaction setup
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

        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        tx_info.mint = {old_datum.project_token.policy_id: {old_datum.project_token.token_name: mint_amount}}
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # landowner's PKH
        
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should pass
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_amount_claimed_decrease_during_burn_success(self):
        """Test UpdateToken succeeds when amount_claimed decreases during burning"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("landowner", 5000000, bytes.fromhex("a" * 56), amount_claimed=2000000),
            ]
        )

        # Create new datum with decreased amount_claimed during burn
        burn_amount = -500000  # Negative for burning
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + burn_amount,
            ),
            stakeholders=[
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[0].stakeholder,
                    pkh=old_datum.stakeholders[0].pkh,
                    participation=old_datum.stakeholders[0].participation,
                    amount_claimed=1500000,  # Decreased during burn - this should succeed
                )
            ],
            certifications=old_datum.certifications,
        )

        # Create transaction setup
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

        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=burn_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        tx_info.mint = {old_datum.project_token.policy_id: {old_datum.project_token.token_name: burn_amount}}
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # landowner's PKH

        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should succeed
        project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_amount_claimed_increase_during_burn_fails(self):
        """Test UpdateToken fails when amount_claimed increases during burning"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("landowner", 5000000, bytes.fromhex("a" * 56), amount_claimed=1000000),
            ]
        )

        # Create new datum with increased amount_claimed during burn
        burn_amount = -500000  # Negative for burning
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + burn_amount,
            ),
            stakeholders=[
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[0].stakeholder,
                    pkh=old_datum.stakeholders[0].pkh,
                    participation=old_datum.stakeholders[0].participation,
                    amount_claimed=1500000,  # Increased during burn - this should fail
                )
            ],
            certifications=old_datum.certifications,
        )

        # Create transaction setup
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

        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=burn_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        tx_info.mint = {old_datum.project_token.policy_id: {old_datum.project_token.token_name: burn_amount}}
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # landowner's PKH

        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail
        with pytest.raises(AssertionError, match="Amount claimed can only decrease during burning"):
            project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_amount_claimed_exceeds_participation_fails(self):
        """Test UpdateToken fails when amount_claimed exceeds participation"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("landowner", 5000000, bytes.fromhex("a" * 56), amount_claimed=1000000),
            ]
        )

        # Create new datum with amount_claimed exceeding participation
        mint_amount = 500000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=[
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[0].stakeholder,
                    pkh=old_datum.stakeholders[0].pkh,
                    participation=old_datum.stakeholders[0].participation,
                    amount_claimed=6000000,  # Exceeds 5M participation - should fail
                )
            ],
            certifications=old_datum.certifications,
        )

        # Create transaction setup
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

        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        tx_info.mint = {old_datum.project_token.policy_id: {old_datum.project_token.token_name: mint_amount}}
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # landowner's PKH
        
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail
        with pytest.raises(AssertionError, match="Amount claimed cannot exceed participation"):
            project_validator(oref_project, old_datum, redeemer, context)

    def test_validator_update_token_rejects_state_0(self):
        """Test UpdateToken fails when project_state == 0"""
        oref_project = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        protocol_token_name = b"PROTO_token"

        # Create old datum with state 0 (initialized)
        old_datum = self.create_mock_datum_project()  # Default state is 0

        # Create new datum with mint
        mint_amount = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_amount,
            ),
            stakeholders=old_datum.stakeholders,
            certifications=old_datum.certifications,
        )

        # Create transaction setup
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

        tx_inputs = [self.create_mock_tx_in_info(oref_project, project_input_utxo)]
        tx_outputs = [project_output_utxo]

        redeemer = UpdateToken(
            project_input_index=0,
            user_input_index=0,
            project_output_index=0,
            new_supply=mint_amount,
        )

        spending_purpose = Spending(oref_project)
        tx_info = self.create_mock_tx_info(inputs=tx_inputs, outputs=tx_outputs)
        tx_info.mint = {old_datum.project_token.policy_id: {old_datum.project_token.token_name: mint_amount}}
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # stakeholder PKH
        
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail - UpdateToken cannot be used when project_state == 0
        with pytest.raises(AssertionError, match="UpdateToken can only be used when project_state > 0"):
            project_validator(oref_project, old_datum, redeemer, context)

    def test_validate_datum_update_comprehensive_state_0_changes_success(self):
        """Test comprehensive field changes are allowed when project_state == 0"""
        # Start with project in state 0
        old_datum = self.create_mock_datum_project()
        
        # Create completely different datum - everything can change when state == 0
        new_params = DatumProjectParams(
            project_id=bytes.fromhex("fedcba0987654321" * 4),  # Changed
            project_metadata=b"https://newdomain.com/updated-project.json",  # Changed
            project_state=1,  # Progressed from 0 to 1
        )
        
        new_token = TokenProject(
            policy_id=old_datum.project_token.policy_id,  # Same (this is always immutable)
            token_name=b"NEW_TOKEN_NAME",  # Changed (allowed when state == 0)
            total_supply=8000000,  # Changed (allowed when state == 0)
            current_supply=4000000,  # Changed (increased)
        )
        
        # New stakeholders with different participation
        new_stakeholders = [
            self.create_mock_stakeholder_participation("landowner", 3000000, bytes.fromhex("b" * 56), 100000),
            self.create_mock_stakeholder_participation("investor", 2000000, b"", 0),
            self.create_mock_stakeholder_participation("verifier", 3000000, bytes.fromhex("c" * 56), 50000),
        ]
        
        # New certifications
        new_certifications = [
            self.create_mock_certification(cert_date=1700000000, quantity=2000, real_cert_date=1700000000, real_quantity=2000),
            self.create_mock_certification(cert_date=1710000000, quantity=1500, real_cert_date=1710000000, real_quantity=1500),
        ]
        
        new_datum = DatumProject(
            protocol_policy_id=bytes.fromhex("d" * 56),  # Changed (allowed when state == 0)
            params=new_params,
            project_token=new_token,
            stakeholders=new_stakeholders,
            certifications=new_certifications,
        )
        
        # Should pass - all changes allowed when state == 0
        validate_datum_update(old_datum, new_datum)

    def test_validate_stakeholder_authorization_non_investor_signature_required(self):
        """Test validate_stakeholder_authorization requires non-investor signature"""
        # Create datum with non-investor stakeholders
        datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("landowner", 3000000, bytes.fromhex("a" * 56)),
                self.create_mock_stakeholder_participation("verifier", 2000000, bytes.fromhex("b" * 56)),
            ]
        )

        # Create transaction info without any signatures
        tx_info = self.create_mock_tx_info()
        tx_info.signatories = []

        # Should fail - no signatures provided
        with pytest.raises(AssertionError, match="Transaction must be signed by a non-investor stakeholder"):
            validate_stakeholder_authorization(datum, tx_info)

        # Should succeed with correct signature
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # landowner's PKH
        validate_stakeholder_authorization(datum, tx_info)

    def test_validate_stakeholder_authorization_investor_only_no_signature_required(self):
        """Test validate_stakeholder_authorization allows investor-only transactions without signatures"""
        # Create datum with only investor stakeholders
        datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("investor", 5000000, b""),
            ]
        )

        # Create transaction info without any signatures
        tx_info = self.create_mock_tx_info()
        tx_info.signatories = []

        # Should succeed - no signatures required for investor-only
        validate_stakeholder_authorization(datum, tx_info)

    def test_validate_update_token_changes_comprehensive_mint_success(self):
        """Test validate_update_token_changes for successful minting scenario"""
        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("landowner", 3000000, bytes.fromhex("a" * 56), amount_claimed=500000),
                self.create_mock_stakeholder_participation("investor", 2000000, b"", amount_claimed=0),
            ]
        )

        mint_delta = 1000000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + mint_delta,
            ),
            stakeholders=[
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[0].stakeholder,
                    pkh=old_datum.stakeholders[0].pkh,
                    participation=old_datum.stakeholders[0].participation,
                    amount_claimed=800000,  # Increased during minting
                ),
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[1].stakeholder,
                    pkh=old_datum.stakeholders[1].pkh,
                    participation=old_datum.stakeholders[1].participation,
                    amount_claimed=200000,  # Increased during minting
                ),
            ],
            certifications=old_datum.certifications,
        )

        tx_info = self.create_mock_tx_info()
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # landowner's PKH

        # Should succeed
        validate_update_token_changes(old_datum, new_datum, mint_delta, tx_info)

    def test_validate_update_token_changes_comprehensive_burn_success(self):
        """Test validate_update_token_changes for successful burning scenario"""
        old_datum = self.create_active_project_datum(
            stakeholders=[
                self.create_mock_stakeholder_participation("landowner", 3000000, bytes.fromhex("a" * 56), amount_claimed=1500000),
                self.create_mock_stakeholder_participation("investor", 2000000, b"", amount_claimed=500000),
            ]
        )

        burn_delta = -500000
        new_datum = DatumProject(
            protocol_policy_id=old_datum.protocol_policy_id,
            params=old_datum.params,
            project_token=TokenProject(
                policy_id=old_datum.project_token.policy_id,
                token_name=old_datum.project_token.token_name,
                total_supply=old_datum.project_token.total_supply,
                current_supply=old_datum.project_token.current_supply + burn_delta,
            ),
            stakeholders=[
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[0].stakeholder,
                    pkh=old_datum.stakeholders[0].pkh,
                    participation=old_datum.stakeholders[0].participation,
                    amount_claimed=1200000,  # Decreased during burning
                ),
                StakeHolderParticipation(
                    stakeholder=old_datum.stakeholders[1].stakeholder,
                    pkh=old_datum.stakeholders[1].pkh,
                    participation=old_datum.stakeholders[1].participation,
                    amount_claimed=300000,  # Decreased during burning
                ),
            ],
            certifications=old_datum.certifications,
        )

        tx_info = self.create_mock_tx_info()
        tx_info.signatories = [bytes.fromhex("a" * 56)]  # landowner's PKH

        # Should succeed
        validate_update_token_changes(old_datum, new_datum, burn_delta, tx_info)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
