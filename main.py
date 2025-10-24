import asyncio

from src.exchanges.common import ExchangeClient
from src.exchanges.common.models import PositionSide
from src.exchanges.gate import GateClient
from src.exchanges.hyperliquid import HyperliquidClient
from src.arbitrage.spread import SpreadFinder
from src.arbitrage.models import BotMode, MinSpread, AnyProfit
from src.arbitrage.bot import Bot
from src.logger import logger

from src.settings import GATE_API_KEY, GATE_API_SECRET, HYPERLIQUID_ACCOUNT_ADDRESS, HYPERLIQUID_SECRET_KEY



async def main():
    async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate_client:
        async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hyperliquid_client:

            gate: ExchangeClient = gate_client
            hyperliquid: ExchangeClient = hyperliquid_client

            async with Bot(MinSpread(percentage=1), gate, hyperliquid) as bot:
                await asyncio.sleep(6)
            
                result = await bot._prepare_leverages()
                print(result)
        

asyncio.run(main())