from datetime import datetime, timedelta

from config.settings import settings
from core.models import Position, PositionStatus
from core.spread import SpreadCalculator
from utils.logging import get_logger


log = get_logger(__name__)


class RiskManager:
  
  def __init__(self, spread_calculator: SpreadCalculator):
    self.spread_calculator = spread_calculator
    
    self.emergency_stop = False
    self.consecutive_losses = 0
    self.daily_pnl = 0.0
    self.last_reset = datetime.now().date()
  
  
  def should_open_position(
    self,
    active_positions_count: int,
    gate_balance: float,
    hl_balance: float,
  ) -> bool:
    if self.emergency_stop:
      log.warning("risk_emergency_stop_active")
      return False
    
    today = datetime.now().date()
    if today > self.last_reset:
      self.daily_pnl = 0.0
      self.consecutive_losses = 0
      self.last_reset = today
    
    min_balance = min(gate_balance, hl_balance)
    daily_loss_limit = min_balance * (settings.daily_loss_limit_pct / 100)
    
    if self.daily_pnl < -daily_loss_limit:
      log.warning(
        "risk_daily_loss_limit_reached",
        daily_pnl=self.daily_pnl,
        limit=-daily_loss_limit,
      )
      return False
    
    if self.consecutive_losses >= settings.consecutive_loss_limit:
      log.warning(
        "risk_consecutive_loss_limit_reached",
        consecutive_losses=self.consecutive_losses,
      )
      return False
    
    if active_positions_count >= settings.max_concurrent_positions:
      log.debug(
        "risk_max_positions_reached",
        active_positions=active_positions_count,
      )
      return False
    
    return True
  
  
  async def should_close_position(
    self, position: Position
  ) -> tuple[bool, str | None]:
    if position.status != PositionStatus.ACTIVE:
      return False, None
    
    age_minutes = (datetime.now() - position.opened_at).total_seconds() / 60
    
    if age_minutes > settings.time_limit_minutes:
      log.info(
        "risk_time_limit_exceeded",
        position_id=position.id,
        coin=position.coin,
        age_minutes=age_minutes,
      )
      return True, f"time_limit_{age_minutes:.1f}min"
    
    current_spread = await self._get_current_spread(position)
    
    if current_spread is None:
      return False, None
    
    position.current_spread_pct = current_spread
    
    if current_spread < 0:
      log.warning(
        "risk_spread_inverted",
        position_id=position.id,
        coin=position.coin,
        entry_spread=position.entry_spread_pct,
        current_spread=current_spread,
      )
      return True, "spread_inverted"
    
    spread_compression_pct = (
      (position.entry_spread_pct - current_spread) / position.entry_spread_pct
    ) * 100
    
    if spread_compression_pct > settings.spread_compression_pct:
      log.warning(
        "risk_spread_compressed",
        position_id=position.id,
        coin=position.coin,
        entry_spread=position.entry_spread_pct,
        current_spread=current_spread,
        compression=spread_compression_pct,
      )
      return True, f"spread_compressed_{spread_compression_pct:.1f}%"
    
    if current_spread <= settings.target_spread_pct:
      log.info(
        "risk_target_reached",
        position_id=position.id,
        coin=position.coin,
        current_spread=current_spread,
      )
      return True, f"target_reached_{current_spread:.3f}%"
    
    profit_captured_pct = (
      (position.entry_spread_pct - current_spread) / position.entry_spread_pct
    ) * 100
    
    if profit_captured_pct >= 60:
      log.info(
        "risk_profit_target_reached",
        position_id=position.id,
        coin=position.coin,
        profit_captured=profit_captured_pct,
      )
      return True, f"profit_captured_{profit_captured_pct:.1f}%"
    
    return False, None
  
  
  def record_position_closed(self, net_pnl: float):
    self.daily_pnl += net_pnl
    
    if net_pnl < 0:
      self.consecutive_losses += 1
    else:
      self.consecutive_losses = 0
    
    if self.consecutive_losses >= settings.consecutive_loss_limit:
      self.emergency_stop = True
      log.critical(
        "risk_emergency_stop_triggered",
        consecutive_losses=self.consecutive_losses,
      )
  
  
  async def _get_current_spread(self, position: Position) -> float | None:
    try:
      gate_to_hl, hl_to_gate = await self.spread_calculator.calculate_spread(
        position.coin,
        position.size_usd,
        position.leverage,
      )
      
      if position.direction == "gate_to_hl":
        return gate_to_hl.net_spread_pct if gate_to_hl else None
      else:
        return hl_to_gate.net_spread_pct if hl_to_gate else None
    except Exception as e:
      log.error(
        "risk_current_spread_error",
        position_id=position.id,
        error=str(e),
      )
      return None