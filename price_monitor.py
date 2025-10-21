from asyncio import Queue
from collections.abc import Callable


class PriceMonitor:
  def __init__(self):
    self.prices: dict[str, float] = {}
    self.queue: Queue[dict[str, float]] = Queue(maxsize=1)
    self.callbacks: list[Callable[[dict[str, float]], None]] = []


  def _ws_callback(self, msg: dict) -> None:
    if msg['channel'] != 'allMids':
      return
    
    mids = msg['data']['mids']
    
    prices = {coin: float(px) for coin, px in mids.items()}
    self.prices = prices
    
    self.queue.put_nowait(prices) if not self.queue.full() else None
    
    for cb in self.callbacks:
      cb(prices)


  async def start(self):
    self.info.subscribe({'type': 'allMids'}, self._ws_callback)
    
    
  async def wait_update(self) -> dict[str, float]:
    return await self.queue.get()


  def get_price(self, coin: str) -> float | None:
    return self.prices.get(coin)


  def add_callback(self, cb: Callable[[dict[str, float]], None]):
    self.callbacks.append(cb)