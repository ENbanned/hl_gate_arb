import asyncio
from typing import Any

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

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


  def get_price(self, coin: str) -> float | None:
    return self.price_monitor.get_price(coin)


  def get_price_unsafe(self, coin: str) -> float:
    return self.price_monitor.get_price_unsafe(coin)


  def has_price(self, coin: str) -> bool:
    return self.price_monitor.has_price(coin)


  @property
  def all_prices(self) -> dict[str, float]:
    return self.price_monitor.prices


  async def user_state(self, address: str | None = None, dex: str = "") -> Any:
    return await asyncio.to_thread(
      self.info.user_state, 
      address or self.account_address, 
      dex
    )


  async def all_mids(self, dex: str = "") -> Any:
    return await asyncio.to_thread(self.info.all_mids, dex)


  async def user_fills(self, address: str | None = None) -> Any:
    return await asyncio.to_thread(
      self.info.user_fills, 
      address or self.account_address
    )


  async def buy_market(
    self, 
    name: str, 
    sz: float, 
    px: float | None = None, 
    slippage: float = 0.05
  ) -> Any:
    return await asyncio.to_thread(
      self.exchange.market_open, 
      name, 
      True, 
      sz, 
      px, 
      slippage
    )


  async def sell_market(
    self, 
    name: str, 
    sz: float, 
    px: float | None = None, 
    slippage: float = 0.05
  ) -> Any:
    return await asyncio.to_thread(
      self.exchange.market_open, 
      name, 
      False, 
      sz, 
      px, 
      slippage
    )


  async def set_leverage(
    self, 
    name: str, 
    leverage: int, 
    is_cross: bool = False
  ) -> Any:
    return await asyncio.to_thread(
      self.exchange.update_leverage, 
      leverage, 
      name, 
      is_cross
    )


  def get_asset_meta(self, name: str) -> dict[str, Any] | None:
    return self.assets_meta.get(name)


  def get_sz_decimals(self, name: str) -> int | None:
    meta = self.assets_meta.get(name)
    return meta['sz_decimals'] if meta else None