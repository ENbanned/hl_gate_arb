import asyncio

from src.exchanges.hyperliquid.price_monitor import HyperliquidPriceMonitor

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info


class HyperliquidClient:
  def __init__(
    self, 
    secret_key: str, 
    account_address: str, 
    base_url: str = None, 
    skip_ws: bool = True,
    meta_update_interval: int = 300
  ):
    self.secret_key = secret_key
    self.account_address = account_address
    self.meta_update_interval = meta_update_interval
    
    account: LocalAccount = eth_account.Account.from_key(self.secret_key)
    self.info = Info(base_url=base_url, skip_ws=skip_ws)
    self.exchange = Exchange(account, base_url, account_address=self.account_address)
    
    self.assets_meta: dict[str, dict] = {}
    self._update_task = None
    self._shutdown = asyncio.Event()


  async def __aenter__(self):
    await self._refresh_meta()
    self._update_task = asyncio.create_task(self._meta_updater())
    
    self.price_monitor = HyperliquidPriceMonitor()
    self.price_monitor.info = self.info
    await self.price_monitor.start()

    return self


  async def __aexit__(self, exc_type, exc_val, exc_tb):
    self._shutdown.set()
    if self._update_task:
      await self._update_task


  async def _refresh_meta(self):
    meta, _ = await asyncio.to_thread(self.info.meta_and_asset_ctxs)
    self.assets_meta = {
      asset['name']: {
        'max_leverage': asset['maxLeverage'],
        'sz_decimals': asset['szDecimals'],
      }
      for asset in meta['universe']
      if not asset.get('isDelisted', False)
    }


  async def _meta_updater(self):
    while not self._shutdown.is_set():
      try:
        await asyncio.wait_for(
          self._shutdown.wait(), 
          timeout=self.meta_update_interval
        )
      except asyncio.TimeoutError:
        await self._refresh_meta()


  async def user_state(self, address: str | None = None, dex: str = ""):
    address = address or self.account_address
    return await asyncio.to_thread(self.info.user_state, address, dex)
    # {'marginSummary': {'accountValue': '463.461863', 'totalNtlPos': '88.666', 'totalRawUsd': '374.795863', 'totalMarginUsed': '8.8666'}, 'crossMarginSummary': {'accountValue': '463.461863', 'totalNtlPos': '88.666', 'totalRawUsd': '374.795863', 'totalMarginUsed': '8.8666'}, 'crossMaintenanceMarginUsed': '4.4333', 'withdrawable': '454.595263', 'assetPositions': [{'type': 'oneWay', 'position': {'coin': 'ENA', 'szi': '200.0', 'leverage': {'type': 'cross', 'value': 10}, 'entryPx': '0.443405', 'positionValue': '88.666', 'unrealizedPnl': '-0.015', 'returnOnEquity': '-0.0016914559', 'liquidationPx': None, 'marginUsed': '8.8666', 'maxLeverage': 10, 'cumFunding': {'allTime': '0.0', 'sinceOpen': '0.0', 'sinceChange': '0.0'}}}], 'time': 1761051391167}


  async def all_mids(self, dex: str = ""):
    return await asyncio.to_thread(self.info.all_mids, dex)


  async def get_price(self, coin: str) -> float | None:
    return await self.price_monitor.get_price(coin)


  async def user_fills(self, address: str | None = None):
    address = address or self.account_address
    return await asyncio.to_thread(self.info.user_fills, address)
    # [{'coin': 'ENA', 'px': '0.44336', 'sz': '200.0', 'side': 'A', 'time': 1761051392573, 'startPosition': '200.0', 'dir': 'Close Long', 'closedPnl': '-0.009', 'hash': '0x77212dfbbf91b3db789a042de991b302017a00e15a94d2ad1ae9d94e7e958dc6', 'oid': 208176168605, 'crossed': True, 'fee': '0.039902', 'tid': 976287900173452, 'feeToken': 'USDC', 'twapId': None}]Fff


  async def buy_market(self, name: str, sz: float, px: float | None = None, slippage: float = 0.05):
    return await asyncio.to_thread(
      self.exchange.market_open, 
      name, 
      True, 
      sz, 
      px, 
      slippage
    )
    # {'status': 'ok', 'response': {'type': 'order', 'data': {'statuses': [{'filled': {'totalSz': '100.0', 'avgPx': '0.44337', 'oid': 208176159676}}]}}}


  async def sell_market(self, name: str, sz: float, px: float | None = None, slippage: float = 0.05):
    return await asyncio.to_thread(
      self.exchange.market_open, 
      name, 
      False, 
      sz, 
      px, 
      slippage
    )
    # {'status': 'ok', 'response': {'type': 'order', 'data': {'statuses': [{'filled': {'totalSz': '200.0', 'avgPx': '0.44336', 'oid': 208176168605}}]}}}


  async def set_leverage(self, name: str, leverage: int, is_cross: bool = False):
    return await asyncio.to_thread(self.exchange.update_leverage, leverage, name, is_cross)





