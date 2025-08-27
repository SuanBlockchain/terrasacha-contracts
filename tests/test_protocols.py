"""
Mock objects and comprehensive test cases for the OpShin protocol validator
"""

from typing import Dict, List, Optional

import pytest
from opshin.ledger.api_v2 import *

# Import OpShin types - adjust these imports based on your project structure
from opshin.prelude import *
from opshin.std.builtins import *

from src.terrasacha_contracts.validators.protocol import validator
from utils.types import Burn, DatumProtocol, Mint

# Mock imports for the validator and types (adjust paths as needed)
from utils.utils import (
    PREFIX_PROTOCOL_NFT,
    PREFIX_USER_NFT,
    find_script_address,
    find_token_output,
    has_utxo,
    unique_token_name,
)

# from dataclasses import dataclass


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

    def create_mock_oref(self, tx_id: bytes = None, idx: int = 0) -> TxOutRef:
        """Create a mock transaction output reference"""
        if tx_id is None:
            tx_id = bytes.fromhex("a" * 64)
        return TxOutRef(tx_id, idx)

    def create_mock_datum_protocol(self, valid: bool = True) -> DatumProtocol:
        """Create a mock protocol datum"""
        if valid:
            return DatumProtocol(
                protocol_admin=[bytes.fromhex("d" * 56)],
                protocol_fee=1000,
                oracle_id=b"oracle_123",
                project_id=b"project_456",
            )
        else:
            # Invalid datum (empty admin list)
            return DatumProtocol(
                protocol_admin=[], protocol_fee=0, oracle_id=b"", project_id=b""
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
            signatories=[bytes.fromhex("d" * 56)],
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

    def test_unique_token_name(self):
        """Test that unique token names are generated correctly"""
        oref1 = self.create_mock_oref(bytes.fromhex("a" * 64), 0)
        oref2 = self.create_mock_oref(bytes.fromhex("b" * 64), 0)
        oref3 = self.create_mock_oref(
            bytes.fromhex("a" * 64), 1
        )  # Same tx, different index

        token1 = unique_token_name(oref1, PREFIX_PROTOCOL_NFT)
        token2 = unique_token_name(oref2, PREFIX_PROTOCOL_NFT)
        token3 = unique_token_name(oref3, PREFIX_PROTOCOL_NFT)

        # All tokens should be different
        assert token1 != token2
        assert token1 != token3
        assert token2 != token3

        # All should start with the prefix
        assert token1.startswith(PREFIX_PROTOCOL_NFT)
        assert token2.startswith(PREFIX_PROTOCOL_NFT)
        assert token3.startswith(PREFIX_PROTOCOL_NFT)

        expected_token_name1 = PREFIX_PROTOCOL_NFT + cons_byte_string(
            oref1.idx, sha3_256(oref1.id)
        )
        expected_token_name2 = PREFIX_PROTOCOL_NFT + cons_byte_string(
            oref2.idx, sha3_256(oref2.id)
        )
        expected_token_name3 = PREFIX_PROTOCOL_NFT + cons_byte_string(
            oref3.idx, sha3_256(oref3.id)
        )
        # All tokens should match the expected names
        assert token1 == expected_token_name1
        assert token2 == expected_token_name2
        assert token3 == expected_token_name3

    def test_has_utxo(self):
        """Test the has_utxo utility function"""
        oref = self.create_mock_oref(bytes.fromhex("a" * 64), 0)

        # Create context with the UTXO
        address = Address(
            PubKeyCredential(bytes.fromhex("c" * 56)), NoStakingCredential()
        )
        consumed_output = self.create_mock_tx_out(address)

        input_info = self.create_mock_tx_in_info(oref, consumed_output)
        # input_info = TxInInfo(oref, consumed_output)
        tx_info = self.create_mock_tx_info(inputs=[input_info])

        context = self.create_mock_script_context(
            Minting(bytes.fromhex("c" * 56)), tx_info
        )

        # Should find the UTXO
        assert has_utxo(context, oref) == True

        # Should not find a different UTXO
        different_oref = self.create_mock_oref(bytes.fromhex("d" * 64), 0)
        # different_oref = TxOutRef(TxId(bytes.fromhex("d" * 64)), 0)
        assert has_utxo(context, different_oref) == False

    def test_find_script_address(self):
        """Test the find_script_address utility function"""
        policy_id = bytes.fromhex("a" * 56)
        address = find_script_address(policy_id)

        assert isinstance(address.payment_credential, ScriptCredential)
        assert address.payment_credential.credential_hash == policy_id
        assert isinstance(address.staking_credential, NoStakingCredential)

    def test_find_token_output(self):
        """Test finding protocol output in transaction outputs"""
        policy_id = bytes.fromhex("a" * 56)
        token_name = b"protocol_token"

        # Create outputs with and without the token
        correct_output = TxOut(
            Address(ScriptCredential(policy_id), NoStakingCredential()),
            {b"": 2000000, policy_id: {token_name: 1}},
            NoOutputDatum(),
            NoScriptHash(),
        )

        wrong_output = TxOut(
            Address(PubKeyCredential(bytes.fromhex("b" * 56)), NoStakingCredential()),
            {b"": 2000000},
            NoOutputDatum(),
            NoScriptHash(),
        )

        outputs = [wrong_output, correct_output]

        found_output = find_token_output(outputs, policy_id, token_name)
        assert found_output == correct_output

        # Test when token not found
        missing_token = b"missing_token"
        not_found = find_token_output(outputs, policy_id, missing_token)
        assert not_found is None


class TestProtocol(MockCommon):
    """Comprehensive test cases for protocol validator"""

    def test_not_minting_purpose_fails(self):
        """Test that validator fails when not minting"""

        oref = self.create_mock_oref()
        redeemer = Mint()

        # Create spending purpose instead of minting
        spending_purpose = Spending(oref)
        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(spending_purpose, tx_info)

        # This should fail because purpose is not Minting
        with pytest.raises(AssertionError, match="Wrong script purpose"):
            validator(oref, redeemer, context)

    def test_utxo_not_consumed_fails(self):
        """Test that validator fails when specified UTXO is not consumed"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        # Create minting purpose but don't include the UTXO in inputs
        minting_purpose = Minting(self.sample_policy_id)
        tx_info = self.create_mock_tx_info(inputs=[])  # Empty inputs
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(AssertionError, match="UTxO not consumed"):
            validator(oref, redeemer, context)

    def test_protocol_token_not_in_outputs_fails(self):
        """Test that validator fails when protocol token is not in outputs"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)

        # Create inputs with the consumed UTXO
        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        # Create outputs without protocol token
        outputs = [self.create_mock_tx_out(self.sample_address)]

        tx_info = self.create_mock_tx_info(inputs=inputs, outputs=outputs)
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(AssertionError, match="Protocol NFT output not found"):
            validator(oref, redeemer, context)

    def test_user_token_not_in_outputs_fails(self):
        """Test that validator fails when user token is not in outputs"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)

        # Create protocol output but no user output
        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={b"": 2000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(self.create_mock_datum_protocol()),
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(inputs=inputs, outputs=[protocol_output])
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(AssertionError, match="User NFT output not found"):
            validator(oref, redeemer, context)

    def test_no_datum_fails(self):
        """Test that validator fails when protocol output has no datum"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # Create protocol output without datum
        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={b"": 2000000, self.sample_policy_id: {protocol_token_name: 1}},
            # No datum provided
        )

        user_output = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {user_token_name: 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[protocol_output, user_output],
            mint={self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}},
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(
            AssertionError, match="Protocol output must have inlined datum"
        ):
            validator(oref, redeemer, context)

    def test_invalid_protocol_datum_type_fails(self):
        """Test that validator fails when protocol datum is not DatumProtocol type"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # Create protocol output with wrong datum type
        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={b"": 2000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(PlutusData()),  # Wrong datum type
        )

        user_output = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {user_token_name: 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[protocol_output, user_output],
            mint={self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}},
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(
            AssertionError, match="Protocol output datum must be DatumProtocol"
        ):
            validator(oref, redeemer, context)

    def test_protocol_nft_wrong_address_fails(self):
        """Test that validator fails when protocol NFT is not sent to correct script address"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # Send protocol NFT to wrong address (user address instead of script)
        protocol_output = self.create_mock_tx_out(
            self.sample_address,  # Wrong address!
            value={b"": 2000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(self.create_mock_datum_protocol()),
        )

        user_output = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {user_token_name: 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[protocol_output, user_output],
            mint={self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}},
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(
            AssertionError, match="Protocol NFT not sent to correct script address"
        ):
            validator(oref, redeemer, context)

    # def test_protocol_token_not_nft_fails(self):
    #     """Test that validator fails when protocol token is not an NFT (amount != 1)"""
    #     oref = self.create_mock_oref()
    #     redeemer = Mint()

    #     minting_purpose = Minting(self.sample_policy_id)
    #     protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
    #     user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

    #     # Create protocol output with multiple tokens
    #     protocol_output = self.create_mock_tx_out(
    #         self.script_address,
    #         value={
    #             b"": 2000000,
    #             self.sample_policy_id: {protocol_token_name: 5}  # Not an NFT!
    #         },
    #         datum=SomeOutputDatum(self.create_mock_datum_protocol())
    #     )

    #     user_output = self.create_mock_tx_out(
    #         self.sample_address,
    #         value={
    #             b"": 2000000,
    #             self.sample_policy_id: {user_token_name: 1}
    #         }
    #     )

    #     consumed_output = self.create_mock_tx_out(self.sample_address)
    #     inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

    #     tx_info = self.create_mock_tx_info(
    #         inputs=inputs,
    #         outputs=[protocol_output, user_output],
    #         mint={self.sample_policy_id: {protocol_token_name: 5, user_token_name: 1}}
    #     )
    #     context = self.create_mock_script_context(minting_purpose, tx_info)

    #     with pytest.raises(AssertionError, match="Protocol output must contain exactly 1 token"):
    #         validator(oref, redeemer, context)

    # def test_user_token_not_nft_fails(self):
    #     """Test that validator fails when user token is not an NFT (amount != 1)"""
    #     oref = self.create_mock_oref()
    #     redeemer = Mint()

    #     minting_purpose = Minting(self.sample_policy_id)
    #     protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
    #     user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

    #     protocol_output = self.create_mock_tx_out(
    #         self.script_address,
    #         value={
    #             b"": 2000000,
    #             self.sample_policy_id: {protocol_token_name: 1}
    #         },
    #         datum=SomeOutputDatum(self.create_mock_datum_protocol())
    #     )

    #     # Create user output with multiple tokens
    #     user_output = self.create_mock_tx_out(
    #         self.sample_address,
    #         value={
    #             b"": 2000000,
    #             self.sample_policy_id: {user_token_name: 3}  # Not an NFT!
    #         }
    #     )

    #     consumed_output = self.create_mock_tx_out(self.sample_address)
    #     inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

    #     tx_info = self.create_mock_tx_info(
    #         inputs=inputs,
    #         outputs=[protocol_output, user_output],
    #         mint={self.sample_policy_id: {protocol_token_name: 1, user_token_name: 3}}
    #     )
    #     context = self.create_mock_script_context(minting_purpose, tx_info)

    #     with pytest.raises(AssertionError, match="User output must contain exactly 1 token"):
    #         validator(oref, redeemer, context)

    def test_unauthorized_token_policies_fails(self):
        """Test that validator fails when outputs contain unauthorized token policies"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)
        unauthorized_policy = bytes.fromhex("f" * 56)

        # Create protocol output with unauthorized tokens
        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={
                b"": 2000000,
                self.sample_policy_id: {protocol_token_name: 1},
                unauthorized_policy: {b"evil_token": 1},  # Unauthorized policy!
            },
            datum=SomeOutputDatum(self.create_mock_datum_protocol()),
        )

        user_output = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {user_token_name: 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[protocol_output, user_output],
            mint={self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}},
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(
            AssertionError, match="Outputs contain unauthorized token policies"
        ):
            validator(oref, redeemer, context)

    def test_more_than_two_tokens_minted_fails(self):
        """Test that validator fails when more than 2 tokens are minted"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)
        extra_token_name = b"extra_token"

        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={b"": 2000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(self.create_mock_datum_protocol()),
        )

        user_output = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {user_token_name: 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[protocol_output, user_output],
            mint={
                self.sample_policy_id: {
                    protocol_token_name: 1,
                    user_token_name: 1,
                    extra_token_name: 1,  # Extra token!
                }
            },
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(AssertionError, match="Must mint exactly 2 tokens"):
            validator(oref, redeemer, context)

    def test_burn_with_tokens_in_outputs_fails(self):
        """Test that validator fails when burning but tokens are sent to outputs"""
        oref = self.create_mock_oref()
        redeemer = Burn()

        minting_purpose = Minting(self.sample_policy_id)

        # Create output with tokens (should be 0 when burning)
        output_with_tokens = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {b"some_token": 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[output_with_tokens],
            mint={self.sample_policy_id: {b"some_token": -1}},  # Burning
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(
            AssertionError, match="Cannot send tokens to outputs when burning"
        ):
            validator(oref, redeemer, context)

    def test_successful_minting(self):
        """Test successful minting scenario"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # Create valid protocol output
        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={b"": 2000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(self.create_mock_datum_protocol()),
        )

        # Create valid user output
        user_output = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {user_token_name: 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[protocol_output, user_output],
            mint={self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}},
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        # This should not raise any exceptions
        try:
            validator(oref, redeemer, context)
        except Exception as e:
            pytest.fail(f"Valid minting transaction failed: {e}")

    def test_successful_burning(self):
        """Test successful burning scenario"""
        oref = self.create_mock_oref()
        redeemer = Burn()

        minting_purpose = Minting(self.sample_policy_id)

        # Create outputs without any tokens from this policy
        output_without_tokens = self.create_mock_tx_out(
            self.sample_address, value={b"": 2000000}  # Only ADA, no tokens
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[output_without_tokens],
            mint={self.sample_policy_id: {b"token_to_burn": -1}},  # Negative = burning
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        # This should not raise any exceptions
        try:
            validator(oref, redeemer, context)
        except Exception as e:
            pytest.fail(f"Valid burning transaction failed: {e}")

    def test_invalid_redeemer_type_fails(self):
        """Test that validator fails with invalid redeemer type"""
        oref = self.create_mock_oref()
        invalid_redeemer = PlutusData()  # Invalid type

        minting_purpose = Minting(self.sample_policy_id)
        tx_info = self.create_mock_tx_info()
        context = self.create_mock_script_context(minting_purpose, tx_info)

        with pytest.raises(AssertionError, match="Invalid redeemer type"):
            validator(oref, invalid_redeemer, context)

    def test_invalid_protocol_datum_constraints_fail(self):
        """Test that validator fails with invalid protocol datum constraints"""
        oref = self.create_mock_oref()
        redeemer = Mint()

        minting_purpose = Minting(self.sample_policy_id)
        protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        # Create invalid protocol datum
        invalid_datum = self.create_mock_datum_protocol(valid=False)

        protocol_output = self.create_mock_tx_out(
            self.script_address,
            value={b"": 2000000, self.sample_policy_id: {protocol_token_name: 1}},
            datum=SomeOutputDatum(invalid_datum),
        )

        user_output = self.create_mock_tx_out(
            self.sample_address,
            value={b"": 2000000, self.sample_policy_id: {user_token_name: 1}},
        )

        consumed_output = self.create_mock_tx_out(self.sample_address)
        inputs = [self.create_mock_tx_in_info(oref, consumed_output)]

        tx_info = self.create_mock_tx_info(
            inputs=inputs,
            outputs=[protocol_output, user_output],
            mint={self.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}},
        )
        context = self.create_mock_script_context(minting_purpose, tx_info)

        # Should fail due to invalid datum constraints
        with pytest.raises(
            AssertionError,
            match="Protocol admin list cannot be empty|Protocol fee must be greater than zero|Oracle ID cannot be empty|Project ID cannot be empty",
        ):
            validator(oref, redeemer, context)


# # Integration test class for end-to-end scenarios
# class TestProtocolIntegration:
#     """Integration tests for complete protocol scenarios"""

#     def setup_method(self):
#         """Setup for integration tests"""
#         self.chain_context = MockChainContext()
#         self.test_protocol = TestProtocol()
#         self.test_protocol.setup_method()

#     def test_complete_protocol_lifecycle(self):
#         """Test complete protocol creation and destruction lifecycle"""
#         # Step 1: Create protocol
#         oref = self.test_protocol.create_mock_oref()
#         mint_redeemer = Mint()

#         minting_purpose = Minting(self.test_protocol.sample_policy_id)
#         protocol_token_name = unique_token_name(oref, PREFIX_PROTOCOL_NFT)
#         user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

#         # Create valid minting transaction
#         protocol_output = self.test_protocol.create_mock_tx_out(
#             self.test_protocol.script_address,
#             value={
#                 b"": 2000000,
#                 self.test_protocol.sample_policy_id: {protocol_token_name: 1}
#             },
#             datum=SomeOutputDatum(self.test_protocol.create_mock_datum_protocol())
#         )

#         user_output = self.test_protocol.create_mock_tx_out(
#             self.test_protocol.sample_address,
#             value={
#                 b"": 2000000,
#                 self.test_protocol.sample_policy_id: {user_token_name: 1}
#             }
#         )

#         consumed_output = self.test_protocol.create_mock_tx_out(self.test_protocol.sample_address)
#         inputs = [self.test_protocol.create_mock_tx_in_info(oref, consumed_output)]

#         mint_tx_info = self.test_protocol.create_mock_tx_info(
#             inputs=inputs,
#             outputs=[protocol_output, user_output],
#             mint={self.test_protocol.sample_policy_id: {protocol_token_name: 1, user_token_name: 1}}
#         )
#         mint_context = self.test_protocol.create_mock_script_context(minting_purpose, mint_tx_info)

#         # Should succeed
#         validator(oref, mint_redeemer, mint_context)

#         # Step 2: Burn protocol tokens
#         burn_redeemer = Burn()

#         burn_tx_info = self.test_protocol.create_mock_tx_info(
#             inputs=inputs,
#             outputs=[self.test_protocol.create_mock_tx_out(self.test_protocol.sample_address)],
#             mint={self.test_protocol.sample_policy_id: {protocol_token_name: -1, user_token_name: -1}}
#         )
#         burn_context = self.test_protocol.create_mock_script_context(minting_purpose, burn_tx_info)

#         # Should also succeed
#         validator(oref, burn_redeemer, burn_context)

#     def test_multiple_protocols_different_utxos(self):
#         """Test that different UTXOs create different protocol tokens"""
#         oref1 = self.test_protocol.create_mock_oref(bytes.fromhex("a" * 64), 0)
#         oref2 = self.test_protocol.create_mock_oref(bytes.fromhex("b" * 64), 0)

#         token1_protocol = unique_token_name(oref1, PREFIX_PROTOCOL_NFT)
#         token1_user = unique_token_name(oref1, PREFIX_USER_NFT)

#         token2_protocol = unique_token_name(oref2, PREFIX_PROTOCOL_NFT)
#         token2_user = unique_token_name(oref2, PREFIX_USER_NFT)

#         # All tokens should be unique
#         tokens = [token1_protocol, token1_user, token2_protocol, token2_user]
#         assert len(set(tokens)) == 4, "All tokens should be unique"


# # Mock class for the complete MockChainContext
# class MockChainContext:
#     """Enhanced mock blockchain context with more realistic data"""

#     def __init__(self):
#         self.current_slot = 1000
#         self.current_time = 1672531200  # 2023-01-01 00:00:00 UTC
#         self.network_id = 1  # Mainnet
#         self.protocol_params = {
#             "min_fee_a": 44,
#             "min_fee_b": 155381,
#             "max_tx_size": 16384,
#             "max_val_size": 5000,
#             "utxo_cost_per_word": 4310,
#             "min_utxo": 1000000
#         }

#     def advance_slot(self, slots: int = 1):
#         """Advance the blockchain by a number of slots"""
#         self.current_slot += slots
#         self.current_time += slots * 20  # Assuming 20 seconds per slot

#     def create_realistic_tx_id(self) -> TxId:
#         """Create a realistic-looking transaction ID"""
#         import hashlib
#         import random

#         # Create pseudo-random but deterministic hash
#         seed = f"tx_{self.current_slot}_{random.randint(1000, 9999)}"
#         tx_hash = hashlib.sha256(seed.encode()).digest()
#         return TxId(tx_hash)


# # Pytest fixtures for the test classes
# @pytest.fixture
# def mock_context():
#     """Fixture providing a mock chain context"""
#     return MockChainContext()

# @pytest.fixture
# def sample_oref():
#     """Fixture providing a sample transaction output reference"""
#     return TxOutRef(TxId(bytes.fromhex("a" * 64)), 0)

# @pytest.fixture
# def sample_policy_id():
#     """Fixture providing a sample policy ID"""
#     return bytes.fromhex("b" * 56)

# @pytest.fixture
# def valid_protocol_datum():
#     """Fixture providing a valid protocol datum"""
#     return DatumProtocol(
#         protocol_admin=[bytes.fromhex("d" * 56)],
#         protocol_fee=1000,
#         oracle_id=b"oracle_123",
#         project_id=b"project_456"
#     )

if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
