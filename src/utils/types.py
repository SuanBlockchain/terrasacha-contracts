from opshin.prelude import *


# @dataclass
# class Mint(PlutusData):
#     CONSTR_ID = 0


# @dataclass
# class Burn(PlutusData):
#     CONSTR_ID = 1


# @dataclass
# class DatumProtocol(PlutusData):
#     """Protocol datum containing admin and configuration information"""

#     CONSTR_ID = 0
#     protocol_admin: List[PubKeyHash]  # List of admin public key hashes
#     protocol_fee: int  # Protocol fee in lovelace
#     oracle_id: bytes  # Oracle identifier
#     project_id: bytes  # Project identifier


@dataclass
class DatumProject(PlutusData):
    """Project-specific datum"""

    CONSTR_ID = 1
    project_id: bytes
    project_state: int  # 0=initialized, 1=distributed, 2=certified, 3=closed
    total_supply: int
    current_supply: int
    emission_dates: List[POSIXTime]


@dataclass
class DatumOracle(PlutusData):
    """Oracle price information"""

    CONSTR_ID = 2
    project_id: bytes
    token_price_ada: int  # Price in lovelace
    token_price_usd: int  # Price in USD cents
    token_price_cop: int  # Price in COP centavos
    last_update: POSIXTime


# Redeemer types for spending operations
@dataclass
class UpdateProtocol(PlutusData):
    CONSTR_ID = 0


@dataclass
class RemoveProtocol(PlutusData):
    CONSTR_ID = 1


@dataclass
class BuyTokens(PlutusData):
    CONSTR_ID = 2


@dataclass
class SellTokens(PlutusData):
    CONSTR_ID = 3
