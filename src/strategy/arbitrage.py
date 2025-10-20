import asyncio
from datetime import datetime

from src.config.settings import settings
from src.core.position import PositionManager
from src.core.risk import RiskManager
from src.core.spread import SpreadCalculator
from src.exchanges.base import ExchangeProtocol
from src.utils.logging import get_logger
from src.utils.telegram import notifier


log = get_logger(__name__)


class ArbitrageStrategy:
  
  def __init__(
    self,
    gate: ExchangeProtocol,
    hyperliquid: ExchangeProtocol,
  ):
    self.gate = gate
    self.hyperliquid = hyperliquid
    
    self.spread_calculator = SpreadCalculator(gate, hyperliquid)
    self.position_manager = PositionManager(gate, hyperliquid)
    self.risk_manager = RiskManager(self.spread_calculator)
    
    self.running = False
    self.common_coins: list[str] = []
  
  
  async def start(self):
    log.info("strategy_starting")
    
    await self._load_common_coins()
    
    gate_balance = await self.gate.get_balance()
    hl_balance = await self.hyperliquid.get_balance()
    
    log.info(
      "strategy_initialized",
      gate_balance=f"${gate_balance.total:.2f}",
      hl_balance=f"${hl_balance.total:.2f}",
      common_coins=len(self.common_coins),
    )
    
    self.running = True
    
    await asyncio.gather(
      self._scan_loop(),
      self._monitor_loop(),
      self._verify_loop(),
    )
  
  
  async def stop(self):
    log.info("strategy_stopping")
    self.running = False
    
    for position in list(self.position_manager.active_positions.values()):
      await self.position_manager.close_position(position, "shutdown")
    
    total_realized_pnl = sum(
      p.realized_pnl_usd for p in self.position_manager.closed_positions
    )
    total_funding_cost = sum(
      p.funding_cost_usd for p in self.position_manager.closed_positions
    )
    net_pnl = total_realized_pnl - total_funding_cost
    
    log.info(
      "strategy_stopped",
      total_realized_pnl=f"${total_realized_pnl:.2f}",
      total_funding_cost=f"${total_funding_cost:.2f}",
      net_pnl=f"${net_pnl:.2f}",
      trades=len(self.position_manager.closed_positions),
    )
  
  
  async def _scan_loop(self):
    while self.running:
      try:
        await self._scan_and_execute()
      except Exception as e:
        log.error("scan_loop_error", error=str(e))
        await notifier.error_alert("Scan Loop Error", str(e))
      
      await asyncio.sleep(settings.scan_interval_seconds)
  
  
  async def _monitor_loop(self):
    while self.running:
      try:
        await self._monitor_positions()
      except Exception as e:
        log.error("monitor_loop_error", error=str(e))
        await notifier.error_alert("Monitor Loop Error", str(e))
      
      await asyncio.sleep(1.0)
  
  
  async def _verify_loop(self):
    while self.running:
      try:
        ok = await self.position_manager.verify_positions()
        if not ok:
          log.critical("verify_loop_desync_detected")
          self.risk_manager.emergency_stop = True
      except Exception as e:
        log.error("verify_loop_error", error=str(e))
      
      await asyncio.sleep(settings.position_check_interval_seconds)
  
  
  async def _scan_and_execute(self):
    if self.risk_manager.emergency_stop:
      log.warning("scan_skipped_emergency_stop")
      return
    
    gate_balance = await self.gate.get_balance()
    hl_balance = await self.hyperliquid.get_balance()
    
    active_count = len(self.position_manager.active_positions)
    
    if not self.risk_manager.should_open_position(
      active_count,
      gate_balance.available,
      hl_balance.available,
    ):
      return
    
    opportunities = await self.spread_calculator.find_best_spreads(
      self.common_coins,
      gate_balance.available,
      hl_balance.available,
    )
    
    if not opportunities:
      return
    
    best = opportunities[0]
    
    log.info(
      "spread_detected",
      coin=best.coin,
      direction=best.direction,
      net_spread=f"{best.net_spread_pct:.3f}%",
      gross_spread=f"{best.gross_spread_pct:.3f}%",
      funding_cost=f"{best.funding_cost_pct:.3f}%",
      estimated_profit=f"${best.estimated_profit_usd:.2f}",
    )
    
    position = await self.position_manager.open_position(best)
    
    if not position:
      log.warning("position_open_failed", coin=best.coin)
  
  
  async def _monitor_positions(self):
    for position in list(self.position_manager.active_positions.values()):
      try:
        should_close, reason = await self.risk_manager.should_close_position(
          position
        )
        
        if should_close and reason:
          net_pnl = await self.position_manager.close_position(
            position, reason
          )
          self.risk_manager.record_position_closed(net_pnl)
      
      except Exception as e:
        log.error(
          "monitor_position_error",
          position_id=position.id,
          error=str(e),
        )
  
  
  async def _load_common_coins(self):
    gate_contracts = set(self.gate.contracts.keys())
    hl_coins = set(self.hyperliquid.coin_to_index.keys())
    
    gate_coins = {c.replace("_USDT", "") for c in gate_contracts if c.endswith("_USDT")}
    
    common = gate_coins & hl_coins
    
    self.common_coins = sorted(list(common))
    
    log.info("common_coins_loaded", count=len(self.common_coins))