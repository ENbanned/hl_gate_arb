import asyncio

from settings import GATE_API_KEY, GATE_API_SECRET
from src.exchanges.gate.client import GateClient


async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate:
    # methods = [m for m in dir(GateClient) if callable(getattr(GateClient, m))]
    # print(methods)

    result_1 = gate.get_price('ENA_USDT')
    print(result_1)

    result_2 = ...
    print(result_2)

    result_3 = ...
    print(result_3)

    result_4 = ...
    print(result_4)



asyncio.run(main())