# Minting Policies

Minting policies control the creation and destruction of tokens in Terrasacha Contracts.

## Overview

Minting policies in Cardano determine:
- When tokens can be minted (created)
- When tokens can be burned (destroyed)
- Token naming rules
- Quantity restrictions

## Protocol NFTs Minting Policy

The main minting policy for protocol and user token pairs.

### Location

`src/terrasacha_contracts/minting_policies/protocol_nfts.py`

### Purpose

- Mints paired NFTs (protocol + user tokens)
- Enforces exactly 2 tokens per mint operation
- Uses UTXO reference for global uniqueness
- Handles both minting and burning operations

### Token Prefixes

```python
PROTO_PREFIX = b"PROTO_"  # Protocol NFT (goes to validator)
USER_PREFIX = b"USER_"     # User NFT (goes to user wallet)
```

### Redeemers

```python
class Mint:
    """Create new token pair"""
    pass

class Burn:
    """Destroy existing token pair"""
    pass
```

## Minting Flow

### 1. UTXO-Based Uniqueness

Token names derive from a consumed UTXO:

```python
# Extract UTXO reference from transaction inputs
utxo_ref = find_consumed_utxo(context.tx_info.inputs)

# Generate unique suffix from UTXO
unique_suffix = hash_utxo(utxo_ref.tx_id, utxo_ref.output_index)

# Create token names
protocol_token = PROTO_PREFIX + unique_suffix
user_token = USER_PREFIX + unique_suffix
```

This guarantees:
- **Global uniqueness**: Each UTXO can only be consumed once
- **Deterministic naming**: Same UTXO always produces same token names
- **No collisions**: Impossible to create duplicate token names

### 2. Paired Minting Validation

Exactly 2 tokens must be minted:

```python
minted_tokens = get_minted_tokens(context.tx_info.mint, own_policy)

assert len(minted_tokens) == 2, "Must mint exactly 2 tokens"

# Verify one protocol token
protocol_tokens = [t for t in minted_tokens if t.startswith(PROTO_PREFIX)]
assert len(protocol_tokens) == 1, "Must mint exactly 1 protocol token"

# Verify one user token
user_tokens = [t for t in minted_tokens if t.startswith(USER_PREFIX)]
assert len(user_tokens) == 1, "Must mint exactly 1 user token"

# Verify matching suffixes
assert protocol_tokens[0][len(PROTO_PREFIX):] == user_tokens[0][len(USER_PREFIX):], \
    "Token suffixes must match"
```

### 3. Distribution Validation

Tokens must go to correct destinations:

```python
# Protocol token must go to protocol validator
protocol_output = find_output_with_token(
    context.tx_info.outputs,
    protocol_token,
    protocol_validator_address
)
assert protocol_output is not None, "Protocol token must go to validator"

# User token goes to user (any address except validator)
user_output = find_output_with_token(
    context.tx_info.outputs,
    user_token
)
assert user_output is not None, "User token must be in outputs"
assert user_output.address != protocol_validator_address, \
    "User token cannot go to validator"
```

### Complete Mint Example

```python
Transaction:
  Inputs:
    - UTXO: tx#123...abc, index 0  ← Consumed for uniqueness
    - User's ADA for fees

  Mint:
    - 1x PROTO_abc123...def (protocol NFT)
    - 1x USER_abc123...def (user NFT)

  Outputs:
    - To protocol validator:
        • 2 ADA
        • 1x PROTO_abc123...def
        • Datum: DatumProtocol(...)

    - To user wallet:
        • 1x USER_abc123...def
        • Change ADA
```

## Burning Flow

### 1. Burn Validation

Tokens must be burned (negative quantities):

```python
burned_tokens = get_burned_tokens(context.tx_info.mint, own_policy)

# Both tokens must be burned together
assert len(burned_tokens) == 2, "Must burn exactly 2 tokens"

# Verify one protocol token burned
protocol_burns = [t for t in burned_tokens if t.startswith(PROTO_PREFIX)]
assert len(protocol_burns) == 1, "Must burn exactly 1 protocol token"

# Verify one user token burned
user_burns = [t for t in burned_tokens if t.startswith(USER_PREFIX)]
assert len(user_burns) == 1, "Must burn exactly 1 user token"

# Verify matching suffixes
assert protocol_burns[0][len(PROTO_PREFIX):] == user_burns[0][len(USER_PREFIX):], \
    "Burned token suffixes must match"
```

