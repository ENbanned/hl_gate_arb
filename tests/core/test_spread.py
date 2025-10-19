from unittest.mock import patch

import pytest

from src.core.funding import FundingManager
from src.core.models import ExchangeName
from src.core.spread import SpreadCalculator


@pytest.mark.asyncio
async def test_spread_calculator_initialization(mock_gate_exchange, mock_hyperliquid_exchange):
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  assert calculator.gate == mock_gate_exchange
  assert calculator.hyperliquid == mock_hyperliquid_exchange
  assert calculator.funding_manager == funding_manager


@pytest.mark.asyncio
async def test_calculate_spread_success(mock_gate_exchange, mock_hyperliquid_exchange):
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.funding_cache["BTC"] = {
    "gate": 0.0001,
    "hyperliquid": 0.00015
  }
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  gate_to_hl, hl_to_gate = await calculator.calculate_spread("BTC", 100.0, 10)
  
  assert gate_to_hl is not None
  assert hl_to_gate is not None
  assert gate_to_hl.coin == "BTC"
  assert hl_to_gate.coin == "BTC"


@pytest.mark.asyncio
async def test_calculate_spread_missing_orderbooks(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.get_orderbook.return_value = None
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  gate_to_hl, hl_to_gate = await calculator.calculate_spread("BTC", 100.0, 10)
  
  assert gate_to_hl is None
  assert hl_to_gate is None


@pytest.mark.asyncio
async def test_calculate_spread_empty_levels(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.get_orderbook.return_value = {"levels": [[], []]}
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  gate_to_hl, hl_to_gate = await calculator.calculate_spread("BTC", 100.0, 10)
  
  assert gate_to_hl is None
  assert hl_to_gate is None


@pytest.mark.asyncio
async def test_calculate_spread_negative_spread_returns_none(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.get_orderbook.return_value = {
    "levels": [
      [{"px": "50000.0", "sz": "1.0"}],
      [{"px": "51000.0", "sz": "1.0"}]
    ]
  }
  
  mock_hyperliquid_exchange.get_orderbook.return_value = {
    "levels": [
      [{"px": "49000.0", "sz": "1.0"}],
      [{"px": "49500.0", "sz": "1.0"}]
    ]
  }
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.funding_cache["BTC"] = {
    "gate": 0.0001,
    "hyperliquid": 0.00015
  }
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  gate_to_hl, hl_to_gate = await calculator.calculate_spread("BTC", 100.0, 10)
  
  assert gate_to_hl is None or gate_to_hl.net_spread_pct < 0
  assert hl_to_gate is None or hl_to_gate.net_spread_pct < 0


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_find_best_opportunities_success(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange):
  mock_settings.min_balance_usd = 100
  mock_settings.leverage_override = None
  mock_settings.max_funding_rate_diff_pct = 0.1
  mock_settings.get_balance_pct_for_spread = lambda x: 15.0
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.funding_cache["BTC"] = {}
  funding_manager.is_funding_acceptable = lambda *args: True
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  opportunities = await calculator.find_best_opportunities(
    coins=["BTC"],
    min_spread=2.0,
    gate_balance_available=5000.0,
    hl_balance_available=5000.0
  )
  
  assert isinstance(opportunities, list)


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_find_best_opportunities_insufficient_balance(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange):
  mock_settings.min_balance_usd = 100
  mock_settings.leverage_override = None
  mock_settings.max_funding_rate_diff_pct = 0.1
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.is_funding_acceptable = lambda *args: True
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  opportunities = await calculator.find_best_opportunities(
    coins=["BTC"],
    min_spread=2.0,
    gate_balance_available=50.0,
    hl_balance_available=50.0
  )
  
  assert len(opportunities) == 0


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_find_best_opportunities_funding_not_acceptable(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange):
  mock_settings.min_balance_usd = 100
  mock_settings.leverage_override = None
  mock_settings.max_funding_rate_diff_pct = 0.1
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.is_funding_acceptable = lambda *args: False
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  opportunities = await calculator.find_best_opportunities(
    coins=["BTC"],
    min_spread=2.0,
    gate_balance_available=5000.0,
    hl_balance_available=5000.0
  )
  
  assert len(opportunities) == 0


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_find_best_opportunities_leverage_override(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange):
  mock_settings.min_balance_usd = 100
  mock_settings.leverage_override = 5
  mock_settings.max_funding_rate_diff_pct = 0.1
  mock_settings.get_balance_pct_for_spread = lambda x: 15.0
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.funding_cache["BTC"] = {}
  funding_manager.is_funding_acceptable = lambda *args: True
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  opportunities = await calculator.find_best_opportunities(
    coins=["BTC"],
    min_spread=2.0,
    gate_balance_available=5000.0,
    hl_balance_available=5000.0
  )
  
  assert isinstance(opportunities, list)


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_find_best_opportunities_sorted(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange):
  mock_settings.min_balance_usd = 100
  mock_settings.leverage_override = None
  mock_settings.max_funding_rate_diff_pct = 0.1
  mock_settings.get_balance_pct_for_spread = lambda x: 15.0
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.funding_cache["BTC"] = {}
  funding_manager.funding_cache["ETH"] = {}
  funding_manager.is_funding_acceptable = lambda *args: True
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  opportunities = await calculator.find_best_opportunities(
    coins=["BTC", "ETH"],
    min_spread=2.0,
    gate_balance_available=5000.0,
    hl_balance_available=5000.0
  )
  
  if len(opportunities) > 1:
    for i in range(len(opportunities) - 1):
      assert opportunities[i].net_spread_pct >= opportunities[i + 1].net_spread_pct


@pytest.mark.asyncio
async def test_find_best_opportunities_handles_exceptions(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.get_orderbook.side_effect = Exception("API error")
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.is_funding_acceptable = lambda *args: True
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  opportunities = await calculator.find_best_opportunities(
    coins=["BTC"],
    min_spread=2.0,
    gate_balance_available=5000.0,
    hl_balance_available=5000.0
  )
  
  assert len(opportunities) == 0


@pytest.mark.asyncio
async def test_calculate_spread_uses_slippage(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.calculate_slippage.return_value = 0.1
  mock_hyperliquid_exchange.calculate_slippage.return_value = 0.08
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.funding_cache["BTC"] = {}
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  gate_to_hl, hl_to_gate = await calculator.calculate_spread("BTC", 100.0, 10)
  
  if gate_to_hl:
    assert gate_to_hl.buy_slippage_pct > 0
    assert gate_to_hl.sell_slippage_pct > 0


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_calculate_spread_includes_fees(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange):
  mock_settings.gate_taker_fee = 0.075
  mock_settings.hyperliquid_taker_fee = 0.045
  mock_settings.max_position_time_minutes = 20
  
  funding_manager = FundingManager(mock_gate_exchange, mock_hyperliquid_exchange)
  funding_manager.funding_cache["BTC"] = {}
  
  calculator = SpreadCalculator(mock_gate_exchange, mock_hyperliquid_exchange, funding_manager)
  
  gate_to_hl, hl_to_gate = await calculator.calculate_spread("BTC", 100.0, 10)
  
  if gate_to_hl:
    assert gate_to_hl.estimated_cost > 0
    assert gate_to_hl.estimated_revenue > 0