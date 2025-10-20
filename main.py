import asyncio
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from settings import HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS


class Hyperliquid:
    def __init__(self, secret_key: str, account_address: str, base_url: str = None, skip_ws: bool = True):
        self.secret_key = secret_key
        self.account_address = account_address
        
        account: LocalAccount = eth_account.Account.from_key(self.secret_key)
        self.info = Info(base_url=base_url, skip_ws=skip_ws)
        self.exchange = Exchange(account, base_url, account_address=self.account_address)

    def buy_market(self):
        print(self.exchange.market_open(name='ENA', is_buy=True, sz=100))
        # {'status': 'ok', 'response': {'type': 'order', 'data': {'statuses': [{'filled': {'totalSz': '100.0', 'avgPx': '0.45189', 'oid': 207485620565}}]}}}

    def sell_market(self):
        print(self.exchange.market_open(name='ENA', is_buy=False, sz=100))
        # {'status': 'ok', 'response': {'type': 'order', 'data': {'statuses': [{'filled': {'totalSz': '100.0', 'avgPx': '0.4517', 'oid': 207486667140}}]}}}

    def leverage(self):
        print(self.exchange.update_leverage(2, 'ASTER', False))


async def main():
    hl = Hyperliquid(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS)
    print(hl.leverage())


asyncio.run(main())



