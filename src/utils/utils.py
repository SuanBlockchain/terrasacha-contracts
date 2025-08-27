from opshin.prelude import *
from opshin.std.builtins import append_byte_string, cons_byte_string, sha3_256

# =============================================================================
# CONSTANTS
# =============================================================================

# Token name prefixes for unique identification
PREFIX_PROTOCOL_NFT = b"100"  # Protocol reference NFT (sent to contract)
PREFIX_USER_NFT = b"200"  # User NFT (sent to creator)
PREFIX_PROJECT_NFT = b"300"  # Project NFT
PREFIX_ORACLE_NFT = b"400"  # Oracle NFT
PREFIX_GREY_TOKEN = b"GREY"  # Grey tokens (pre-certification)
PREFIX_GREEN_TOKEN = b"GREEN"  # Green tokens (certified)

# Project states
PROJECT_STATE_INITIALIZED = 0
PROJECT_STATE_DISTRIBUTED = 1
PROJECT_STATE_CERTIFIED = 2
PROJECT_STATE_CLOSED = 3

# Minimum values
MIN_PROTOCOL_FEE = 1000000  # 1 ADA minimum fee
MIN_TOKEN_AMOUNT = 1


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def unique_token_name(oref: TxOutRef, prefix: bytes) -> TokenName:
    """
    Generate unique token name from output reference and prefix.

    Args:
        oref: Transaction output reference
        prefix: Byte prefix for token name

    Returns:
        Unique token name
    """
    txid_hash = sha3_256(oref.id)
    prepend_index = cons_byte_string(oref.idx, txid_hash)
    token_name = append_byte_string(prefix, prepend_index)

    return token_name


def has_utxo(context: ScriptContext, oref: TxOutRef) -> bool:
    """
    Check if the specified UTXO is consumed in this transaction.

    Args:
        context: Script execution context
        oref: Transaction output reference to check

    Returns:
        True if UTXO is consumed, False otherwise
    """
    return any([oref == i.out_ref for i in context.tx_info.inputs])


def find_script_address(policy_id: PolicyId) -> Address:
    """
    Get the script address from policy ID.

    Args:
        policy_id: The policy ID of the script

    Returns:
        Script address
    """
    return Address(ScriptCredential(policy_id), NoStakingCredential())


def find_token_output(
    outputs: List[TxOut], policy_id: PolicyId, protocol_token_name: TokenName
) -> TxOut:
    """Find the output containing the protocol NFT"""
    result = None
    for output in outputs:
        token_amount = output.value.get(policy_id, {b"": 0}).get(protocol_token_name, 0)
        if token_amount == 1:
            result = output
    return result


# TODO: pending to create test case
def check_admin_signature(context: ScriptContext, admin_list: List[PubKeyHash]) -> bool:
    """
    Check if at least one admin has signed the transaction.

    Args:
        context: Script execution context
        admin_list: List of admin public key hashes

    Returns:
        True if at least one admin signed, False otherwise
    """
    signatories = context.tx_info.signatories
    return any(admin in signatories for admin in admin_list)


# TODO: pending to create test case
def find_token_input(
    inputs: List[TxInInfo], policy_id: PolicyId, token_name: TokenName
) -> TxInInfo:
    """
    Find input containing specific token.

    Args:
        inputs: List of transaction inputs
        policy_id: Policy ID of the token
        token_name: Name of the token

    Returns:
        Input containing the token

    Raises:
        ValueError: If token input not found
    """
    for input_info in inputs:
        utxo = input_info.resolved
        token_amount = utxo.value.get(policy_id, {b"": 0}).get(token_name, 0)
        if token_amount > 0:
            return input_info
    raise ValueError(f"Token input not found for {token_name.hex()}")


# TODO: pending to create test case
def get_token_amount(value: Value, policy_id: PolicyId, token_name: TokenName) -> int:
    """
    Get amount of specific token in value.

    Args:
        value: Value to search in
        policy_id: Policy ID of the token
        token_name: Name of the token

    Returns:
        Amount of tokens (0 if not found)
    """
    return value.get(policy_id, {b"": 0}).get(token_name, 0)


def validate_single_token_mint(
    context: ScriptContext,
    policy_id: PolicyId,
    token_name: TokenName,
    expected_amount: int,
) -> None:
    """
    Validate that exactly one type of token is minted with expected amount.

    Args:
        context: Script execution context
        policy_id: Policy ID to check
        token_name: Expected token name
        expected_amount: Expected mint amount (positive for mint, negative for burn)
    """
    mint_value = context.tx_info.mint
    our_minted = mint_value.get(policy_id, {b"": 0})

    # Check exactly one token type
    assert len(our_minted) == 1, "Must mint/burn exactly one token type"

    # Check token name and amount
    actual_amount = our_minted.get(token_name, 0)
    assert (
        actual_amount == expected_amount
    ), f"Expected {expected_amount} of {token_name.hex()}, got {actual_amount}"


def validate_datum_type(datum: OutputDatum, expected_type: type) -> PlutusData:
    """
    Validate and extract datum of expected type.

    Args:
        datum: Output datum to validate
        expected_type: Expected datum type

    Returns:
        Validated datum data

    Raises:
        AssertionError: If datum is not of expected type
    """
    assert isinstance(datum, SomeOutputDatum), "Output must have inlined datum"
    datum_data = datum.datum
    assert isinstance(
        datum_data, expected_type
    ), f"Datum must be {expected_type.__name__}"
    return datum_data


def calculate_protocol_fee(amount: int, fee_percentage: int) -> int:
    """
    Calculate protocol fee based on amount and percentage.

    Args:
        amount: Base amount
        fee_percentage: Fee percentage (in basis points, e.g., 250 = 2.5%)

    Returns:
        Calculated fee amount
    """
    return (amount * fee_percentage) // 10000


def validate_ada_payment(
    outputs: List[TxOut], recipient: PubKeyHash, min_amount: int
) -> None:
    """
    Validate that sufficient ADA is paid to recipient.

    Args:
        outputs: Transaction outputs
        recipient: Recipient public key hash
        min_amount: Minimum ADA amount required (in lovelace)
    """
    total_paid = 0
    recipient_found = False

    for output in outputs:
        if isinstance(output.address.payment_credential, PubKeyCredential):
            if output.address.payment_credential.credential_hash == recipient:
                recipient_found = True
                ada_amount = output.value.get(b"", {b"": 0}).get(b"", 0)
                total_paid += ada_amount

    assert recipient_found, "Recipient address not found in outputs"
    assert (
        total_paid >= min_amount
    ), f"Insufficient payment: {total_paid} < {min_amount}"


def validate_token_conservation(
    inputs: List[TxInInfo],
    outputs: List[TxOut],
    mint_value: Value,
    policy_id: PolicyId,
    token_name: TokenName,
) -> None:
    """
    Validate token conservation (inputs + mints = outputs).

    Args:
        inputs: Transaction inputs
        outputs: Transaction outputs
        mint_value: Minted/burned tokens
        policy_id: Policy ID to check
        token_name: Token name to check
    """
    input_amount = sum(
        get_token_amount(inp.resolved.value, policy_id, token_name) for inp in inputs
    )

    output_amount = sum(
        get_token_amount(out.value, policy_id, token_name) for out in outputs
    )

    minted_amount = mint_value.get(policy_id, {b"": 0}).get(token_name, 0)

    assert (
        input_amount + minted_amount == output_amount
    ), f"Token conservation violated: {input_amount} + {minted_amount} != {output_amount}"
