import asyncio
from typing import Any

__all__ = ['HyperliquidPriceMonitor']


class HyperliquidPriceMonitor:
  __slots__ = ('info', '_prices', '_ready', '_loop', '_is_ready')
  
  def __init__(self, info):
    self.info = info
    self._prices: dict[str, float] = {}
    self._ready = asyncio.Event()
    self._loop = None
    self._is_ready = False


  def _on_mids_update(self, msg: Any) -> None:
    if msg['channel'] != 'allMids':
      return
    
    data = msg['data']['mids']
    prices = self._prices
    
    for coin, px in data.items():
      prices[coin] = float(px)
    
    if not self._is_ready:
      self._is_ready = True
      self._loop.call_soon_threadsafe(self._ready.set)


  async def start(self) -> None:
    self._loop = asyncio.get_running_loop()
    self.info.subscribe({'type': 'allMids'}, self._on_mids_update)
    await self._ready.wait()


  def get_price(self, coin: str) -> float | None:
    try:
      return self._prices[coin]
    except KeyError:
      return None


  def get_price_unsafe(self, coin: str) -> float:
    return self._prices[coin]


  def has_price(self, coin: str) -> bool:
    return coin in self._prices


  @property
  def prices(self) -> dict[str, float]:
    return self._prices