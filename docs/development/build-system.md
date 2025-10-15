# Build System

Understanding the contract build system in Terrasacha Contracts.

## Overview

Contracts are written in Python (OpShin) and compiled to Plutus for on-chain deployment.

## Build Process

```
OpShin Source (.py)
      ↓
OpShin Compiler
      ↓
   ┌──┴──┐
   ↓     ↓
.plutus  .cbor
(JSON)   (Binary)
```

### Output Formats

**`.plutus` (JSON)**:
- Human-readable
- Useful for debugging
- Can be inspected with text editors
- Used for testing and verification

**`.cbor` (Binary)**:
- Compact format
- Used for on-chain deployment
- More efficient storage
- Required by Cardano node

## Building Contracts

### Build All Contracts

```bash
uv run python src/scripts/build_contracts.py
```

This compiles:
- All validators in `src/terrasacha_contracts/validators/`
- All minting policies in `src/terrasacha_contracts/minting_policies/`
- Outputs to `artifacts/` directory

### Build Individual Contract

Validator:
```bash
uv run opshin compile src/terrasacha_contracts/validators/protocol.py
```

Minting policy:
```bash
uv run opshin compile src/terrasacha_contracts/minting_policies/protocol_nfts.py
```

### Interactive Build

Use the CLI menu:
```bash
uv run python src/scripts/cli_menu.py
```

Options:
- **Option 2**: Compile/Recompile All Contracts (full)
- **Option 3**: Compile New Project Contract Only (fast)

## Artifacts Directory

After building:

```
artifacts/
├── validators/
│   ├── protocol.plutus      # JSON format
│   └── protocol.cbor         # Binary format
└── minting_policies/
    ├── protocol_nfts.plutus
    └── protocol_nfts.cbor
```

## Build Script

### Location

`src/scripts/build_contracts.py`

### Features

- Automatic discovery of contracts
- Parallel compilation (faster)
- Error reporting
- Artifact organization

### Configuration

OpShin version: `>=0.26.0` (specified in `pyproject.toml`)

## Compilation Options

### Standard Compilation

```bash
uv run opshin compile <contract_file>
```

### With Optimization

```bash
uv run opshin compile --optimize <contract_file>
```

### Generate Only CBOR

```bash
uv run opshin compile --cbor-only <contract_file>
```

## Verification

### Inspect Plutus Output

```bash
cat artifacts/validators/protocol.plutus | jq .
```

### Check CBOR Size

```bash
ls -lh artifacts/validators/protocol.cbor
```

### Verify Compilation

Run contract tests:
```bash
uv run pytest -m contracts
```

## Troubleshooting

### Compilation Errors

**Syntax errors**:
```bash
# Check Python syntax
python -m py_compile src/terrasacha_contracts/validators/protocol.py
```

**Type errors**:
```bash
# Run type checker
uv run mypy src/terrasacha_contracts/
```

**OpShin errors**:
```bash
# Check OpShin version
uv run opshin --version

# Update OpShin
uv add opshin --upgrade
```

### Clean Build

Remove old artifacts:
```bash
rm -rf artifacts/
uv run python src/scripts/build_contracts.py
```

### Build Performance

Optimize build time:
```bash
# Use faster compilation (skip optimizations)
export OPSHIN_FAST_BUILD=1
uv run python src/scripts/build_contracts.py
```

## Best Practices

### Before Committing

1. Clean build all contracts
2. Run contract tests
3. Verify artifact sizes reasonable
4. Check for compilation warnings

```bash
rm -rf artifacts/
uv run python src/scripts/build_contracts.py
uv run pytest -m contracts
```

### Version Control

**Do commit**:
- Source contracts (`.py` files)
- Build scripts
- Test files

**Don't commit** (add to `.gitignore`):
- Artifacts directory
- Compilation cache
- Temporary files

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Build contracts
  run: |
    uv sync
    uv run python src/scripts/build_contracts.py

- name: Test contracts
  run: |
    uv run pytest -m contracts
```

## See Also

- [Development Guide](../getting-started/development.md)
- [CLI Tools](cli-tools.md)
- [OpShin Documentation](https://opshin.opshin.dev/)
