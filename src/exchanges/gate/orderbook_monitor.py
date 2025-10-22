import asyncio
import json
import threading
import time
from collections import deque
from decimal import Decimal
from typing import Any

import websocket

from ..common.models import Orderbook, OrderbookLevel


__all__ = ['GateOrderbookMonitor']


class GateOrderbookMonitor:
  __slots__ = (
    'settle',
    'ws_url',
    'futures_api',
    '_orderbooks',
    '_update_queues',
    '_base_ids',
    '_ready',
    '_loop',
    '_is_ready',
    '_ws_app',
    '_ws_thread',
    '_contracts'
  )
  
  def __init__(self, settle: str, futures_api):
    self.settle = settle
    self.ws_url = f'wss://fx-ws.gateio.ws/v4/ws/{settle}'
    self.futures_api = futures_api
    self._orderbooks: dict[str, Orderbook] = {}
    self._update_queues: dict[str, deque] = {}
    self._base_ids: dict[str, int] = {}
    self._ready = asyncio.Event()
    self._loop = None
    self._is_ready = False
    self._ws_app = None
    self._ws_thread = None
    self._contracts: list[str] = []


  def _on_message(self, ws: Any, message: str) -> None:
    try:
      msg = json.loads(message)
      
      if msg.get('channel') != 'futures.order_book_update':
        return
      
      event = msg.get('event')
      
      if event == 'update':
        result = msg.get('result')
        if not result:
          return
        
        contract = result['s']
        symbol = contract.replace('_USDT', '')
        
        update_id_first = result['U']
        update_id_last = result['u']
        
        if symbol not in self._base_ids:
          if symbol not in self._update_queues:
            self._update_queues[symbol] = deque(maxlen=1000)
          self._update_queues[symbol].append(result)
          return
        
        base_id = self._base_ids[symbol]
        
        if update_id_first > base_id + 1:
          asyncio.run_coroutine_threadsafe(
            self._resync_orderbook(symbol, contract),
            self._loop
          )
          return
        
        if update_id_last < base_id + 1:
          return
        
        self._apply_update(symbol, result)
        self._base_ids[symbol] = update_id_last
      
      elif event == 'subscribe':
        if not self._is_ready:
          self._is_ready = True
          self._loop.call_soon_threadsafe(self._ready.set)
    
    except (KeyError, ValueError, TypeError):
      pass


  def _apply_update(self, symbol: str, update: dict[str, Any]) -> None:
    book = self._orderbooks.get(symbol)
    if not book:
      return
    
    bids_dict = {level.price: level for level in book.bids}
    asks_dict = {level.price: level for level in book.asks}
    
    for bid in update.get('b', []):
      price = Decimal(bid['p'])
      size = Decimal(str(bid['s']))
      
      if size == 0:
        bids_dict.pop(price, None)
      else:
        bids_dict[price] = OrderbookLevel(price=price, size=size)
    
    for ask in update.get('a', []):
      price = Decimal(ask['p'])
      size = Decimal(str(ask['s']))
      
      if size == 0:
        asks_dict.pop(price, None)
      else:
        asks_dict[price] = OrderbookLevel(price=price, size=size)
    
    book.bids = sorted(bids_dict.values(), key=lambda x: x.price, reverse=True)
    book.asks = sorted(asks_dict.values(), key=lambda x: x.price)
    book.timestamp = int(update['t'] * 1000)


  async def _resync_orderbook(self, symbol: str, contract: str) -> None:
    await self._fetch_snapshot(symbol, contract)


  async def _fetch_snapshot(self, symbol: str, contract: str) -> None:
    try:
      raw = await asyncio.to_thread(
        self.futures_api.list_futures_order_book,
        self.settle,
        contract,
        limit=100,
        with_id=True
      )
      
      snapshot = raw.to_dict()
      base_id = snapshot['id']
      
      bids = [
        OrderbookLevel(price=Decimal(level['p']), size=Decimal(str(level['s'])))
        for level in snapshot['bids']
      ]
      asks = [
        OrderbookLevel(price=Decimal(level['p']), size=Decimal(str(level['s'])))
        for level in snapshot['asks']
      ]
      
      self._orderbooks[symbol] = Orderbook(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp=int(snapshot['current'] * 1000)
      )
      self._base_ids[symbol] = base_id
      
      if symbol in self._update_queues:
        queue = self._update_queues[symbol]
        
        while queue:
          update = queue[0]
          u_first = update['U']
          u_last = update['u']
          
          if u_last < base_id + 1:
            queue.popleft()
            continue
          
          if u_first <= base_id + 1 and u_last >= base_id + 1:
            self._apply_update(symbol, update)
            self._base_ids[symbol] = u_last
            queue.popleft()
          else:
            break
        
        del self._update_queues[symbol]
    
    except Exception:
      pass


  def _on_error(self, ws: Any, error: Any) -> None:
    pass


  def _on_close(self, ws: Any, close_status_code: Any, close_msg: Any) -> None:
    pass


  def _on_open(self, ws: Any, contracts: list[str]) -> None:
    subscriptions = []
    for contract in contracts:
      subscriptions.append([contract, '100ms', '100'])
    
    ws.send(json.dumps({
      'time': int(time.time()),
      'channel': 'futures.order_book_update',
      'event': 'subscribe',
      'payload': subscriptions
    }))


  async def start(self, contracts: list[str]) -> None:
    self._loop = asyncio.get_running_loop()
    self._contracts = contracts
    
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
    
    tasks = []
    for contract in contracts:
      symbol = contract.replace('_USDT', '')
      tasks.append(self._fetch_snapshot(symbol, contract))
    
    await asyncio.gather(*tasks, return_exceptions=True)


  def stop(self) -> None:
    if self._ws_app:
      self._ws_app.close()
    if self._ws_thread and self._ws_thread.is_alive():
      self._ws_thread.join(timeout=2)


  def get_orderbook(self, symbol: str) -> Orderbook | None:
    return self._orderbooks.get(symbol)


  def get_best_bid(self, symbol: str) -> OrderbookLevel | None:
    book = self._orderbooks.get(symbol)
    if not book or not book.bids:
      return None
    return book.bids[0]


  def get_best_ask(self, symbol: str) -> OrderbookLevel | None:
    book = self._orderbooks.get(symbol)
    if not book or not book.asks:
      return None
    return book.asks[0]


  def has_orderbook(self, symbol: str) -> bool:
    return symbol in self._orderbooks