from opshin.prelude import *

from terrasacha_contracts.util import *

# USDA stable coin policy ID (hardcoded)
USDA_POLICY_ID = b"\xc4\x8c\xbb=^W\xedV\xe2v\xbcE\xf9\x9a\xb3\x9a\xbe\x94\xe6\xcdz\xc3\x9f\xb4\x02\xdaG\xad\x00\x14\xdf\x10USDATEST"

################################################
# Investor Data Types
################################################

@dataclass()
class PriceWithPrecision(PlutusData):
    """
    Price with precision following Orcfax pattern.

    Price is stored as an integer with a precision value indicating decimal places.
    Example: $1.25 with 6 decimals = PriceWithPrecision(1250000, 6)
    Calculation: actual_price = price / (10 ^ precision) = 1250000 / 1000000 = 1.25

    Fields:
        price: Price as integer (e.g., 1250000 for $1.25 with 6 decimals)
        precision: Number of decimal places (e.g., 6 means divide by 10^6)
    """
    CONSTR_ID = 4
    price: int
    precision: int


@dataclass()
class DatumInvestor(PlutusData):
    """
    Investor contract datum for grey token sales.

    Fields:
        seller_pkh: Public key hash of the seller
        grey_token_amount: Total amount of grey tokens available for sale
        price_per_token: Price per token with precision (USDA)
        min_purchase_amount: Minimum amount of tokens that can be purchased
    """
    CONSTR_ID = 0
    seller_pkh: bytes
    grey_token_amount: int
    price_per_token: PriceWithPrecision
    min_purchase_amount: int

@dataclass()
class BuyGrey(PlutusData):
    """Buy grey tokens redeemer"""
    CONSTR_ID = 0
    buyer_pkh: bytes  # Public key hash of the buyer
    amount: int  # Amount of tokens to buy
    investor_input_index: int  # Index of investor contract input
    protocol_ref_index: int  # Index of protocol reference input for fee
    investor_output_index: int  # Index of investor contract output (if tokens remain)


@dataclass()
class CancelSale(PlutusData):
    """Cancel sale redeemer - seller retrieves all tokens"""
    CONSTR_ID = 1
    investor_input_index: int


@dataclass()
class UpdatePrice(PlutusData):
    """Update price redeemer"""
    CONSTR_ID = 2
    new_price_per_token: PriceWithPrecision
    investor_input_index: int
    investor_output_index: int


RedeemerInvestor = Union[BuyGrey, CancelSale, UpdatePrice]


################################################
# Helper Functions
################################################

def get_protocol_fee_from_reference(
    tx_info: TxInfo,
    protocol_ref_index: int,
    protocol_nft_policy_id: PolicyId
) -> int:
    """
    Extract protocol fee from protocol NFT reference input.

    Args:
        tx_info: Transaction info
        protocol_ref_index: Index of protocol reference input
        protocol_nft_policy_id: Policy ID of protocol NFT

    Returns:
        Protocol fee amount in lovelace
    """
    protocol_input = tx_info.reference_inputs[protocol_ref_index].resolved

    # Validate protocol NFT is present
    assert check_token_present(
        protocol_nft_policy_id, protocol_input
    ), "Protocol reference input must contain protocol NFT"

    # Extract datum
    protocol_datum = protocol_input.datum
    assert isinstance(protocol_datum, SomeOutputDatum), "Protocol input must have datum"
    protocol_datum_value: DatumProtocol = protocol_datum.datum

    return protocol_datum_value.protocol_fee

def validate_usda_payment(
    outputs: List[TxOut],
    recipient_pkh: bytes,
    expected_amount: int
) -> None:
    """
    Validate that USDA payment is sent to recipient.

    Args:
        outputs: Transaction outputs
        recipient_pkh: Public key hash of payment recipient
        expected_amount: Expected USDA amount
    """
    total_received = 0

    for output in outputs:
        if output.address.payment_credential.credential_hash == recipient_pkh:
            usda_amount = output.value.get(USDA_POLICY_ID, {b"": 0}).get(b"USDATEST", 0)
            total_received += usda_amount

    assert total_received >= expected_amount, "Insufficient USDA payment"

def validate_grey_token_transfer(
    outputs: List[TxOut],
    buyer_pkh: bytes,
    grey_policy_id: PolicyId,
    grey_token_name: TokenName,
    expected_amount: int
) -> None:
    """
    Validate that grey tokens are transferred to buyer.

    Args:
        outputs: Transaction outputs
        buyer_pkh: Public key hash of buyer
        grey_policy_id: Grey token policy ID
        grey_token_name: Grey token name
        expected_amount: Expected token amount
    """
    total_tokens_sent = 0

    for output in outputs:
        if output.address.payment_credential.credential_hash == buyer_pkh:
            tokens = output.value.get(grey_policy_id, {b"": 0}).get(grey_token_name, 0)
            total_tokens_sent += tokens

    assert total_tokens_sent <= expected_amount, "Tokens sent cannot be higher than the expected amount"


