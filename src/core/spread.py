import asyncio

from src.config.constants import (
  GATE_FEE_TAKER,
  HYPERLIQUID_FEE_TAKER,
)
from src.config.settings import settings
from src.core.models import ExchangeName, Spread
from src.exchanges.base import ExchangeProtocol
from src.utils.logging import get_logger


log = get_logger(__name__)


class SpreadCalculator:
  
  def __init__(
    self,
    gate: ExchangeProtocol,
    hyperliquid: ExchangeProtocol,
  ):
    self.gate = gate
    self.hyperliquid = hyperliquid
  
  
  async def calculate_spread(
    self,
    coin: str,
    size_usd: float,
    leverage: int,
  ) -> tuple[Spread | None, Spread | None]:
    gate_book = await self.gate.get_orderbook(coin)
    hl_book = await self.hyperliquid.get_orderbook(coin)
    
    if not gate_book or not hl_book:
      return None, None
    
    if not gate_book.bids or not gate_book.asks:
      return None, None
    if not hl_book.bids or not hl_book.asks:
      return None, None
    
    gate_bid = gate_book.bids[0].price
    gate_ask = gate_book.asks[0].price
    hl_bid = hl_book.bids[0].price
    hl_ask = hl_book.asks[0].price
    
    gate_funding = await self.gate.get_funding_rate(coin)
    hl_funding = await self.hyperliquid.get_funding_rate(coin)
    
    gate_to_hl = await self._calculate_directional_spread(
      coin=coin,
      buy_exchange=self.gate,
      sell_exchange=self.hyperliquid,
      buy_price=gate_ask,
      sell_price=hl_bid,
      buy_funding=gate_funding.rate if gate_funding else 0.0,
      sell_funding=hl_funding.rate if hl_funding else 0.0,
      size_usd=size_usd,
      leverage=leverage,
      direction="gate_to_hl",
    )
    
    hl_to_gate = await self._calculate_directional_spread(
      coin=coin,
      buy_exchange=self.hyperliquid,
      sell_exchange=self.gate,
      buy_price=hl_ask,
      sell_price=gate_bid,
      buy_funding=hl_funding.rate if hl_funding else 0.0,
      sell_funding=gate_funding.rate if gate_funding else 0.0,
      size_usd=size_usd,
      leverage=leverage,
      direction="hl_to_gate",
    )
    
    return gate_to_hl, hl_to_gate
  
  
  async def _calculate_directional_spread(
    self,
    coin: str,
    buy_exchange: ExchangeProtocol,
    sell_exchange: ExchangeProtocol,
    buy_price: float,
    sell_price: float,
    buy_funding: float,
    sell_funding: float,
    size_usd: float,
    leverage: int,
    direction: str,
  ) -> Spread | None:
    if buy_price >= sell_price:
      return None
    
    gross_spread_pct = ((sell_price - buy_price) / buy_price) * 100
    
    buy_fee = GATE_FEE_TAKER if buy_exchange.name == ExchangeName.GATE else HYPERLIQUID_FEE_TAKER
    sell_fee = GATE_FEE_TAKER if sell_exchange.name == ExchangeName.GATE else HYPERLIQUID_FEE_TAKER
    
    fee_cost_pct = (buy_fee + sell_fee) * 100
    
    expected_hold_hours = 0.5
    funding_cost_pct = abs(buy_funding - sell_funding) * expected_hold_hours * 100
    
    if funding_cost_pct > settings.max_funding_rate_pct:
      return None
    
    net_spread_pct = gross_spread_pct - fee_cost_pct - funding_cost_pct
    
    if net_spread_pct < settings.min_net_spread_pct:
      return None
    
    estimated_profit_usd = (size_usd * leverage * net_spread_pct) / 100
    
    return Spread(
      coin=coin,
      direction=direction,
      buy_exchange=buy_exchange.name,
      sell_exchange=sell_exchange.name,
      buy_price=buy_price,
      sell_price=sell_price,
      gross_spread_pct=gross_spread_pct,
      funding_cost_pct=funding_cost_pct,
      net_spread_pct=net_spread_pct,
      size_usd=size_usd,
      leverage=leverage,
      estimated_profit_usd=estimated_profit_usd,
    )
  
  
  async def find_best_spreads(
    self,
    coins: list[str],
    gate_balance: float,
    hl_balance: float,
  ) -> list[Spread]:
    min_balance = min(gate_balance, hl_balance)
    
    if min_balance < settings.min_balance_usd:
      return []
    
    opportunities = []
    
    for idx, coin in enumerate(coins):
      try:
        if idx > 0 and idx % 10 == 0:
          await asyncio.sleep(0.5)
        
        gate_lev_min, gate_lev_max = await self.gate.get_leverage_limits(coin)
        hl_lev_min, hl_lev_max = await self.hyperliquid.get_leverage_limits(coin)
        
        max_leverage = min(gate_lev_max, hl_lev_max)
        
        if settings.leverage_override:
          max_leverage = min(max_leverage, settings.leverage_override)
        
        if max_leverage < 1:
          continue
        
        position_size = min_balance * (settings.position_size_pct / 100)
        
        gate_to_hl, hl_to_gate = await self.calculate_spread(
          coin, position_size, max_leverage
        )
        
        if gate_to_hl:
          opportunities.append(gate_to_hl)
        
        if hl_to_gate:
          opportunities.append(hl_to_gate)
      
      except Exception as e:
        log.debug("spread_calc_error", coin=coin, error=str(e))
        continue
    
    opportunities.sort(key=lambda x: x.net_spread_pct, reverse=True)
    
    return opportunities