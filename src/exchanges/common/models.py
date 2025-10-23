from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class PositionSide(str, Enum):
    LONG = 'long'
    SHORT = 'short'


class OrderStatus(str, Enum):
    FILLED = 'filled'
    PARTIAL = 'partial'
    REJECTED = 'rejected'


class Position(BaseModel):
    coin: str
    size: Decimal
    side: PositionSide
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    liquidation_price: Decimal | None
    margin_used: Decimal
    leverage: int | None = None


class Order(BaseModel):
    order_id: str
    coin: str
    size: Decimal
    side: PositionSide
    fill_price: Decimal
    status: OrderStatus
    fee: Decimal = Field(default=Decimal('0'))


class Balance(BaseModel):
    total: Decimal
    available: Decimal
    used: Decimal


class SymbolInfo(BaseModel):
    symbol: str
    max_leverage: int
    sz_decimals: int


class OrderbookLevel(BaseModel):
    price: Decimal
    size: Decimal


class Orderbook(BaseModel):
    symbol: str
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    timestamp: int


class FundingRate(BaseModel):
    symbol: str
    rate: Decimal
    timestamp: int


class Volume24h(BaseModel):
    symbol: str
    base_volume: Decimal
    quote_volume: Decimal
