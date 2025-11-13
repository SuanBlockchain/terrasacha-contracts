# Types & Datums

Type definitions and data structures used throughout Terrasacha Contracts.

## Overview

The type system ensures:
- **Type safety**: Compile-time checking with mypy
- **On-chain correctness**: Proper serialization to Plutus data
- **Clear contracts**: Self-documenting code

### Location

`src/terrasacha_contracts/types.py`

## Core Types

### DatumProtocol

The main datum type attached to protocol UTXOs.

```python
@dataclass
class DatumProtocol:
    """
    Protocol state stored on-chain.
    Attached to UTXOs locked at protocol validator.
    """
    admin: List[PubKeyHash]  # Admin public key hashes (multi-sig support)
    fees: int                # Protocol fee amount in lovelace
    oracle_id: bytes         # Oracle identifier (immutable)
    project_id: bytes        # Project identifier (immutable)
```

#### Fields

**admin** (`List[PubKeyHash]`)
- Public key hashes authorized to update protocol
- Supports multi-signature (any admin can authorize)
- **Immutable**: Cannot be changed after initialization

**fees** (`int`)
- Protocol fee in lovelace (1 ADA = 1,000,000 lovelace)
- **Mutable**: Can be updated via UpdateProtocol redeemer
- Example: `2_000_000` = 2 ADA fee

**oracle_id** (`bytes`)
- Identifies the oracle providing data feeds
- **Immutable**: Cannot be changed after initialization
- Typically a hash or identifier

**project_id** (`bytes`)
- Identifies the carbon credit project
- **Immutable**: Cannot be changed after initialization
- Links protocol to specific project

#### Usage

```python
# Create initial datum
datum = DatumProtocol(
    admin=[PubKeyHash(b"admin_key_hash_1"), PubKeyHash(b"admin_key_hash_2")],
    fees=2_000_000,  # 2 ADA
    oracle_id=b"oracle_xyz",
    project_id=b"project_abc"
)

# Update mutable fields
new_datum = DatumProtocol(
    admin=datum.admin,         # Must stay same
    fees=5_000_000,            # Can update (5 ADA)
    oracle_id=datum.oracle_id, # Must stay same
    project_id=datum.project_id # Must stay same
)
```

## Redeemer Types

### Validator Redeemers

Used with protocol validator to specify actions.

#### UpdateProtocol

```python
@dataclass
class UpdateProtocol:
    """
    Redeemer to update protocol parameters.
    Requires admin signature.
    """
    pass  # No additional data needed
```

**Usage**:
```python
redeemer = UpdateProtocol()
```

**Requirements**:
- Admin signature in transaction
- Linear progression (1 input → 1 output)
- Immutable fields unchanged

#### EndProtocol

```python
@dataclass
class EndProtocol:
    """
    Redeemer to terminate protocol.
    Burns protocol NFT.
    Requires admin signature.
    """
    pass  # No additional data needed
```

**Usage**:
```python
redeemer = EndProtocol()
```

**Requirements**:
- Admin signature in transaction
- Protocol NFT burned (not in outputs)

### Minting Policy Redeemers

Used with minting policies to control token operations.

#### Mint

```python
@dataclass
class Mint:
    """
    Redeemer to mint new token pair.
    Creates protocol + user NFTs.
    """
    pass  # No additional data needed
```

**Usage**:
```python
redeemer = Mint()
```

**Requirements**:
- UTXO consumed for uniqueness
- Exactly 2 tokens minted
- Correct token naming
- Proper distribution

#### Burn

```python
@dataclass
class Burn:
    """
    Redeemer to burn token pair.
    Destroys protocol + user NFTs.
    """
    pass  # No additional data needed
```

**Usage**:
```python
redeemer = Burn()
```

**Requirements**:
- Both tokens burned together
- Proper authorization
- Matching token suffixes

## Type Aliases

### PubKeyHash

```python
PubKeyHash = bytes  # 28-byte hash of public key
```

**Usage**:
```python
admin_key = PubKeyHash(b"\\x12\\x34...\\xab\\xcd")  # 28 bytes
```

### PolicyId

```python
PolicyId = bytes  # 28-byte minting policy hash
```

**Usage**:
```python
policy = PolicyId(b"\\xab\\xcd...\\x12\\x34")  # 28 bytes
```

### TokenName

```python
TokenName = bytes  # Token name (max 32 bytes)
```

