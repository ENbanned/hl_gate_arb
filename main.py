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
        meta, _ = self.info.meta_and_asset_ctxs()
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


    def buy_market(self, name: str, sz: float):
        return self.exchange.market_open(name=name, is_buy=True, sz=sz)


    def sell_market(self, name: str, sz: float):
        return self.exchange.market_open(name=name, is_buy=False, sz=sz)


    def set_leverage(self, name: str, leverage: int, is_cross: bool = False):
        return self.exchange.update_leverage(leverage, name, is_cross)


async def main():
    async with Hyperliquid(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hl:
        print(hl.assets_meta['BTC']['max_leverage'])
        
        await asyncio.sleep(1000)


asyncio.run(main())



