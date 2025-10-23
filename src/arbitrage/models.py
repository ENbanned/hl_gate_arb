from enum import Enum
from decimal import Decimal
from pydantic import BaseModel


class RawSpread(BaseModel):
    spread_pct: Decimal


class SpreadDirection(str, Enum):
    GATE_SHORT = 'gate_short'
    GATE_LONG = 'gate_long'