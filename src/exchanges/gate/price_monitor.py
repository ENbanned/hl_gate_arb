import asyncio
import json
import time
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol


__all__ = ['GatePriceMonitor']


class GatePriceMonitor:
  __slots__ = ('settle', 'ws_url', '_prices', '_ready', '_is_ready', '_ws_task', '_shutdown')
  
  def __init__(self, settle: str = 'usdt') -> None:
    self.settle = settle
    self.ws_url = f'wss://fx-ws.gateio.ws/v4/ws/{settle}'
    self._prices: dict[str, float] = {}
    self._ready = asyncio.Event()
    self._is_ready = False
    self._ws_task: asyncio.Task | None = None
    self._shutdown = asyncio.Event()


  async def _handle_message(self, message: str) -> None:
    try:
      msg = json.loads(message)
      channel = msg.get('channel')
      
      if channel == 'futures.tickers':
        event = msg.get('event')
        
        if event == 'update':
          prices = self._prices
          for ticker in msg['result']:
            contract = ticker['contract'].replace('_USDT', '')
            prices[contract] = float(ticker['last'])
          
          if not self._is_ready:
            self._is_ready = True
            self._ready.set()
        
        elif event == 'subscribe' and msg.get('error') is None and not self._is_ready:
          self._is_ready = True
          self._ready.set()
    
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
      pass


  async def _ws_loop(self, contracts: list[str]) -> None:
    while not self._shutdown.is_set():
      try:
        async with websockets.connect(self.ws_url) as ws:
          subscribe_msg = json.dumps({
            'time': int(time.time()),
            'channel': 'futures.tickers',
            'event': 'subscribe',
            'payload': contracts
          })
          await ws.send(subscribe_msg)
          
          async for message in ws:
            if self._shutdown.is_set():
              break
            await self._handle_message(message)
      
      except (websockets.exceptions.WebSocketException, ConnectionError, OSError):
        if not self._shutdown.is_set():
          await asyncio.sleep(5)


  async def start(self, contracts: list[str]) -> None:
    self._ws_task = asyncio.create_task(self._ws_loop(contracts))
    await self._ready.wait()


  async def stop(self) -> None:
    self._shutdown.set()
    if self._ws_task:
      self._ws_task.cancel()
      try:
        await self._ws_task
      except asyncio.CancelledError:
        pass


  def get_price(self, symbol: str) -> float | None:
    return self._prices.get(symbol)


  def get_price_unsafe(self, symbol: str) -> float:
    return self._prices[symbol]


  def has_price(self, symbol: str) -> bool:
    return symbol in self._prices


  @property
  def prices(self) -> dict[str, float]:
    return self._prices