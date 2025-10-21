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
    print(12345678)
    self.info.subscribe({'type': 'allMids'}, self._ws_callback)
    print(123456789)
    await self._ready.wait()
    print(1234567890)


  def get_price(self, coin: str) -> float | None:
    return self.prices.get(coin)