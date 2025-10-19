import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import ExchangeName, PositionSide
from src.exchanges.hyperliquid import HyperliquidExchange


@pytest.fixture
def mock_info():
  info = MagicMock()
  info.meta = MagicMock(return_value={
    "universe": [
      {"name": "BTC", "maxLeverage": 20, "szDecimals": 3},
      {"name": "ETH", "maxLeverage": 25, "szDecimals": 2}
    ]
  })
  info.subscribe = MagicMock()
  info.disconnect_websocket = MagicMock()
  return info


@pytest.fixture
def mock_exchange_sdk():
  exchange = MagicMock()
  exchange.update_leverage = MagicMock()
  exchange.market_open = MagicMock(return_value={"status": "ok"})
  exchange.market_close = MagicMock(return_value={"status": "ok"})
  return exchange


def test_hyperliquid_initialization():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        
        assert exchange.name == ExchangeName.HYPERLIQUID
        assert exchange.address == "0xaccount"


@pytest.mark.asyncio
async def test_hyperliquid_aenter(mock_info, mock_exchange_sdk):
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info', return_value=mock_info):
      with patch('src.exchanges.hyperliquid.Exchange', return_value=mock_exchange_sdk):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        
        with patch('asyncio.create_task'):
          await exchange.__aenter__()
        
        assert "BTC" in exchange._meta_cache
        assert "ETH" in exchange._meta_cache


@pytest.mark.asyncio
async def test_hyperliquid_aexit(mock_info, mock_exchange_sdk):
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info', return_value=mock_info):
      with patch('src.exchanges.hyperliquid.Exchange', return_value=mock_exchange_sdk):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        
        async def dummy_task():
          try:
            while True:
              await asyncio.sleep(1)
          except asyncio.CancelledError:
            pass
        
        await exchange.__aenter__()
        exchange._update_task = asyncio.create_task(dummy_task())
        await exchange.__aexit__(None, None, None)
        
        assert exchange._update_task.cancelled()


@pytest.mark.asyncio
async def test_get_balance():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info') as mock_info_class:
      with patch('src.exchanges.hyperliquid.Exchange'):
        mock_info_instance = MagicMock()
        mock_info_instance.user_state = MagicMock(return_value={
          "marginSummary": {
            "accountValue": "10000",
            "totalMarginUsed": "2000",
            "totalRawUsd": "10100"
          },
          "withdrawable": "8000"
        })
        mock_info_class.return_value = mock_info_instance
        
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        balance = await exchange.get_balance()
        
        assert balance.exchange == ExchangeName.HYPERLIQUID
        assert balance.account_value == 10000.0
        assert balance.available == 8000.0


@pytest.mark.asyncio
async def test_get_orderbook():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        exchange.orderbooks["BTC"] = {"levels": [[], []]}
        
        book = await exchange.get_orderbook("BTC")
        
        assert "levels" in book


@pytest.mark.asyncio
async def test_get_leverage_limits():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        exchange._meta_cache["BTC"] = {"maxLeverage": 20}
        
        min_lev, max_lev = await exchange.get_leverage_limits("BTC")
        
        assert min_lev == 1
        assert max_lev == 20


@pytest.mark.asyncio
async def test_get_leverage_limits_missing():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        
        min_lev, max_lev = await exchange.get_leverage_limits("BTC")
        
        assert min_lev == 1
        assert max_lev == 1


@pytest.mark.asyncio
async def test_get_funding_rate():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        exchange._asset_ctxs_cache["BTC"] = {"funding": "0.0001"}
        
        rate = await exchange.get_funding_rate("BTC")
        
        assert rate == 0.0001


@pytest.mark.asyncio
async def test_get_funding_rate_missing():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        
        rate = await exchange.get_funding_rate("BTC")
        
        assert rate == 0.0


def test_calculate_slippage():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        exchange.orderbooks["BTC"] = {
          "levels": [
            [{"px": "50000.0", "sz": "1.0"}],
            [{"px": "50100.0", "sz": "1.0"}]
          ]
        }
        
        slippage = exchange.calculate_slippage("BTC", 100000.0, True)
        
        assert slippage >= 0.0


@pytest.mark.asyncio
async def test_open_position_success(mock_exchange_sdk):
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange', return_value=mock_exchange_sdk):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        exchange._meta_cache["BTC"] = {"szDecimals": 3}
        exchange.orderbooks["BTC"] = {
          "levels": [
            [{"px": "50000.0", "sz": "1.0"}],
            [{"px": "50100.0", "sz": "1.0"}]
          ]
        }
        
        result = await exchange.open_position("BTC", PositionSide.LONG, 1000.0, 10)
        
        assert result.success is True
        assert result.coin == "BTC"


@pytest.mark.asyncio
async def test_open_position_missing_asset():
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange'):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        
        result = await exchange.open_position("BTC", PositionSide.LONG, 1000.0, 10)
        
        assert result.success is False
        assert result.error == "asset_not_found"


@pytest.mark.asyncio
async def test_close_position_success(mock_exchange_sdk):
  with patch('eth_account.Account.from_key') as mock_from_key:
    mock_account = MagicMock()
    mock_account.address = "0x123"
    mock_from_key.return_value = mock_account
    
    with patch('src.exchanges.hyperliquid.Info'):
      with patch('src.exchanges.hyperliquid.Exchange', return_value=mock_exchange_sdk):
        exchange = HyperliquidExchange("0xprivate", "0xaccount")
        
        result = await exchange.close_position("BTC", PositionSide.LONG)
        
        assert result.success is True
        assert result.coin == "BTC"