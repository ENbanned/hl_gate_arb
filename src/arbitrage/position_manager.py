import uuid
from decimal import Decimal
from datetime import datetime

from .models import ArbitragePosition, SpreadDirection, SpreadStatus, SpreadOpportunity
from .calculator import calculate_spread_profit


type ExchangeClient = object


class PositionManager:
  __slots__ = ('exchanges', 'positions', 'max_positions', 'close_threshold_pct')
  
  def __init__(
    self,
    exchanges: dict[str, ExchangeClient],
    max_positions: int = 5,
    close_threshold_pct: Decimal = Decimal('0.1')
  ):
    self.exchanges = exchanges
    self.positions: dict[str, ArbitragePosition] = {}
    self.max_positions = max_positions
    self.close_threshold_pct = close_threshold_pct


  async def open_position(
    self,
    opportunity: SpreadOpportunity,
    size: Decimal | None = None
  ) -> ArbitragePosition:
    if len(self.positions) >= self.max_positions:
      raise RuntimeError(f"Max positions limit reached: {self.max_positions}")
    
    spread = opportunity.spread
    actual_size = size if size else opportunity.max_size
    
    client_a = self.exchanges[spread.exchange_a]
    client_b = self.exchanges[spread.exchange_b]
    
    if opportunity.direction == SpreadDirection.LONG_A_SHORT_B:
      order_a = await client_a.buy_market(spread.symbol, float(actual_size))
      order_b = await client_b.sell_market(spread.symbol, float(actual_size))
    else:
      order_a = await client_a.sell_market(spread.symbol, float(actual_size))
      order_b = await client_b.buy_market(spread.symbol, float(actual_size))
    
    position = ArbitragePosition(
      id=str(uuid.uuid4()),
      symbol=spread.symbol,
      exchange_a=spread.exchange_a,
      exchange_b=spread.exchange_b,
      direction=opportunity.direction,
      size=actual_size,
      entry_price_a=order_a.fill_price,
      entry_price_b=order_b.fill_price,
      entry_spread=spread.deviation_pct,
      fees_paid=order_a.fee + order_b.fee,
      status=SpreadStatus.OPEN
    )
    
    self.positions[position.id] = position
    return position


  async def close_position(self, position_id: str) -> ArbitragePosition:
    position = self.positions.get(position_id)
    if not position:
      raise ValueError(f"Position {position_id} not found")
    
    if position.status != SpreadStatus.OPEN:
      raise ValueError(f"Position {position_id} is not open")
    
    position.status = SpreadStatus.CLOSING
    
    client_a = self.exchanges[position.exchange_a]
    client_b = self.exchanges[position.exchange_b]
    
    try:
      if position.direction == SpreadDirection.LONG_A_SHORT_B:
        order_a = await client_a.sell_market(position.symbol, float(position.size))
        order_b = await client_b.buy_market(position.symbol, float(position.size))
      else:
        order_a = await client_a.buy_market(position.symbol, float(position.size))
        order_b = await client_b.sell_market(position.symbol, float(position.size))
      
      exit_price_a = order_a.fill_price
      exit_price_b = order_b.fill_price
      
      direction_long_a = position.direction == SpreadDirection.LONG_A_SHORT_B
      
      profit = calculate_spread_profit(
        position.entry_price_a,
        position.entry_price_b,
        exit_price_a,
        exit_price_b,
        position.size,
        direction_long_a
      )
      
      total_fees = position.fees_paid + order_a.fee + order_b.fee
      
      position.realized_pnl = profit - total_fees
      position.fees_paid = total_fees
      position.status = SpreadStatus.CLOSED
      position.closed_at = datetime.now()
      
      return position
      
    except Exception as ex:
      position.status = SpreadStatus.FAILED
      raise RuntimeError(f"Failed to close position {position_id}: {str(ex)}") from ex


  async def update_positions(self) -> None:
    for position in self.positions.values():
      if position.status != SpreadStatus.OPEN:
        continue
      
      await self._update_position(position)


  async def _update_position(self, position: ArbitragePosition) -> None:
    client_a = self.exchanges[position.exchange_a]
    client_b = self.exchanges[position.exchange_b]
    
    price_a = client_a.price_monitor.get_price(position.symbol)
    price_b = client_b.price_monitor.get_price(position.symbol)
    
    if price_a is None or price_b is None:
      return
    
    price_a_dec = Decimal(str(price_a))
    price_b_dec = Decimal(str(price_b))
    
    avg = (price_a_dec + price_b_dec) / 2
    current_spread = ((price_a_dec - price_b_dec) / avg) * 100 if avg > 0 else Decimal('0')
    position.current_spread = current_spread
    
    direction_long_a = position.direction == SpreadDirection.LONG_A_SHORT_B
    
    unrealized = calculate_spread_profit(
      position.entry_price_a,
      position.entry_price_b,
      price_a_dec,
      price_b_dec,
      position.size,
      direction_long_a
    )
    
    position.unrealized_pnl = unrealized - position.fees_paid


  async def check_close_conditions(self) -> list[str]:
    positions_to_close = []
    
    for pos_id, position in self.positions.items():
      if position.status != SpreadStatus.OPEN:
        continue
      
      if position.current_spread is None:
        continue
      
      if abs(position.current_spread) <= self.close_threshold_pct:
        positions_to_close.append(pos_id)
    
    return positions_to_close


  def get_position(self, position_id: str) -> ArbitragePosition | None:
    return self.positions.get(position_id)


  def get_open_positions(self) -> list[ArbitragePosition]:
    return [
      pos for pos in self.positions.values() 
      if pos.status == SpreadStatus.OPEN
    ]


  def get_all_positions(self) -> list[ArbitragePosition]:
    return list(self.positions.values())


  def get_total_pnl(self) -> Decimal:
    total = Decimal('0')
    for position in self.positions.values():
      if position.status == SpreadStatus.CLOSED:
        total += position.realized_pnl
      elif position.status == SpreadStatus.OPEN:
        total += position.unrealized_pnl
    return total