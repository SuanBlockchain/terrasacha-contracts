"""
Mock objects and comprehensive test cases for the OpShin protocol validator
"""

from typing import Dict, List, Optional

import pytest
from opshin.ledger.api_v2 import *
from opshin.prelude import *
from opshin.std.builtins import *

from src.terrasacha_contracts.minting_policies.authentication_nfts import (
    Burn,
    Mint,
)
from src.terrasacha_contracts.minting_policies.authentication_nfts import (
    validator as protocol_nft_validator,
)
from src.terrasacha_contracts.util import *
from src.terrasacha_contracts.validators.protocol import (
    DatumProtocol,
    EndProtocol,
    UpdateProtocol,
    validate_datum_update,
)
from src.terrasacha_contracts.validators.protocol import validator as protocol_validator


class MockCommon:
    """Common Mock class used in tests"""

    def setup_method(self):
        """Setup method called before each test"""
        # self.mock_context = MockChainContext()
        self.sample_tx_id = TxId(bytes.fromhex("a" * 64))
        self.sample_policy_id = bytes.fromhex("b" * 56)
        self.sample_address = Address(
            PubKeyCredential(bytes.fromhex("c" * 56)), NoStakingCredential()
        )
        self.script_address = Address(
            ScriptCredential(self.sample_policy_id), NoStakingCredential()
        )

    def create_mock_oref(self, tx_id_bytes: bytes = None, idx: int = 0) -> TxOutRef:
        """Create a mock transaction output reference"""
        if tx_id_bytes is None:
            tx_id = TxId(bytes.fromhex("a" * 64))
        else:
            tx_id = TxId(tx_id_bytes)
        return TxOutRef(tx_id, idx)

    def create_mock_datum_protocol(self, valid: bool = True) -> DatumProtocol:
        """Create a mock protocol datum"""
        if valid:
            return DatumProtocol(
                protocol_admin=[bytes.fromhex("d" * 56)],
                protocol_fee=1000,
                oracle_id=bytes.fromhex("e" * 56),  # PolicyId is bytes
                projects=[bytes.fromhex("f" * 56)],
            )
        else:
            # Invalid datum (empty admin list)
            return DatumProtocol(
                protocol_admin=[],
                protocol_fee=0,
                oracle_id=bytes.fromhex("0" * 56),
                projects=[],
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
                # Include the UTXO that should be consumed
                consumed_output = self.create_mock_tx_out(self.sample_address)
                inputs = [self.create_mock_tx_in_info(purpose_oref, consumed_output)]
            else:
                inputs = []

        if outputs is None:
            outputs = []

        if mint is None:
            mint = {}

        if signatories is None:
            signatories = [bytes.fromhex("d" * 56)]

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


# Additional utility test class for helper functions
class TestUtilityFunctions(MockCommon):
    """Test utility functions used by the protocol validator"""

    def test_get_minting_purpose(self):
        """Test get_minting_purpose utility function"""
        # Test successful case
        minting_purpose = Minting(self.sample_policy_id)
        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(minting_purpose, tx_info)

        result = get_minting_purpose(context)
        assert isinstance(result, Minting)
        assert result.policy_id == self.sample_policy_id

        # Test failure case with wrong purpose type
        spending_purpose = Spending(self.create_mock_oref())
        wrong_context = self.create_mock_script_context(spending_purpose, tx_info)

        with pytest.raises(AssertionError):
            get_minting_purpose(wrong_context)

    def test_get_spending_purpose(self):
        """Test get_spending_purpose utility function"""
        # Test successful case
        oref = self.create_mock_oref()
        spending_purpose = Spending(oref)
        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(spending_purpose, tx_info)

        result = get_spending_purpose(context)
        assert isinstance(result, Spending)
        assert result.tx_out_ref == oref

        # Test failure case with wrong purpose type
        minting_purpose = Minting(self.sample_policy_id)
        wrong_context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(AssertionError):
            get_spending_purpose(wrong_context)

    def test_unique_token_name(self):
        """Test that unique token names are generated correctly"""
        oref1 = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref2 = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref3 = self.create_mock_oref(bytes.fromhex("a" * 64), 1)  # Same tx, different index

        token1 = unique_token_name(oref1, PREFIX_REFERENCE_NFT)
        token2 = unique_token_name(oref2, PREFIX_REFERENCE_NFT)
        token3 = unique_token_name(oref3, PREFIX_REFERENCE_NFT)

        # All tokens should be different
        assert token1 != token2
        assert token1 != token3
        assert token2 != token3

        # All should start with the prefix
        assert token1.startswith(PREFIX_REFERENCE_NFT)
        assert token2.startswith(PREFIX_REFERENCE_NFT)
        assert token3.startswith(PREFIX_REFERENCE_NFT)

        expected_token_name1 = append_byte_string(
            PREFIX_REFERENCE_NFT,
            sha3_256(append_byte_string(oref1.id.tx_id, cons_byte_string(oref1.idx % 256, b""))),
        )
        if len(expected_token_name1) > 32:
            expected_token_name1 = slice_byte_string(0, 32, expected_token_name1)

        expected_token_name2 = append_byte_string(
            PREFIX_REFERENCE_NFT,
            sha3_256(append_byte_string(oref2.id.tx_id, cons_byte_string(oref2.idx % 256, b""))),
        )
        if len(expected_token_name2) > 32:
            expected_token_name2 = slice_byte_string(0, 32, expected_token_name2)

        expected_token_name3 = append_byte_string(
            PREFIX_REFERENCE_NFT,
            sha3_256(append_byte_string(oref3.id.tx_id, cons_byte_string(oref3.idx % 256, b""))),
        )
        if len(expected_token_name3) > 32:
            expected_token_name3 = slice_byte_string(0, 32, expected_token_name3)

        # All tokens should match the expected names
        assert token1 == expected_token_name1
        assert token2 == expected_token_name2
        assert token3 == expected_token_name3

    def test_has_utxo(self):
        """Test the has_utxo utility function"""
        oref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create context with the UTXO
        address = Address(PubKeyCredential(bytes.fromhex("c" * 56)), NoStakingCredential())
        consumed_output = self.create_mock_tx_out(address)

        input_info = self.create_mock_tx_in_info(oref, consumed_output)
        # input_info = TxInInfo(oref, consumed_output)
        tx_info = self.create_mock_tx_info(inputs=[input_info])

        context = self.create_mock_script_context(Minting(bytes.fromhex("c" * 56)), tx_info)

        # Should find the UTXO
        assert has_utxo(context, oref) == True

        # Should not find a different UTXO
        different_oref = self.create_mock_oref(bytes.fromhex("d" * 64), 0)
        # different_oref = TxOutRef(TxId(bytes.fromhex("d" * 64)), 0)
        assert has_utxo(context, different_oref) == False

    def test_only_one_input_from_address(self):
        """Test only_one_input_from_address utility function"""
        address1 = self.sample_address
        address2 = Address(PubKeyCredential(bytes.fromhex("e" * 56)), NoStakingCredential())

        # Create inputs
        input1 = self.create_mock_tx_in_info(
            self.create_mock_oref(bytes.fromhex("a" * 64), 0),
            self.create_mock_tx_out(address1),
        )
        input2 = self.create_mock_tx_in_info(
            self.create_mock_oref(bytes.fromhex("b" * 64), 0),
            self.create_mock_tx_out(address2),
        )
        input3 = self.create_mock_tx_in_info(
            self.create_mock_oref(bytes.fromhex("c" * 64), 0),
            self.create_mock_tx_out(address1),  # Same address as input1
        )

        # Test with only one input from address1
        assert only_one_input_from_address(address1, [input1, input2]) == True

        # Test with two inputs from address1
        assert only_one_input_from_address(address1, [input1, input2, input3]) == False

        # Test with no inputs from address1
        assert only_one_input_from_address(address1, [input2]) == False

        # Test with empty input list
        assert only_one_input_from_address(address1, []) == False

    def test_only_one_output_to_address(self):
        """Test only_one_output_to_address utility function"""
        address1 = self.sample_address
        address2 = Address(PubKeyCredential(bytes.fromhex("e" * 56)), NoStakingCredential())

        # Create outputs
        output1 = self.create_mock_tx_out(address1)
        output2 = self.create_mock_tx_out(address2)
        output3 = self.create_mock_tx_out(address1)  # Same address as output1

        # Test with only one output to address1
        assert only_one_output_to_address(address1, [output1, output2]) == True

        # Test with two outputs to address1
        assert only_one_output_to_address(address1, [output1, output2, output3]) == False

        # Test with no outputs to address1
        assert only_one_output_to_address(address1, [output2]) == False

        # Test with empty output list
        assert only_one_output_to_address(address1, []) == False

    def test_amount_of_token_in_output(self):
        """Test amount_of_token_in_output utility function"""
        policy_id = self.sample_policy_id
        token_name = b"test_token"
        token = Token(policy_id, token_name)

        # Test output with the token
        output_with_token = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, policy_id: {token_name: 5}}
        )
        assert amount_of_token_in_output(token, output_with_token) == 5

        # Test output without the token
        output_without_token = self.create_mock_tx_out(self.sample_address, value={b"": 2000000})
        assert amount_of_token_in_output(token, output_without_token) == 0

        # Test output with different policy
        different_policy = bytes.fromhex("f" * 56)
        output_different_policy = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, different_policy: {token_name: 3}}
        )
        assert amount_of_token_in_output(token, output_different_policy) == 0

        # Test output with same policy but different token name
        output_different_token = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, policy_id: {b"different_token": 7}},
        )
        assert amount_of_token_in_output(token, output_different_token) == 0

    def test_resolve_linear_input(self):
        """Test resolve_linear_input utility function"""
        oref = self.create_mock_oref()
        spending_purpose = Spending(oref)

        # Test successful case
        contract_address = self.script_address
        correct_input = self.create_mock_tx_in_info(
            oref, self.create_mock_tx_out(contract_address)  # Same oref as in purpose
        )

        tx_info = self.create_mock_tx_info(inputs=[correct_input])

        result = resolve_linear_input(tx_info, 0, spending_purpose)
        assert result.address == contract_address

        # Test failure case - wrong oref
        wrong_oref = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        wrong_input = self.create_mock_tx_in_info(
            wrong_oref, self.create_mock_tx_out(contract_address)  # Different oref
        )

        tx_info_wrong = self.create_mock_tx_info(inputs=[wrong_input])

        with pytest.raises(AssertionError, match="Referenced wrong input"):
            resolve_linear_input(tx_info_wrong, 0, spending_purpose)

        # Test failure case - multiple inputs from same address
        duplicate_input = self.create_mock_tx_in_info(
            self.create_mock_oref(bytes.fromhex("c" * 64), 0),
            self.create_mock_tx_out(contract_address),  # Same address
        )

        tx_info_duplicate = self.create_mock_tx_info(inputs=[correct_input, duplicate_input])

        with pytest.raises(AssertionError, match="More than one input from the contract address"):
            resolve_linear_input(tx_info_duplicate, 0, spending_purpose)

    def test_resolve_linear_output(self):
        """Test resolve_linear_output utility function"""
        contract_address = self.script_address
        user_address = self.sample_address

        # Create previous state input
        previous_input = self.create_mock_tx_out(contract_address)

        # Test successful case
        correct_output = self.create_mock_tx_out(contract_address)  # Same address
        other_output = self.create_mock_tx_out(user_address)  # Different address

        tx_info = self.create_mock_tx_info(outputs=[correct_output, other_output])

        result = resolve_linear_output(previous_input, tx_info, 0)
        assert result.address == contract_address

        # Test failure case - moved funds to different address
        wrong_output = self.create_mock_tx_out(user_address)  # Different address
        tx_info_wrong = self.create_mock_tx_info(outputs=[wrong_output])

        with pytest.raises(AssertionError, match="Moved funds to different address"):
            resolve_linear_output(previous_input, tx_info_wrong, 0)

        # Test failure case - multiple outputs to same address
        duplicate_output = self.create_mock_tx_out(contract_address)  # Same address
        tx_info_duplicate = self.create_mock_tx_info(outputs=[correct_output, duplicate_output])

        with pytest.raises(AssertionError, match="More than one output to the contract address"):
            resolve_linear_output(previous_input, tx_info_duplicate, 0)

    def test_check_token_present(self):
        """Test check_token_present utility function"""
        policy_id = self.sample_policy_id
        token_name = b"test_token"
        # token = Token(policy_id, token_name)

        # Test token present
        output_with_token = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, policy_id: {token_name: 5}}
        )
        assert check_token_present(policy_id, output_with_token) == True

        # Test token not present - no policy
        output_no_policy = self.create_mock_tx_out(self.sample_address, value={b"": 2000000})
        assert check_token_present(policy_id, output_no_policy) == False

        # Test token present with amount 1 (minimum positive)
        output_one_token = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, policy_id: {token_name: 1}}
        )
        assert check_token_present(policy_id, output_one_token) == True


