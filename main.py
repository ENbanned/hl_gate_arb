import asyncio
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from settings import HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS


class Hyperliquid:
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
    return self


  async def __aexit__(self, exc_type, exc_val, exc_tb):
    self._shutdown.set()
    if self._update_task:
      await self._update_task


  async def _refresh_meta(self):
    meta, _ = await asyncio.to_thread(self.info.meta_and_asset_ctxs)
    print(meta)
    self.assets_meta = {
      asset['name']: {
        'max_leverage': asset['maxLeverage'],
        'sz_decimals': asset['szDecimals'],
        'only_isolated': asset['onlyIsolated']
      }
      for asset in meta['universe']
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


  async def open_orders(self, address: str | None = None, dex: str = ""):
    address = address or self.account_address
    return await asyncio.to_thread(self.info.open_orders, address, dex)


  async def all_mids(self, dex: str = ""):
    return await asyncio.to_thread(self.info.all_mids, dex)


  async def user_fills(self, address: str | None = None):
    address = address or self.account_address
    return await asyncio.to_thread(self.info.user_fills, address)


  async def buy_market(self, name: str, sz: float, px: float | None = None, slippage: float = 0.05):
    return await asyncio.to_thread(
      self.exchange.market_open, 
      name, 
      True, 
      sz, 
      px, 
      slippage
    )


  async def sell_market(self, name: str, sz: float, px: float | None = None, slippage: float = 0.05):
    return await asyncio.to_thread(
      self.exchange.market_open, 
      name, 
      False, 
      sz, 
      px, 
      slippage
    )


  async def market_close(self, name: str, sz: float | None = None, px: float | None = None, slippage: float = 0.05):
    return await asyncio.to_thread(
      self.exchange.market_close,
      name,
      sz,
      px,
      slippage
    )


  async def set_leverage(self, name: str, leverage: int, is_cross: bool = False):
    return await asyncio.to_thread(self.exchange.update_leverage, leverage, name, is_cross)


async def main():
  async with Hyperliquid(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hl:
    print(hl.assets_meta['BTC']['max_leverage'])
    
    result = await hl.buy_market('ENA', 100)
    print(result)
    
    state = await hl.user_state()
    print(state)
    
    await asyncio.sleep(1000)


asyncio.run(main())



