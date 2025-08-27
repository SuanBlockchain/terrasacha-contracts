#!/usr/bin/env python3
"""
Build script for OpShin contracts
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from opshin import build


def build_contract(
    contract_path: str, output_dir: str, contract_name: str
) -> Optional[Any]:
    """
    Build a single OpShin contract
    """
    print(f"Building {contract_name}...")

    try:
        # Build the contract
        contract = build(contract_path)

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Extract CBOR data using bytes() conversion
        cbor_data = bytes(contract)

        # Write the compiled contract
        output_file = os.path.join(output_dir, f"{contract_name}.plutus")
        with open(output_file, "w") as f:
            json.dump(
                {
                    "type": "PlutusScriptV2",
                    "description": f"OpShin {contract_name} Contract",
                    "cborHex": cbor_data.hex(),
                },
                f,
                indent=2,
            )

        print(f"✅ Built {contract_name} -> {output_file}")

        # Also save as binary for pycardano
        binary_file = os.path.join(output_dir, f"{contract_name}.cbor")
        with open(binary_file, "wb") as f:
            f.write(cbor_data)

        return contract

    except Exception as e:
        print(f"❌ Failed to build {contract_name}: {e}")
        return None


def main() -> None:
    """
    Build all contracts
    """
    base_dir = Path(__file__).parent.parent
    contracts_dir = base_dir / "terrasacha_contracts"
    artifacts_dir = base_dir / "artifacts"

    # Build validators
    validators_dir = contracts_dir / "validators"
    validators_output = artifacts_dir / "validators"

    if validators_dir.exists():
        for contract_file in validators_dir.glob("*.py"):
            contract_name = contract_file.stem
            build_contract(str(contract_file), str(validators_output), contract_name)

    # Build minting policies
    policies_dir = contracts_dir / "minting_policies"
    policies_output = artifacts_dir / "minting_policies"

    if policies_dir.exists():
        for contract_file in policies_dir.glob("*.py"):
            contract_name = contract_file.stem
            build_contract(str(contract_file), str(policies_output), contract_name)

    print("\n🎉 Build complete!")


if __name__ == "__main__":
    main()
