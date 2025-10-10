---
description: "Compile all OpShin contracts in the project"
tools: ["bash"]
---

# Build All Contracts

Compile all OpShin validators and minting policies using the project's build script.

This will:
1. Build all validator contracts in `src/terrasacha_contracts/validators/`
2. Build all minting policy contracts in `src/terrasacha_contracts/minting_policies/`
3. Generate both `.plutus` (JSON) and `.cbor` (binary) artifacts
4. Output compiled contracts to the `artifacts/` directory

```bash
uv run python src/scripts/build_contracts.py
```

After building, check the `artifacts/` directory for the compiled contracts.