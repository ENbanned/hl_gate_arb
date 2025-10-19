from src.config.settings import settings
from src.core.funding import FundingManager
from src.core.models import ExchangeName, Spread
from src.exchanges.base import ExchangeProtocol
from src.utils.logging import get_logger


log = get_logger(__name__)


class SpreadCalculator:
  
  def __init__(
    self,
    gate: ExchangeProtocol,
    hyperliquid: ExchangeProtocol,
    funding_manager: FundingManager,
  ):
    self.gate = gate
    self.hyperliquid = hyperliquid
    self.funding_manager = funding_manager


  async def calculate_spread(
    self, 
    coin: str, 
    size_usd: float,
    leverage: int
  ) -> tuple[Spread | None, Spread | None]:
    
    gate_book = await self.gate.get_orderbook(coin)
    hl_book = await self.hyperliquid.get_orderbook(coin)
    
    if not gate_book or not hl_book:
      return None, None
    
    if not gate_book.get("levels") or not hl_book.get("levels"):
      return None, None
    
    gate_bids = gate_book["levels"][0]
    gate_asks = gate_book["levels"][1]
    hl_bids = hl_book["levels"][0]
    hl_asks = hl_book["levels"][1]
    
    if not gate_bids or not gate_asks or not hl_bids or not hl_asks:
      return None, None
    
    gate_bid = float(gate_bids[0]["px"])
    gate_ask = float(gate_asks[0]["px"])
    hl_bid = float(hl_bids[0]["px"])
    hl_ask = float(hl_asks[0]["px"])
    
    gate_to_hl = self._calculate_directional_spread(
      coin=coin,
      buy_exchange=self.gate,
      sell_exchange=self.hyperliquid,
      buy_price=gate_ask,
      sell_price=hl_bid,
      size_usd=size_usd,
      leverage=leverage,
      direction="gate_to_hl"
    )
    
    hl_to_gate = self._calculate_directional_spread(
      coin=coin,
      buy_exchange=self.hyperliquid,
      sell_exchange=self.gate,
      buy_price=hl_ask,
      sell_price=gate_bid,
      size_usd=size_usd,
      leverage=leverage,
      direction="hl_to_gate"
    )
    
    return gate_to_hl, hl_to_gate


  def _calculate_directional_spread(
    self,
    coin: str,
    buy_exchange: ExchangeProtocol,
    sell_exchange: ExchangeProtocol,
    buy_price: float,
    sell_price: float,
    size_usd: float,
    leverage: int,
    direction: str
  ) -> Spread | None:
    
    buy_slippage_pct = buy_exchange.calculate_slippage(coin, size_usd * leverage, is_buy=True)
    sell_slippage_pct = sell_exchange.calculate_slippage(coin, size_usd * leverage, is_buy=False)
    
    buy_fee = settings.gate_taker_fee if buy_exchange.name == ExchangeName.GATE else settings.hyperliquid_taker_fee
    sell_fee = settings.gate_taker_fee if sell_exchange.name == ExchangeName.GATE else settings.hyperliquid_taker_fee
    
    notional_value = size_usd * leverage
    
    actual_buy_price = buy_price * (1 + buy_slippage_pct / 100)
    actual_sell_price = sell_price * (1 - sell_slippage_pct / 100)
    
    size_in_coins = notional_value / actual_buy_price
    
    buy_cost_notional = size_in_coins * actual_buy_price
    buy_cost_with_fees = buy_cost_notional * (1 + buy_fee / 100)
    
    sell_revenue_notional = size_in_coins * actual_sell_price
    sell_revenue_with_fees = sell_revenue_notional * (1 - sell_fee / 100)
    
    gross_spread_pct = ((sell_revenue_with_fees / buy_cost_with_fees) - 1) * 100
    
    buy_funding_rate, sell_funding_rate, funding_cost_pct = self.funding_manager.calculate_funding_cost(
      coin=coin,
      buy_exchange=buy_exchange.name,
      sell_exchange=sell_exchange.name,
      position_time_minutes=settings.max_position_time_minutes,
      size_usd=size_usd,
      leverage=leverage,
    )
    
    net_spread_pct = gross_spread_pct - funding_cost_pct
    
    estimated_profit = (net_spread_pct / 100) * size_usd * leverage
    
    if net_spread_pct < 0:
      return None
    
    return Spread(
      coin=coin,
      direction=direction,
      buy_exchange=buy_exchange.name,
      sell_exchange=sell_exchange.name,
      buy_price=buy_price,
      sell_price=sell_price,
      buy_slippage_pct=buy_slippage_pct,
      sell_slippage_pct=sell_slippage_pct,
      gross_spread_pct=gross_spread_pct,
      net_spread_pct=net_spread_pct,
      estimated_cost=buy_cost_with_fees,
      estimated_revenue=sell_revenue_with_fees,
      estimated_profit=estimated_profit,
      buy_funding_rate=buy_funding_rate,
      sell_funding_rate=sell_funding_rate,
      funding_cost_pct=funding_cost_pct,
      leverage=leverage,
      position_size_usd=size_usd
    )


  async def find_best_opportunities(
    self, 
    coins: list[str],
    min_spread: float,
    gate_balance_available: float,
    hl_balance_available: float
  ) -> list[Spread]:
    
    opportunities = []
    min_balance = min(gate_balance_available, hl_balance_available)
    
    for coin in coins:
      try:
        if not self.funding_manager.is_funding_acceptable(
          coin,
          ExchangeName.GATE,
          ExchangeName.HYPERLIQUID,
          settings.max_funding_rate_diff_pct,
        ):
          continue
        
        gate_leverage_min, gate_leverage_max = await self.gate.get_leverage_limits(coin)
        hl_leverage_min, hl_leverage_max = await self.hyperliquid.get_leverage_limits(coin)
        
        max_leverage = min(gate_leverage_max, hl_leverage_max)
        
        if settings.leverage_override:
          max_leverage = min(max_leverage, settings.leverage_override)
        
        if max_leverage < 1:
          continue
        
        if min_balance < settings.min_balance_usd:
          continue
        
        test_size = 100.0
        
        gate_to_hl, hl_to_gate = await self.calculate_spread(coin, test_size, max_leverage)
        
        if gate_to_hl and gate_to_hl.net_spread_pct >= min_spread:
          balance_pct = settings.get_balance_pct_for_spread(gate_to_hl.net_spread_pct)
          actual_size = min_balance * (balance_pct / 100)
          
          gate_to_hl_final, _ = await self.calculate_spread(coin, actual_size, max_leverage)
          
          if gate_to_hl_final and gate_to_hl_final.net_spread_pct >= min_spread:
            opportunities.append(gate_to_hl_final)
        
        if hl_to_gate and hl_to_gate.net_spread_pct >= min_spread:
          balance_pct = settings.get_balance_pct_for_spread(hl_to_gate.net_spread_pct)
          actual_size = min_balance * (balance_pct / 100)
          
          _, hl_to_gate_final = await self.calculate_spread(coin, actual_size, max_leverage)
          
          if hl_to_gate_final and hl_to_gate_final.net_spread_pct >= min_spread:
            opportunities.append(hl_to_gate_final)
      
      except Exception as e:
        log.debug("spread_calc_error", coin=coin, error=str(e))
        continue
    
    opportunities.sort(key=lambda x: x.net_spread_pct, reverse=True)
    
    return opportunities