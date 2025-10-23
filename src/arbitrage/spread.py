from decimal import Decimal

from ..exchanges.common import ExchangeClient, PositionSide
from ..settings import GATE_TAKER_FEE, HYPERLIQUID_TAKER_FEE


class SpreadFinder:
  __slots__ = ('gate', 'hl', 'gate_taker_fee', 'hl_taker_fee')
  
  def __init__(
    self,
    gate: ExchangeClient,
    hl: ExchangeClient,
    gate_taker_fee: Decimal = GATE_TAKER_FEE,
    hl_taker_fee: Decimal = HYPERLIQUID_TAKER_FEE
  ):
    self.gate = gate
    self.hl = hl
    self.gate_taker_fee = gate_taker_fee
    self.hl_taker_fee = hl_taker_fee


  async def estimate_execution_price(
    self,
    exchange: ExchangeClient,
    symbol: str,
    size: float,
    side: PositionSide
  ) -> Decimal:
    price = await exchange.estimate_fill_price(symbol, size, side)
    
    fee = self.gate_taker_fee if exchange == self.gate else self.hl_taker_fee
    
    if side == PositionSide.LONG:
      return price * (Decimal('1') + fee)
    else:
      return price * (Decimal('1') - fee)


  async def find_spreads(self, symbols: list[str], volume: float) -> list[dict]:
    results = []
    
    for symbol in symbols:
      gate_buy_price = "твой_метод_оценки(gate, 'buy', volume)"
      gate_sell_price = "твой_метод_оценки(gate, 'sell', volume)"
      hl_buy_price = "твой_метод_оценки(hl, 'buy', volume)"
      hl_sell_price = "твой_метод_оценки(hl, 'sell', volume)"
      
    return results