from asyncio import Event
from typing import Any


class HyperliquidPriceMonitor:
  
  def __init__(self, info):
    self.info = info
    self.prices: dict[str, float] = {}
    self._ready = Event()


  def _on_mids_update(self, msg: Any) -> None:
    if msg['channel'] != 'allMids':
      return
    
    self.prices = {
      coin: float(px) 
      for coin, px in msg['data']['mids'].items()
    }
    
    if not self._ready.is_set():
      self._ready.set()


  async def start(self):
    self.info.subscribe({'type': 'allMids'}, self._on_mids_update)
    await self._ready.wait()


  def get_price(self, coin: str) -> float | None:
    return self.prices.get(coin)


  def get_all_prices(self) -> dict[str, float]:
    return self.prices.copy()