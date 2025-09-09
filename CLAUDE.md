# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Install dependencies
poetry install

# Activate virtual environment
poetry shell

# Build all contracts
poetry run python src/scripts/build_contracts.py

# Alternative: Use the CLI menu for interactive contract compilation
# - Option 2: Compile/Recompile All Contracts (full compilation)
# - Option 3: Compile New Project Contract Only (fast, protocol must exist)

# Run tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_protocols.py

# Run tests with coverage
poetry run pytest --cov=src

# Format code
poetry run black .

# Sort imports
poetry run isort .

# Type checking
poetry run mypy .

# Compile individual contract
poetry run opshin compile src/terrasacha_contracts/validators/protocol.py
poetry run opshin compile src/terrasacha_contracts/minting_policies/protocol_nfts.py
```

## Project Architecture

This is a Cardano smart contract project built with OpShin that implements a protocol for carbon credit tokens and NFTs. The architecture follows a modular design:

### Core Components

**Validators** (`src/terrasacha_contracts/validators/`):
- `protocol.py`: Main protocol validator handling protocol NFT validation and datum updates
  - Validates protocol NFT continuation across transactions
  - Handles protocol updates with proper authorization checks
  - Implements linear progression patterns (one input → one output)

**Minting Policies** (`src/terrasacha_contracts/minting_policies/`):
- `protocol_nfts.py`: Mints paired NFTs (protocol + user tokens) with unique names derived from UTXO references
  - Enforces exactly 2 tokens per mint (1 protocol, 1 user)
  - Uses UTXO reference for uniqueness guarantee
  - Handles both minting and burning operations

**Types** (`src/terrasacha_contracts/types.py`):
- `DatumProtocol`: Protocol state containing admin keys, fees, oracle/project IDs
- `Mint/Burn`: Minting policy redeemers
- `UpdateProtocol/EndProtocol`: Protocol validator redeemers
- Token prefixes: `PROTO_` for protocol NFTs, `USER_` for user NFTs

**Utilities** (`src/terrasacha_contracts/util.py`):
- Linear validation helpers (`resolve_linear_input`, `resolve_linear_output`)
- Token name generation with UTXO-based uniqueness
- Purpose extraction and UTXO validation functions

### Key Design Patterns

1. **Linear Progression**: Contracts enforce one-input-to-one-output patterns to prevent state fragmentation
2. **Paired Token System**: Protocol and user NFTs are minted together with shared unique suffixes
3. **Datum Immutability**: Core protocol parameters (admin, oracle_id, project_id) cannot be changed
4. **UTXO-Based Uniqueness**: Token names derived from consuming specific UTXOs ensure global uniqueness

### Build System

- Contracts compile to both `.plutus` (JSON format) and `.cbor` (binary) in `artifacts/`
- Build script automatically processes all validators and minting policies
- OpShin version pinned to 0.24.x for compatibility

### Testing

- Uses pytest with comprehensive coverage reporting
- Test markers: `slow`, `integration`, `unit`, `performance`, `contracts`
- Mock utilities in `tests/mock.py` and `tests/tool.py`
- Ledger compatibility testing with both API v1 and v2

The codebase follows strict typing with mypy and uses black/isort for consistent formatting.