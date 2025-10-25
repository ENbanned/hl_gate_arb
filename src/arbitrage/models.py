from enum import Enum
from decimal import Decimal
from typing import Union
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
    """
    Mode для арбитража с минимальным порогом спреда

    percentage: минимальный спред в % для открытия позиции
    usd_size_per_pos: размер позиции в USDT
    target_spread_pct: целевой спред в % для закрытия с профитом (тейк-профит)
    stop_loss_pct: расширение спреда в % для стоп-лосса
    timeout_minutes: таймаут в минутах, если спред не сошелся
    """
    percentage: float
    usd_size_per_pos: float
    target_spread_pct: float
    stop_loss_pct: float
    timeout_minutes: float


class AnyProfit(BaseModel):
    pass


BotMode = Union[MinSpread, AnyProfit] 

