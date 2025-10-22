import asyncio

from src.exchanges.common import ExchangeClient
from src.exchanges.common.models import PositionSide
from src.exchanges.gate import GateClient
from src.exchanges.hyperliquid import HyperliquidClient

from settings import GATE_API_KEY, GATE_API_SECRET, HYPERLIQUID_ACCOUNT_ADDRESS, HYPERLIQUID_SECRET_KEY



async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate_client:
    async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hyperliquid_client:

      gate: ExchangeClient = gate_client
      hyperliquid: ExchangeClient = hyperliquid_client

      gate_book = await gate.estimate_fill_price('ENA', 5000000, PositionSide.SHORT, depth=100)
      hyperliquid_book = await hyperliquid.estimate_fill_price('ENA', 5000000, PositionSide.SHORT, depth=100)

      print(gate_book)
      print('*'*80)
      print(hyperliquid_book)
      

asyncio.run(main())