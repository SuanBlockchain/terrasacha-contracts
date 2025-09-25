# Contract Validations Reference

This document provides a comprehensive list of all validations performed by each contract in the Terrasacha protocol.

## Project Contract (`project.py`)

The project contract validates ProjectDatum updates and stakeholder operations. It works in tandem with the grey token minting policy to ensure consistency.

### UpdateProject Path Validations

**Preconditions:**
- Transaction must consume exactly one project NFT input
- User must possess the required protocol NFT

**Validations:**
1. **User Authorization**
   - User input must contain the required protocol token
   - Only authorized users can update project parameters

2. **NFT Continuation**
   - Project NFT must continue to exactly one output
   - NFT amount must remain 1 in the output

3. **Datum Update Business Rules** (`validate_datum_update`):

   **When project_state == 0 (Initialization Phase):**
   - Current supply can only increase
   - Current supply ≤ total supply
   - Total supply > 0, current supply ≥ 0
   - Sum of stakeholder participation == total supply
   - Certifications can only be added, not removed
   - Real certification values can only increase

   **When project_state >= 1 (Locked Phase):**
   - ALL fields must remain completely immutable
   - No changes allowed to any project parameters
   - Project enters permanent locked state

4. **Project State Progression**
   - Project state can only move forward (0→1→2→3)
   - Invalid states (> 3) are rejected

### UpdateToken Path Validations

**Preconditions:**
- Project state must be > 0 (active project required)
- Transaction must include token minting/burning

**Validations:**
1. **State Validation**
   - Project must be in active state (project_state > 0)
   - Cannot use UpdateToken during initialization phase

2. **Mint Amount Validation**
   - Minted/burned tokens must match redeemer.new_supply exactly
   - No discrepancies between declared and actual token operations

3. **Stakeholder Authorization** (`validate_stakeholder_authorization`)
   - If non-investor stakeholders exist, at least one must sign transaction
   - If only investor stakeholders exist, no signature required (public access)
   - Investor transactions are permissionless

4. **NFT Continuation**
   - Project NFT must continue to exactly one output
   - NFT amount must remain 1

5. **Supply Updates** (`validate_update_token_changes`)
   - Current supply = old_supply + mint_delta (exactly)
   - Current supply ≤ total supply
   - Current supply ≥ 0
   - No over-minting or invalid supply states

6. **Field Immutability**
   - Protocol policy ID cannot change
   - Project ID, project state, metadata cannot change
   - Token policy ID, token name, total supply cannot change
   - Stakeholder structure (identity, PKH, participation) cannot change
   - All certification data cannot change

7. **Amount Claimed Updates**
   - **During Minting (mint_delta > 0)**: amount_claimed can increase
   - **During Burning (mint_delta < 0)**: amount_claimed can decrease
   - Amount claimed ≥ 0 (no negative claims)
   - No cash refunds during burning operations

8. **Stakeholder Claim Limits**
   - Amount claimed ≤ stakeholder participation
   - Amount claimed ≤ total supply
   - Non-investor stakeholders must sign for their own claim changes
   - Investor claims are permissionless

### EndProject Path Validations

**Preconditions:**
- User must possess the required protocol NFT

**Validations:**
1. **User Authorization**
   - User input must contain the required protocol token
   - Only authorized users can end projects

---

## Grey Token Minting Policy (`grey.py`)

This minting policy validates token minting/burning operations and ensures they coordinate properly with the project contract datum updates.

### Common Validations (Both Mint and Burn)

1. **Project Reference Validation** (`validate_project_reference`)
   - Transaction must have at least one reference input
   - Reference input must contain project NFT with correct policy ID
   - Project token policy ID must match this minting policy ID
   - Project state must be > 0 (active state required)

2. **Token Operation Constraints**
   - Must mint or burn exactly one token type
   - Token name must match project datum token name
   - Cannot operate on multiple token types simultaneously

### Mint Operation Validations (`validate_mint_operation`)

**Preconditions:**
- Redeemer must be of type `Mint`
- Project must be in active state

**Validations:**
1. **Amount Validation**
   - Must mint exactly one token type
   - Minted amount must be positive (> 0)
   - Token name must match project datum specification

2. **Supply Constraints**
   - Minted amount ≤ remaining mintable supply (total - current)
   - Cannot exceed total supply defined in project datum
   - Ensures token scarcity and prevents over-minting

3. **Project State Validation**
   - Project must be in active state (project_state > 0)
   - Cannot mint during initialization phase

### Burn Operation Validations (`validate_burn_operation`)

**Preconditions:**
- Redeemer must be of type `Burn`
- Tokens to burn must exist in circulation

**Validations:**
1. **Amount Validation**
   - Must burn exactly one token type
   - Burned amount must be negative (in mint value representation)
   - Token name must match project datum specification

2. **Supply Constraints**
   - Burned amount ≤ current supply in circulation
   - Cannot burn more tokens than exist
   - Prevents invalid burn operations

3. **Output Constraints**
   - No tokens of this policy can be sent to outputs during burning
   - Ensures complete token destruction
   - Prevents partial burns or token retention

### Coordination with Project Contract

The grey minting policy works in coordination with the project contract:

**Project Contract Responsibilities:**
- Validates datum updates (current_supply, amount_claimed)
- Enforces stakeholder authorization
- Ensures immutable fields remain unchanged
- Validates UpdateToken redeemer parameters

**Grey Minting Policy Responsibilities:**
- Validates actual token amounts being minted/burned
- Ensures project reference input is correct and valid
- Prevents over-minting beyond total supply
- Prevents burning more than current supply
- Enforces complete token destruction during burns

**Coordination Mechanism:**
- Both contracts must validate successfully for token operations
- Reference input provides immutable project state for validation
- Supply tracking ensures token economics remain consistent
- Mint amounts must match between contracts

---

## Protocol Contract (`protocol.py`)

### UpdateProtocol Path Validations

1. **User Authorization**
   - User must possess the required protocol NFT
   - Only protocol admins can update protocol parameters

2. **NFT Continuation**
   - Protocol NFT must continue to exactly one output

3. **Datum Update Validation**
   - Protocol parameters can be updated based on business rules
   - Fee structures and admin lists can be modified

### EndProtocol Path Validations

1. **User Authorization**
   - User must possess the required protocol NFT
   - Only authorized users can end protocol

---

## Key Security Principles

1. **Linear Progression**: All contracts enforce one-input-to-one-output patterns to prevent state fragmentation

2. **Immutability After Lock**: Once project state ≥ 1, core parameters become immutable

3. **Supply Conservation**: Token supply is strictly tracked and enforced across all operations

4. **Authorization Hierarchy**: Different stakeholder types have different permission levels

5. **Reference Input Validation**: Immutable project state is used for validation across contracts

6. **Atomic Operations**: All validations must pass for transaction success

7. **No Partial Operations**: Token operations are all-or-nothing to maintain consistency