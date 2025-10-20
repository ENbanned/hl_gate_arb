from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ExchangeName(str, Enum):
  GATE = "gate"
  HYPERLIQUID = "hyperliquid"


class PositionStatus(str, Enum):
  OPENING = "opening"
  ACTIVE = "active"
  CLOSING = "closing"
  CLOSED = "closed"
  FAILED = "failed"


class Balance(BaseModel):
  total: float
  available: float
  in_positions: float
  timestamp: datetime = Field(default_factory=datetime.now)


class OrderbookLevel(BaseModel):
  price: float
  size: float


class Orderbook(BaseModel):
  bids: list[OrderbookLevel]
  asks: list[OrderbookLevel]
  timestamp: datetime = Field(default_factory=datetime.now)


class FundingRate(BaseModel):
  rate: float
  next_funding_time: datetime
  timestamp: datetime = Field(default_factory=datetime.now)


class Spread(BaseModel):
  coin: str
  direction: Literal["gate_to_hl", "hl_to_gate"]
  
  buy_exchange: ExchangeName
  sell_exchange: ExchangeName
  
  buy_price: float
  sell_price: float
  
  gross_spread_pct: float
  funding_cost_pct: float
  net_spread_pct: float
  
  size_usd: float
  leverage: int
  
  estimated_profit_usd: float
  
  timestamp: datetime = Field(default_factory=datetime.now)


class Position(BaseModel):
  id: str
  coin: str
  direction: Literal["gate_to_hl", "hl_to_gate"]
  
  buy_exchange: ExchangeName
  sell_exchange: ExchangeName
  
  size_usd: float
  leverage: int
  
  entry_spread_pct: float
  entry_buy_price: float
  entry_sell_price: float
  
  expected_profit_usd: float
  
  buy_order_id: str | None = None
  sell_order_id: str | None = None
  
  status: PositionStatus
  
  opened_at: datetime = Field(default_factory=datetime.now)
  closed_at: datetime | None = None
  
  current_spread_pct: float | None = None
  realized_pnl_usd: float = 0.0
  funding_cost_usd: float = 0.0
  
  close_reason: str | None = None


class PositionSnapshot(BaseModel):
  exchange: ExchangeName
  coin: str
  size: float
  side: Literal["long", "short"]
  entry_price: float
  mark_price: float
  unrealized_pnl: float
  margin_used: float