# Terrasacha Contracts

Welcome to the **Terrasacha Contracts** documentation. This project implements Cardano smart contracts for carbon credit tokens and NFTs using [OpShin](https://opshin.opshin.dev/).

## Overview

A Cardano decentralized application (dApp) built with OpShin smart contracts and uv for fast dependency management. The project implements a protocol for managing carbon credit tokens and NFTs with advanced validation and minting capabilities.

## Key Features

- **Protocol Validator**: Manages protocol state and NFT validation with linear progression patterns
- **Minting Policies**: Creates unique paired NFTs (protocol + user tokens) with UTXO-based uniqueness
- **Linear Progression**: Enforces one-input-to-one-output patterns to prevent state fragmentation
- **Datum Immutability**: Core protocol parameters cannot be changed after initialization
- **Type Safety**: Comprehensive type checking with mypy and strict validation

## Quick Start

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --extra dev

# Build all contracts
uv run python src/scripts/build_contracts.py

# Run tests
uv run pytest
```

## Project Structure

```
terrasacha-contracts/
├── src/terrasacha_contracts/
│   ├── validators/           # OpShin validator contracts
│   ├── minting_policies/     # OpShin minting policies
│   ├── types.py             # Type definitions and datums
│   └── util.py              # Helper functions
├── artifacts/
│   ├── validators/          # Compiled validator contracts
│   └── minting_policies/    # Compiled minting policies
├── src/scripts/             # Build and utility scripts
├── tests/                   # Test files
└── pyproject.toml          # Project configuration
```

## Quick Links

- [Installation Guide](getting-started/installation.md) - Set up your development environment
- [Quick Start](getting-started/quickstart.md) - Build and deploy your first contract
- [Architecture Overview](architecture/overview.md) - Understand the system design
- [API Reference](api/validators.md) - Detailed API documentation

## Technology Stack

- **OpShin** 0.26.x - Python-based smart contract language for Cardano
- **uv** - Fast Python package manager
- **pytest** - Testing framework with comprehensive coverage
- **ruff** - Fast Python linter and formatter
- **mypy** - Static type checker

## Project Status

Built with OpShin 0.26.x targeting the Cardano blockchain. Currently in active development.

## Support

- [GitHub Repository](https://github.com/SuanBlockchain/terrasacha-contracts)
- [OpShin Documentation](https://opshin.opshin.dev/)
- [Cardano Developer Portal](https://developers.cardano.org/)