**Usage**:
```python
token = TokenName(b"PROTO_abc123def456")
```

## Constants

### Token Prefixes

```python
PROTO_PREFIX = b"PROTO_"  # Protocol NFT identifier
USER_PREFIX = b"USER_"     # User NFT identifier
```

**Usage**:
```python
# Generate token names
suffix = generate_unique_suffix(utxo_ref)
protocol_token = PROTO_PREFIX + suffix
user_token = USER_PREFIX + suffix
```

## Serialization

### To Plutus Data

Types automatically serialize to Plutus data format:

```python
datum = DatumProtocol(...)

# Serialization happens automatically when used in contracts
# OpShin handles conversion to Plutus data
```

### From Plutus Data

Deserialization from on-chain data:

```python
# In validator
def validator(datum: DatumProtocol, redeemer: UpdateProtocol, context: ScriptContext):
    # datum automatically deserialized from Plutus data
    admin_keys = datum.admin
    ...
```

## Type Validation

### Compile-Time Checks

OpShin provides type checking during compilation:

```python
# ✅ Valid
datum = DatumProtocol(
    admin=[PubKeyHash(b"key1")],
    fees=1_000_000,
    oracle_id=b"oracle",
    project_id=b"project"
)

# ❌ Invalid - type error
datum = DatumProtocol(
    admin="not a list",  # Wrong type
    fees="not an int",   # Wrong type
    ...
)
```

### Runtime Checks

Validators perform runtime validation:

```python
# Check immutable fields
assert new_datum.admin == old_datum.admin, "Admin cannot change"
assert new_datum.oracle_id == old_datum.oracle_id, "Oracle ID immutable"
assert new_datum.project_id == old_datum.project_id, "Project ID immutable"

# Validate fee range
assert new_datum.fees >= 0, "Fees cannot be negative"
assert new_datum.fees <= MAX_FEE, "Fees exceed maximum"
```

## Best Practices

### Datum Creation

```python
# ✅ Good: Clear, explicit values
datum = DatumProtocol(
    admin=[admin_key_1, admin_key_2],
    fees=2_000_000,
    oracle_id=oracle_hash,
    project_id=project_hash
)

# ❌ Bad: Magic numbers, unclear values
datum = DatumProtocol(
    admin=[b"\\x12\\x34..."],
    fees=2000000,  # What unit?
    oracle_id=b"xyz",
    project_id=b"abc"
)
```

### Type Hints

```python
# ✅ Good: Explicit type hints
def create_protocol_datum(
    admin_keys: List[PubKeyHash],
    fee_amount: int,
    oracle: bytes,
    project: bytes
) -> DatumProtocol:
    return DatumProtocol(
        admin=admin_keys,
        fees=fee_amount,
        oracle_id=oracle,
        project_id=project
    )
```

### Validation

```python
# ✅ Good: Validate inputs
def validate_datum(datum: DatumProtocol) -> bool:
    # Check required fields
    assert len(datum.admin) > 0, "At least one admin required"
    assert datum.fees >= 0, "Fees must be non-negative"
    assert len(datum.oracle_id) > 0, "Oracle ID required"
    assert len(datum.project_id) > 0, "Project ID required"
    return True
```

## Testing Types

```python
def test_datum_creation():
    """Test DatumProtocol creation"""
    admin = [PubKeyHash(b"admin_key")]
    datum = DatumProtocol(
        admin=admin,
        fees=1_000_000,
        oracle_id=b"oracle",
        project_id=b"project"
    )

    assert datum.admin == admin
    assert datum.fees == 1_000_000
    assert datum.oracle_id == b"oracle"
    assert datum.project_id == b"project"


def test_datum_immutability():
    """Test immutable fields cannot change"""
    old_datum = DatumProtocol(...)
    new_datum = DatumProtocol(
        admin=old_datum.admin,  # Keep same
        fees=5_000_000,         # Can change
        oracle_id=old_datum.oracle_id,  # Keep same
        project_id=old_datum.project_id  # Keep same
    )

    # Validate immutability
    assert new_datum.admin == old_datum.admin
    assert new_datum.oracle_id == old_datum.oracle_id
    assert new_datum.project_id == old_datum.project_id
```

## See Also

- [Validators](validators.md) - Using datums in validators
- [Minting Policies](minting-policies.md) - Using redeemers
- [API Reference](../api/types.md) - Full type documentation
