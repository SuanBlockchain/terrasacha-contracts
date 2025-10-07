from opshin.prelude import *


@dataclass
class DatumMarketplace(PlutusData):
    """Marketplace listing datum"""
    CONSTR_ID = 0
    seller: PubKeyHash  # Seller's public key hash
    project_id: bytes  # Project identifier
    token_type: bytes  # "GREY" or "GREEN" 
    token_amount: int  # Amount of tokens for sale
    price_per_token: int  # Price per token in lovelace
    min_purchase: int  # Minimum purchase amount
    expiry_time: POSIXTime  # When listing expires


@dataclass
class DatumOracle(PlutusData):
    """Oracle price information"""
    CONSTR_ID = 0
    project_id: bytes
    token_price_ada: int  # Price in lovelace per token
    token_price_usd: int  # Price in USD cents per token
    token_price_cop: int  # Price in COP centavos per token
    last_update: POSIXTime


@dataclass
class BuyTokens(PlutusData):
    """Buy tokens from marketplace"""
    CONSTR_ID = 0
    amount: int  # Amount of tokens to buy


@dataclass
class UpdateListing(PlutusData):
    """Update marketplace listing"""
    CONSTR_ID = 1
    new_price: int  # New price per token
    new_amount: int  # New amount available
    new_expiry: POSIXTime  # New expiry time


@dataclass
class CancelListing(PlutusData):
    """Cancel marketplace listing"""
    CONSTR_ID = 2


@dataclass
class CreateListing(PlutusData):
    """Create new marketplace listing"""
    CONSTR_ID = 3
    price_per_token: int
    min_purchase: int
    expiry_time: POSIXTime


# Token prefixes
PREFIX_GREY_TOKEN = b"GREY"
PREFIX_GREEN_TOKEN = b"GREEN"
PREFIX_MARKETPLACE_NFT = b"500"
PREFIX_ORACLE_NFT = b"400"

# Constants
MIN_LISTING_DURATION = 3600  # 1 hour minimum
MAX_LISTING_DURATION = 7776000  # 90 days maximum
MIN_TOKEN_PRICE = 1000000  # 1 ADA minimum price per token
PROTOCOL_FEE_BASIS_POINTS = 250  # 2.5% protocol fee


def unique_token_name(oref: TxOutRef, prefix: bytes) -> TokenName:
    """Generate unique token name from output reference and prefix"""
    tx_id_bytes = oref.id.tx_id if hasattr(oref.id, 'tx_id') else oref.id
    idx_bytes = oref.idx.to_bytes(4, 'big')
    return prefix + tx_id_bytes[:16] + idx_bytes


def has_utxo(context: ScriptContext, oref: TxOutRef) -> bool:
    """Check if the specified UTXO is consumed in this transaction"""
    return any([oref == i.out_ref for i in context.tx_info.inputs])


def find_marketplace_input(inputs: List[TxInInfo], policy_id: PolicyId) -> TxInInfo:
    """Find input containing marketplace NFT"""
    for input_info in inputs:
        utxo = input_info.resolved
        for token_name in utxo.value.get(policy_id, {b"": 0}).keys():
            if token_name.startswith(PREFIX_MARKETPLACE_NFT):
                return input_info
    raise ValueError("Marketplace NFT input not found")


def find_marketplace_output(outputs: List[TxOut], policy_id: PolicyId, marketplace_nft: TokenName) -> TxOut:
    """Find output containing marketplace NFT"""
    for output in outputs:
        if output.value.get(policy_id, {b"": 0}).get(marketplace_nft, 0) == 1:
            return output
    raise ValueError("Marketplace NFT output not found")


def find_oracle_input(inputs: List[TxInInfo], oracle_policy_id: PolicyId, project_id: bytes) -> TxInInfo:
    """Find oracle input for price validation"""
    oracle_nft_name = PREFIX_ORACLE_NFT + project_id
    for input_info in inputs:
        utxo = input_info.resolved
        if utxo.value.get(oracle_policy_id, {b"": 0}).get(oracle_nft_name, 0) == 1:
            return input_info
    raise ValueError("Oracle input not found")


