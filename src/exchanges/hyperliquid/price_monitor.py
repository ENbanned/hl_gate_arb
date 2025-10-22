import asyncio
from typing import Any

from ..common.logging import get_logger


logger = get_logger(__name__)


class HyperliquidPriceMonitor:
  __slots__ = ('info', '_prices', '_ready', '_is_ready')
  
  def __init__(self, info):
    self.info = info
    self._prices: dict[str, float] = {}
    self._ready = asyncio.Event()
    self._is_ready = False


  def _on_mids_update(self, msg: Any) -> None:
    try:
      if msg.get('channel') != 'allMids':
        return
      
      data = msg.get('data', {})
      mids = data.get('mids', {})
      prices = self._prices
      
      for coin, px in mids.items():
        prices[coin] = float(px)
      
      if not self._is_ready:
        self._is_ready = True
        self._ready.set()
        logger.info("hyperliquid_price_monitor_ready", symbols=len(prices))
    
    except (KeyError, ValueError, TypeError) as e:
      logger.warning("hyperliquid_price_parse_error", error=str(e))
    except Exception as e:
      logger.error("hyperliquid_price_error", error=str(e), exc_info=True)


  async def start(self) -> None:
    logger.info("hyperliquid_price_monitor_starting")
    self.info.subscribe({'type': 'allMids'}, self._on_mids_update)
    
    try:
      await asyncio.wait_for(self._ready.wait(), timeout=30)
    except asyncio.TimeoutError:
      logger.error("hyperliquid_price_monitor_timeout")
      raise


  def get_price(self, coin: str) -> float | None:
    return self._prices.get(coin)


  def get_price_unsafe(self, coin: str) -> float:
    return self._prices[coin]


  def has_price(self, coin: str) -> bool:
    return coin in self._prices


  @property
  def prices(self) -> dict[str, float]:
    return self._prices