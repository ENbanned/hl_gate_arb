from decimal import Decimal
from datetime import datetime

from .models import Spread, SpreadDirection, SpreadOpportunity
from .calculator import (
  calculate_deviation,
  calculate_max_position_size,
  calculate_total_fees,
  calculate_funding_cost_daily,
  calculate_roi_daily
)


type ExchangeClient = object


class SpreadFinder:
  __slots__ = ('exchanges', 'min_deviation', 'fee_rate')
  
  def __init__(
    self,
    exchanges: dict[str, ExchangeClient],
    min_deviation: Decimal = Decimal('0.5'),
    fee_rate: Decimal = Decimal('0.0006')
  ):
    self.exchanges = exchanges
    self.min_deviation = min_deviation
    self.fee_rate = fee_rate


  def find_spreads(self, symbols: list[str]) -> list[Spread]:
    spreads = []
    
    exchange_names = list(self.exchanges.keys())
    if len(exchange_names) < 2:
      return spreads
    
    for symbol in symbols:
      for i, name_a in enumerate(exchange_names):
        for name_b in exchange_names[i + 1:]:
          spread = self._calculate_spread(symbol, name_a, name_b)
          if spread and abs(spread.deviation_pct) >= self.min_deviation:
            spreads.append(spread)
    
    return spreads


  def _calculate_spread(
    self, 
    symbol: str, 
    exchange_a: str, 
    exchange_b: str
  ) -> Spread | None:
    client_a = self.exchanges[exchange_a]
    client_b = self.exchanges[exchange_b]
    
    price_a = client_a.price_monitor.get_price(symbol)
    price_b = client_b.price_monitor.get_price(symbol)
    
    if price_a is None or price_b is None:
      return None
    
    price_a_dec = Decimal(str(price_a))
    price_b_dec = Decimal(str(price_b))
    
    deviation = calculate_deviation(price_a_dec, price_b_dec)
    
    return Spread(
      symbol=symbol,
      exchange_a=exchange_a,
      exchange_b=exchange_b,
      price_a=price_a_dec,
      price_b=price_b_dec,
      deviation_pct=deviation,
      timestamp=datetime.now()
    )


  async def analyze_opportunity(
    self,
    spread: Spread,
    leverage_a: int = 10,
    leverage_b: int = 10
  ) -> SpreadOpportunity | None:
    client_a = self.exchanges[spread.exchange_a]
    client_b = self.exchanges[spread.exchange_b]
    
    balance_a = await client_a.get_balance()
    balance_b = await client_b.get_balance()
    
    max_size = calculate_max_position_size(
      balance_a.available,
      balance_b.available,
      spread.price_a,
      spread.price_b,
      leverage_a,
      leverage_b
    )
    
    if max_size <= 0:
      return None
    
    direction = (
      SpreadDirection.LONG_A_SHORT_B 
      if spread.price_a < spread.price_b 
      else SpreadDirection.SHORT_A_LONG_B
    )
    
    fees = calculate_total_fees(
      max_size,
      spread.price_a,
      spread.price_b,
      spread.price_a,
      spread.price_b,
      self.fee_rate
    )
    
    try:
      funding_a = await client_a.get_funding_rate(spread.symbol)
      funding_b = await client_b.get_funding_rate(spread.symbol)
      
      funding_cost_a = calculate_funding_cost_daily(
        max_size,
        spread.price_a,
        funding_a.rate
      )
      funding_cost_b = calculate_funding_cost_daily(
        max_size,
        spread.price_b,
        funding_b.rate
      )
      funding_cost = funding_cost_a + funding_cost_b
    except Exception:
      funding_cost = Decimal('0')
    
    notional = max_size * (spread.price_a + spread.price_b) / 2
    profit_pct = abs(spread.deviation_pct) - (fees / notional * 100)
    profit_usd = notional * profit_pct / 100
    
    margin_used = notional / Decimal(str((leverage_a + leverage_b) / 2))
    roi = calculate_roi_daily(profit_usd, margin_used, funding_cost)
    
    return SpreadOpportunity(
      spread=spread,
      direction=direction,
      estimated_profit_pct=profit_pct,
      estimated_profit_usd=profit_usd,
      max_size=max_size,
      funding_cost_daily=funding_cost,
      roi_daily=roi
    )


  def get_spread_for_symbol(
    self, 
    symbol: str, 
    exchange_a: str, 
    exchange_b: str
  ) -> Spread | None:
    return self._calculate_spread(symbol, exchange_a, exchange_b)


  def get_all_spreads_for_symbol(self, symbol: str) -> list[Spread]:
    spreads = []
    exchange_names = list(self.exchanges.keys())
    
    for i, name_a in enumerate(exchange_names):
      for name_b in exchange_names[i + 1:]:
        spread = self._calculate_spread(symbol, name_a, name_b)
        if spread:
          spreads.append(spread)
    
    return spreads