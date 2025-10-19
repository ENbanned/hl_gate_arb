from src.config.settings import settings
from src.core.models import Position, PositionStatus
from src.utils.logging import get_logger


log = get_logger(__name__)


class RiskManager:
  
  def __init__(self):
    self.total_realized_pnl = 0.0
    self.total_funding_cost = 0.0
    self.initial_balance = 0.0
    self.emergency_stop = False
  
  
  def set_initial_balance(self, balance: float):
    self.initial_balance = balance
    log.debug("risk_initial_balance_set", balance=balance)
  
  
  def update_realized_pnl(self, pnl: float, funding_cost: float):
    self.total_realized_pnl += pnl
    self.total_funding_cost += funding_cost
    
    net_pnl = self.total_realized_pnl - self.total_funding_cost
    
    if self.initial_balance > 0:
      drawdown_pct = abs(net_pnl / self.initial_balance) * 100
      
      if net_pnl < 0 and drawdown_pct >= settings.emergency_stop_loss_pct:
        self.emergency_stop = True
        log.error(
          "emergency_stop_triggered",
          total_pnl=self.total_realized_pnl,
          funding_cost=self.total_funding_cost,
          net_pnl=net_pnl,
          drawdown_pct=drawdown_pct,
          threshold=settings.emergency_stop_loss_pct
        )
  
  
  def should_stop_trading(self) -> bool:
    return self.emergency_stop
  
  
  def check_position_risk(self, position: Position, current_spread: float) -> tuple[bool, str]:
    if position.status != PositionStatus.OPEN:
      return False, ""
    
    spread_change = current_spread - position.entry_spread
    
    if spread_change <= -settings.stop_loss_pct:
      log.warning(
        "position_stop_loss_triggered",
        position_id=position.id,
        coin=position.coin,
        entry_spread=position.entry_spread,
        current_spread=current_spread,
        change=spread_change
      )
      return True, "stop_loss"
    
    if position.is_expired(settings.max_position_time_minutes):
      log.warning(
        "position_time_limit_reached",
        position_id=position.id,
        coin=position.coin,
        duration_minutes=position.get_duration_minutes()
      )
      return True, "time_limit"
    
    return False, ""
  
  
  def get_performance_summary(self) -> dict:
    net_pnl = self.total_realized_pnl - self.total_funding_cost
    
    return {
      "total_realized_pnl": self.total_realized_pnl,
      "total_funding_cost": self.total_funding_cost,
      "net_pnl": net_pnl,
      "initial_balance": self.initial_balance,
      "return_pct": (net_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0,
      "emergency_stop": self.emergency_stop
    }