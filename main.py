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

            # Конфигурация режима MinSpread:
            # - percentage: минимальный спред для открытия (1%)
            # - usd_size_per_pos: размер позиции в USDT ($300)
            # - target_spread_pct: целевой спред для закрытия с профитом (0.2%)
            # - stop_loss_pct: расширение спреда для стоп-лосса (0.3%)
            # - timeout_minutes: таймаут для закрытия если спред не сошелся (10 минут)
            # - min_24h_volume_usd: минимальный 24h объем для фильтрации токенов (1M USDT, 0 = без фильтрации)
            mode = MinSpread(
                percentage=1.0,
                usd_size_per_pos=300.0,
                target_spread_pct=0.2,
                stop_loss_pct=0.3,
                timeout_minutes=10.0,
                min_24h_volume_usd=1_000_000.0  # $1M 24h объем
            )

            async with Bot(mode, gate, hyperliquid) as bot:
                # Запускаем основной цикл бота
                await bot.run()
        

asyncio.run(main())