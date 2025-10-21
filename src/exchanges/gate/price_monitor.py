import asyncio
import json
import threading
from typing import Any

import websocket


__all__ = ['GatePriceMonitor']


class GatePriceMonitor:
  __slots__ = ('settle', 'ws_url', '_prices', '_ready', '_loop', '_is_ready', '_ws_app', '_ws_thread', '_shutdown')
  
  def __init__(self, settle: str = 'usdt'):
    self.settle = settle
    self.ws_url = f'wss://fx-ws.gateio.ws/v4/ws/{settle}'
    
    self._prices: dict[str, float] = {}
    self._ready = asyncio.Event()
    self._loop = None
    self._is_ready = False
    self._ws_app = None
    self._ws_thread = None
    self._shutdown = False


  def _on_message(self, ws: Any, message: str) -> None:
    try:
      msg = json.loads(message)
      
      if msg.get('channel') == 'futures.tickers' and msg.get('event') == 'update':
        result = msg.get('result', [])
        prices = self._prices
        
        for ticker in result:
          contract = ticker.get('contract')
          last = ticker.get('last')
          
          if contract and last:
            prices[contract] = float(last)
        
        if not self._is_ready:
          self._is_ready = True
          if self._loop:
            self._loop.call_soon_threadsafe(self._ready.set)
      
      elif msg.get('channel') == 'futures.tickers' and msg.get('event') == 'subscribe':
        if msg.get('error') is None:
          pass
    
    except Exception:
      pass


  def _on_error(self, ws: Any, error: Any) -> None:
    pass


  def _on_close(self, ws: Any, close_status_code: Any, close_msg: Any) -> None:
    pass


  def _on_open(self, ws: Any) -> None:
    subscribe_msg = {
      'time': int(asyncio.get_event_loop().time()),
      'channel': 'futures.tickers',
      'event': 'subscribe',
      'payload': []
    }
    ws.send(json.dumps(subscribe_msg))


  async def start(self) -> None:
    self._loop = asyncio.get_running_loop()
    
    self._ws_app = websocket.WebSocketApp(
      self.ws_url,
      on_message=self._on_message,
      on_error=self._on_error,
      on_close=self._on_close,
      on_open=self._on_open
    )
    
    self._ws_thread = threading.Thread(
      target=self._ws_app.run_forever,
      daemon=True
    )
    self._ws_thread.start()
    
    await self._ready.wait()


  def stop(self) -> None:
    self._shutdown = True
    if self._ws_app:
      self._ws_app.close()
    if self._ws_thread:
      self._ws_thread.join(timeout=2)


  def get_price(self, contract: str) -> float | None:
    try:
      return self._prices[contract]
    except KeyError:
      return None


  def get_price_unsafe(self, contract: str) -> float:
    return self._prices[contract]


  def has_price(self, contract: str) -> bool:
    return contract in self._prices


  @property
  def prices(self) -> dict[str, float]:
    return self._prices