import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import ExchangeName, OrderResult, PositionSide
from src.exchanges.gate import GateExchange


@pytest.fixture
def mock_gate_api():
  api = MagicMock()
  api.list_futures_contracts = MagicMock(return_value=[])
  api.list_futures_accounts = MagicMock()
  api.set_dual_mode = MagicMock()
  api.list_positions = MagicMock(return_value=[])
  return api


def test_gate_exchange_initialization():
  exchange = GateExchange("test_key", "test_secret")
  
  assert exchange.name == ExchangeName.GATE
  assert exchange.settle == "usdt"
  assert len(exchange.orderbooks) == 0


@pytest.mark.asyncio
async def test_gate_exchange_aenter(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_contract = MagicMock()
  mock_contract.name = "BTC_USDT"
  mock_contract.leverage_min = "1"
  mock_contract.leverage_max = "20"
  mock_gate_api.list_futures_contracts.return_value = [mock_contract]
  
  mock_account = MagicMock()
  mock_account.in_dual_mode = True
  mock_gate_api.list_futures_accounts.return_value = mock_account
  
  with patch('asyncio.create_task'):
    await exchange.__aenter__()
  
  assert "BTC" in exchange._coins
  assert exchange._dual_mode_enabled is True


@pytest.mark.asyncio
async def test_gate_exchange_aexit():
  exchange = GateExchange("test_key", "test_secret")
  
  await exchange.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_enable_dual_mode_already_enabled(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_account = MagicMock()
  mock_account.in_dual_mode = True
  mock_gate_api.list_futures_accounts.return_value = mock_account
  
  await exchange._enable_dual_mode()
  
  assert exchange._dual_mode_enabled is True
  mock_gate_api.set_dual_mode.assert_not_called()


@pytest.mark.asyncio
async def test_enable_dual_mode_with_positions(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_account = MagicMock()
  mock_account.in_dual_mode = False
  mock_gate_api.list_futures_accounts.return_value = mock_account
  
  mock_position = MagicMock()
  mock_position.size = "10"
  mock_gate_api.list_positions.return_value = [mock_position]
  
  with pytest.raises(RuntimeError, match="Cannot enable dual mode"):
    await exchange._enable_dual_mode()


@pytest.mark.asyncio
async def test_enable_dual_mode_success(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_account = MagicMock()
  mock_account.in_dual_mode = False
  mock_gate_api.list_futures_accounts.return_value = mock_account
  mock_gate_api.list_positions.return_value = []
  
  await exchange._enable_dual_mode()
  
  assert exchange._dual_mode_enabled is True
  mock_gate_api.set_dual_mode.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_orderbook(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_book = MagicMock()
  mock_bid = MagicMock()
  mock_bid.p = "50000"
  mock_bid.s = "1.0"
  mock_ask = MagicMock()
  mock_ask.p = "50100"
  mock_ask.s = "0.5"
  mock_book.bids = [mock_bid]
  mock_book.asks = [mock_ask]
  mock_gate_api.list_futures_order_book.return_value = mock_book
  
  result = await exchange._fetch_orderbook("BTC_USDT")
  
  assert "levels" in result
  assert len(result["levels"]) == 2
  assert len(result["levels"][0]) == 1
  assert result["levels"][0][0]["px"] == "50000"


@pytest.mark.asyncio
async def test_get_balance(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_account = MagicMock()
  mock_account.total = "10000"
  mock_account.available = "8000"
  mock_account.position_margin = "1500"
  mock_account.order_margin = "500"
  mock_account.unrealised_pnl = "100"
  mock_gate_api.list_futures_accounts.return_value = mock_account
  
  balance = await exchange.get_balance()
  
  assert balance.exchange == ExchangeName.GATE
  assert balance.account_value == 10000.0
  assert balance.available == 8000.0
  assert balance.total_margin_used == 2000.0
  assert balance.unrealised_pnl == 100.0


@pytest.mark.asyncio
async def test_get_orderbook():
  exchange = GateExchange("test_key", "test_secret")
  exchange.orderbooks["BTC"] = {"levels": [[], []], "timestamp": datetime.now(datetime.UTC)}
  
  book = await exchange.get_orderbook("BTC")
  
  assert "levels" in book


@pytest.mark.asyncio
async def test_get_orderbook_missing():
  exchange = GateExchange("test_key", "test_secret")
  
  book = await exchange.get_orderbook("BTC")
  
  assert book == {}


@pytest.mark.asyncio
async def test_get_leverage_limits():
  exchange = GateExchange("test_key", "test_secret")
  
  mock_contract = MagicMock()
  mock_contract.leverage_min = "1"
  mock_contract.leverage_max = "20"
  exchange._contracts_cache["BTC"] = mock_contract
  
  min_lev, max_lev = await exchange.get_leverage_limits("BTC")
  
  assert min_lev == 1
  assert max_lev == 20


@pytest.mark.asyncio
async def test_get_leverage_limits_missing():
  exchange = GateExchange("test_key", "test_secret")
  
  min_lev, max_lev = await exchange.get_leverage_limits("BTC")
  
  assert min_lev == 1
  assert max_lev == 1


@pytest.mark.asyncio
async def test_get_funding_rate(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_ticker = MagicMock()
  mock_ticker.funding_rate = "0.0001"
  mock_gate_api.list_futures_tickers.return_value = [mock_ticker]
  
  rate = await exchange.get_funding_rate("BTC")
  
  assert rate == 0.0001


@pytest.mark.asyncio
async def test_get_funding_rate_error(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_gate_api.list_futures_tickers.side_effect = Exception("API error")
  
  rate = await exchange.get_funding_rate("BTC")
  
  assert rate == 0.0


def test_calculate_slippage():
  exchange = GateExchange("test_key", "test_secret")
  exchange.orderbooks["BTC"] = {
    "levels": [
      [{"px": "50000.0", "sz": "1.0"}, {"px": "49950.0", "sz": "2.0"}],
      [{"px": "50100.0", "sz": "1.0"}, {"px": "50150.0", "sz": "2.0"}]
    ]
  }
  
  slippage = exchange.calculate_slippage("BTC", 100000.0, True)
  
  assert slippage >= 0.0


def test_calculate_slippage_missing_orderbook():
  exchange = GateExchange("test_key", "test_secret")
  
  slippage = exchange.calculate_slippage("BTC", 100000.0, True)
  
  assert slippage == 0.0


def test_calculate_slippage_empty_levels():
  exchange = GateExchange("test_key", "test_secret")
  exchange.orderbooks["BTC"] = {"levels": [[], []]}
  
  slippage = exchange.calculate_slippage("BTC", 100000.0, True)
  
  assert slippage == 0.0


@pytest.mark.asyncio
async def test_open_position_success(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  exchange.orderbooks["BTC"] = {
    "levels": [
      [{"px": "50000.0", "sz": "1.0"}],
      [{"px": "50100.0", "sz": "1.0"}]
    ]
  }
  
  mock_result = MagicMock()
  mock_result.id = "12345"
  mock_result.fill_price = "50100.0"
  mock_gate_api.create_futures_order.return_value = mock_result
  
  result = await exchange.open_position("BTC", PositionSide.LONG, 1000.0, 10)
  
  assert result.success is True
  assert result.coin == "BTC"
  assert result.side == PositionSide.LONG


@pytest.mark.asyncio
async def test_open_position_no_orderbook(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  result = await exchange.open_position("BTC", PositionSide.LONG, 1000.0, 10)
  
  assert result.success is False
  assert result.error == "orderbook_not_available"


@pytest.mark.asyncio
async def test_open_position_exception(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  exchange.orderbooks["BTC"] = {
    "levels": [
      [{"px": "50000.0", "sz": "1.0"}],
      [{"px": "50100.0", "sz": "1.0"}]
    ]
  }
  
  mock_gate_api.create_futures_order.side_effect = Exception("Order failed")
  
  result = await exchange.open_position("BTC", PositionSide.LONG, 1000.0, 10)
  
  assert result.success is False
  assert "Order failed" in result.error


@pytest.mark.asyncio
async def test_close_position_success(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_result = MagicMock()
  mock_result.id = "67890"
  mock_result.fill_price = "50050.0"
  mock_gate_api.create_futures_order.return_value = mock_result
  
  result = await exchange.close_position("BTC", PositionSide.LONG)
  
  assert result.success is True
  assert result.coin == "BTC"


@pytest.mark.asyncio
async def test_close_position_exception(mock_gate_api):
  exchange = GateExchange("test_key", "test_secret")
  exchange.api = mock_gate_api
  
  mock_gate_api.create_futures_order.side_effect = Exception("Close failed")
  
  result = await exchange.close_position("BTC", PositionSide.LONG)
  
  assert result.success is False
  assert "Close failed" in result.error