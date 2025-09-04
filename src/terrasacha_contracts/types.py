from opshin.prelude import *


@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0

@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1

# Constants
PREFIX_PROTOCOL_NFT = b"PROTO_"
PREFIX_USER_NFT = b"USER_"

@dataclass()
class DatumProtocol(PlutusData):
    CONSTR_ID = 0
    protocol_admin: List[bytes]  # List of admin public key hashes
    protocol_fee: int           # Protocol fee in lovelace
    oracle_id: bytes           # Oracle identifier

@dataclass()
class UpdateProtocol(PlutusData):
    CONSTR_ID = 1
    protocol_input_index: int
    user_input_index: int
    protocol_output_index: int

@dataclass()
class EndProtocol(PlutusData):
    CONSTR_ID = 2
    protocol_input_index: int

RedeemerProtocol = Union[UpdateProtocol, EndProtocol]