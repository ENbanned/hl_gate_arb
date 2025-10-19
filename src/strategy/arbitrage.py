import asyncio
import uuid
from datetime import datetime, UTC

from src.config.settings import settings
from src.core.funding import FundingManager
from src.core.models import ExchangeName, Position, PositionSide, PositionStatus
from src.core.risk import RiskManager
from src.core.spread import SpreadCalculator
from src.exchanges.gate import GateExchange
from src.exchanges.hyperliquid import HyperliquidExchange
from src.utils.logging import get_logger
from src.utils.emergency_shutdown import emergency_close_all



log = get_logger(__name__)


class ArbitrageStrategy:
  
  def __init__(self, gate: GateExchange, hyperliquid: HyperliquidExchange):
    self.gate = gate
    self.hyperliquid = hyperliquid
    
    self.funding_manager = FundingManager(gate, hyperliquid)
    self.spread_calculator = SpreadCalculator(gate, hyperliquid, self.funding_manager)
    self.risk_manager = RiskManager()
    
    self.active_positions: dict[str, Position] = {}
    self.closed_positions: list[Position] = []
    
    self.position_entry_balances: dict[str, float] = {}
    
    self._monitoring_task = None
    self._funding_update_task = None
    self._consistency_check_task = None
    self._shutdown_requested = False


  async def initialize(self):
    gate_balance = await self.gate.get_balance()
    hl_balance = await self.hyperliquid.get_balance()
    
    total_balance = gate_balance.account_value + hl_balance.account_value
    self.risk_manager.set_initial_balance(total_balance)
    
    gate_coins = set(self.gate.orderbooks.keys())
    hl_coins = set(self.hyperliquid.orderbooks.keys())
    common_coins = list(gate_coins & hl_coins)
    
    await self.funding_manager.update_funding_rates(common_coins)
    
    log.info(
      "strategy_initialized",
      gate_balance=gate_balance.account_value,
      hyperliquid_balance=hl_balance.account_value,
      total_balance=total_balance,
      common_coins=len(common_coins)
    )


  async def start(self):
    log.info("strategy_started")
    
    await self.initialize()
    
    self._monitoring_task = asyncio.create_task(self._monitor_positions_loop())
    self._funding_update_task = asyncio.create_task(self._update_funding_loop())
    self._consistency_check_task = asyncio.create_task(self._check_consistency_loop())
    
    while not self.risk_manager.should_stop_trading() and not self._shutdown_requested:
      try:
        await self._scan_and_execute()
        await asyncio.sleep(2)
      
      except Exception as e:
        log.error("strategy_loop_error", error=str(e), exc_info=True)
        await asyncio.sleep(5)
    
    if self.risk_manager.should_stop_trading():
      log.error("strategy_stopped_emergency", **self.risk_manager.get_performance_summary())
    else:
      log.debug("strategy_stopped_gracefully")


  async def _update_funding_loop(self):
    while not self._shutdown_requested:
      try:
        gate_coins = set(self.gate.orderbooks.keys())
        hl_coins = set(self.hyperliquid.orderbooks.keys())
        common_coins = list(gate_coins & hl_coins)
        
        await self.funding_manager.update_funding_rates(common_coins)
        log.debug("funding_rates_updated", coins_count=len(common_coins))
        
        await asyncio.sleep(300)
      
      except Exception as e:
        log.error("funding_update_error", error=str(e))
        await asyncio.sleep(60)


  async def _check_consistency_loop(self):
    await asyncio.sleep(30)
    
    while not self._shutdown_requested:
      try:
        await self._verify_positions_consistency()
        await asyncio.sleep(60)
      
      except Exception as e:
        log.error("consistency_check_error", error=str(e))
        await asyncio.sleep(60)


  async def _verify_positions_consistency(self):
    if not self.active_positions:
      return
    
    try:
      gate_positions = await self.gate.get_open_positions()
      hl_positions = await self.hyperliquid.get_open_positions()
      
      gate_coins = {p["coin"]: p for p in gate_positions}
      hl_coins = {p["coin"]: p for p in hl_positions}
      
      for pos_id, position in list(self.active_positions.items()):
        coin = position.coin
        
        gate_exists = coin in gate_coins
        hl_exists = coin in hl_coins
        
        if position.buy_exchange == ExchangeName.GATE:
          expected_gate = True
          expected_hl = True
        else:
          expected_gate = True
          expected_hl = True
        
        if gate_exists != expected_gate or hl_exists != expected_hl:
          log.critical(
            "position_inconsistency_detected",
            position_id=pos_id,
            coin=coin,
            gate_exists=gate_exists,
            hl_exists=hl_exists,
            expected_gate=expected_gate,
            expected_hl=expected_hl
          )
          
          await self._handle_partial_close(position, gate_exists, hl_exists)
    
    except Exception as e:
      log.error("verify_positions_error", error=str(e))


  async def _handle_partial_close(self, position: Position, gate_exists: bool, hl_exists: bool):
    log.critical(
      "handling_partial_close",
      position_id=position.id,
      coin=position.coin,
      gate_exists=gate_exists,
      hl_exists=hl_exists
    )
    
    position.status = PositionStatus.FAILED
    
    try:
      if gate_exists and not hl_exists:
        log.critical("closing_orphaned_gate_position", coin=position.coin)
        side = PositionSide.LONG if position.buy_exchange == ExchangeName.GATE else PositionSide.SHORT
        await self.gate.close_position(position.coin, side)
      
      elif hl_exists and not gate_exists:
        log.critical("closing_orphaned_hl_position", coin=position.coin)
        side = PositionSide.LONG if position.buy_exchange == ExchangeName.HYPERLIQUID else PositionSide.SHORT
        await self.hyperliquid.close_position(position.coin, side)
    
    except Exception as e:
      log.error("failed_to_close_orphaned_position", coin=position.coin, error=str(e))
    
    del self.active_positions[position.id]
    del self.position_entry_balances[position.id]
    self.closed_positions.append(position)
    
    self.risk_manager.emergency_stop = True
    log.critical("emergency_stop_triggered_partial_close", coin=position.coin)


  async def _scan_and_execute(self):
    gate_balance = await self.gate.get_balance()
    hl_balance = await self.hyperliquid.get_balance()
    
    min_balance = min(gate_balance.available, hl_balance.available)
    
    if min_balance < settings.min_balance_usd:
      log.debug(
        "insufficient_balance",
        gate_available=gate_balance.available,
        hl_available=hl_balance.available,
        min_required=settings.min_balance_usd
      )
      await asyncio.sleep(10)
      return
    
    gate_coins = set(self.gate.orderbooks.keys())
    hl_coins = set(self.hyperliquid.orderbooks.keys())
    common_coins = list(gate_coins & hl_coins)
    
    if not common_coins:
      log.debug("no_common_coins_available")
      await asyncio.sleep(5)
      return
    
    opportunities = await self.spread_calculator.find_best_opportunities(
      common_coins,
      settings.min_spread_pct,
      gate_balance.available,
      hl_balance.available
    )
    
    if not opportunities:
      return
    
    best = opportunities[0]
    
    log.info(
      "spread_opportunity_detected",
      coin=best.coin,
      direction=best.direction,
      gross_spread=f"{best.gross_spread_pct:.3f}%",
      funding_cost=f"{best.funding_cost_pct:.3f}%",
      net_spread=f"{best.net_spread_pct:.3f}%",
      estimated_profit=f"${best.estimated_profit:.2f}",
      size_usd=f"${best.position_size_usd:.0f}",
      leverage=best.leverage
    )
    
    await self._execute_arbitrage(best)


  async def _execute_arbitrage(self, spread):
    position_id = str(uuid.uuid4())[:8]
    
    buy_exchange = self.gate if spread.buy_exchange == ExchangeName.GATE else self.hyperliquid
    sell_exchange = self.hyperliquid if spread.sell_exchange == ExchangeName.HYPERLIQUID else self.gate
    
    gate_balance_before = await self.gate.get_balance()
    hl_balance_before = await self.hyperliquid.get_balance()
    total_balance_before = gate_balance_before.account_value + hl_balance_before.account_value
    
    buy_result, sell_result = await asyncio.gather(
      buy_exchange.open_position(
        spread.coin,
        PositionSide.LONG,
        spread.position_size_usd,
        spread.leverage
      ),
      sell_exchange.open_position(
        spread.coin,
        PositionSide.SHORT,
        spread.position_size_usd,
        spread.leverage
      ),
      return_exceptions=True
    )
    
    if isinstance(buy_result, Exception):
      buy_result = None
    if isinstance(sell_result, Exception):
      sell_result = None
    
    if not buy_result or not buy_result.success or not sell_result or not sell_result.success:
      log.error(
        "position_open_failed",
        position_id=position_id,
        coin=spread.coin,
        buy_success=buy_result.success if buy_result else False,
        sell_success=sell_result.success if sell_result else False
      )
      
      if buy_result and buy_result.success:
        await buy_exchange.close_position(spread.coin, PositionSide.LONG)
      
      if sell_result and sell_result.success:
        await sell_exchange.close_position(spread.coin, PositionSide.SHORT)
      
      return
    
    position = Position(
      id=position_id,
      coin=spread.coin,
      buy_exchange=spread.buy_exchange,
      sell_exchange=spread.sell_exchange,
      buy_order=buy_result,
      sell_order=sell_result,
      entry_spread=spread.net_spread_pct,
      expected_profit=spread.estimated_profit,
      buy_funding_rate=spread.buy_funding_rate,
      sell_funding_rate=spread.sell_funding_rate,
      estimated_funding_cost=(spread.funding_cost_pct / 100) * spread.position_size_usd * spread.leverage,
      accumulated_funding_cost=0.0,
      leverage=spread.leverage,
      size_usd=spread.position_size_usd,
      opened_at=datetime.now(UTC),
      closed_at=None,
      status=PositionStatus.OPEN
    )
    
    self.active_positions[position_id] = position
    self.position_entry_balances[position_id] = total_balance_before
    
    log.info(
      "position_opened",
      position_id=position_id,
      coin=spread.coin,
      direction=spread.direction,
      net_spread=f"{spread.net_spread_pct:.3f}%",
      size_usd=f"${spread.position_size_usd:.0f}",
      leverage=spread.leverage,
      expected_profit=f"${spread.estimated_profit:.2f}"
    )


  async def _monitor_positions_loop(self):
    while not self._shutdown_requested:
      try:
        await asyncio.sleep(10)
        
        if not self.active_positions:
          continue
        
        positions_snapshot = list(self.active_positions.items())
        
        for position_id, position in positions_snapshot:
          if position_id not in self.active_positions:
            continue
          await self._check_position(position_id, position)
      
      except Exception as e:
        log.error("monitor_positions_error", error=str(e))


  async def _check_position(self, position_id: str, position: Position):
    try:
      gate_to_hl, hl_to_gate = await self.spread_calculator.calculate_spread(
        position.coin,
        position.size_usd,
        position.leverage
      )
      
      current_spread = None
      if position.buy_exchange == ExchangeName.GATE and gate_to_hl:
        current_spread = gate_to_hl.net_spread_pct
      elif position.buy_exchange == ExchangeName.HYPERLIQUID and hl_to_gate:
        current_spread = hl_to_gate.net_spread_pct
      
      if current_spread is None:
        return
      
      gate_rate = self.funding_manager.get_funding_rate(position.coin, ExchangeName.GATE)
      hl_rate = self.funding_manager.get_funding_rate(position.coin, ExchangeName.HYPERLIQUID)
      position.update_funding_cost(gate_rate, hl_rate)
      
      should_close, reason = self.risk_manager.check_position_risk(position, current_spread)
      
      if current_spread <= 0.1:
        should_close = True
        reason = "converged"
        log.debug(
          "position_converged",
          position_id=position_id,
          coin=position.coin,
          current_spread=current_spread
        )
      
      if should_close:
        if reason == "stop_loss":
          position.stop_loss_triggered = True
        elif reason == "time_limit":
          position.time_limit_triggered = True
        
        await self._close_position(position_id, position)
    
    except Exception as e:
      log.error("check_position_error", position_id=position_id, coin=position.coin, error=str(e))


  async def _close_position(self, position_id: str, position: Position):
    buy_exchange = self.gate if position.buy_exchange == ExchangeName.GATE else self.hyperliquid
    sell_exchange = self.hyperliquid if position.sell_exchange == ExchangeName.HYPERLIQUID else self.gate
    
    buy_close_result, sell_close_result = await asyncio.gather(
      buy_exchange.close_position(position.coin, PositionSide.LONG),
      sell_exchange.close_position(position.coin, PositionSide.SHORT),
      return_exceptions=True
    )
    
    if isinstance(buy_close_result, Exception):
      buy_close_result = None
    if isinstance(sell_close_result, Exception):
      sell_close_result = None
    
    buy_success = buy_close_result and buy_close_result.success
    sell_success = sell_close_result and sell_close_result.success
    
    if not buy_success or not sell_success:
      log.critical(
        "critical_close_failure",
        position_id=position_id,
        coin=position.coin,
        buy_success=buy_success,
        sell_success=sell_success,
        buy_error=buy_close_result.error if buy_close_result else "exception",
        sell_error=sell_close_result.error if sell_close_result else "exception"
      )
      
      position.status = PositionStatus.FAILED
      
      del self.active_positions[position_id]
      del self.position_entry_balances[position_id]
      self.closed_positions.append(position)
      
      self.risk_manager.emergency_stop = True
      
      log.critical(
        "emergency_stop_activated_partial_close",
        position_id=position_id,
        coin=position.coin,
        message="Bot stopped due to partial position close. Manual intervention required."
      )
      
      return
    
    position.closed_at = datetime.now(UTC)
    position.status = PositionStatus.CLOSED
    
    gate_balance_after = await self.gate.get_balance()
    hl_balance_after = await self.hyperliquid.get_balance()
    total_balance_after = gate_balance_after.account_value + hl_balance_after.account_value
    
    balance_before = self.position_entry_balances.get(position_id, 0)
    realized_pnl = total_balance_after - balance_before
    
    position.realized_pnl = realized_pnl
    
    self.risk_manager.update_realized_pnl(realized_pnl, position.accumulated_funding_cost)
    
    del self.active_positions[position_id]
    del self.position_entry_balances[position_id]
    self.closed_positions.append(position)
    
    duration_minutes = position.get_duration_minutes()
    
    log.info(
      "position_closed",
      position_id=position_id,
      coin=position.coin,
      entry_spread=f"{position.entry_spread:.3f}%",
      expected_profit=f"${position.expected_profit:.2f}",
      realized_pnl=f"${realized_pnl:.2f}",
      funding_cost=f"${position.accumulated_funding_cost:.2f}",
      net_pnl=f"${realized_pnl - position.accumulated_funding_cost:.2f}",
      duration_minutes=f"{duration_minutes:.1f}",
      stop_loss=position.stop_loss_triggered,
      time_limit=position.time_limit_triggered
    )


  async def shutdown(self):
    self._shutdown_requested = True
    log.debug("strategy_shutting_down")
    
    if self._monitoring_task:
      self._monitoring_task.cancel()
      try:
        await self._monitoring_task
      except asyncio.CancelledError:
        pass
    
    if self._funding_update_task:
      self._funding_update_task.cancel()
      try:
        await self._funding_update_task
      except asyncio.CancelledError:
        pass
    
    if self._consistency_check_task:
      self._consistency_check_task.cancel()
      try:
        await self._consistency_check_task
      except asyncio.CancelledError:
        pass
    
    for position_id, position in list(self.active_positions.items()):
      log.debug("closing_position_on_shutdown", position_id=position_id, coin=position.coin)
      await self._close_position(position_id, position)
    
    log.debug("strategy_shutdown_complete", **self.risk_manager.get_performance_summary())