class TestProtocol(MockCommon):
    """Comprehensive test cases for protocol validator"""

    def test_validate_protocol_nft_continues_success(self):
        """Test successful protocol NFT continuation validation"""
        policy_id = self.sample_policy_id
        token_name = b"PROTO_test_token"
        protocol_token = Token(policy_id, token_name)

        # Create protocol output with the NFT
        protocol_output = self.create_mock_tx_out(
            self.script_address, value={b"": 2000000, policy_id: {token_name: 1}}
        )

        # Should not raise any exception
        validate_nft_continues(protocol_output, protocol_token)

    def test_validate_protocol_nft_continues_missing_token(self):
        """Test protocol NFT continuation fails when token is missing"""
        policy_id = self.sample_policy_id
        token_name = b"PROTO_test_token"
        protocol_token = Token(policy_id, token_name)

        # Create protocol output without the NFT
        protocol_output = self.create_mock_tx_out(
            self.script_address, value={b"": 2000000}  # No tokens
        )

        with pytest.raises(AssertionError, match="NFT .* must continue to output"):
            validate_nft_continues(protocol_output, protocol_token)

    def test_validate_protocol_nft_continues_wrong_amount(self):
        """Test protocol NFT continuation fails with wrong token amount"""
        policy_id = self.sample_policy_id
        token_name = b"PROTO_test_token"
        protocol_token = Token(policy_id, token_name)

        # Create protocol output with wrong amount
        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={b"": 2000000, policy_id: {token_name: 2}},  # Wrong amount
        )

        with pytest.raises(AssertionError, match="NFT .* must continue to output"):
            validate_nft_continues(protocol_output, protocol_token)

    def test_extract_protocol_token_from_input_success(self):
        """Test successful protocol token extraction from input"""
        policy_id = self.sample_policy_id
        token_name = b"PROTO_test_token"

        # Create protocol input with token
        protocol_input = self.create_mock_tx_out(
            self.script_address, value={b"": 2000000, policy_id: {token_name: 1}}
        )

        extracted_token = extract_token_from_input(protocol_input)

        assert extracted_token.policy_id == policy_id
        assert extracted_token.token_name == token_name

    def test_extract_protocol_token_from_input_multiple_policies(self):
        """Test protocol token extraction with multiple policies"""
        policy_id1 = bytes.fromhex("a" * 56)
        policy_id2 = bytes.fromhex("b" * 56)
        token_name1 = b"PROTO_token1"
        token_name2 = b"PROTO_token2"

        # Create protocol input with multiple policies
        protocol_input = self.create_mock_tx_out(
            self.script_address,
            value={
                b"": 2000000,  # ADA
                policy_id1: {token_name1: 1},
                policy_id2: {token_name2: 1},
            },
        )

        extracted_token = extract_token_from_input(protocol_input)

        # Should extract the first non-ADA policy found
        assert extracted_token.policy_id in [policy_id1, policy_id2]
        assert extracted_token.token_name in [token_name1, token_name2]

    def test_extract_protocol_token_from_input_no_tokens(self):
        """Test protocol token extraction fails with no tokens"""
        # Create protocol input with only ADA
        protocol_input = self.create_mock_tx_out(
            self.script_address, value={b"": 2000000}  # Only ADA
        )

        with pytest.raises(AssertionError, match="Token not found in transaction input"):
            extract_token_from_input(protocol_input)

    def test_validate_datum_update_success(self):
        """Test successful datum update validation"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create new datum with only fee change
        new_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],  # Same
            protocol_fee=2000,  # Changed
            oracle_id=bytes.fromhex("a" * 56),  # Same
            projects=[bytes.fromhex("b" * 56)],  # Same
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_admin_change_success(self):
        """Test successful admin update validation"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[
                bytes.fromhex("b" * 56),
                bytes.fromhex("c" * 56),
            ],  # Changed admin list
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_oracle_change_success(self):
        """Test successful oracle ID update validation"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("c" * 56),  # Changed oracle
            projects=[bytes.fromhex("b" * 56)],
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_negative_fee_fails(self):
        """Test datum update fails with negative fee"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=-100,  # Negative fee
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        with pytest.raises(AssertionError, match="Protocol fee must be non-negative"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_empty_admin_list_fails(self):
        """Test datum update fails with empty admin list"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[],  # Empty admin list
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        with pytest.raises(AssertionError, match="Protocol must have at least one admin"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_too_many_admins_fails(self):
        """Test datum update fails with too many admins"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[
                bytes.fromhex("a" * 56),
                bytes.fromhex("b" * 56),
                bytes.fromhex("c" * 56),
                bytes.fromhex("d" * 56),
            ],  # 4 admins (too many)
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        with pytest.raises(AssertionError, match="Protocol cannot have more than"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_max_admins_success(self):
        """Test datum update succeeds with maximum allowed admins (3)"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[
                bytes.fromhex("a" * 56),
                bytes.fromhex("b" * 56),
                bytes.fromhex("c" * 56),
            ],  # 3 admins (maximum allowed)
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_empty_projects_fails(self):
        """Test datum update fails with empty projects list"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[],  # Empty projects list
        )

        with pytest.raises(AssertionError, match="Protocol must have at least one project"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_too_many_projects_fails(self):
        """Test datum update fails with too many projects"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create list with 11 projects (too many)
        too_many_projects = [bytes.fromhex(f"{i:02x}" + "0" * 54) for i in range(11)]
        new_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=too_many_projects,
        )

        with pytest.raises(AssertionError, match="Protocol cannot have more than 10 projects"):
            validate_datum_update(old_datum, new_datum)

    def test_validate_datum_update_projects_change_success(self):
        """Test successful projects update validation"""
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        new_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[
                bytes.fromhex("c" * 56),
                bytes.fromhex("d" * 56),
            ],  # Changed projects
        )

        # Should not raise any exception
        validate_datum_update(old_datum, new_datum)

    def test_validator_update_protocol_success(self):
        """Test successful UpdateProtocol validation"""
        # Create test data
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        protocol_token_name = unique_token_name(oref_protocol, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref_protocol, PREFIX_USER_NFT)  # Same oref for pairing

        # Create old datum
        old_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create new datum (only fee changed)
        new_datum = DatumProtocol(
            protocol_admin=[bytes.fromhex("a" * 56)],
            protocol_fee=2000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        protocol_output_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, policy_id: {user_token_name: 1}}
        )

        # Create transaction inputs
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        # Create transaction info
        tx_info = self.create_mock_tx_info(
            inputs=[user_input, protocol_input],  # user at index 0, protocol at index 1
            outputs=[protocol_output_utxo],
        )

        # Create script context
        spending_purpose = Spending(oref_protocol)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Create redeemer
        redeemer = UpdateProtocol(
            protocol_input_index=1, user_input_index=0, protocol_output_index=0
        )

        # Should not raise any exception
        protocol_validator(oref_protocol, old_datum, redeemer, context)

    def test_validator_update_protocol_missing_user_token_completely(self):
        """Test UpdateProtocol fails when user has no token at all for the policy"""
        # Create test data
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        protocol_token_name = unique_token_name(oref_protocol, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref_protocol, PREFIX_USER_NFT)  # Correct pairing

        # Create datums
        old_datum = self.create_mock_datum_protocol()
        new_datum = DatumProtocol(
            protocol_admin=old_datum.protocol_admin,
            protocol_fee=2000,  # Only fee changed
            oracle_id=old_datum.oracle_id,
            projects=old_datum.projects,
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        protocol_output_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        # User has NO token for this policy (only ADA)
        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000},  # Only ADA, no tokens for policy_id
        )

        # Create transaction
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[user_input, protocol_input], outputs=[protocol_output_utxo]
        )

        spending_purpose = Spending(oref_protocol)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProtocol(
            protocol_input_index=1, user_input_index=0, protocol_output_index=0
        )
        with pytest.raises(AssertionError, match="User does not have required token"):
            protocol_validator(oref_protocol, old_datum, redeemer, context)

    def test_validator_update_protocol_user_has_different_policy_token(self):
        """Test UpdateProtocol when user has token from completely different policy"""
        # Create test data
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        different_policy_id = bytes.fromhex("f" * 56)  # Completely different policy

        protocol_token_name = unique_token_name(oref_protocol, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(
            oref_protocol, PREFIX_USER_NFT
        )  # Correct name but will be under wrong policy

        # Create datums
        old_datum = self.create_mock_datum_protocol()
        new_datum = DatumProtocol(
            protocol_admin=old_datum.protocol_admin,
            protocol_fee=2000,
            oracle_id=old_datum.oracle_id,
            projects=old_datum.projects,
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        protocol_output_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        # User has token with correct name but under different policy
        user_input_utxo = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                different_policy_id: {user_token_name: 1},
            },  # Wrong policy!
        )

        # Create transaction
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[user_input, protocol_input], outputs=[protocol_output_utxo]
        )

        spending_purpose = Spending(oref_protocol)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProtocol(
            protocol_input_index=1, user_input_index=0, protocol_output_index=0
        )

        with pytest.raises(AssertionError, match="User does not have required token"):
            protocol_validator(oref_protocol, old_datum, redeemer, context)

    def test_validator_update_protocol_invalid_datum_change(self):
        """Test UpdateProtocol fails with invalid admin count"""
        # Create test data
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        protocol_token_name = unique_token_name(oref_protocol, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref_protocol, PREFIX_USER_NFT)

        # Create datums with invalid change (too many admins)
        old_datum = self.create_mock_datum_protocol()
        new_datum = DatumProtocol(
            protocol_admin=[
                bytes.fromhex("a" * 56),
                bytes.fromhex("b" * 56),
                bytes.fromhex("c" * 56),
                bytes.fromhex("d" * 56),
            ],  # 4 admins (too many)
            protocol_fee=old_datum.protocol_fee,
            oracle_id=old_datum.oracle_id,
            projects=old_datum.projects,
        )

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        protocol_output_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(new_datum),
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, policy_id: {user_token_name: 1}}
        )

        # Create transaction
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[user_input, protocol_input], outputs=[protocol_output_utxo]
        )

        spending_purpose = Spending(oref_protocol)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProtocol(
            protocol_input_index=1, user_input_index=0, protocol_output_index=0
        )

        # Should fail due to too many admins
        with pytest.raises(AssertionError, match="Protocol cannot have more than"):
            protocol_validator(oref_protocol, old_datum, redeemer, context)

    def test_validator_update_protocol_no_output_datum(self):
        """Test UpdateProtocol fails when output has no datum"""
        # Create test data
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_user = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        policy_id = self.sample_policy_id
        protocol_token_name = unique_token_name(oref_protocol, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref_protocol, PREFIX_USER_NFT)

        old_datum = self.create_mock_datum_protocol()

        # Create UTxOs
        protocol_input_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(old_datum),
        )

        # Protocol output without datum
        protocol_output_utxo = self.create_mock_tx_out(
            self.script_address,
            value={b"": 10000000, policy_id: {protocol_token_name: 1}},
            # No datum provided
        )

        user_input_utxo = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000, policy_id: {user_token_name: 1}}
        )

        # Create transaction
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_input_utxo)
        user_input = self.create_mock_tx_in_info(oref_user, user_input_utxo)

        tx_info = self.create_mock_tx_info(
            inputs=[user_input, protocol_input], outputs=[protocol_output_utxo]
        )

        spending_purpose = Spending(oref_protocol)
        context = self.create_mock_script_context(spending_purpose, tx_info)

        redeemer = UpdateProtocol(
            protocol_input_index=1, user_input_index=0, protocol_output_index=0
        )

        # Should fail because output has no datum
        with pytest.raises(AssertionError):
            protocol_validator(oref_protocol, old_datum, redeemer, context)

    def test_validator_end_protocol_single_admin_signature_success(self):
        """Test EndProtocol succeeds when single admin signs the transaction"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create protocol datum with single admin
        admin_pkh = bytes.fromhex("abc123" + "0" * 50)
        protocol_datum = DatumProtocol(
            protocol_admin=[admin_pkh],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        redeemer = EndProtocol(protocol_input_index=0)

        # Create tx_info with admin signature
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(inputs=[protocol_input], signatories=[admin_pkh])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should not raise any exception
        protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_end_protocol_multiple_admins_one_signs(self):
        """Test EndProtocol succeeds when one of multiple admins signs"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create protocol datum with multiple admins
        admin1_pkh = bytes.fromhex("abc123" + "0" * 50)
        admin2_pkh = bytes.fromhex("def456" + "0" * 50)
        admin3_pkh = bytes.fromhex("789fed" + "0" * 50)

        protocol_datum = DatumProtocol(
            protocol_admin=[admin1_pkh, admin2_pkh, admin3_pkh],
            protocol_fee=1500,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        redeemer = EndProtocol(protocol_input_index=0)

        # Create tx_info with only admin2 signature (should be enough)
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(inputs=[protocol_input], signatories=[admin2_pkh])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should not raise any exception
        protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_end_protocol_multiple_admins_multiple_sign(self):
        """Test EndProtocol succeeds when multiple admins sign"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create protocol datum with multiple admins
        admin1_pkh = bytes.fromhex("abc123" + "0" * 50)
        admin2_pkh = bytes.fromhex("def456" + "0" * 50)
        admin3_pkh = bytes.fromhex("789fed" + "0" * 50)

        protocol_datum = DatumProtocol(
            protocol_admin=[admin1_pkh, admin2_pkh, admin3_pkh],
            protocol_fee=2000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        redeemer = EndProtocol(protocol_input_index=0)

        # Create tx_info with multiple admin signatures
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input], signatories=[admin1_pkh, admin3_pkh]
        )
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should not raise any exception
        protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_end_protocol_no_signatures_fails(self):
        """Test EndProtocol fails when no signatures provided"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create protocol datum with admin
        admin_pkh = bytes.fromhex("abc123" + "0" * 50)
        protocol_datum = DatumProtocol(
            protocol_admin=[admin_pkh],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        redeemer = EndProtocol(protocol_input_index=0)

        # Create tx_info with no signatures
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(inputs=[protocol_input], signatories=[])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail due to missing admin signature
        with pytest.raises(
            AssertionError, match="EndProtocol requires signature from protocol admin"
        ):
            protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_end_protocol_wrong_signatures_fails(self):
        """Test EndProtocol fails when non-admin signatures provided"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create protocol datum with admin
        admin_pkh = bytes.fromhex("abc123" + "0" * 50)
        protocol_datum = DatumProtocol(
            protocol_admin=[admin_pkh],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        redeemer = EndProtocol(protocol_input_index=0)

        # Create tx_info with wrong (non-admin) signatures
        wrong_pkh1 = bytes.fromhex("111111" + "0" * 50)
        wrong_pkh2 = bytes.fromhex("222222" + "0" * 50)
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(
            inputs=[protocol_input], signatories=[wrong_pkh1, wrong_pkh2]
        )
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail due to no valid admin signature
        with pytest.raises(
            AssertionError, match="EndProtocol requires signature from protocol admin"
        ):
            protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_end_protocol_empty_admin_list_fails(self):
        """Test EndProtocol fails when protocol admin list is empty"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create protocol datum with empty admin list
        protocol_datum = DatumProtocol(
            protocol_admin=[],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        redeemer = EndProtocol(protocol_input_index=0)

        # Create tx_info with any signature (won't matter since admin list is empty)
        random_pkh = bytes.fromhex("abcdef" + "0" * 50)
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(inputs=[protocol_input], signatories=[random_pkh])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should fail due to empty admin list
        with pytest.raises(
            AssertionError, match="EndProtocol requires signature from protocol admin"
        ):
            protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_end_protocol_correct_protocol_input_index(self):
        """Test EndProtocol succeeds with correct protocol_input_index"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref_other = self.create_mock_oref(bytes.fromhex("b" * 64), 1)

        # Create protocol datum with admin
        admin_pkh = bytes.fromhex("abc123" + "0" * 50)
        protocol_datum = DatumProtocol(
            protocol_admin=[admin_pkh],
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        # Create other input (not protocol) with different address
        other_address = Address(bytes.fromhex("0" * 56), None)
        other_output = self.create_mock_tx_out(other_address)
        other_input = self.create_mock_tx_in_info(oref_other, other_output)

        redeemer = EndProtocol(protocol_input_index=1)  # Protocol is at index 1

        # Create tx_info with inputs in specific order
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(
            inputs=[other_input, protocol_input],  # Protocol at index 1
            signatories=[admin_pkh],
        )
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should not raise any exception
        protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_end_protocol_large_admin_list_one_valid_signer(self):
        """Test EndProtocol with large admin list but only one valid signer"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create protocol datum with many admins
        valid_admin = bytes.fromhex("aabbcc" + "0" * 50)
        admin_list = [bytes.fromhex(f"{i:06x}" + "0" * 50) for i in range(100)]
        admin_list.append(valid_admin)  # Add our valid admin to the end

        protocol_datum = DatumProtocol(
            protocol_admin=admin_list,
            protocol_fee=1000,
            oracle_id=bytes.fromhex("a" * 56),
            projects=[bytes.fromhex("b" * 56)],
        )

        # Create protocol input with datum
        protocol_output = self.create_mock_tx_out(
            self.sample_address, datum=SomeOutputDatum(protocol_datum)
        )
        protocol_input = self.create_mock_tx_in_info(oref_protocol, protocol_output)

        redeemer = EndProtocol(protocol_input_index=0)

        # Create tx_info with valid admin signature
        spending_purpose = Spending(oref_protocol)
        tx_info = self.create_mock_tx_info(inputs=[protocol_input], signatories=[valid_admin])
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # Should not raise any exception
        protocol_validator(oref_protocol, protocol_datum, redeemer, context)

    def test_validator_invalid_redeemer_type(self):
        """Test validator fails with invalid redeemer type"""
        oref_protocol = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        old_datum = self.create_mock_datum_protocol()
        invalid_redeemer = PlutusData()  # Invalid redeemer type

        spending_purpose = Spending(self.create_mock_oref())
        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(spending_purpose, tx_info)

        with pytest.raises(AssertionError, match="Invalid redeemer type"):
            protocol_validator(oref_protocol, old_datum, invalid_redeemer, context)


class TestMintingContract(MockCommon):
    """Test cases for the minting contract validator"""

    def test_mint_successful_case(self):
        """Test successful minting of protocol and user NFTs"""
        # Create unique UTXO reference
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create the consumed UTXO
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        # Generate expected token names
        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(consumed_utxo_ref, PREFIX_USER_NFT)

        # Create mint value
        mint_value = {self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}}

        # Create transaction info
        tx_info = self.create_mock_tx_info(inputs=[consumed_input], mint=mint_value)

        # Create minting context
        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        # Create redeemer
        redeemer = Mint()

        protocol_nft_validator(consumed_utxo_ref, redeemer, context)  # unique_utxo_index = 0

    def test_mint_wrong_token_count_fails(self):
        """Test minting fails when not exactly 2 tokens are minted"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(consumed_utxo_ref, PREFIX_USER_NFT)

        # Try minting 3 tokens instead of 2
        mint_value = {
            self.sample_policy_id: {
                protocol_token_name: 1,
                user_token_name: 1,
                b"extra_token": 1,  # Extra token
            }
        }

        tx_info = self.create_mock_tx_info(inputs=[consumed_input], mint=mint_value)

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Mint()

        with pytest.raises(AssertionError, match="Must mint exactly 2 tokens"):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)

    def test_mint_wrong_protocol_token_amount_fails(self):
        """Test minting fails when protocol token amount is not 1"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(consumed_utxo_ref, PREFIX_USER_NFT)

        # Mint 2 protocol tokens instead of 1
        mint_value = {
            self.sample_policy_id: {
                protocol_token_name: 2,  # Wrong amount
                user_token_name: 1,
            }
        }

        tx_info = self.create_mock_tx_info(inputs=[consumed_input], mint=mint_value)

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Mint()

        with pytest.raises(AssertionError, match="Must mint exactly 1 protocol token"):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)

    def test_mint_wrong_user_token_amount_fails(self):
        """Test minting fails when user token amount is not 1"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(consumed_utxo_ref, PREFIX_USER_NFT)

        # Mint 0 user tokens
        mint_value = {
            self.sample_policy_id: {
                protocol_token_name: 1,
                user_token_name: 3,  # Wrong amount
            }
        }

        tx_info = self.create_mock_tx_info(inputs=[consumed_input], mint=mint_value)

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Mint()

        with pytest.raises(AssertionError, match="Must mint exactly 1 user token"):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)

    def test_burn_successful_case(self):
        """Test successful burning of tokens"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(consumed_utxo_ref, PREFIX_USER_NFT)

        # Burn tokens (negative amounts)
        mint_value = {self.sample_policy_id: {protocol_token_name: -1, user_token_name: -1}}

        # Create outputs with no tokens of this policy
        output_no_tokens = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000}  # Only ADA
        )

        tx_info = self.create_mock_tx_info(
            inputs=[consumed_input], outputs=[output_no_tokens], mint=mint_value
        )

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Burn()

        # Should not raise any exception
        protocol_nft_validator(consumed_utxo_ref, redeemer, context)

    def test_burn_wrong_policy_fails(self):
        """Test burning fails when burning with wrong policy"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        # wrong_oref = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        wrong_policy_id = bytes.fromhex("a" * 56)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(consumed_utxo_ref, PREFIX_USER_NFT)

        # Burn tokens (negative amounts)
        mint_value = {wrong_policy_id: {protocol_token_name: -1, user_token_name: -1}}

        output_with_tokens = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {user_token_name: 1},  # Contains tokens!
            },
        )

        # Create outputs with no tokens of this policy
        # output_no_tokens = self.create_mock_tx_out(
        #     self.sample_address,
        #     value={b"": 2000000}  # Only ADA
        # )

        tx_info = self.create_mock_tx_info(
            inputs=[consumed_input], outputs=[output_with_tokens], mint=mint_value
        )

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Burn()

        with pytest.raises(
            AssertionError,
            match="Must burn exactly 2 tokens \\(protocol \\+ user pair\\)",
        ):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)

    def test_burn_positive_amount_fails(self):
        """Test burning fails when amounts are positive"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)

        # Try to burn with positive amount
        mint_value = {
            self.sample_policy_id: {protocol_token_name: 1}  # Positive amount (should be negative)
        }

        tx_info = self.create_mock_tx_info(inputs=[consumed_input], mint=mint_value)

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Burn()

        with pytest.raises(
            AssertionError,
            match="Must burn exactly 2 tokens \\(protocol \\+ user pair\\)",
        ):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)

    def test_burn_tokens_in_outputs_fails(self):
        """Test burning fails when tokens are sent to outputs"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(consumed_utxo_ref, PREFIX_USER_NFT)

        # Burn tokens (negative amounts)
        mint_value = {self.sample_policy_id: {protocol_token_name: -1, user_token_name: -1}}

        # Create output that contains tokens of this policy
        output_with_tokens = self.create_mock_tx_out(
            self.sample_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {protocol_token_name: 1},  # Contains tokens!
            },
        )

        tx_info = self.create_mock_tx_info(
            inputs=[consumed_input], outputs=[output_with_tokens], mint=mint_value
        )

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Burn()

        with pytest.raises(AssertionError, match="Cannot send tokens to outputs when burning"):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)

    def test_invalid_redeemer_type_fails(self):
        """Test minting fails with invalid redeemer type"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        tx_info = self.create_mock_tx_info(inputs=[consumed_input])

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        invalid_redeemer = PlutusData()  # Invalid redeemer type

        with pytest.raises(AssertionError, match="Invalid redeemer type"):
            protocol_nft_validator(0, invalid_redeemer, context)

    def test_wrong_utxo_reference_fails(self):
        """Test minting fails when unique_utxo_index is wrong"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        other_utxo_ref = self.create_mock_oref(bytes.fromhex("b" * 64), 0)

        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        other_utxo = self.create_mock_tx_out(self.sample_address)

        other_input = self.create_mock_tx_in_info(other_utxo_ref, other_utxo)

        protocol_token_name = unique_token_name(other_utxo_ref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(other_utxo_ref, PREFIX_USER_NFT)

        mint_value = {self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}}

        tx_info = self.create_mock_tx_info(
            inputs=[other_input], mint=mint_value  # consumed_input is at index 1
        )

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Mint()

        with pytest.raises(AssertionError, match="UTxO not consumed"):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)

        # Correct index should work
        protocol_nft_validator(other_utxo_ref, redeemer, context)  # Should not raise

    def test_mint_only_one_token_fails(self):
        """Test minting fails when only one token is minted"""
        consumed_utxo_ref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        consumed_utxo = self.create_mock_tx_out(self.sample_address)
        consumed_input = self.create_mock_tx_in_info(consumed_utxo_ref, consumed_utxo)

        protocol_token_name = unique_token_name(consumed_utxo_ref, PREFIX_REFERENCE_NFT)

        # Mint only protocol token, not user token
        mint_value = {
            self.sample_policy_id: {
                protocol_token_name: 1
                # Missing user token
            }
        }

        tx_info = self.create_mock_tx_info(inputs=[consumed_input], mint=mint_value)

        minting_purpose = Minting(self.sample_policy_id)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        redeemer = Mint()

        with pytest.raises(AssertionError, match="Must mint exactly 2 tokens"):
            protocol_nft_validator(consumed_utxo_ref, redeemer, context)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
