import asyncio

from settings import GATE_API_KEY, GATE_API_SECRET
from src.exchanges.gate.client import GateClient


async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate:
    # methods = [m for m in dir(GateClient) if callable(getattr(GateClient, m))]
    # print(methods)

    print('-' * 20)
    
    result_1 = gate.get_price('ENA_USDT')
    print(result_1)

    print('-' * 20)

    result_2 = await gate.buy_market('ENA_USDT', 100)
    print(result_2)

    print('-' * 20)

    result_3 = await gate.get_positions()
    print(result_3)

    print('-' * 20)

    result_4 = await gate.sell_market('ENA_USDT', 100)
    print(result_4)

    print('-' * 20)



asyncio.run(main())