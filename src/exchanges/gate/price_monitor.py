import asyncio
import json
import threading
import time
from typing import Any

import websocket


__all__ = ['GatePriceMonitor']


class GatePriceMonitor:
  __slots__ = ('settle', 'ws_url', '_prices', '_ready', '_loop', '_is_ready', '_ws_app', '_ws_thread')
  
  def __init__(self, settle: str = 'usdt'):
    self.settle = settle
    self.ws_url = f'wss://fx-ws.gateio.ws/v4/ws/{settle}'
    self._prices: dict[str, float] = {}
    self._ready = asyncio.Event()
    self._loop = None
    self._is_ready = False
    self._ws_app = None
    self._ws_thread = None


  def _on_message(self, ws: Any, message: str) -> None:
    try:
      msg = json.loads(message)
      channel = msg['channel']
      
      if channel == 'futures.tickers':
        event = msg['event']
        
        if event == 'update':
          prices = self._prices
          for ticker in msg['result']:
            prices[ticker['contract']] = float(ticker['last'])
          
          if not self._is_ready:
            self._is_ready = True
            self._loop.call_soon_threadsafe(self._ready.set)
        
        elif event == 'subscribe' and msg.get('error') is None and not self._is_ready:
          self._is_ready = True
          self._loop.call_soon_threadsafe(self._ready.set)
    
    except (KeyError, ValueError, TypeError):
      pass


  def _on_error(self, ws: Any, error: Any) -> None:
    pass


  def _on_close(self, ws: Any, close_status_code: Any, close_msg: Any) -> None:
    pass


  def _on_open(self, ws: Any, contracts: list[str]) -> None:
    ws.send(json.dumps({
      'time': int(time.time()),
      'channel': 'futures.tickers',
      'event': 'subscribe',
      'payload': contracts
    }))


  async def start(self, contracts: list[str]) -> None:
    self._loop = asyncio.get_running_loop()
    
    self._ws_app = websocket.WebSocketApp(
      self.ws_url,
      on_message=self._on_message,
      on_error=self._on_error,
      on_close=self._on_close,
      on_open=lambda ws: self._on_open(ws, contracts)
    )
    
    self._ws_thread = threading.Thread(
      target=self._ws_app.run_forever,
      daemon=True
    )
    self._ws_thread.start()
    
    await self._ready.wait()


  def stop(self) -> None:
    if self._ws_app:
      self._ws_app.close()
    if self._ws_thread and self._ws_thread.is_alive():
      self._ws_thread.join(timeout=2)


  def get_price(self, contract: str) -> float | None:
    return self._prices.get(contract)


  def get_price_unsafe(self, contract: str) -> float:
    return self._prices[contract]


  def has_price(self, contract: str) -> bool:
    return contract in self._prices


  @property
  def prices(self) -> dict[str, float]:
    return self._prices