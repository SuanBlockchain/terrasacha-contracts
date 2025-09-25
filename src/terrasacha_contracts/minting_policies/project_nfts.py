#!opshin
from opshin.prelude import *

from terrasacha_contracts.util import *


@dataclass()
class MintProject(PlutusData):
    CONSTR_ID = 0
    protocol_input_index: int  # Index of the input UTXO to be consumed

@dataclass()
class BurnProject(PlutusData):
    CONSTR_ID = 1
    protocol_input_index: int  # Index of the reference input UTXO

def validate_signatories(input_datum: DatumProtocol, tx_info: TxInfo) -> None:
    """
    Validate that one of the admins in DatumProtocol signed the transaction.
    Required for Minting operations.
    """
    signatories = tx_info.signatories
    admins = input_datum.project_admins

    for signer in signatories:
        assert any([admin == signer for admin in admins]), "Minting requires signature from one of the admins"

def validator(
    oref: TxOutRef,
    protocol_policy_id: PolicyId,
    redeemer: Union[MintProject, BurnProject],
    context: ScriptContext,
) -> None:
    """
    Protocol contract validator for minting and burning protocol NFTs.

    Args:
        oref: Transaction output reference used for unique token name generation
        redeemer: Either Mint or Burn operation (as PlutusData)
        context: Script execution context
    """
    purpose = get_minting_purpose(context)
    own_policy_id = purpose.policy_id
    tx_info = context.tx_info
    mint_value = tx_info.mint

    our_minted = mint_value.get(own_policy_id, {b"": 0})
    assert len(our_minted) == 2, "Must mint or burn exactly 2 tokens"

    protocol_reference_input = tx_info.reference_inputs[redeemer.protocol_input_index].resolved
    protocol_token = extract_token_from_input(protocol_reference_input)

    assert protocol_token.policy_id == protocol_policy_id, "Wrong protocol token policy ID"

    assert check_token_present(
        protocol_token.policy_id,
        protocol_reference_input,
    ), "Protocol reference input must have the protocol token"

    protocol_datum = protocol_reference_input.datum
    assert isinstance(protocol_datum, SomeOutputDatum)
    protocol_datum_value: DatumProtocol = protocol_datum.datum
    # Transaction must be signed by one of the admins in the protocol datum
    validate_signatories(protocol_datum_value, tx_info)

    if isinstance(redeemer, MintProject):

        # 1. Validate that the specified UTXO is consumed
        assert has_utxo(context, oref), "UTxO not consumed"

        # Generate unique token names based on UTXO reference
        project_token_name = unique_token_name(oref, PREFIX_REFERENCE_NFT)
        user_token_name = unique_token_name(oref, PREFIX_USER_NFT)

        assert our_minted.get(project_token_name, 0) == 1, "Must mint exactly 1 project token"
        assert our_minted.get(user_token_name, 0) == 1, "Must mint exactly 1 user token"

    elif isinstance(redeemer, BurnProject):

        # Ensure no tokens are sent to any output with this policy
        for output in tx_info.outputs:
            token_amount = sum(output.value.get(own_policy_id, {b"": 0}).values())
            assert token_amount == 0, "Cannot send tokens to outputs when burning"
    else:
        assert False, "Invalid redeemer type"
