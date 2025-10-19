from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PositionSide(str, Enum):
  LONG = "long"
  SHORT = "short"


class PositionStatus(str, Enum):
  OPEN = "open"
  CLOSED = "closed"
  FAILED = "failed"


class ExchangeName(str, Enum):
  GATE = "gate"
  HYPERLIQUID = "hyperliquid"


@dataclass
class Balance:
  exchange: ExchangeName
  account_value: float
  available: float
  total_margin_used: float
  unrealised_pnl: float


@dataclass
class FundingRate:
  exchange: ExchangeName
  coin: str
  rate: float
  timestamp: datetime
  next_funding_time: datetime | None = None


@dataclass
class Spread:
  coin: str
  direction: str
  
  buy_exchange: ExchangeName
  sell_exchange: ExchangeName
  
  buy_price: float
  sell_price: float
  
  buy_slippage_pct: float
  sell_slippage_pct: float
  
  gross_spread_pct: float
  net_spread_pct: float
  
  estimated_cost: float
  estimated_revenue: float
  estimated_profit: float
  
  buy_funding_rate: float
  sell_funding_rate: float
  funding_cost_pct: float
  
  leverage: int
  position_size_usd: float


@dataclass
class OrderResult:
  exchange: ExchangeName
  coin: str
  side: PositionSide
  size: float
  executed_price: float | None
  success: bool
  error: str | None = None
  order_id: str | None = None


@dataclass
class Position:
  id: str
  coin: str
  
  buy_exchange: ExchangeName
  sell_exchange: ExchangeName
  
  buy_order: OrderResult
  sell_order: OrderResult
  
  entry_spread: float
  expected_profit: float
  
  buy_funding_rate: float
  sell_funding_rate: float
  estimated_funding_cost: float
  accumulated_funding_cost: float
  
  leverage: int
  size_usd: float
  
  opened_at: datetime
  closed_at: datetime | None
  
  status: PositionStatus
  
  realized_pnl: float = 0.0
  stop_loss_triggered: bool = False
  time_limit_triggered: bool = False
  
  
  def is_expired(self, max_minutes: int) -> bool:
    if self.closed_at:
      return False
    elapsed = (datetime.now(datetime.UTC) - self.opened_at).total_seconds() / 60
    return elapsed >= max_minutes
  
  
  def get_duration_minutes(self) -> float:
    end_time = self.closed_at or datetime.now(datetime.UTC)
    return (end_time - self.opened_at).total_seconds() / 60
  
  
  def update_funding_cost(self, gate_rate: float, hl_rate: float):
    duration_hours = self.get_duration_minutes() / 60
    
    if self.buy_exchange == ExchangeName.GATE:
      gate_cost = gate_rate * (duration_hours / 8)
      hl_cost = -hl_rate * duration_hours
    else:
      hl_cost = hl_rate * duration_hours
      gate_cost = -gate_rate * (duration_hours / 8)
    
    self.accumulated_funding_cost = (gate_cost + hl_cost) * self.size_usd * self.leverage