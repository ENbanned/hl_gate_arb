import asyncio
import secrets
from datetime import datetime

from src.core.models import (
  ExchangeName,
  Position,
  PositionStatus,
  Spread,
)
from src.exchanges.base import ExchangeProtocol
from src.utils.logging import get_logger
from src.utils.telegram import notifier


log = get_logger(__name__)


class PositionManager:
  
  def __init__(
    self,
    gate: ExchangeProtocol,
    hyperliquid: ExchangeProtocol,
  ):
    self.gate = gate
    self.hyperliquid = hyperliquid
    
    self.active_positions: dict[str, Position] = {}
    self.closed_positions: list[Position] = []
  
  
  async def open_position(self, spread: Spread) -> Position | None:
    position_id = secrets.token_hex(4)
    
    position = Position(
      id=position_id,
      coin=spread.coin,
      direction=spread.direction,
      buy_exchange=spread.buy_exchange,
      sell_exchange=spread.sell_exchange,
      size_usd=spread.size_usd,
      leverage=spread.leverage,
      entry_spread_pct=spread.net_spread_pct,
      entry_buy_price=spread.buy_price,
      entry_sell_price=spread.sell_price,
      expected_profit_usd=spread.estimated_profit_usd,
      status=PositionStatus.OPENING,
    )
    
    buy_ex = self.gate if spread.buy_exchange == ExchangeName.GATE else self.hyperliquid
    sell_ex = self.gate if spread.sell_exchange == ExchangeName.GATE else self.hyperliquid
    
    try:
      buy_order_id = await buy_ex.open_position(
        spread.coin,
        "long",
        spread.size_usd,
        spread.leverage,
      )
      
      if not buy_order_id:
        log.error("position_buy_order_failed", position_id=position_id)
        return None
      
      position.buy_order_id = buy_order_id
      
      sell_order_id = await sell_ex.open_position(
        spread.coin,
        "short",
        spread.size_usd,
        spread.leverage,
      )
      
      if not sell_order_id:
        log.error("position_sell_order_failed", position_id=position_id)
        await buy_ex.close_position(spread.coin)
        return None
      
      position.sell_order_id = sell_order_id
      position.status = PositionStatus.ACTIVE
      
      self.active_positions[position_id] = position
      
      log.info(
        "position_opened",
        position_id=position_id,
        coin=spread.coin,
        direction=spread.direction,
        net_spread=f"{spread.net_spread_pct:.3f}%",
        size_usd=f"${spread.size_usd:.0f}",
        leverage=spread.leverage,
        expected_profit=f"${spread.estimated_profit_usd:.2f}",
      )
      
      await notifier.position_opened(
        coin=spread.coin,
        direction=spread.direction,
        net_spread=spread.net_spread_pct,
        size_usd=spread.size_usd,
        leverage=spread.leverage,
        expected_profit=spread.estimated_profit_usd,
      )
      
      return position
    
    except Exception as e:
      log.error("position_open_error", error=str(e))
      return None
  
  
  async def close_position(
    self, position: Position, reason: str
  ) -> float:
    position.status = PositionStatus.CLOSING
    position.close_reason = reason
    
    buy_ex = self.gate if position.buy_exchange == ExchangeName.GATE else self.hyperliquid
    sell_ex = self.gate if position.sell_exchange == ExchangeName.GATE else self.hyperliquid
    
    try:
      buy_closed = await buy_ex.close_position(position.coin)
      sell_closed = await sell_ex.close_position(position.coin)
      
      await asyncio.sleep(2)
      
      buy_pos = await buy_ex.get_position(position.coin)
      sell_pos = await sell_ex.get_position(position.coin)
      
      realized_pnl = 0.0
      if buy_pos:
        realized_pnl += buy_pos.unrealized_pnl
      if sell_pos:
        realized_pnl += sell_pos.unrealized_pnl
      
      position.realized_pnl_usd = realized_pnl
      position.closed_at = datetime.now()
      position.status = PositionStatus.CLOSED
      
      net_pnl = realized_pnl - position.funding_cost_usd
      
      duration_minutes = (
        (position.closed_at - position.opened_at).total_seconds() / 60
      )
      
      log.info(
        "position_closed",
        position_id=position.id,
        coin=position.coin,
        entry_spread=f"{position.entry_spread_pct:.3f}%",
        realized_pnl=f"${realized_pnl:.2f}",
        funding_cost=f"${position.funding_cost_usd:.2f}",
        net_pnl=f"${net_pnl:.2f}",
        duration_minutes=f"{duration_minutes:.1f}",
        reason=reason,
      )
      
      await notifier.position_closed(
        coin=position.coin,
        entry_spread=position.entry_spread_pct,
        realized_pnl=realized_pnl,
        funding_cost=position.funding_cost_usd,
        net_pnl=net_pnl,
        duration_minutes=duration_minutes,
        reason=reason,
      )
      
      if position.id in self.active_positions:
        del self.active_positions[position.id]
      
      self.closed_positions.append(position)
      
      return net_pnl
    
    except Exception as e:
      log.error("position_close_error", position_id=position.id, error=str(e))
      position.status = PositionStatus.FAILED
      return 0.0
  
  
  async def verify_positions(self) -> bool:
    try:
      gate_positions = await self.gate.get_all_positions()
      hl_positions = await self.hyperliquid.get_all_positions()
      
      gate_coins = {p.coin for p in gate_positions}
      hl_coins = {p.coin for p in hl_positions}
      
      for position in list(self.active_positions.values()):
        expected_gate = position.buy_exchange == ExchangeName.GATE or position.sell_exchange == ExchangeName.GATE
        expected_hl = position.buy_exchange == ExchangeName.HYPERLIQUID or position.sell_exchange == ExchangeName.HYPERLIQUID
        
        gate_exists = position.coin in gate_coins
        hl_exists = position.coin in hl_coins
        
        if (expected_gate != gate_exists) or (expected_hl != hl_exists):
          log.critical(
            "position_desync_detected",
            position_id=position.id,
            coin=position.coin,
            expected_gate=expected_gate,
            expected_hl=expected_hl,
            gate_exists=gate_exists,
            hl_exists=hl_exists,
          )
          
          await notifier.error_alert(
            "Position Desync",
            f"Position {position.coin} desync detected. Expected: Gate={expected_gate}, HL={expected_hl}. Actual: Gate={gate_exists}, HL={hl_exists}",
          )
          
          return False
      
      return True
    
    except Exception as e:
      log.error("verify_positions_error", error=str(e))
      return False