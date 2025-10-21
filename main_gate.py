import asyncio
from settings import GATE_API_KEY, GATE_API_SECRET
from src.exchanges.gate.client import GateClient


async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate:
    await asyncio.sleep(2)
    
    print('BTC price:', gate.get_price('BTC_USDT'))
    print('ENA price:', gate.get_price('ENA_USDT'))
    print('All prices:', gate.all_prices)
    
    await asyncio.sleep(60)


asyncio.run(main())