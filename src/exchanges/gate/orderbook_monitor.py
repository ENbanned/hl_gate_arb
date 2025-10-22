import asyncio
import json
import time
from collections import deque
from decimal import Decimal
from typing import Any
from enum import Enum

import websockets
from websockets.exceptions import WebSocketException
from gate_api import FuturesApi

from ..common.models import Orderbook, OrderbookLevel
from ..common.logging import get_logger
from ..common.exceptions import WebSocketError


logger = get_logger(__name__)


class BookState(Enum):
  WAITING_SNAPSHOT = 'waiting'
  SYNCING = 'syncing'
  READY = 'ready'


class GateOrderbookMonitor:
  __slots__ = (
    'settle',
    'ws_url',
    'futures_api',
    '_orderbooks',
    '_update_queues',
    '_base_ids',
    '_book_states',
    '_ready',
    '_is_ready',
    '_ws',
    '_ws_task',
    '_shutdown',
    '_reconnect_delay',
    '_max_reconnect_delay',
    '_contracts'
  )
  
  def __init__(self, settle: str, futures_api: FuturesApi):
    self.settle = settle
    self.ws_url = f'wss://fx-ws.gateio.ws/v4/ws/{settle}'
    self.futures_api = futures_api
    self._orderbooks: dict[str, Orderbook] = {}
    self._update_queues: dict[str, deque] = {}
    self._base_ids: dict[str, int] = {}
    self._book_states: dict[str, BookState] = {}
    self._ready = asyncio.Event()
    self._is_ready = False
    self._ws = None
    self._ws_task = None
    self._shutdown = asyncio.Event()
    self._reconnect_delay = 1
    self._max_reconnect_delay = 60
    self._contracts: list[str] = []


  async def _handle_message(self, msg: dict[str, Any]) -> None:
    try:
      if msg.get('channel') != 'futures.order_book_update':
        return
      
      event = msg.get('event')
      
      if event == 'update':
        result = msg.get('result')
        if not result:
          return
        
        contract = result.get('s', '')
        symbol = contract.replace('_USDT', '')
        
        update_id_first = result.get('U', 0)
        update_id_last = result.get('u', 0)
        
        state = self._book_states.get(symbol, BookState.WAITING_SNAPSHOT)
        
        if state == BookState.WAITING_SNAPSHOT:
          if symbol not in self._update_queues:
            self._update_queues[symbol] = deque(maxlen=1000)
          self._update_queues[symbol].append(result)
          return
        
        if symbol not in self._base_ids:
          logger.warning("orderbook_no_base_id", symbol=symbol)
          return
        
        base_id = self._base_ids[symbol]
        
        if update_id_first > base_id + 1:
          logger.warning("orderbook_gap_detected", symbol=symbol, expected=base_id + 1, got=update_id_first)
          await self._resync_orderbook(symbol, contract)
          return
        
        if update_id_last < base_id + 1:
          return
        
        self._apply_update(symbol, result)
        self._base_ids[symbol] = update_id_last
        self._book_states[symbol] = BookState.READY
      
      elif event == 'subscribe':
        if not self._is_ready:
          self._is_ready = True
          self._ready.set()
          logger.info("orderbook_monitor_subscribed")
    
    except (KeyError, ValueError) as e:
      logger.warning("orderbook_parse_error", error=str(e))
    except Exception as e:
      logger.error("orderbook_handle_error", error=str(e), exc_info=True)


  def _apply_update(self, symbol: str, update: dict[str, Any]) -> None:
    book = self._orderbooks.get(symbol)
    if not book:
      return
    
    bids_dict = {level.price: level for level in book.bids}
    asks_dict = {level.price: level for level in book.asks}
    
    for bid in update.get('b', []):
      price = Decimal(bid.get('p', '0'))
      size = Decimal(str(bid.get('s', '0')))
      
      if size == 0:
        bids_dict.pop(price, None)
      else:
        bids_dict[price] = OrderbookLevel(price=price, size=size)
    
    for ask in update.get('a', []):
      price = Decimal(ask.get('p', '0'))
      size = Decimal(str(ask.get('s', '0')))
      
      if size == 0:
        asks_dict.pop(price, None)
      else:
        asks_dict[price] = OrderbookLevel(price=price, size=size)
    
    book.bids = sorted(bids_dict.values(), key=lambda x: x.price, reverse=True)
    book.asks = sorted(asks_dict.values(), key=lambda x: x.price)
    book.timestamp = int(update.get('t', 0) * 1000)


  async def _resync_orderbook(self, symbol: str, contract: str) -> None:
    logger.info("orderbook_resyncing", symbol=symbol)
    self._book_states[symbol] = BookState.SYNCING
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
      base_id = snapshot.get('id', 0)
      
      bids = [
        OrderbookLevel(
          price=Decimal(level.get('p', '0')),
          size=Decimal(str(level.get('s', '0')))
        )
        for level in snapshot.get('bids', [])
      ]
      asks = [
        OrderbookLevel(
          price=Decimal(level.get('p', '0')),
          size=Decimal(str(level.get('s', '0')))
        )
        for level in snapshot.get('asks', [])
      ]
      
      self._orderbooks[symbol] = Orderbook(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp=int(snapshot.get('current', 0) * 1000)
      )
      self._base_ids[symbol] = base_id
      self._book_states[symbol] = BookState.SYNCING
      
      logger.info("orderbook_snapshot_fetched", symbol=symbol, base_id=base_id)
      
      if symbol in self._update_queues:
        queue = self._update_queues[symbol]
        
        while queue:
          update = queue[0]
          u_first = update.get('U', 0)
          u_last = update.get('u', 0)
          
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
      
      self._book_states[symbol] = BookState.READY
      logger.info("orderbook_synced", symbol=symbol)
    
    except Exception as e:
      logger.error("orderbook_snapshot_error", symbol=symbol, error=str(e), exc_info=True)
      self._book_states[symbol] = BookState.WAITING_SNAPSHOT


  async def _ws_loop(self, contracts: list[str]) -> None:
    while not self._shutdown.is_set():
      try:
        logger.info("orderbook_monitor_connecting", url=self.ws_url)
        
        async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
          self._ws = ws
          self._reconnect_delay = 1
          
          subscriptions = [[contract, '100ms', '100'] for contract in contracts]
          
          subscribe_msg = {
            'time': int(time.time()),
            'channel': 'futures.order_book_update',
            'event': 'subscribe',
            'payload': subscriptions
          }
          
          await ws.send(json.dumps(subscribe_msg))
          logger.info("orderbook_monitor_subscribe_sent", contracts=len(contracts))
          
          async for raw_msg in ws:
            if self._shutdown.is_set():
              break
            
            try:
              msg = json.loads(raw_msg)
              await self._handle_message(msg)
            except json.JSONDecodeError as e:
              logger.warning("orderbook_json_error", error=str(e))
      
      except WebSocketException as e:
        logger.error("orderbook_ws_error", error=str(e))
        if not self._shutdown.is_set():
          await asyncio.sleep(self._reconnect_delay)
          self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
      
      except Exception as e:
        logger.error("orderbook_unexpected_error", error=str(e), exc_info=True)
        if not self._shutdown.is_set():
          await asyncio.sleep(self._reconnect_delay)


  async def start(self, contracts: list[str]) -> None:
    self._contracts = contracts
    
    for contract in contracts:
      symbol = contract.replace('_USDT', '')
      self._book_states[symbol] = BookState.WAITING_SNAPSHOT
    
    self._ws_task = asyncio.create_task(self._ws_loop(contracts))
    
    try:
      await asyncio.wait_for(self._ready.wait(), timeout=30)
    except asyncio.TimeoutError:
      logger.error("orderbook_monitor_start_timeout")
      raise WebSocketError("Orderbook monitor failed to start within 30s")
    
    tasks = []
    for contract in contracts:
      symbol = contract.replace('_USDT', '')
      tasks.append(self._fetch_snapshot(symbol, contract))
    
    await asyncio.gather(*tasks, return_exceptions=True)


  async def stop(self) -> None:
    logger.info("orderbook_monitor_stopping")
    self._shutdown.set()
    
    if self._ws:
      await self._ws.close()
    
    if self._ws_task:
      try:
        await asyncio.wait_for(self._ws_task, timeout=5)
      except asyncio.TimeoutError:
        logger.warning("orderbook_monitor_stop_timeout")
        self._ws_task.cancel()
    
    logger.info("orderbook_monitor_stopped")


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
    return symbol in self._orderbooks and self._book_states.get(symbol) == BookState.READY