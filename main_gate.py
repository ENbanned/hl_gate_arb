import asyncio

from settings import GATE_API_KEY, GATE_API_SECRET
from src.exchanges.gate.client import GateClient


async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate:
    
    result = await gate.buy_market('XPL_USDT', 100)
    print(result)



asyncio.run(main())