### 2. Authorization Check

Only authorized parties can burn:

```python
# Typically requires signature from admin or token holder
authorized = check_burn_authorization(context.tx_info.signatories)
assert authorized, "Unauthorized burn attempt"
```

### Complete Burn Example

```python
Transaction:
  Inputs:
    - From protocol validator:
        • 2 ADA
        • 1x PROTO_abc123...def

    - From user wallet:
        • 1x USER_abc123...def

  Mint (negative = burn):
    - -1x PROTO_abc123...def
    - -1x USER_abc123...def

  Outputs:
    - To user wallet:
        • Reclaimed ADA
```

## Token Naming Convention

### Format

```
<PREFIX>_<UNIQUE_SUFFIX>

Where:
  PREFIX = "PROTO" or "USER"
  UNIQUE_SUFFIX = sha256(tx_id || output_index)
```

### Example

```
Input UTXO:
  tx_id = 0x123abc...
  output_index = 0

Hash = sha256("0x123abc..." + "0")
     = 0xdef456...

Tokens:
  Protocol: PROTO_def456...
  User:     USER_def456...
```

### Benefits

- **Uniqueness**: UTXO consumption ensures one-time use
- **Verifiable**: Anyone can verify token authenticity
- **Deterministic**: Same input always produces same output
- **Collision-resistant**: SHA256 prevents collisions

## Helper Functions

### hash_utxo

Generates unique hash from UTXO reference:

```python
def hash_utxo(tx_id: bytes, output_index: int) -> bytes:
    """
    Create unique hash from UTXO components.
    Returns first 28 bytes of SHA256 hash.
    """
    data = tx_id + output_index.to_bytes(8, 'big')
    return sha256(data)[:28]  # Cardano token name limit
```

### find_consumed_utxo

Extracts specific UTXO from inputs:

```python
def find_consumed_utxo(
    inputs: List[TxInInfo],
    tx_id: bytes,
    index: int
) -> TxInInfo:
    """
    Find input with specific UTXO reference.
    Used to verify correct UTXO consumed for minting.
    """
```

## Error Cases

### Wrong Token Count

```
Error: "Must mint exactly 2 tokens"
Cause: Attempting to mint 1, 3, or more tokens
Fix: Always mint exactly 1 protocol + 1 user token
```

### Mismatched Suffixes

```
Error: "Token suffixes must match"
Cause: Protocol and user tokens have different suffixes
Fix: Generate both from same UTXO hash
```

### Wrong Distribution

```
Error: "Protocol token must go to validator"
Cause: Protocol token sent to wrong address
Fix: Send protocol token to validator address
```

### UTXO Not Found

```
Error: "Required UTXO not consumed"
Cause: Specified UTXO not in transaction inputs
Fix: Include correct UTXO in inputs
```

## Best Practices

### When Minting

1. Choose a UTXO to consume for uniqueness
2. Generate token names from UTXO hash
3. Mint exactly 2 tokens (1 protocol, 1 user)
4. Send protocol token to validator with datum
5. Send user token to user wallet

### When Burning

1. Include both tokens in burn
2. Provide proper authorization
3. Reclaim locked ADA from validator
4. Clean up protocol state

### Testing Minting Policies

```python
def test_protocol_nft_mint():
    # Setup
    utxo_ref = mock_utxo_reference()
    redeemer = Mint()
    context = mock_mint_context(utxo_ref, 2)

    # Execute
    result = protocol_nfts_policy(redeemer, context)

    # Assert
    assert result is True
```

## See Also

- [Validators](validators.md) - Protocol state validation
- [Types](types.md) - Datum and redeemer definitions
- [API Reference](../api/minting-policies.md) - Full API documentation
