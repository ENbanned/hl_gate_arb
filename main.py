import asyncio

from src.exchanges.common import ExchangeClient
from src.exchanges.common.models import PositionSide
from src.exchanges.gate import GateClient
from src.exchanges.hyperliquid import HyperliquidClient
from src.arbitrage.spread import SpreadFinder

from src.settings import GATE_API_KEY, GATE_API_SECRET, HYPERLIQUID_ACCOUNT_ADDRESS, HYPERLIQUID_SECRET_KEY



async def main():
    async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate_client:
        async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hyperliquid_client:

            gate: ExchangeClient = gate_client
            hyperliquid: ExchangeClient = hyperliquid_client
            
            common = gate.get_available_symbols() & hyperliquid.get_available_symbols()
            symbols = sorted(common)
            contracts = [f'{s}_USDT' for s in symbols]

            print(f"Starting monitors for {len(symbols)} common symbols")

            await asyncio.sleep(6)
            
        

asyncio.run(main())