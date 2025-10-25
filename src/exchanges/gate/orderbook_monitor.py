import asyncio
import json
import time
from collections import deque
from decimal import Decimal
from typing import Any

import websockets
from gate_api import FuturesApi
from gate_api.exceptions import GateApiException

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
        '_is_ready',
        '_ws_task',
        '_shutdown',
        '_contracts'
    )
  
    def __init__(self, settle: str, futures_api: FuturesApi) -> None:
        self.settle = settle
        self.ws_url = f'wss://fx-ws.gateio.ws/v4/ws/{settle}'
        self.futures_api = futures_api
        self._orderbooks: dict[str, Orderbook] = {}
        self._update_queues: dict[str, deque[dict[str, Any]]] = {}
        self._base_ids: dict[str, int] = {}
        self._ready = asyncio.Event()
        self._is_ready = False
        self._ws_task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()
        self._contracts: list[str] = []


    async def _handle_message(self, message: str) -> None:
        try:
            msg = json.loads(message)
            
            channel = msg.get('channel')
            event = msg.get('event')
            
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
                    await self._resync_orderbook(symbol, contract)
                    return
                
                if update_id_last < base_id + 1:
                    return
                
                self._apply_update(symbol, result)
                self._base_ids[symbol] = update_id_last
            
            elif event == 'subscribe':
                if not self._is_ready:
                    self._is_ready = True
                    self._ready.set()
        
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
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


    async def _fetch_snapshot(self, symbol: str, contract: str, max_retries: int = 5) -> None:
        for attempt in range(max_retries):
            try:
                raw = await asyncio.to_thread(
                    self.futures_api.list_futures_order_book,
                    self.settle,
                    contract,
                    limit=50,
                    with_id='true'
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
                
                return
            
            except GateApiException as ex:
                if ex.label == 'TOO_MANY_REQUESTS' and attempt < max_retries - 1:
                    reset_ts = ex.headers.get('X-Gate-RateLimit-Reset')
                    if reset_ts:
                        wait_time = int(reset_ts) - int(time.time()) + 0.1
                        if wait_time > 0:
                            print(f"[RATE LIMIT] Waiting {wait_time:.1f}s until {reset_ts}")
                            await asyncio.sleep(wait_time)
                    else:
                        await asyncio.sleep(2 ** attempt)
                else:
                    print(f"[DEBUG] Failed to fetch {symbol}: {type(ex).__name__}: {ex.message}")
                    return
            
            except Exception as e:
                print(f"[DEBUG] Failed to fetch {symbol}: {type(e).__name__}: {e}")
                return


    async def _ws_loop(self, contracts: list[str]) -> None:
        while not self._shutdown.is_set():
            try:
                async with websockets.connect(self.ws_url) as ws:
                    # Отправляем все подписки без задержки для максимальной скорости
                    for contract in contracts:
                        subscribe_msg = json.dumps({
                            'time': int(time.time()),
                            'channel': 'futures.order_book_update',
                            'event': 'subscribe',
                            'payload': [contract, '100ms', '50']
                        })
                        await ws.send(subscribe_msg)
                        await asyncio.sleep(0.1)

                    async for message in ws:
                        if self._shutdown.is_set():
                            break
                        await self._handle_message(message)
            
            except (websockets.exceptions.WebSocketException, ConnectionError, OSError):
                if not self._shutdown.is_set():
                    await asyncio.sleep(5)


    async def start(self, contracts: list[str]) -> None:
        self._contracts = contracts
        
        self._ws_task = asyncio.create_task(self._ws_loop(contracts))
        await self._ready.wait()
        
        tasks = [
            self._fetch_snapshot(contract.replace('_USDT', ''), contract)
            for contract in contracts
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)


    async def stop(self) -> None:
        self._shutdown.set()
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass


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