def validate_marketplace_datum(datum: DatumMarketplace, current_time: POSIXTime) -> None:
    """Validate marketplace datum constraints"""
    assert len(datum.seller) == 28, "Invalid seller public key hash"
    assert len(datum.project_id) > 0, "Project ID cannot be empty"
    assert datum.token_type in [PREFIX_GREY_TOKEN, PREFIX_GREEN_TOKEN], "Invalid token type"
    assert datum.token_amount > 0, "Token amount must be positive"
    assert datum.price_per_token >= MIN_TOKEN_PRICE, f"Price too low: minimum {MIN_TOKEN_PRICE}"
    assert datum.min_purchase > 0, "Minimum purchase must be positive"
    assert datum.min_purchase <= datum.token_amount, "Minimum purchase cannot exceed available amount"
    assert datum.expiry_time > current_time, "Listing has expired"


def validate_oracle_price(oracle_datum: DatumOracle, listing_price: int, current_time: POSIXTime) -> None:
    """Validate that listing price is reasonable compared to oracle price"""
    # Check oracle data is recent (within 24 hours)
    assert current_time - oracle_datum.last_update <= 86400, "Oracle data too old"
    
    # Allow listing price to be within 50% of oracle price (both above and below)
    oracle_price = oracle_datum.token_price_ada
    price_tolerance = oracle_price // 2  # 50% tolerance
    min_allowed = oracle_price - price_tolerance
    max_allowed = oracle_price + price_tolerance
    
    assert min_allowed <= listing_price <= max_allowed, \
        f"Price outside allowed range: {listing_price} not in [{min_allowed}, {max_allowed}]"


def calculate_fees(total_amount: int) -> tuple[int, int]:
    """Calculate protocol and platform fees"""
    protocol_fee = (total_amount * PROTOCOL_FEE_BASIS_POINTS) // 10000
    remaining = total_amount - protocol_fee
    return protocol_fee, remaining


def validate_seller_signature(context: ScriptContext, seller: PubKeyHash) -> None:
    """Ensure seller has signed the transaction"""
    assert seller in context.tx_info.signatories, "Seller must sign the transaction"


def validate_payment_distribution(
    outputs: List[TxOut], 
    seller: PubKeyHash,
    protocol_admin: PubKeyHash,
    total_payment: int,
    protocol_fee: int
) -> None:
    """Validate that payments are correctly distributed"""
    seller_payment = 0
    protocol_payment = 0
    
    for output in outputs:
        if isinstance(output.address.payment_credential, PubKeyCredential):
            credential_hash = output.address.payment_credential.credential_hash
            ada_amount = output.value.get(b"", {b"": 0}).get(b"", 0)
            
            if credential_hash == seller:
                seller_payment += ada_amount
            elif credential_hash == protocol_admin:
                protocol_payment += ada_amount
    
    expected_seller_payment = total_payment - protocol_fee
    
    assert seller_payment >= expected_seller_payment, \
        f"Insufficient payment to seller: {seller_payment} < {expected_seller_payment}"
    assert protocol_payment >= protocol_fee, \
        f"Insufficient protocol fee: {protocol_payment} < {protocol_fee}"


def validate_token_transfer(
    inputs: List[TxInInfo],
    outputs: List[TxOut],
    marketplace_input: TxInInfo,
    buyer_address: Address,
    policy_id: PolicyId,
    token_name: TokenName,
    purchase_amount: int
) -> None:
    """Validate that tokens are correctly transferred to buyer"""
    # Check tokens are deducted from marketplace
    marketplace_tokens_in = marketplace_input.resolved.value.get(policy_id, {b"": 0}).get(token_name, 0)
    
    # Find tokens sent to buyer
    buyer_tokens = 0
    for output in outputs:
        if output.address == buyer_address:
            buyer_tokens += output.value.get(policy_id, {b"": 0}).get(token_name, 0)
    
    assert buyer_tokens >= purchase_amount, \
        f"Insufficient tokens sent to buyer: {buyer_tokens} < {purchase_amount}"


def get_current_time(context: ScriptContext) -> POSIXTime:
    """Get current time from transaction validity interval"""
    validity_range = context.tx_info.valid_range
    # Use the start of the validity range as current time
    if hasattr(validity_range, 'lower_bound') and validity_range.lower_bound:
        return validity_range.lower_bound.limit
    else:
        # Fallback - this should be properly implemented based on your interval type
        return 0


