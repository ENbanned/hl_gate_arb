from enum import Enum
from decimal import Decimal
from pydantic import BaseModel


class SpreadDirection(str, Enum):
    GATE_SHORT = 'gate_short'
    GATE_LONG = 'gate_long'


class RawSpread(BaseModel):
    spread_pct: Decimal
    direction: SpreadDirection
    gate_price: Decimal
    hl_price: Decimal


