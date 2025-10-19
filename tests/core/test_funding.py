from datetime import datetime

import pytest

from src.core.funding import FundingManager
from src.core.models import ExchangeName, FundingRate


@pytest.mark.asyncio
async def test_funding_manager_initialization(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  
  assert manager.gate == mock_gate_exchange
  assert manager.hyperliquid == mock_hyperliquid_exchange
  assert len(manager.funding_cache) == 0


@pytest.mark.asyncio
async def test_update_funding_rates_success(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.get_funding_rate.return_value = 0.0001
  mock_hyperliquid_exchange.get_funding_rate.return_value = 0.00015
  
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  await manager.update_funding_rates(["BTC"])
  
  assert "BTC" in manager.funding_cache
  assert ExchangeName.GATE in manager.funding_cache["BTC"]
  assert ExchangeName.HYPERLIQUID in manager.funding_cache["BTC"]
  assert manager.funding_cache["BTC"][ExchangeName.GATE].rate == 0.0001
  assert manager.funding_cache["BTC"][ExchangeName.HYPERLIQUID].rate == 0.00015


@pytest.mark.asyncio
async def test_update_funding_rates_multiple_coins(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.get_funding_rate.return_value = 0.0001
  mock_hyperliquid_exchange.get_funding_rate.return_value = 0.00015
  
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  await manager.update_funding_rates(["BTC", "ETH", "SOL"])
  
  assert len(manager.funding_cache) == 3
  assert "BTC" in manager.funding_cache
  assert "ETH" in manager.funding_cache
  assert "SOL" in manager.funding_cache


@pytest.mark.asyncio
async def test_update_funding_rates_with_exception(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.get_funding_rate.side_effect = Exception("API error")
  
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  await manager.update_funding_rates(["BTC"])
  
  assert len(manager.funding_cache) == 0


def test_get_funding_rate_existing(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  manager.funding_cache["BTC"] = {
    ExchangeName.GATE: FundingRate(
      exchange=ExchangeName.GATE,
      coin="BTC",
      rate=0.0001,
      timestamp=datetime.utcnow()
    )
  }
  
  rate = manager.get_funding_rate("BTC", ExchangeName.GATE)
  assert rate == 0.0001


def test_get_funding_rate_missing_coin(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  
  rate = manager.get_funding_rate("BTC", ExchangeName.GATE)
  assert rate == 0.0


def test_get_funding_rate_missing_exchange(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  manager.funding_cache["BTC"] = {
    ExchangeName.GATE: FundingRate(
      exchange=ExchangeName.GATE,
      coin="BTC",
      rate=0.0001,
      timestamp=datetime.utcnow()
    )
  }
  
  rate = manager.get_funding_rate("BTC", ExchangeName.HYPERLIQUID)
  assert rate == 0.0


def test_calculate_funding_cost_gate_buy(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  manager.funding_cache["BTC"] = {
    ExchangeName.GATE: FundingRate(
      exchange=ExchangeName.GATE,
      coin="BTC",
      rate=0.0001,
      timestamp=datetime.utcnow()
    ),
    ExchangeName.HYPERLIQUID: FundingRate(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      rate=0.00015,
      timestamp=datetime.utcnow()
    )
  }
  
  buy_rate, sell_rate, net_cost_pct = manager.calculate_funding_cost(
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    position_time_minutes=60,
    size_usd=1000.0,
    leverage=10
  )
  
  assert buy_rate == 0.0001
  assert sell_rate == 0.00015
  assert isinstance(net_cost_pct, float)


def test_calculate_funding_cost_hyperliquid_buy(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  manager.funding_cache["BTC"] = {
    ExchangeName.GATE: FundingRate(
      exchange=ExchangeName.GATE,
      coin="BTC",
      rate=0.0001,
      timestamp=datetime.utcnow()
    ),
    ExchangeName.HYPERLIQUID: FundingRate(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      rate=0.00015,
      timestamp=datetime.utcnow()
    )
  }
  
  buy_rate, sell_rate, net_cost_pct = manager.calculate_funding_cost(
    coin="BTC",
    buy_exchange=ExchangeName.HYPERLIQUID,
    sell_exchange=ExchangeName.GATE,
    position_time_minutes=60,
    size_usd=1000.0,
    leverage=10
  )
  
  assert buy_rate == 0.00015
  assert sell_rate == 0.0001
  assert isinstance(net_cost_pct, float)


def test_is_funding_acceptable_within_threshold(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  manager.funding_cache["BTC"] = {
    ExchangeName.GATE: FundingRate(
      exchange=ExchangeName.GATE,
      coin="BTC",
      rate=0.0001,
      timestamp=datetime.utcnow()
    ),
    ExchangeName.HYPERLIQUID: FundingRate(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      rate=0.00015,
      timestamp=datetime.utcnow()
    )
  }
  
  result = manager.is_funding_acceptable(
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    max_diff_pct=0.001
  )
  
  assert result is True


def test_is_funding_acceptable_exceeds_threshold(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  manager.funding_cache["BTC"] = {
    ExchangeName.GATE: FundingRate(
      exchange=ExchangeName.GATE,
      coin="BTC",
      rate=0.0001,
      timestamp=datetime.utcnow()
    ),
    ExchangeName.HYPERLIQUID: FundingRate(
      exchange=ExchangeName.HYPERLIQUID,
      coin="BTC",
      rate=0.0005,
      timestamp=datetime.utcnow()
    )
  }
  
  result = manager.is_funding_acceptable(
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    max_diff_pct=0.0001
  )
  
  assert result is False


def test_is_funding_acceptable_missing_rates(mock_gate_exchange, mock_hyperliquid_exchange):
  manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  
  result = manager.is_funding_acceptable(
    coin="BTC",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    max_diff_pct=0.001
  )
  
  assert result is True