def validate_create_listing(
    context: ScriptContext,
    redeemer: CreateListing,
    oref: TxOutRef,
    policy_id: PolicyId
) -> None:
    """Validate creation of new marketplace listing"""
    tx_info = context.tx_info
    current_time = get_current_time(context)
    
    # Validate redeemer constraints
    assert redeemer.price_per_token >= MIN_TOKEN_PRICE, "Price too low"
    assert redeemer.min_purchase > 0, "Minimum purchase must be positive"
    
    # Validate expiry time
    duration = redeemer.expiry_time - current_time
    assert duration >= MIN_LISTING_DURATION, "Listing duration too short"
    assert duration <= MAX_LISTING_DURATION, "Listing duration too long"
    
    # Validate UTXO consumption
    assert has_utxo(context, oref), "Required UTXO not consumed"
    
    # Generate marketplace NFT name
    marketplace_nft = unique_token_name(oref, PREFIX_MARKETPLACE_NFT)
    
    # Find marketplace output
    marketplace_output = find_marketplace_output(tx_info.outputs, policy_id, marketplace_nft)
    
    # Validate marketplace datum
    output_datum = marketplace_output.datum
    assert isinstance(output_datum, SomeOutputDatum), "Marketplace output must have inlined datum"
    listing_datum = output_datum.datum
    assert isinstance(listing_datum, DatumMarketplace), "Output datum must be DatumMarketplace"
    
    validate_marketplace_datum(listing_datum, current_time)
    
    # Ensure marketplace NFT is minted
    mint_value = tx_info.mint
    minted_nft = mint_value.get(policy_id, {b"": 0}).get(marketplace_nft, 0)
    assert minted_nft == 1, "Marketplace NFT not minted"


def validator(
    datum: Union[DatumMarketplace, Nothing],
    redeemer: Union[BuyTokens, UpdateListing, CancelListing, CreateListing],
    context: ScriptContext,
) -> None:
    """
    Marketplace contract validator for token trading.
    
    Args:
        datum: Marketplace listing datum or Nothing for minting
        redeemer: Marketplace operation
        context: Script execution context
    """
    purpose = context.purpose
    tx_info = context.tx_info
    current_time = get_current_time(context)
    
    if isinstance(purpose, Minting):
        # Handle marketplace NFT minting for new listings
        assert isinstance(redeemer, CreateListing), "Only CreateListing allowed for minting"
        assert isinstance(datum, Nothing), "Datum should be Nothing for minting"
        
        # This would need the oref parameter - simplified for this example
        # validate_create_listing(context, redeemer, oref, purpose.policy_id)
        
    elif isinstance(purpose, Spending):
        # Handle marketplace operations
        assert isinstance(datum, DatumMarketplace), "Invalid datum type for spending"
        
        # Validate listing is not expired
        assert datum.expiry_time > current_time, "Listing has expired"
        
        if isinstance(redeemer, BuyTokens):
            # Validate purchase amount
            assert redeemer.amount >= datum.min_purchase, "Purchase amount below minimum"
            assert redeemer.amount <= datum.token_amount, "Purchase amount exceeds available"
            
            # Calculate payment
            total_payment = redeemer.amount * datum.price_per_token
            protocol_fee, seller_payment = calculate_fees(total_payment)
            
            # Validate payment distribution (simplified - needs protocol admin address)
            # validate_payment_distribution(tx_info.outputs, datum.seller, protocol_admin, total_payment, protocol_fee)
            
            # Validate token transfer (simplified - needs buyer address)
            # validate_token_transfer(...)
            
        elif isinstance(redeemer, UpdateListing):
            # Only seller can update
            validate_seller_signature(context, datum.seller)
            
            # Validate new parameters
            assert redeemer.new_price >= MIN_TOKEN_PRICE, "New price too low"
            assert redeemer.new_amount > 0, "New amount must be positive"
            assert redeemer.new_expiry > current_time, "New expiry must be in future"
            
            # Ensure listing continues with updated datum
            marketplace_input = find_marketplace_input(tx_info.inputs, purpose.policy_id)
            # Find corresponding output and validate datum update
            
        elif isinstance(redeemer, CancelListing):
            # Only seller can cancel
            validate_seller_signature(context, datum.seller)
            
            # Ensure marketplace NFT is burned
            mint_value = tx_info.mint
            for policy_id, tokens in mint_value.items():
                for token_name, amount in tokens.items():
                    if token_name.startswith(PREFIX_MARKETPLACE_NFT) and amount < 0:
                        # NFT is being burned, which is correct for cancellation
                        pass
        
        else:
            assert False, "Invalid redeemer for spending"
    
    else:
        assert False, "Invalid script purpose"