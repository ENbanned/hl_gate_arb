import asyncio

from settings import HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS
from src.exchanges.hyperliquid.client import HyperliquidClient


async def main():
  async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hl:
    print(123)
    result = await hl.set_leverage('ENA', 5)

    print(result)
    
    await asyncio.sleep(1000)


asyncio.run(main())
