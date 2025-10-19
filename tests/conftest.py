import asyncio
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

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


@pytest.fixture
def event_loop():
  loop = asyncio.get_event_loop_policy().new_event_loop()
  yield loop
  loop.close()


@pytest.fixture
def mock_gate_exchange():
  exchange = MagicMock()
  exchange.name = ExchangeName.GATE
  exchange.get_balance = AsyncMock(return_value=Balance(
    exchange=ExchangeName.GATE,
    account_value=10000.0,
    available=8000.0,
    total_margin_used=2000.0,
    unrealised_pnl=100.0
  ))
  exchange.get_orderbook = AsyncMock(return_value={
    "levels": [
      [{"px": "49900.0", "sz": "1.0"}],  
      [{"px": "50000.0", "sz": "1.0"}]
    ],
    "timestamp": datetime.now(UTC)
  })
  exchange.get_leverage_limits = AsyncMock(return_value=(1, 20))
  exchange.get_funding_rate = AsyncMock(return_value=0.0001)
  exchange.calculate_slippage = MagicMock(return_value=0.05)
  exchange.open_position = AsyncMock()
  exchange.close_position = AsyncMock()
  return exchange


@pytest.fixture
def mock_hyperliquid_exchange():
  exchange = MagicMock()
  exchange.name = ExchangeName.HYPERLIQUID
  exchange.get_balance = AsyncMock(return_value=Balance(
    exchange=ExchangeName.HYPERLIQUID,
    account_value=10000.0,
    available=8000.0,
    total_margin_used=2000.0,
    unrealised_pnl=50.0
  ))
  exchange.get_orderbook = AsyncMock(return_value={
    "levels": [
      [{"px": "50100.0", "sz": "1.0"}],
      [{"px": "50200.0", "sz": "1.0"}]
    ],
    "timestamp": datetime.now(UTC)
  })
  exchange.get_leverage_limits = AsyncMock(return_value=(1, 25))
  exchange.get_funding_rate = AsyncMock(return_value=0.00015)
  exchange.calculate_slippage = MagicMock(return_value=0.04)
  exchange.open_position = AsyncMock()
  exchange.close_position = AsyncMock()
  return exchange


@pytest.fixture
def sample_spread():
  return Spread(
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


@pytest.fixture
def sample_position(sample_spread):
  buy_order = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.02,
    executed_price=50100.0,
    success=True,
    order_id="buy_123"
  )
  
  sell_order = OrderResult(
    exchange=ExchangeName.HYPERLIQUID,
    coin="BTC",
    side=PositionSide.SHORT,
    size=0.02,
    executed_price=50050.0,
    success=True,
    order_id="sell_456"
  )
  
  return Position(
    id="test_pos_1",
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_order=buy_order,
    sell_order=sell_order,
    entry_spread=3.0,
    expected_profit=35.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    estimated_funding_cost=0.5,
    accumulated_funding_cost=0.0,
    leverage=10,
    size_usd=100.0,
    opened_at=datetime.now(UTC),
    closed_at=None,
    status=PositionStatus.OPEN
  )


@pytest.fixture
def sample_funding_rate():
  return FundingRate(
    exchange=ExchangeName.GATE,
    coin="BTC",
    rate=0.0001,
    timestamp=datetime.now(UTC),
    next_funding_time=None
  )