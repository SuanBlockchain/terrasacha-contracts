from opshin.prelude import *

from terrasacha_contracts.util import *


@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0


@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1


def validator(redeemer: Union[Mint, Burn], context: ScriptContext) -> None:
    _ = get_minting_purpose(context)
    if isinstance(redeemer, Mint):
        assert True, "Minting myUSDFree token"
    elif isinstance(redeemer, Burn):
        assert True, "Burning myUSDFree token"
