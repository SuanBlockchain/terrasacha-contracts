#!opshin
from opshin.prelude import *


@dataclass
class SimpleDatum(PlutusData):
    """
    Simple datum that stores an integer value
    """

    CONSTR_ID = 0
    value: int


@dataclass
class SimpleRedeemer(PlutusData):
    """
    Simple redeemer with an action
    """

    CONSTR_ID = 0
    action: int


def validator(
    datum: SimpleDatum, redeemer: SimpleRedeemer, context: ScriptContext
) -> bool:
    """
    A simple validator that allows spending if:
    1. The redeemer action equals the datum value
    2. The transaction is signed by a specific public key hash
    """

    # Check if redeemer action matches datum value
    action_matches = redeemer.action == datum.value

    # Get transaction info
    tx_info = context.tx_info

    # Example: Check if transaction has at least one signature
    # In a real contract, you'd check for specific signature
    has_signature = len(tx_info.signatories) > 0

    # Allow spending if both conditions are met
    return action_matches and has_signature
