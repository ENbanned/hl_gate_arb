import asyncio

from src.exchanges.common import ExchangeClient
from src.exchanges.gate import GateClient
from src.exchanges.hyperliquid import HyperliquidClient

from settings import GATE_API_KEY, GATE_API_SECRET, HYPERLIQUID_ACCOUNT_ADDRESS, HYPERLIQUID_SECRET_KEY



async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate_client:
    async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hyperliquid_client:

      gate: ExchangeClient = gate_client
      hyperliquid: ExchangeClient = hyperliquid_client

      gate_book = await gate.get_orderbook('ENA')
      hyperliquid_book = await hyperliquid.get_orderbook('ENA')

      print(gate_book)
      

asyncio.run(main())