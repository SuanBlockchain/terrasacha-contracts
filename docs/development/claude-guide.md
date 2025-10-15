# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Install dependencies
uv sync

# Install with dev dependencies
uv sync --extra dev

# Activate virtual environment
source .venv/bin/activate

# Build all contracts
uv run python src/scripts/build_contracts.py

# Alternative: Use the CLI menu for interactive contract compilation
# - Option 2: Compile/Recompile All Contracts (full compilation)
# - Option 3: Compile New Project Contract Only (fast, protocol must exist)

# Run tests
uv run pytest

# Run specific test file
uv run pytest tests/test_protocols.py

# Run tests with coverage
uv run pytest --cov=src

# Format code
uv run ruff format .

# Sort imports
uv run ruff check --select I --fix .

# Lint and fix issues
uv run ruff check --fix .

# Type checking
uv run mypy .

# Compile individual contract
uv run opshin compile src/terrasacha_contracts/validators/protocol.py
uv run opshin compile src/terrasacha_contracts/minting_policies/protocol_nfts.py

# Update dependencies
uv lock --upgrade
uv sync

# Add new dependency
uv add <package-name>

# Add dev dependency
uv add --dev <package-name>
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