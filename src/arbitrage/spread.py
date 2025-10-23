from decimal import Decimal

from ..exchanges.common import ExchangeClient, PositionSide
from ..settings import GATE_TAKER_FEE, HYPERLIQUID_TAKER_FEE


class SpreadFinder:
  __slots__ = ('gate', 'hyperliquid', 'gate_taker_fee', 'hl_taker_fee')
  
  def __init__(
    self,
    gate: ExchangeClient,
    hyperliquid: ExchangeClient,
    gate_taker_fee: Decimal = GATE_TAKER_FEE,
    hl_taker_fee: Decimal = HYPERLIQUID_TAKER_FEE
  ):
    self.gate = gate
    self.hyperliquid = hyperliquid
    self.gate_taker_fee = gate_taker_fee
    self.hl_taker_fee = hl_taker_fee


  async def check_spread(self, symbol: str, size: float) -> list[dict]:

    gate_buy_price = await self.gate.estimate_fill_price(symbol, size, PositionSide.LONG)
    gate_sell_price = await self.gate.estimate_fill_price(symbol, size, PositionSide.SHORT)
    hyperliquid_buy_price = await self.hyperliquid.estimate_fill_price(symbol, size, PositionSide.LONG)
    hyperliquid_sell_price = await self.hyperliquid.estimate_fill_price(symbol, size, PositionSide.SHORT)

    


      
