import asyncio

from settings import HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS
from src.exchanges.hyperliquid.client import HyperliquidClient


async def main():
  async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS, skip_ws=False) as hl:

    result = await hl.get_price('ENA')
    print(result)
    
    await asyncio.sleep(1000)


asyncio.run(main())
