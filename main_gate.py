import asyncio

from settings import GATE_API_KEY, GATE_API_SECRET
from src.exchanges.gate.client import GateClient


async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate:
    print(123)
    result = await gate.buy_market('ENA_USDT', 100)

    print(result)
    result = await gate.sell_market('ENA_USDT', 100)

    print(result)
    
    await asyncio.sleep(1000)


asyncio.run(main())
