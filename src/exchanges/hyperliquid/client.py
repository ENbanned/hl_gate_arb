import asyncio
from typing import Any

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from ..common.exceptions import OrderError
from ..common.models import Balance, Order, Position, PositionSide
from .adapters import adapt_balance, adapt_order, adapt_position
from .price_monitor import HyperliquidPriceMonitor


__all__ = ['HyperliquidClient']


class HyperliquidClient:
  __slots__ = (
    'secret_key',
    'account_address', 
    'meta_update_interval',
    'info',
    'exchange',
    'price_monitor',
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
    meta_update_interval: int = 300
  ):
    self.secret_key = secret_key
    self.account_address = account_address
    self.meta_update_interval = meta_update_interval
    
    self._account: LocalAccount = eth_account.Account.from_key(secret_key)
    self.info = Info(base_url=base_url, skip_ws=False)
    self.exchange = Exchange(
      self._account, 
      base_url, 
      account_address=account_address
    )
    
    self.assets_meta: dict[str, dict[str, Any]] = {}
    self._leverage_cache: dict[str, int] = {}
    self._update_task = None
    self._shutdown = asyncio.Event()
    
    self.price_monitor = HyperliquidPriceMonitor(self.info)


  async def __aenter__(self):
    await self._refresh_meta()
    self._update_task = asyncio.create_task(self._meta_updater())
    await self.price_monitor.start()
    return self


  async def __aexit__(self, exc_type, exc_val, exc_tb):
    self._shutdown.set()
    if self._update_task:
      await self._update_task
    
    if self.info.ws_manager:
      self.info.disconnect_websocket()


  async def _refresh_meta(self) -> None:
    meta, _ = await asyncio.to_thread(self.info.meta_and_asset_ctxs)
    
    assets = {}
    for asset in meta['universe']:
      if not asset.get('isDelisted', False):
        assets[asset['name']] = {
          'max_leverage': asset['maxLeverage'],
          'sz_decimals': asset['szDecimals'],
        }
    
    self.assets_meta = assets


  async def _meta_updater(self) -> None:
    shutdown_wait = self._shutdown.wait
    interval = self.meta_update_interval
    
    while not self._shutdown.is_set():
      try:
        await asyncio.wait_for(shutdown_wait(), timeout=interval)
      except asyncio.TimeoutError:
        await self._refresh_meta()


  async def _ensure_leverage(self, symbol: str, leverage: int) -> None:
    if self._leverage_cache.get(symbol) == leverage:
      return
    
    try:
      await asyncio.to_thread(
        self.exchange.update_leverage,
        leverage,
        symbol,
        True
      )
      self._leverage_cache[symbol] = leverage
    except Exception as ex:
      raise OrderError(f"Failed to set leverage: {str(ex)}") from ex


  async def set_leverage(self, symbol: str, leverage: int) -> None:
    await self._ensure_leverage(symbol, leverage)


  async def buy_market(self, symbol: str, size: float, leverage: int | None = None, slippage: float = 0.05) -> Order:
    if leverage:
      await self._ensure_leverage(symbol, leverage)
    
    try:
      raw = await asyncio.to_thread(
        self.exchange.market_open, 
        symbol, 
        True, 
        size, 
        None,
        slippage
      )
      return adapt_order(raw, symbol, size, PositionSide.LONG)
    except Exception as ex:
      raise OrderError(f"Failed to buy market: {str(ex)}") from ex


  async def sell_market(self, symbol: str, size: float, leverage: int | None = None, slippage: float = 0.05) -> Order:
    if leverage:
      await self._ensure_leverage(symbol, leverage)
    
    try:
      raw = await asyncio.to_thread(
        self.exchange.market_open, 
        symbol, 
        False, 
        size,
        None,
        slippage
      )
      return adapt_order(raw, symbol, size, PositionSide.SHORT)
    except Exception as ex:
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
      raise OrderError(f"Failed to get positions: {str(ex)}") from ex


  async def get_balance(self) -> Balance:
    try:
      state = await asyncio.to_thread(
        self.info.user_state, 
        self.account_address
      )
      return adapt_balance(state)
    except Exception as ex:
      raise OrderError(f"Failed to get balance: {str(ex)}") from ex