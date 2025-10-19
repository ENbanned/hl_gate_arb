from datetime import datetime, timedelta

import pytest

from src.core.models import (
  Balance,
  ExchangeName,
  FundingRate,
  OrderResult,
  Position,
  PositionSide,
  PositionStatus,
  Spread,
)


def test_position_side_enum():
  assert PositionSide.LONG == "long"
  assert PositionSide.SHORT == "short"


def test_position_status_enum():
  assert PositionStatus.OPEN == "open"
  assert PositionStatus.CLOSED == "closed"
  assert PositionStatus.FAILED == "failed"


def test_exchange_name_enum():
  assert ExchangeName.GATE == "gate"
  assert ExchangeName.HYPERLIQUID == "hyperliquid"


def test_balance_dataclass():
  balance = Balance(
    exchange=ExchangeName.GATE,
    account_value=10000.0,
    available=8000.0,
    total_margin_used=2000.0,
    unrealised_pnl=100.0
  )
  
  assert balance.exchange == ExchangeName.GATE
  assert balance.account_value == 10000.0
  assert balance.available == 8000.0
  assert balance.total_margin_used == 2000.0
  assert balance.unrealised_pnl == 100.0


def test_funding_rate_dataclass():
  now = datetime.now(datetime.UTC)
  funding = FundingRate(
    exchange=ExchangeName.GATE,
    coin="BTC",
    rate=0.0001,
    timestamp=now,
    next_funding_time=None
  )
  
  assert funding.exchange == ExchangeName.GATE
  assert funding.coin == "BTC"
  assert funding.rate == 0.0001
  assert funding.timestamp == now


def test_spread_dataclass():
  spread = Spread(
    coin="BTC",
    direction="gate_to_hl",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_price=50100.0,
    sell_price=50050.0,
    buy_slippage_pct=0.05,
    sell_slippage_pct=0.04,
    gross_spread_pct=3.5,
    net_spread_pct=3.0,
    estimated_cost=1000.0,
    estimated_revenue=1035.0,
    estimated_profit=35.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    funding_cost_pct=0.5,
    leverage=10,
    position_size_usd=100.0
  )
  
  assert spread.coin == "BTC"
  assert spread.direction == "gate_to_hl"
  assert spread.leverage == 10
  assert spread.net_spread_pct == 3.0


def test_order_result_success():
  order = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.1,
    executed_price=50000.0,
    success=True,
    order_id="12345"
  )
  
  assert order.success is True
  assert order.error is None
  assert order.order_id == "12345"


def test_order_result_failure():
  order = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.0,
    executed_price=None,
    success=False,
    error="insufficient_balance"
  )
  
  assert order.success is False
  assert order.error == "insufficient_balance"
  assert order.executed_price is None


def test_position_is_expired():
  now = datetime.now(datetime.UTC)
  
  position = Position(
    id="test_1",
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_order=OrderResult(
      exchange=ExchangeName.GATE,
      coin="BTC",
      side=PositionSide.LONG,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    sell_order=OrderResult(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      side=PositionSide.SHORT,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    entry_spread=3.0,
    expected_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=100.0,
    opened_at=now - timedelta(minutes=25),
    closed_at=None,
    status=PositionStatus.OPEN
  )
  
  assert position.is_expired(20) is True
  assert position.is_expired(30) is False


def test_position_is_expired_when_closed():
  now = datetime.now(datetime.UTC)
  
  position = Position(
    id="test_1",
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_order=OrderResult(
      exchange=ExchangeName.GATE,
      coin="BTC",
      side=PositionSide.LONG,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    sell_order=OrderResult(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      side=PositionSide.SHORT,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    entry_spread=3.0,
    expected_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=100.0,
    opened_at=now - timedelta(minutes=25),
    closed_at=now,
    status=PositionStatus.CLOSED
  )
  
  assert position.is_expired(20) is False


def test_position_get_duration_minutes():
  now = datetime.now(datetime.UTC)
  
  position = Position(
    id="test_1",
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_order=OrderResult(
      exchange=ExchangeName.GATE,
      coin="BTC",
      side=PositionSide.LONG,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    sell_order=OrderResult(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      side=PositionSide.SHORT,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    entry_spread=3.0,
    expected_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=100.0,
    opened_at=now - timedelta(minutes=15),
    closed_at=None,
    status=PositionStatus.OPEN
  )
  
  duration = position.get_duration_minutes()
  assert 14.5 < duration < 15.5


def test_position_get_duration_minutes_when_closed():
  now = datetime.now(datetime.UTC)
  opened = now - timedelta(minutes=20)
  closed = now - timedelta(minutes=5)
  
  position = Position(
    id="test_1",
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_order=OrderResult(
      exchange=ExchangeName.GATE,
      coin="BTC",
      side=PositionSide.LONG,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    sell_order=OrderResult(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      side=PositionSide.SHORT,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    entry_spread=3.0,
    expected_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=100.0,
    opened_at=opened,
    closed_at=closed,
    status=PositionStatus.CLOSED
  )
  
  duration = position.get_duration_minutes()
  assert 14.5 < duration < 15.5


def test_position_update_funding_cost_gate_buy():
  now = datetime.now(datetime.UTC)
  
  position = Position(
    id="test_1",
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_order=OrderResult(
      exchange=ExchangeName.GATE,
      coin="BTC",
      side=PositionSide.LONG,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    sell_order=OrderResult(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      side=PositionSide.SHORT,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    entry_spread=3.0,
    expected_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=1000.0,
    opened_at=now - timedelta(hours=1),
    closed_at=None,
    status=PositionStatus.OPEN
  )
  
  position.update_funding_cost(0.0001, 0.00015)
  
  assert position.accumulated_funding_cost != 0.0


def test_position_update_funding_cost_hyperliquid_buy():
  now = datetime.now(datetime.UTC)
  
  position = Position(
    id="test_1",
    coin="BTC",
    buy_exchange=ExchangeName.HYPERLIQUID,
    sell_exchange=ExchangeName.GATE,
    buy_order=OrderResult(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      side=PositionSide.LONG,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    sell_order=OrderResult(
      exchange=ExchangeName.GATE,
      coin="BTC",
      side=PositionSide.SHORT,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    entry_spread=3.0,
    expected_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=1000.0,
    opened_at=now - timedelta(hours=1),
    closed_at=None,
    status=PositionStatus.OPEN
  )
  
  position.update_funding_cost(0.0001, 0.00015)
  
  assert position.accumulated_funding_cost != 0.0


def test_position_defaults():
  now = datetime.now(datetime.UTC)
  
  position = Position(
    id="test_1",
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_order=OrderResult(
      exchange=ExchangeName.GATE,
      coin="BTC",
      side=PositionSide.LONG,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    sell_order=OrderResult(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      side=PositionSide.SHORT,
      size=0.1,
      executed_price=50000.0,
      success=True
    ),
    entry_spread=3.0,
    expected_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=100.0,
    opened_at=now,
    closed_at=None,
    status=PositionStatus.OPEN
  )
  
  assert position.realized_pnl == 0.0
  assert position.stop_loss_triggered is False
  assert position.time_limit_triggered is False