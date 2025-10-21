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
  # текущие открытые позиции
  # {'marginSummary': {'accountValue': '462.860761', 'totalNtlPos': '554.70656', 'totalRawUsd': '-91.845799', 'totalMarginUsed': '27.735328'}, 'crossMarginSummary': {'accountValue': '462.860761', 'totalNtlPos': '554.70656', 'totalRawUsd': '-91.845799', 'totalMarginUsed': '27.735328'}, 'crossMaintenanceMarginUsed': '6.933832', 'withdrawable': '407.390105', 'assetPositions': [{'type': 'oneWay', 'position': {'coin': 'BTC', 'szi': '0.00496', 'leverage': {'type': 'cross', 'value': 20}, 'entryPx': '111900.0', 'positionValue': '554.70656', 'unrealizedPnl': '-0.31744', 'returnOnEquity': '-0.0114387846', 'liquidationPx': '18751.694365047', 'marginUsed': '27.735328', 'maxLeverage': 40, 'cumFunding': {'allTime': '0.0', 'sinceOpen': '0.0', 'sinceChange': '0.0'}}}], 'time': 1761076514978}


  async def all_mids(self, dex: str = "") -> Any:
    return await asyncio.to_thread(self.info.all_mids, dex)


  async def user_fills(self, address: str | None = None) -> Any:
    return await asyncio.to_thread(
      self.info.user_fills, 
      address or self.account_address
    )
  # полная история ордеров (позиций)
  # [{'coin': 'BTC', 'px': '111900.0', 'sz': '0.00496', 'side': 'B', 'time': 1761076505449, 'startPosition': '0.0', 'dir': 'Open Long', 'closedPnl': '0.0', 'hash': '0xbd64c10b31d81eb8bede042dee54c002023d00f0ccdb3d8a612d6c5df0dbf8a3', 'oid': 208552372756, 'crossed': True, 'fee': '0.24976', 'tid': 427573722877253, 'feeToken': 'USDC', 'twapId': None}, {'coin': 'ENA', 'px': '0.44336', 'sz': '200.0', 'side': 'A', 'time': 1761051392573, 'startPosition': '200.0', 'dir': 'Close Long', 'closedPnl': '-0.009', 'hash': '0x77212dfbbf91b3db789a042de991b302017a00e15a94d2ad1ae9d94e7e958dc6', 'oid': 208176168605, 'crossed': True, 'fee': '0.039902', 'tid': 976287900173452, 'feeToken': 'USDC', 'twapId': None}


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
  # {'status': 'ok', 'response': {'type': 'order', 'data': {'statuses': [{'filled': {'totalSz': '100.0', 'avgPx': '0.45985', 'oid': 208554252757}}]}}}


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
  # {'status': 'ok', 'response': {'type': 'order', 'data': {'statuses': [{'filled': {'totalSz': '100.0', 'avgPx': '0.45971', 'oid': 208554587406}}]}}}


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
  # {'status': 'ok', 'response': {'type': 'default'}}


  def get_asset_meta(self, name: str) -> dict[str, Any] | None:
    return self.assets_meta.get(name)
  # {'max_leverage': 10, 'sz_decimals': 0}


  def get_sz_decimals(self, name: str) -> int | None:
    meta = self.assets_meta.get(name)
    return meta['sz_decimals'] if meta else None
  # 5