import asyncio
from decimal import Decimal

from ..common.models import Orderbook, OrderbookLevel
from ..common.logging import get_logger


logger = get_logger(__name__)


class HyperliquidOrderbookMonitor:
  __slots__ = ('info', '_orderbooks', '_ready', '_is_ready')
  
  def __init__(self, info):
    self.info = info
    self._orderbooks: dict[str, Orderbook] = {}
    self._ready = asyncio.Event()
    self._is_ready = False


  def _on_book_update(self, msg: dict) -> None:
    try:
      if msg.get('channel') != 'l2Book':
        return
      
      data = msg.get('data', {})
      symbol = data.get('coin', '')
      levels = data.get('levels', [[], []])
      
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
        timestamp=data.get('time', 0)
      )
      
      if not self._is_ready:
        self._is_ready = True
        self._ready.set()
        logger.info("hyperliquid_orderbook_monitor_ready")
    
    except (KeyError, ValueError, TypeError) as e:
      logger.warning("hyperliquid_orderbook_parse_error", error=str(e))
    except Exception as e:
      logger.error("hyperliquid_orderbook_error", error=str(e), exc_info=True)


  async def start(self, symbols: list[str]) -> None:
    logger.info("hyperliquid_orderbook_monitor_starting", symbols=len(symbols))
    
    for symbol in symbols:
      self.info.subscribe({'type': 'l2Book', 'coin': symbol}, self._on_book_update)
    
    try:
      await asyncio.wait_for(self._ready.wait(), timeout=30)
    except asyncio.TimeoutError:
      logger.error("hyperliquid_orderbook_monitor_timeout")
      raise


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