from enum import Enum
from decimal import Decimal
from pydantic import BaseModel, Field


class SpreadDirection(str, Enum):
    GATE_SHORT = 'gate_short'
    HL_SHORT = 'hl_long'


class RawSpread(BaseModel):
    spread_pct: Decimal
    direction: SpreadDirection
    gate_price: Decimal
    hl_price: Decimal


class NetSpread(BaseModel):
    symbol: str
    size: float
    gate_short_pct: Decimal
    hl_short_pct: Decimal
    profit_usd_gate_short: Decimal
    profit_usd_hl_short: Decimal
    best_direction: SpreadDirection
    best_usd_profit: Decimal


class MinSpread(BaseModel):
    percentage: float
    usd_size_per_pos: 


class AnyProfit(BaseModel):
    pass


type BotMode = MinSpread | AnyProfit 

