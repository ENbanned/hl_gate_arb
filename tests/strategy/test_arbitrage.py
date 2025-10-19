import asyncio
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import (
  Balance,
  ExchangeName,
  OrderResult,
  Position,
  PositionSide,
  PositionStatus,
  Spread,
)
from src.strategy.arbitrage import ArbitrageStrategy


@pytest.mark.asyncio
async def test_arbitrage_strategy_initialization(mock_gate_exchange, mock_hyperliquid_exchange):
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  assert strategy.gate == mock_gate_exchange
  assert strategy.hyperliquid == mock_hyperliquid_exchange
  assert len(strategy.active_positions) == 0
  assert len(strategy.closed_positions) == 0
  assert strategy._shutdown_requested is False


@pytest.mark.asyncio
async def test_initialize_strategy(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.orderbooks = {"BTC": {}, "ETH": {}}
  mock_hyperliquid_exchange.orderbooks = {"BTC": {}, "SOL": {}}
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  with patch.object(strategy.funding_manager, 'update_funding_rates', new=AsyncMock()):
    await strategy.initialize()
  
  assert strategy.risk_manager.initial_balance > 0


@pytest.mark.asyncio
async def test_update_funding_loop(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.orderbooks = {"BTC": {}}
  mock_hyperliquid_exchange.orderbooks = {"BTC": {}}
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy._shutdown_requested = False
  
  with patch.object(strategy.funding_manager, 'update_funding_rates', new=AsyncMock()) as mock_update:
    task = asyncio.create_task(strategy._update_funding_loop())
    
    await asyncio.sleep(0.1)
    
    strategy._shutdown_requested = True
    
    try:
      await asyncio.wait_for(task, timeout=1.0)
    except asyncio.TimeoutError:
      task.cancel()


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_scan_and_execute_insufficient_balance(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange):
  mock_settings.min_balance_usd = 1000
  
  mock_gate_exchange.get_balance.return_value = Balance(
    exchange=ExchangeName.GATE,
    account_value=500.0,
    available=100.0,
    total_margin_used=400.0,
    unrealised_pnl=0.0
  )
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  await strategy._scan_and_execute()
  
  mock_gate_exchange.open_position.assert_not_called()


@pytest.mark.asyncio
async def test_scan_and_execute_no_common_coins(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.orderbooks = {"BTC": {}}
  mock_hyperliquid_exchange.orderbooks = {"ETH": {}}
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  await strategy._scan_and_execute()
  
  mock_gate_exchange.open_position.assert_not_called()


@pytest.mark.asyncio
async def test_scan_and_execute_no_opportunities(mock_gate_exchange, mock_hyperliquid_exchange):
  mock_gate_exchange.orderbooks = {"BTC": {}}
  mock_hyperliquid_exchange.orderbooks = {"BTC": {}}
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  with patch.object(strategy.spread_calculator, 'find_best_opportunities', new=AsyncMock(return_value=[])):
    await strategy._scan_and_execute()
  
  mock_gate_exchange.open_position.assert_not_called()


@pytest.mark.asyncio
async def test_execute_arbitrage_success(mock_gate_exchange, mock_hyperliquid_exchange, sample_spread):
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
  
  mock_gate_exchange.open_position.return_value = buy_order
  mock_hyperliquid_exchange.open_position.return_value = sell_order
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  await strategy._execute_arbitrage(sample_spread)
  
  assert len(strategy.active_positions) == 1


@pytest.mark.asyncio
async def test_execute_arbitrage_buy_failure(mock_gate_exchange, mock_hyperliquid_exchange, sample_spread):
  buy_order = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.0,
    executed_price=None,
    success=False,
    error="insufficient_balance"
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
  
  mock_gate_exchange.open_position.return_value = buy_order
  mock_hyperliquid_exchange.open_position.return_value = sell_order
  mock_hyperliquid_exchange.close_position.return_value = OrderResult(
    exchange=ExchangeName.HYPERLIQUID,
    coin="BTC",
    side=PositionSide.SHORT,
    size=0.0,
    executed_price=None,
    success=True
  )
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  await strategy._execute_arbitrage(sample_spread)
  
  assert len(strategy.active_positions) == 0
  mock_hyperliquid_exchange.close_position.assert_called_once()


@pytest.mark.asyncio
async def test_execute_arbitrage_sell_failure(mock_gate_exchange, mock_hyperliquid_exchange, sample_spread):
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
    size=0.0,
    executed_price=None,
    success=False,
    error="order_rejected"
  )
  
  mock_gate_exchange.open_position.return_value = buy_order
  mock_hyperliquid_exchange.open_position.return_value = sell_order
  mock_gate_exchange.close_position.return_value = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.0,
    executed_price=None,
    success=True
  )
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  await strategy._execute_arbitrage(sample_spread)
  
  assert len(strategy.active_positions) == 0
  mock_gate_exchange.close_position.assert_called_once()


@pytest.mark.asyncio
async def test_execute_arbitrage_exception_handling(mock_gate_exchange, mock_hyperliquid_exchange, sample_spread):
  mock_gate_exchange.open_position.side_effect = Exception("Network error")
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  await strategy._execute_arbitrage(sample_spread)
  
  assert len(strategy.active_positions) == 0


@pytest.mark.asyncio
async def test_check_position_convergence(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy.position_entry_balances["test_pos_1"] = 10000.0
  
  converged_spread = Spread(
    coin="BTC",
    direction="gate_to_hl",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_price=50100.0,
    sell_price=50050.0,
    buy_slippage_pct=0.05,
    sell_slippage_pct=0.04,
    gross_spread_pct=0.05,
    net_spread_pct=0.05,
    estimated_cost=1000.0,
    estimated_revenue=1000.5,
    estimated_profit=0.5,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    funding_cost_pct=0.01,
    leverage=10,
    position_size_usd=100.0
  )
  
  with patch.object(strategy.spread_calculator, 'calculate_spread', new=AsyncMock(return_value=(converged_spread, None))):
    with patch.object(strategy, '_close_position', new=AsyncMock()):
      await strategy._check_position("test_pos_1", sample_position)
      
      strategy._close_position.assert_called_once()


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_check_position_stop_loss(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  mock_settings.stop_loss_pct = 2.0
  mock_settings.max_position_time_minutes = 20
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy.position_entry_balances["test_pos_1"] = 10000.0
  
  sample_position.entry_spread = 5.0
  
  negative_spread = Spread(
    coin="BTC",
    direction="gate_to_hl",
    buy_exchange=ExchangeName.GATE,
    sell_exchange=ExchangeName.HYPERLIQUID,
    buy_price=50100.0,
    sell_price=50050.0,
    buy_slippage_pct=0.05,
    sell_slippage_pct=0.04,
    gross_spread_pct=2.5,
    net_spread_pct=2.5,
    estimated_cost=1000.0,
    estimated_revenue=1025.0,
    estimated_profit=25.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    funding_cost_pct=0.5,
    leverage=10,
    position_size_usd=100.0
  )
  
  with patch.object(strategy.spread_calculator, 'calculate_spread', new=AsyncMock(return_value=(negative_spread, None))):
    with patch.object(strategy, '_close_position', new=AsyncMock()):
      await strategy._check_position("test_pos_1", sample_position)
      
      strategy._close_position.assert_called_once()
      assert sample_position.stop_loss_triggered is True


@pytest.mark.asyncio
@patch('src.config.settings.settings')
async def test_check_position_time_limit(mock_settings, mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  mock_settings.stop_loss_pct = 2.0
  mock_settings.max_position_time_minutes = 20
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy.position_entry_balances["test_pos_1"] = 10000.0
  
  sample_position.opened_at = datetime.now(UTC) - timedelta(minutes=25)
  
  normal_spread = Spread(
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
    estimated_revenue=1030.0,
    estimated_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    funding_cost_pct=0.5,
    leverage=10,
    position_size_usd=100.0
  )
  
  with patch.object(strategy.spread_calculator, 'calculate_spread', new=AsyncMock(return_value=(normal_spread, None))):
    with patch.object(strategy, '_close_position', new=AsyncMock()):
      await strategy._check_position("test_pos_1", sample_position)
      
      strategy._close_position.assert_called_once()
      assert sample_position.time_limit_triggered is True


@pytest.mark.asyncio
async def test_close_position_success(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  close_buy = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.0,
    executed_price=50150.0,
    success=True,
    order_id="close_buy_123"
  )
  
  close_sell = OrderResult(
    exchange=ExchangeName.HYPERLIQUID,
    coin="BTC",
    side=PositionSide.SHORT,
    size=0.0,
    executed_price=50100.0,
    success=True,
    order_id="close_sell_456"
  )
  
  mock_gate_exchange.close_position.return_value = close_buy
  mock_hyperliquid_exchange.close_position.return_value = close_sell
  
  mock_gate_exchange.get_balance.return_value = Balance(
    exchange=ExchangeName.GATE,
    account_value=10050.0,
    available=8050.0,
    total_margin_used=2000.0,
    unrealised_pnl=0.0
  )
  
  mock_hyperliquid_exchange.get_balance.return_value = Balance(
    exchange=ExchangeName.HYPERLIQUID,
    account_value=10050.0,
    available=8050.0,
    total_margin_used=2000.0,
    unrealised_pnl=0.0
  )
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy.position_entry_balances["test_pos_1"] = 20000.0
  
  await strategy._close_position("test_pos_1", sample_position)
  
  assert sample_position.status == PositionStatus.CLOSED
  assert sample_position.closed_at is not None
  assert "test_pos_1" not in strategy.active_positions
  assert len(strategy.closed_positions) == 1


@pytest.mark.asyncio
async def test_close_position_failure(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  close_buy = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.0,
    executed_price=None,
    success=False,
    error="close_failed"
  )
  
  close_sell = OrderResult(
    exchange=ExchangeName.HYPERLIQUID,
    coin="BTC",
    side=PositionSide.SHORT,
    size=0.0,
    executed_price=50100.0,
    success=True,
    order_id="close_sell_456"
  )
  
  mock_gate_exchange.close_position.return_value = close_buy
  mock_hyperliquid_exchange.close_position.return_value = close_sell
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy.position_entry_balances["test_pos_1"] = 20000.0
  
  await strategy._close_position("test_pos_1", sample_position)
  
  assert "test_pos_1" in strategy.active_positions
  assert len(strategy.closed_positions) == 0


@pytest.mark.asyncio
async def test_close_position_exception_handling(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  mock_gate_exchange.close_position.side_effect = Exception("Network error")
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy.position_entry_balances["test_pos_1"] = 20000.0
  
  await strategy._close_position("test_pos_1", sample_position)
  
  assert "test_pos_1" in strategy.active_positions


@pytest.mark.asyncio
async def test_shutdown_closes_all_positions(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  close_order = OrderResult(
    exchange=ExchangeName.GATE,
    coin="BTC",
    side=PositionSide.LONG,
    size=0.0,
    executed_price=50100.0,
    success=True
  )
  
  mock_gate_exchange.close_position.return_value = close_order
  mock_hyperliquid_exchange.close_position.return_value = close_order
  
  mock_gate_exchange.get_balance.return_value = Balance(
    exchange=ExchangeName.GATE,
    account_value=10000.0,
    available=8000.0,
    total_margin_used=2000.0,
    unrealised_pnl=0.0
  )
  
  mock_hyperliquid_exchange.get_balance.return_value = Balance(
    exchange=ExchangeName.HYPERLIQUID,
    account_value=10000.0,
    available=8000.0,
    total_margin_used=2000.0,
    unrealised_pnl=0.0
  )
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy.position_entry_balances["test_pos_1"] = 20000.0
  
  await strategy.shutdown()
  
  assert len(strategy.active_positions) == 0
  assert strategy._shutdown_requested is True


@pytest.mark.asyncio
async def test_shutdown_cancels_tasks(mock_gate_exchange, mock_hyperliquid_exchange):
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  # Создаем реальные задачи
  async def dummy():
    while True:
      await asyncio.sleep(1)
  
  strategy._monitoring_task = asyncio.create_task(dummy())
  strategy._funding_update_task = asyncio.create_task(dummy())
  
  await strategy.shutdown()
  
  assert strategy._monitoring_task.cancelled()
  assert strategy._funding_update_task.cancelled()


@pytest.mark.asyncio
async def test_monitor_positions_loop(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  strategy._shutdown_requested = False
  
  with patch.object(strategy, '_check_position', new=AsyncMock()) as mock_check:
    task = asyncio.create_task(strategy._monitor_positions_loop())
    
    await asyncio.sleep(0.2)
    
    strategy._shutdown_requested = True
    
    try:
      await asyncio.wait_for(task, timeout=1.0)
    except asyncio.TimeoutError:
      task.cancel()


@pytest.mark.asyncio
async def test_execute_arbitrage_tracks_balance(mock_gate_exchange, mock_hyperliquid_exchange, sample_spread):
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
  
  mock_gate_exchange.open_position.return_value = buy_order
  mock_hyperliquid_exchange.open_position.return_value = sell_order
  
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  
  await strategy._execute_arbitrage(sample_spread)
  
  position_id = list(strategy.active_positions.keys())[0]
  assert position_id in strategy.position_entry_balances
  assert strategy.position_entry_balances[position_id] > 0


@pytest.mark.asyncio
async def test_check_position_updates_funding_cost(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  
  strategy.funding_manager.funding_cache["BTC"] = {}
  
  normal_spread = Spread(
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
    estimated_revenue=1030.0,
    estimated_profit=30.0,
    buy_funding_rate=0.0001,
    sell_funding_rate=0.00015,
    funding_cost_pct=0.5,
    leverage=10,
    position_size_usd=100.0
  )
  
  with patch.object(strategy.spread_calculator, 'calculate_spread', new=AsyncMock(return_value=(normal_spread, None))):
    with patch.object(strategy.funding_manager, 'get_funding_rate', return_value=0.0001):
      await strategy._check_position("test_pos_1", sample_position)


@pytest.mark.asyncio
async def test_check_position_handles_none_spread(mock_gate_exchange, mock_hyperliquid_exchange, sample_position):
  strategy = ArbitrageStrategy(mock_gate_exchange, mock_hyperliquid_exchange)
  strategy.active_positions["test_pos_1"] = sample_position
  
  with patch.object(strategy.spread_calculator, 'calculate_spread', new=AsyncMock(return_value=(None, None))):
    await strategy._check_position("test_pos_1", sample_position)
    
    assert "test_pos_1" in strategy.active_positions