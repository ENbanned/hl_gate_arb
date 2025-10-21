from asyncio import Event


class HyperliquidPriceMonitor:
  
  def __init__(self):
    self.prices: dict[str, float] = {}
    self._ready = Event()


  def _ws_callback(self, msg: dict) -> None:
    if msg['channel'] != 'allMids':
      return
    
    self.prices = {coin: float(px) for coin, px in msg['data']['mids'].items()}
    self._ready.set()


  async def start(self):
    self.info.subscribe({'type': 'allMids'}, self._ws_callback)
    await self._ready.wait()


  def get_price(self, coin: str) -> float | None:
    return self.prices.get(coin)