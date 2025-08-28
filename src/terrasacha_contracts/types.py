from opshin.prelude import *

@dataclass()
class DatumProtocol(PlutusData):
    CONSTR_ID = 0
    protocol_admin: List[bytes]  # List of admin public key hashes
    protocol_fee: int           # Protocol fee in lovelace
    oracle_id: bytes           # Oracle identifier
    project_id: bytes          # Project identifier

@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0

@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1

# Constants
PREFIX_PROTOCOL_NFT = b"PROTO_"
PREFIX_USER_NFT = b"USER_"