def validator(
    protocol_policy_id: PolicyId,
    grey_token: Token,
    datum: DatumInvestor,
    redeemer: RedeemerInvestor,
    context: ScriptContext,
) -> None:
    """
    Investor contract validator for grey token purchases.

    Handles:
    - BuyGrey: Purchase grey tokens with USDA payment
    - CancelSale: Seller cancels sale and retrieves tokens
    - UpdatePrice: Seller updates token price

    Args:
        datum: Investor contract datum
        redeemer: Operation to perform
        context: Script execution context
    """
    tx_info = context.tx_info
    purpose = get_spending_purpose(context)

    investor_input = resolve_linear_input(tx_info, redeemer.investor_input_index, purpose)
    assert check_token_present(grey_token.policy_id, investor_input), "Investor input must contain grey token"

    if isinstance(redeemer, BuyGrey):
        # Validate purchase amount
        assert redeemer.amount >= datum.min_purchase_amount, "Purchase amount below minimum"
        assert redeemer.amount <= datum.grey_token_amount, "Purchase amount exceeds available tokens"
        
        # Get protocol fee from reference input
        protocol_fee = get_protocol_fee_from_reference(
            tx_info,
            redeemer.protocol_ref_index,
            protocol_policy_id
        )
        # Validate grey token transfer to buyer
        validate_grey_token_transfer(
            tx_info.outputs,
            redeemer.buyer_pkh,
            grey_token.policy_id,
            grey_token.token_name,
            redeemer.amount
        )

        # Calculate payment with precision
        # Formula: (amount * price) / (10 ^ precision)
        total_payment_raw = redeemer.amount * datum.price_per_token.price
        divisor = 10 ** datum.price_per_token.precision
        total_payment = total_payment_raw // divisor

        # Calculate seller payment (total - protocol fee)
        seller_payment = total_payment - protocol_fee

        # Validate USDA payments
        validate_usda_payment(tx_info.outputs, datum.seller_pkh, seller_payment)

        # If there are remaining tokens, validate contract continuation
        remaining_tokens = datum.grey_token_amount - redeemer.amount
        if remaining_tokens > 0:
            
            investor_output = resolve_linear_output(investor_input, tx_info, redeemer.investor_output_index)

            # Validate output goes back to same contract address
            assert investor_output.address == investor_input.address, "Remaining tokens must return to contract"

            # Validate remaining tokens are in output
            output_tokens = investor_output.value.get(grey_token.policy_id, {b"": 0}).get(grey_token.token_name, 0)
            assert output_tokens >= remaining_tokens, "Insufficient tokens returned to contract"

            # Validate datum update
            output_datum = investor_output.datum
            assert isinstance(output_datum, SomeOutputDatum), "Investor output must have datum"
            new_datum: DatumInvestor = output_datum.datum

            # Validate immutable fields
            assert new_datum.seller_pkh == datum.seller_pkh, "Seller PKH cannot change"
            assert new_datum.price_per_token.price == datum.price_per_token.price, "Price cannot change during buy"
            assert new_datum.price_per_token.precision == datum.price_per_token.precision, "Price precision cannot change during buy"
            assert new_datum.min_purchase_amount == datum.min_purchase_amount, "Min purchase cannot change"

            # Validate token amount decreased correctly
            assert new_datum.grey_token_amount == remaining_tokens, "Token amount must match remaining tokens"

    elif isinstance(redeemer, CancelSale):
        # Only seller can cancel
        assert datum.seller_pkh in tx_info.signatories, "Only seller can cancel sale"

        # No specific output validation needed - seller can do whatever with the tokens
        # Contract just needs to be consumed

    elif isinstance(redeemer, UpdatePrice):
        # Only seller can update price
        assert datum.seller_pkh in tx_info.signatories, "Only seller can update price"

        # Validate new price
        assert redeemer.new_price_per_token.price > 0, "Price must be positive"
        assert redeemer.new_price_per_token.precision >= 0, "Precision must be non-negative"

        # Validate contract continuation
        investor_output = resolve_linear_output(investor_input, tx_info, redeemer.investor_output_index)

        assert investor_output.address == investor_input.address, "Output must return to contract"

        # Validate datum update
        output_datum = investor_output.datum
        assert isinstance(output_datum, SomeOutputDatum), "Investor output must have datum"
        new_datum: DatumInvestor = output_datum.datum

        # Validate immutable fields
        assert new_datum.seller_pkh == datum.seller_pkh, "Seller PKH cannot change"
        assert new_datum.grey_token_amount == datum.grey_token_amount, "Token amount cannot change"
        assert new_datum.min_purchase_amount == datum.min_purchase_amount, "Min purchase cannot change"

        # Validate price was updated
        assert new_datum.price_per_token.price == redeemer.new_price_per_token.price, "Price must be updated to new value"
        assert new_datum.price_per_token.precision == redeemer.new_price_per_token.precision, "Precision must be updated to new value"

        # Validate tokens remain in contract
        output_tokens = investor_output.value.get(grey_token.policy_id, {b"": 0}).get(grey_token.token_name, 0)
        assert output_tokens >= datum.grey_token_amount, "All tokens must remain in contract"

    else:
        assert False, "Invalid redeemer type"
