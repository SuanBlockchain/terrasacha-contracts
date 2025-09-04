"""
Refactored Test Cardano App

Backward-compatible wrapper that uses the new core Cardano library architecture.
Maintains the same interface as the original CardanoDApp for existing tests.
"""

import os
import json
import pathlib
import time
from typing import Dict, Optional, Any

from dotenv import load_dotenv
import pycardano as pc
from opshin.builder import PlutusContract

# Import new core functionality
from src.cardano_offchain import (
    CardanoWallet,
    CardanoChainContext, 
    CardanoTransactions,
    ContractManager,
    TokenOperations
)
# from tests.cardano_cli import CardanoCLI

# Load .env from project root
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / 'tests/.env'
load_dotenv(ENV_FILE)


# Test class for backward compatibility
class TestCardanoDApp:
    pass