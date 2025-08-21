# Cardano OpShin dApp

A Cardano decentralized application (dApp) built with OpShin smart contracts and Poetry for dependency management.

## Project Structure

```
cardano-opshin-dapp/
├── contracts/
│   ├── validators/           # OpShin validator contracts
│   └── minting_policies/     # OpShin minting policies
├── artifacts/
│   ├── validators/           # Compiled validator contracts
│   └── minting_policies/     # Compiled minting policies
├── scripts/                  # Build and utility scripts
├── utils/                    # Helper functions
├── tests/                    # Test files
└── pyproject.toml           # Poetry configuration
```

## Setup

1. **Install Poetry** (if not already installed):
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Install dependencies**:
   ```bash
   poetry install
   ```

3. **Activate the virtual environment**:
   ```bash
   poetry shell
   ```

## Building Contracts

To compile all OpShin contracts:

```bash
poetry run python scripts/build_contracts.py
```

Or compile individual contracts:

```bash
# Compile a validator
poetry run opshin compile contracts/validators/simple_validator.py

# Compile a minting policy
poetry run opshin compile contracts/minting_policies/simple_nft.py
```

## Development Commands

```bash
# Run tests
poetry run pytest

# Format code
poetry run black .

# Sort imports
poetry run isort .

# Type checking
poetry run mypy .

# Run OpShin commands
poetry run opshin --help
poetry run opshin compile <contract_file>
poetry run opshin eval <contract_file>
```

## Environment Variables

Create a `.env` file for configuration:

```env
BLOCKFROST_PROJECT_ID=your_blockfrost_project_id
NETWORK=testnet  # or mainnet
WALLET_MNEMONIC=your_wallet_mnemonic_phrase
```

## Contract Examples

### Simple Validator
- **File**: `contracts/validators/simple_validator.py`
- **Purpose**: Basic UTXO validator with datum/redeemer validation
- **Features**: Checks redeemer action against datum value

### Simple NFT Minting Policy
- **File**: `contracts/minting_policies/simple_nft.py`
- **Purpose**: Mint exactly one NFT token
- **Features**: Allows minting 1 token or burning any amount

## Usage Examples

```python
from utils.helpers import load_contract, get_script_address
from pycardano import Network

# Load a compiled contract
validator = load_contract("artifacts/validators/simple_validator.plutus")

# Get the script address
script_address = get_script_address(validator, Network.TESTNET)
```

## Testing

Run the test suite:

```bash
poetry run pytest tests/
```

## Contributing

1. Install development dependencies: `poetry install`
2. Format code: `poetry run black .`
3. Sort imports: `poetry run isort .`
4. Run type checking: `poetry run mypy .`
5. Run tests: `poetry run pytest`

## Resources

- [OpShin Documentation](https://opshin.opshin.dev/)
- [PyCardano Documentation](https://pycardano.readthedocs.io/)
- [Cardano Developer Portal](https://developers.cardano.org/)
- [Plutus Documentation](https://plutus.readthedocs.io/)