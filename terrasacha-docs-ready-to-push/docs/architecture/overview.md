# Architecture Overview

Terrasacha Contracts implements a modular smart contract system for carbon credit tokens and NFTs on the Cardano blockchain.

## System Design

The architecture follows a **modular design** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                   Protocol System                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────┐         ┌─────────────────┐       │
│  │   Validators    │◄────────┤ Minting Policies │       │
│  │                 │         │                 │       │
│  │  - protocol.py  │         │ - protocol_nfts │       │
│  └────────┬────────┘         └────────┬────────┘       │
│           │                           │                 │
│           │    ┌──────────────┐       │                 │
│           └────┤    Types     │───────┘                 │
│                │              │                          │
│                │ - DatumProto │                          │
│                │ - Redeemers  │                          │
│                └──────┬───────┘                          │
│                       │                                  │
│                ┌──────┴───────┐                          │
│                │  Utilities   │                          │
│                │              │                          │
│                │ - Linear     │                          │
│                │ - UTXO       │                          │
│                └──────────────┘                          │
└─────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Validators

Validators enforce business logic and state transitions.

**Protocol Validator** (`protocol.py`):
- Validates protocol NFT continuation across transactions
- Handles protocol updates with authorization checks
- Implements linear progression (one input → one output)
- Prevents state fragmentation

See: [Validators Documentation](validators.md)

### 2. Minting Policies

Minting policies control token creation and burning.

**Protocol NFTs** (`protocol_nfts.py`):
- Mints paired NFTs (protocol + user tokens)
- Enforces exactly 2 tokens per mint
- Uses UTXO reference for uniqueness
- Handles burning operations

See: [Minting Policies Documentation](minting-policies.md)

### 3. Types and Datums

Type definitions ensure type safety and correctness.

**DatumProtocol**:
```python
class DatumProtocol:
    admin: List[PubKeyHash]    # Admin public key hashes
    fees: int                  # Protocol fees
    oracle_id: bytes           # Oracle identifier
    project_id: bytes          # Project identifier
```

See: [Types & Datums Documentation](types.md)

### 4. Utilities

Helper functions for common operations.

- **Linear validation**: `resolve_linear_input`, `resolve_linear_output`
- **Token naming**: UTXO-based unique name generation
- **UTXO helpers**: Purpose extraction and validation

## Key Design Patterns

### Linear Progression

Contracts enforce **one-input-to-one-output** patterns:

```
Input UTXO ──────► Validator ──────► Output UTXO
  (with NFT)                          (with same NFT)
```

Benefits:
- Prevents state fragmentation
- Ensures state continuity
- Simplifies validation logic
- Reduces complexity

### Paired Token System

Protocol and user NFTs are minted together:

```
Mint Transaction
├── Token 1: PROTO_<unique_suffix>  (to protocol validator)
└── Token 2: USER_<unique_suffix>   (to user wallet)
```

Benefits:
- Shared uniqueness guarantee
- Simplified tracking
- Clear ownership model

### UTXO-Based Uniqueness

Token names derive from consuming specific UTXOs:

```python
unique_suffix = sha256(txid + output_index)
protocol_token = "PROTO_" + unique_suffix
user_token = "USER_" + unique_suffix
```

Benefits:
- Guaranteed global uniqueness
- No need for centralized registry
- Verifiable on-chain

### Datum Immutability

Core protocol parameters cannot change:

```python
# ✅ Can update
new_datum.fees = updated_fees

# ❌ Cannot change
new_datum.admin = ...        # Must stay same
new_datum.oracle_id = ...    # Must stay same
new_datum.project_id = ...   # Must stay same
```

Benefits:
- Predictable behavior
- Trust preservation
- Security guarantee

## Transaction Flow

### Minting Flow

1. User initiates mint transaction
2. Minting policy validates:
   - Exactly 2 tokens minted
   - Token names follow convention
   - UTXO consumed for uniqueness
3. Tokens distributed:
   - Protocol token → validator script
   - User token → user wallet
4. Protocol datum initialized

### Update Flow

1. User submits update transaction
2. Validator verifies:
   - Correct redeemer (UpdateProtocol)
   - Admin signature present
   - Linear progression maintained
   - Immutable fields unchanged
3. New datum created with updates
4. Protocol NFT continues to output

### Burning Flow

1. User initiates burn transaction
2. Minting policy validates:
   - Correct burn redeemer
   - Proper authorization
3. Tokens destroyed
4. Protocol state cleaned up

## Security Model

### Authorization

- Admin keys control protocol updates
- Multi-signature support for admin actions
- User keys control user tokens

### Validation Layers

1. **Type safety**: OpShin type checking
2. **On-chain validation**: Plutus validators
3. **Off-chain validation**: Client-side checks
4. **Test coverage**: Comprehensive test suite

### Attack Mitigation

- **Double spending**: UTXO model prevents
- **State fragmentation**: Linear progression prevents
- **Unauthorized updates**: Admin key checks prevent
- **Token duplication**: Minting policy prevents

## Build System

Contracts compile to two formats:

- **`.plutus`**: JSON format for inspection/debugging
- **`.cbor`**: Binary format for on-chain deployment

Build pipeline:
```
OpShin Source (.py)
    │
    ├──► Compiler
    │
    ├──► .plutus (JSON)
    │
    └──► .cbor (Binary)
```

## Testing Strategy

Multi-layered testing approach:

1. **Unit tests**: Test individual functions
2. **Integration tests**: Test component interactions
3. **Contract tests**: Test compiled contracts
4. **Property tests**: Hypothesis-based testing

See: [Testing Documentation](../testing/overview.md)

## Next Steps

- [Validators](validators.md) - Deep dive into validator logic
- [Minting Policies](minting-policies.md) - Understand token minting
- [Types](types.md) - Explore type definitions
- [API Reference](../api/validators.md) - Full API documentation
