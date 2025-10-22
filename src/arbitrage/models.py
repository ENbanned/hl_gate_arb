from decimal import Decimal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SpreadDirection(str, Enum):
  LONG_A_SHORT_B = 'long_a_short_b'
  SHORT_A_LONG_B = 'short_a_long_b'


class SpreadStatus(str, Enum):
  OPEN = 'open'
  CLOSING = 'closing'
  CLOSED = 'closed'
  FAILED = 'failed'


class Spread(BaseModel):
  symbol: str
  exchange_a: str
  exchange_b: str
  price_a: Decimal
  price_b: Decimal
  deviation_pct: Decimal
  timestamp: datetime = Field(default_factory=datetime.now)


class SpreadOpportunity(BaseModel):
  spread: Spread
  direction: SpreadDirection
  estimated_profit_pct: Decimal
  estimated_profit_usd: Decimal
  max_size: Decimal
  funding_cost_daily: Decimal
  roi_daily: Decimal


class ArbitragePosition(BaseModel):
  id: str
  symbol: str
  exchange_a: str
  exchange_b: str
  direction: SpreadDirection
  size: Decimal
  entry_price_a: Decimal
  entry_price_b: Decimal
  entry_spread: Decimal
  current_spread: Decimal | None = None
  realized_pnl: Decimal = Field(default=Decimal('0'))
  unrealized_pnl: Decimal = Field(default=Decimal('0'))
  fees_paid: Decimal = Field(default=Decimal('0'))
  funding_paid: Decimal = Field(default=Decimal('0'))
  status: SpreadStatus = SpreadStatus.OPEN
  opened_at: datetime = Field(default_factory=datetime.now)
  closed_at: datetime | None = None
  