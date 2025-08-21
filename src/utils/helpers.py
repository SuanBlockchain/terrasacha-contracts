"""
Utility functions for Cardano dApp development
"""

import json
from pathlib import Path
from typing import Any, Dict

from pycardano import *


def load_contract(contract_path: str) -> PlutusV2Script:
    """
    Load a compiled OpShin contract
    """
    with open(contract_path, "r") as f:
        contract_json = json.load(f)

    cbor_hex = contract_json["cborHex"]
    return PlutusV2Script(bytes.fromhex(cbor_hex))


def get_script_address(
    script: PlutusV2Script, network: Network = Network.TESTNET
) -> Address:
    """
    Get the address of a script
    """
    script_hash = script_hash(script)
    return Address(ScriptCredential(script_hash), network=network)


def create_datum_hash(datum: PlutusData) -> DatumHash:
    """
    Create a datum hash from PlutusData
    """
    return datum_hash(datum)


def ada_to_lovelace(ada: float) -> int:
    """
    Convert ADA to lovelace
    """
    return int(ada * 1_000_000)


def lovelace_to_ada(lovelace: int) -> float:
    """
    Convert lovelace to ADA
    """
    return lovelace / 1_000_000


def load_wallet_from_mnemonic(
    mnemonic: str, network: Network = Network.TESTNET
) -> HDWallet:
    """
    Load wallet from mnemonic phrase
    """
    return HDWallet.from_mnemonic(mnemonic)


def get_wallet_address(wallet: HDWallet, network: Network = Network.TESTNET) -> Address:
    """
    Get the payment address from a wallet
    """
    payment_skey = wallet.derive_from_path("m/1852'/1815'/0'/0/0").signing_key
    payment_vkey = PaymentVerificationKey.from_signing_key(payment_skey)

    return Address(payment_part=payment_vkey.hash(), network=network)


class CardanoConfig:
    """
    Configuration for Cardano network
    """

    def __init__(self, network: Network = Network.TESTNET):
        self.network = network

        if network == Network.TESTNET:
            self.base_url = "https://cardano-preview.blockfrost.io/api/v0"
            self.magic = 2  # Preview testnet
        else:
            self.base_url = "https://cardano-mainnet.blockfrost.io/api/v0"
            self.magic = 764824073  # Mainnet

    def get_chain_context(self, project_id: str) -> ChainContext:
        """
        Get chain context for blockchain operations
        """
        return BlockFrostChainContext(project_id=project_id, base_url=self.base_url)
