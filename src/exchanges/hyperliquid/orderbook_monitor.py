import asyncio
from decimal import Decimal
from typing import Any

from hyperliquid.info import Info

from ..common.models import Orderbook, OrderbookLevel


__all__ = ['HyperliquidOrderbookMonitor']


class HyperliquidOrderbookMonitor:
  __slots__ = ('info', '_orderbooks', '_ready', '_is_ready', '_loop')
  
  def __init__(self, info: Info) -> None:
    self.info = info
    self._orderbooks: dict[str, Orderbook] = {}
    self._ready = asyncio.Event()
    self._is_ready = False
    self._loop: asyncio.AbstractEventLoop | None = None


  def _on_book_update(self, msg: dict[str, Any]) -> None:
    if msg['channel'] != 'l2Book':
      return
    
    data = msg['data']
    symbol = data['coin']
    levels = data['levels']
    
    bids = [
      OrderbookLevel(price=Decimal(level['px']), size=Decimal(level['sz']))
      for level in levels[0]
    ]
    asks = [
      OrderbookLevel(price=Decimal(level['px']), size=Decimal(level['sz']))
      for level in levels[1]
    ]
    
    self._orderbooks[symbol] = Orderbook(
      symbol=symbol,
      bids=bids,
      asks=asks,
      timestamp=data['time']
    )
    
    if not self._is_ready and self._loop:
      self._is_ready = True
      self._loop.call_soon_threadsafe(self._ready.set)


  async def start(self, symbols: list[str]) -> None:
    self._loop = asyncio.get_running_loop()
    
    for symbol in symbols:
      self.info.subscribe({'type': 'l2Book', 'coin': symbol}, self._on_book_update)
    
    await self._ready.wait()


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