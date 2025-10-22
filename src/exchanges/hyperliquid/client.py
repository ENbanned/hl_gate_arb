import asyncio
import time
from typing import Any
from decimal import Decimal

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from ..common.exceptions import OrderError
from ..common.models import Balance, FundingRate, Order, Orderbook, Position, PositionSide, SymbolInfo, Volume24h
from ..common.logging import get_logger
from .adapters import adapt_balance, adapt_funding_rate, adapt_order, adapt_orderbook, adapt_position, adapt_symbol_info, adapt_volume_24h
from .price_monitor import HyperliquidPriceMonitor
from .orderbook_monitor import HyperliquidOrderbookMonitor


logger = get_logger(__name__)


class HyperliquidClient:
  __slots__ = (
    'secret_key',
    'account_address', 
    'meta_update_interval',
    'leverage_cache_ttl',
    'info',
    'exchange',
    'price_monitor',
    'orderbook_monitor',
    'assets_meta',
    '_leverage_cache',
    '_update_task',
    '_shutdown',
    '_account'
  )
  
  def __init__(
    self, 
    secret_key: str, 
    account_address: str, 
    base_url: str | None = None, 
    meta_update_interval: int = 300,
    leverage_cache_ttl: int = 3600
  ):
    self.secret_key = secret_key
    self.account_address = account_address
    self.meta_update_interval = meta_update_interval
    self.leverage_cache_ttl = leverage_cache_ttl
    
    self._account: LocalAccount = eth_account.Account.from_key(secret_key)
    self.info = Info(base_url=base_url, skip_ws=False)
    self.exchange = Exchange(
      self._account, 
      base_url, 
      account_address=account_address
    )
    
    self.assets_meta: dict[str, dict[str, Any]] = {}
    self._leverage_cache: dict[str, tuple[int, float]] = {}
    self._update_task = None
    self._shutdown = asyncio.Event()
    
    self.price_monitor = HyperliquidPriceMonitor(self.info)
    self.orderbook_monitor = HyperliquidOrderbookMonitor(self.info)


  async def __aenter__(self):
    logger.info("hyperliquid_client_starting")
    await self._refresh_meta()
    self._update_task = asyncio.create_task(self._meta_updater())
    
    symbols = list(self.assets_meta.keys())

    await self.price_monitor.start()
    await self.orderbook_monitor.start(symbols)
    logger.info("hyperliquid_client_started", symbols=len(symbols))
    return self


  async def __aexit__(self, exc_type, exc_val, exc_tb):
    logger.info("hyperliquid_client_stopping")
    self._shutdown.set()
    if self._update_task:
      await self._update_task
    
    if self.info.ws_manager:
      self.info.disconnect_websocket()
    logger.info("hyperliquid_client_stopped")


  async def _refresh_meta(self) -> None:
    try:
      meta, _ = await asyncio.to_thread(self.info.meta_and_asset_ctxs)
      
      assets = {}
      for asset in meta.get('universe', []):
        if not asset.get('isDelisted', False):
          assets[asset['name']] = {
            'name': asset['name'],
            'max_leverage': asset['maxLeverage'],
            'sz_decimals': asset['szDecimals'],
          }
      
      self.assets_meta = assets
      logger.info("hyperliquid_meta_refreshed", count=len(assets))
    except Exception as e:
      logger.error("hyperliquid_meta_refresh_error", error=str(e), exc_info=True)
      raise


  async def _meta_updater(self) -> None:
    shutdown_wait = self._shutdown.wait
    interval = self.meta_update_interval
    
    while not self._shutdown.is_set():
      try:
        await asyncio.wait_for(shutdown_wait(), timeout=interval)
      except asyncio.TimeoutError:
        await self._refresh_meta()


  async def set_leverage(self, symbol: str, leverage: int) -> None:
    cached = self._leverage_cache.get(symbol)
    if cached:
      cached_lev, cached_time = cached
      if cached_lev == leverage and (time.time() - cached_time) < self.leverage_cache_ttl:
        return
    
    try:
      await asyncio.to_thread(
        self.exchange.update_leverage,
        leverage,
        symbol,
        False
      )
      self._leverage_cache[symbol] = (leverage, time.time())
      logger.info("hyperliquid_leverage_set", symbol=symbol, leverage=leverage)
    except Exception as ex:
      logger.error("hyperliquid_leverage_error", symbol=symbol, error=str(ex))
      raise OrderError(f"Failed to set leverage for {symbol}: {str(ex)}") from ex


  async def set_leverages(self, leverages: dict[str, int]) -> None:
    tasks = [self.set_leverage(symbol, lev) for symbol, lev in leverages.items()]
    await asyncio.gather(*tasks)


  def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
    raw = self.assets_meta.get(symbol)
    if not raw:
      return None
    return adapt_symbol_info(raw)


  async def buy_market(self, symbol: str, size: float, slippage: float = 0.05) -> Order:
    try:
      raw = await asyncio.to_thread(
        self.exchange.market_open, 
        symbol, 
        True, 
        size, 
        None,
        slippage
      )
      result = adapt_order(raw, symbol, size, PositionSide.LONG)
      logger.info("hyperliquid_buy_success", symbol=symbol, size=size, fill_price=result.fill_price)
      return result
    except Exception as ex:
      logger.error("hyperliquid_buy_error", symbol=symbol, error=str(ex))
      raise OrderError(f"Failed to buy market: {str(ex)}") from ex


  async def sell_market(self, symbol: str, size: float, slippage: float = 0.05) -> Order:
    try:
      raw = await asyncio.to_thread(
        self.exchange.market_open, 
        symbol, 
        False, 
        size,
        None,
        slippage
      )
      result = adapt_order(raw, symbol, size, PositionSide.SHORT)
      logger.info("hyperliquid_sell_success", symbol=symbol, size=size, fill_price=result.fill_price)
      return result
    except Exception as ex:
      logger.error("hyperliquid_sell_error", symbol=symbol, error=str(ex))
      raise OrderError(f"Failed to sell market: {str(ex)}") from ex


  async def get_positions(self) -> list[Position]:
    try:
      state = await asyncio.to_thread(
        self.info.user_state, 
        self.account_address
      )
      
      positions = []
      asset_positions = state.get('assetPositions', [])
      
      for item in asset_positions:
        pos = adapt_position(item)
        positions.append(pos)
      
      return positions
    except Exception as ex:
      logger.error("hyperliquid_get_positions_error", error=str(ex))
      raise OrderError(f"Failed to get positions: {str(ex)}") from ex


  async def get_balance(self) -> Balance:
    try:
      state = await asyncio.to_thread(
        self.info.user_state, 
        self.account_address
      )
      return adapt_balance(state)
    except Exception as ex:
      logger.error("hyperliquid_get_balance_error", error=str(ex))
      raise OrderError(f"Failed to get balance: {str(ex)}") from ex


  async def get_funding_rate(self, symbol: str) -> FundingRate:
    try:
      meta, asset_ctxs = await asyncio.to_thread(self.info.meta_and_asset_ctxs)
      
      for i, asset in enumerate(meta.get('universe', [])):
        if asset['name'] == symbol:
          ctx = asset_ctxs[i]
          return adapt_funding_rate(ctx, symbol)
      
      raise OrderError(f"Symbol {symbol} not found")
    except Exception as ex:
      logger.error("hyperliquid_funding_rate_error", symbol=symbol, error=str(ex))
      raise OrderError(f"Failed to get funding rate for {symbol}: {str(ex)}") from ex


  async def get_orderbook(self, symbol: str, depth: int = 20) -> Orderbook:
    try:
      raw = await asyncio.to_thread(self.info.l2_snapshot, symbol)
      
      book = adapt_orderbook(raw)
      
      book.bids = book.bids[:depth]
      book.asks = book.asks[:depth]
      
      return book
    except Exception as ex:
      logger.error("hyperliquid_orderbook_error", symbol=symbol, error=str(ex))
      raise OrderError(f"Failed to get orderbook for {symbol}: {str(ex)}") from ex


  async def get_24h_volume(self, symbol: str) -> Volume24h:
    try:
      meta, asset_ctxs = await asyncio.to_thread(self.info.meta_and_asset_ctxs)
      
      for i, asset in enumerate(meta.get('universe', [])):
        if asset['name'] == symbol:
          ctx = asset_ctxs[i]
          return adapt_volume_24h(ctx, symbol)
      
      raise OrderError(f"Symbol {symbol} not found")
    except Exception as ex:
      logger.error("hyperliquid_volume_error", symbol=symbol, error=str(ex))
      raise OrderError(f"Failed to get 24h volume for {symbol}: {str(ex)}") from ex


  async def estimate_fill_price(self, symbol: str, size: float, side: PositionSide, depth: int = 100) -> Decimal:
    book = self.orderbook_monitor.get_orderbook(symbol)
    
    if not book:
      book = await self.get_orderbook(symbol, depth=min(depth, 50))
    
    levels = book.asks if side == PositionSide.LONG else book.bids
    
    if not levels:
      raise OrderError(f"No orderbook data for {symbol}")
    
    remaining = Decimal(str(abs(size)))
    total_cost = Decimal('0')
    filled = Decimal('0')
    
    for level in levels:
      if remaining <= 0:
        break
      
      fill = min(remaining, level.size)
      total_cost += fill * level.price
      filled += fill
      remaining -= fill
    
    if remaining > 0:
      last_level = levels[-1]
      slippage_factor = Decimal('1.005') if side == PositionSide.LONG else Decimal('0.995')
      extrapolated_price = last_level.price * slippage_factor
      
      total_cost += remaining * extrapolated_price
      filled += remaining
    
    return total_cost / filled