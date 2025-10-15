# Validators

Validators are the core logic components that enforce business rules and state transitions in Terrasacha Contracts.

## Overview

Validators in Cardano smart contracts determine whether a UTXO can be spent. They receive three inputs:

1. **Datum**: State data attached to the UTXO
2. **Redeemer**: Action/intent from the spender
3. **ScriptContext**: Transaction context and environment

## Protocol Validator

The main validator managing protocol state and NFT validation.

### Location

`src/terrasacha_contracts/validators/protocol.py`

### Purpose

- Validates protocol NFT continuation across transactions
- Handles protocol updates with proper authorization
- Implements linear progression patterns (one input → one output)
- Prevents state fragmentation and unauthorized modifications

### Redeemers

```python
class UpdateProtocol:
    """Update protocol parameters (authorized)"""
    pass

class EndProtocol:
    """Terminate protocol and burn NFT"""
    pass
```

### Validation Logic

#### Linear Progression Check

Ensures one input with protocol NFT → one output with same NFT:

```python
# Resolve the single input containing protocol NFT
own_input = resolve_linear_input(context.tx_info.inputs, own_policy)

# Resolve the single output continuing protocol NFT
own_output = resolve_linear_output(
    context.tx_info.outputs,
    own_address,
    own_policy
)
```

Benefits:
- Prevents splitting protocol state into multiple UTXOs
- Ensures clear state continuity
- Simplifies validation logic

#### Authorization Check

Verifies admin signatures for updates:

```python
# Extract admin keys from datum
admin_keys = datum.admin

# Check that transaction is signed by at least one admin
authorized = any(
    admin in context.tx_info.signatories
    for admin in admin_keys
)

assert authorized, "Unauthorized: missing admin signature"
```

#### Datum Immutability Check

Ensures core fields cannot change:

```python
new_datum = resolve_datum_from_output(own_output)

# These fields must remain constant
assert new_datum.admin == datum.admin, "Admin cannot be changed"
assert new_datum.oracle_id == datum.oracle_id, "Oracle ID is immutable"
assert new_datum.project_id == datum.project_id, "Project ID is immutable"

# Fees can be updated
# new_datum.fees can differ from datum.fees
```

#### NFT Continuation Check

Validates protocol NFT is preserved:

```python
# Check input has protocol NFT
input_value = own_input.resolved.value
assert has_protocol_nft(input_value, own_policy)

# Check output has same protocol NFT
output_value = own_output.value
assert has_protocol_nft(output_value, own_policy)
assert same_token_name(input_value, output_value, own_policy)
```

### Update Flow

1. User submits transaction with `UpdateProtocol` redeemer
2. Validator checks:
   - Admin signature present
   - Linear progression (1 input → 1 output)
   - Protocol NFT continues
   - Immutable fields unchanged
3. If all checks pass, transaction succeeds
4. New datum with updates is stored in output

### End Flow

1. User submits transaction with `EndProtocol` redeemer
2. Validator checks:
   - Admin signature present
   - Protocol NFT is burned (not in outputs)
3. If checks pass, protocol terminates
4. UTXO can be spent without continuing NFT

## Validation Helpers

### resolve_linear_input

Finds the single input containing a specific policy ID:

```python
def resolve_linear_input(
    inputs: List[TxInInfo],
    policy_id: PolicyId
) -> TxInInfo:
    """
    Returns the single input with the given policy.
    Fails if zero or multiple inputs found.
    """
```

### resolve_linear_output

Finds the single output at an address with a specific policy:

```python
def resolve_linear_output(
    outputs: List[TxOut],
    address: Address,
    policy_id: PolicyId
) -> TxOut:
    """
    Returns the single output at address with the given policy.
    Fails if zero or multiple outputs found.
    """
```

### resolve_datum_from_output

Extracts and decodes datum from output:

```python
def resolve_datum_from_output(output: TxOut) -> DatumProtocol:
    """
    Extracts datum from output and decodes to DatumProtocol.
    Handles both inline datums and datum hashes.
    """
```

## Error Cases

### Unauthorized Update

```
Error: "Unauthorized: missing admin signature"
Cause: Transaction not signed by any admin key
Fix: Include admin signature in transaction
```

### State Fragmentation

```
Error: "Multiple inputs with protocol NFT"
Cause: Attempting to spend multiple protocol UTXOs
Fix: Only spend one protocol UTXO per transaction
```

### Immutable Field Change

```
Error: "Oracle ID is immutable"
Cause: Attempted to change oracle_id in update
Fix: Keep oracle_id unchanged in new datum
```

### Missing NFT Continuation

```
Error: "Protocol NFT not in output"
Cause: Output doesn't contain protocol NFT
Fix: Ensure protocol NFT is in exactly one output
```

## Best Practices

### When Updating Protocol

1. Always include admin signature
2. Preserve immutable fields (admin, oracle_id, project_id)
3. Ensure linear progression (1 in → 1 out)
4. Include protocol NFT in output

### When Ending Protocol

1. Include admin signature
2. Burn protocol NFT (don't include in outputs)
3. Coordinate with user token burning

### Testing Validators

```python
def test_protocol_update():
    # Setup
    datum = DatumProtocol(...)
    redeemer = UpdateProtocol()
    context = mock_script_context(...)

    # Execute
    result = protocol_validator(datum, redeemer, context)

    # Assert
    assert result is True
```

## See Also

- [Minting Policies](minting-policies.md) - Token creation logic
- [Types](types.md) - Datum and redeemer definitions
- [API Reference](../api/validators.md) - Full API documentation
