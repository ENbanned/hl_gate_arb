from datetime import datetime

from src.core.models import ExchangeName, FundingRate
from src.exchanges.base import ExchangeProtocol
from src.utils.logging import get_logger


log = get_logger(__name__)


class FundingManager:
  
  def __init__(self, gate: ExchangeProtocol, hyperliquid: ExchangeProtocol):
    self.gate = gate
    self.hyperliquid = hyperliquid
    self.funding_cache: dict[str, dict[ExchangeName, FundingRate]] = {}
  
  
  async def update_funding_rates(self, coins: list[str]):
    for coin in coins:
      try:
        gate_rate = await self.gate.get_funding_rate(coin)
        hl_rate = await self.hyperliquid.get_funding_rate(coin)
        
        self.funding_cache[coin] = {
          ExchangeName.GATE: FundingRate(
            exchange=ExchangeName.GATE,
            coin=coin,
            rate=gate_rate,
            timestamp=datetime.utcnow(),
          ),
          ExchangeName.HYPERLIQUID: FundingRate(
            exchange=ExchangeName.HYPERLIQUID,
            coin=coin,
            rate=hl_rate,
            timestamp=datetime.utcnow(),
          ),
        }
      
      except Exception as e:
        log.debug("funding_rate_update_failed", coin=coin, error=str(e))
  
  
  def get_funding_rate(self, coin: str, exchange: ExchangeName) -> float:
    if coin not in self.funding_cache:
      return 0.0
    
    funding = self.funding_cache[coin].get(exchange)
    if not funding:
      return 0.0
    
    return funding.rate
  
  
  def calculate_funding_cost(
    self,
    coin: str,
    buy_exchange: ExchangeName,
    sell_exchange: ExchangeName,
    position_time_minutes: float,
    size_usd: float,
    leverage: int,
  ) -> tuple[float, float, float]:
    
    buy_rate = self.get_funding_rate(coin, buy_exchange)
    sell_rate = self.get_funding_rate(coin, sell_exchange)
    
    position_time_hours = position_time_minutes / 60
    
    if buy_exchange == ExchangeName.GATE:
      gate_funding_intervals = position_time_hours / 8
      buy_cost = buy_rate * gate_funding_intervals
      sell_cost = -sell_rate * position_time_hours
    else:
      hl_funding_intervals = position_time_hours
      buy_cost = buy_rate * hl_funding_intervals
      sell_cost = -sell_rate * (position_time_hours / 8)
    
    net_funding_cost = (buy_cost + sell_cost) * size_usd * leverage
    net_funding_cost_pct = (buy_cost + sell_cost) * 100
    
    return buy_rate, sell_rate, net_funding_cost_pct
  
  
  def is_funding_acceptable(
    self,
    coin: str,
    buy_exchange: ExchangeName,
    sell_exchange: ExchangeName,
    max_diff_pct: float,
  ) -> bool:
    
    buy_rate = abs(self.get_funding_rate(coin, buy_exchange))
    sell_rate = abs(self.get_funding_rate(coin, sell_exchange))
    
    diff = abs(buy_rate - sell_rate)
    
    return diff <= max_diff_pct