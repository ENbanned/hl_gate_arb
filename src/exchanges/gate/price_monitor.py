import asyncio
import json
import time
from typing import Any

import websockets
from websockets.exceptions import WebSocketException

from ..common.logging import get_logger
from ..common.exceptions import WebSocketError


logger = get_logger(__name__)


class GatePriceMonitor:
  __slots__ = (
    'settle',
    'ws_url',
    '_prices',
    '_ready',
    '_is_ready',
    '_ws',
    '_ws_task',
    '_shutdown',
    '_reconnect_delay',
    '_max_reconnect_delay'
  )
  
  def __init__(self, settle: str = 'usdt'):
    self.settle = settle
    self.ws_url = f'wss://fx-ws.gateio.ws/v4/ws/{settle}'
    self._prices: dict[str, float] = {}
    self._ready = asyncio.Event()
    self._is_ready = False
    self._ws = None
    self._ws_task = None
    self._shutdown = asyncio.Event()
    self._reconnect_delay = 1
    self._max_reconnect_delay = 60


  async def _handle_message(self, msg: dict[str, Any]) -> None:
    try:
      channel = msg.get('channel')
      
      if channel != 'futures.tickers':
        return
      
      event = msg.get('event')
      
      if event == 'update':
        prices = self._prices
        for ticker in msg.get('result', []):
          contract = ticker.get('contract', '').replace('_USDT', '')
          if contract:
            prices[contract] = float(ticker.get('last', 0))
        
        if not self._is_ready:
          self._is_ready = True
          self._ready.set()
          logger.info("price_monitor_ready", symbols=len(prices))
      
      elif event == 'subscribe':
        if msg.get('error') is None and not self._is_ready:
          self._is_ready = True
          self._ready.set()
          logger.info("price_monitor_subscribed")
    
    except (KeyError, ValueError) as e:
      logger.warning("price_monitor_parse_error", error=str(e))
    except Exception as e:
      logger.error("price_monitor_handle_error", error=str(e), exc_info=True)


  async def _ws_loop(self, contracts: list[str]) -> None:
    while not self._shutdown.is_set():
      try:
        logger.info("price_monitor_connecting", url=self.ws_url)
        
        async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
          self._ws = ws
          self._reconnect_delay = 1
          
          subscribe_msg = {
            'time': int(time.time()),
            'channel': 'futures.tickers',
            'event': 'subscribe',
            'payload': contracts
          }
          
          await ws.send(json.dumps(subscribe_msg))
          logger.info("price_monitor_subscribe_sent", contracts=len(contracts))
          
          async for raw_msg in ws:
            if self._shutdown.is_set():
              break
            
            try:
              msg = json.loads(raw_msg)
              await self._handle_message(msg)
            except json.JSONDecodeError as e:
              logger.warning("price_monitor_json_error", error=str(e))
      
      except WebSocketException as e:
        logger.error("price_monitor_ws_error", error=str(e))
        if not self._shutdown.is_set():
          await asyncio.sleep(self._reconnect_delay)
          self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
      
      except Exception as e:
        logger.error("price_monitor_unexpected_error", error=str(e), exc_info=True)
        if not self._shutdown.is_set():
          await asyncio.sleep(self._reconnect_delay)


  async def start(self, contracts: list[str]) -> None:
    self._ws_task = asyncio.create_task(self._ws_loop(contracts))
    
    try:
      await asyncio.wait_for(self._ready.wait(), timeout=30)
    except asyncio.TimeoutError:
      logger.error("price_monitor_start_timeout")
      raise WebSocketError("Price monitor failed to start within 30s")


  async def stop(self) -> None:
    logger.info("price_monitor_stopping")
    self._shutdown.set()
    
    if self._ws:
      await self._ws.close()
    
    if self._ws_task:
      try:
        await asyncio.wait_for(self._ws_task, timeout=5)
      except asyncio.TimeoutError:
        logger.warning("price_monitor_stop_timeout")
        self._ws_task.cancel()
    
    logger.info("price_monitor_stopped")


  def get_price(self, contract: str) -> float | None:
    return self._prices.get(contract)


  def get_price_unsafe(self, contract: str) -> float:
    return self._prices[contract]


  def has_price(self, contract: str) -> bool:
    return contract in self._prices


  @property
  def prices(self) -> dict[str, float]:
    return self._prices