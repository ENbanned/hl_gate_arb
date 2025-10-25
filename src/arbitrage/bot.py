import asyncio
from decimal import Decimal

from .spread import SpreadFinder
from .models import BotMode, MinSpread, SpreadDirection
from .position_manager import PositionManager
from ..exchanges.common import ExchangeClient, Balance
from ..logger import logger


class Bot:
    """
    Основной класс бота для арбитража между Gate.io и Hyperliquid

    Отвечает только за логику арбитража - определение выгодных спредов
    и принятие решений об открытии позиций
    """

    def __init__(
        self,
        mode: BotMode,
        gate: ExchangeClient,
        hyperliquid: ExchangeClient
    ):
        self.mode = mode
        self.gate = gate
        self.hyperliquid = hyperliquid
        self.finder = SpreadFinder(gate, hyperliquid)
        self.position_manager = PositionManager(
            gate,
            hyperliquid,
            on_position_closed=self._on_position_closed_callback
        )

        self.symbols: list[str] = []

        # Локальные балансы
        self.gate_balance: Balance | None = None
        self.hyperliquid_balance: Balance | None = None

        self._running = False


    async def __aenter__(self):
        """Инициализация бота при старте"""

        # Получаем общие символы для обеих бирж
        common = self.gate.get_available_symbols() & self.hyperliquid.get_available_symbols()
        self.symbols = sorted(common)

        gate_contracts = [f'{s}_USDT' for s in self.symbols]

        logger.info(f"[BOT] Starting monitors for {len(self.symbols)} symbols...")

        # Запускаем мониторы цен и ордербуков
        await self.gate.price_monitor.start(gate_contracts)
        await self.gate.orderbook_monitor.start(gate_contracts)
        await self.hyperliquid.price_monitor.start()
        await self.hyperliquid.orderbook_monitor.start(self.symbols)

        # Получаем балансы один раз при старте
        self.gate_balance = await self.gate.get_balance()
        self.hyperliquid_balance = await self.hyperliquid.get_balance()

        logger.info(
            f"[BOT] Balances | Gate: ${self.gate_balance.available} | "
            f"Hyperliquid: ${self.hyperliquid_balance.available}"
        )

        # Устанавливаем плечи
        await self._prepare_leverages()

        # Запускаем мониторинг позиций
        self.position_manager.start_monitor()

        logger.info(f"[BOT] Ready | Mode: {type(self.mode).__name__}")
        return self


    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Очистка при завершении работы"""
        self._running = False
        self.position_manager.stop_monitor()
        logger.info("[BOT] Stopped")


    async def _prepare_leverages(self):
        """Устанавливает плечи на обеих биржах"""
        leverages = {}

        for symbol in self.symbols:
            gate_info = self.gate.get_symbol_info(symbol)
            hl_info = self.hyperliquid.get_symbol_info(symbol)

            min_leverage = min(gate_info.max_leverage, hl_info.max_leverage)
            leverages[symbol] = min_leverage

        if not leverages:
            return

        await asyncio.gather(
            self.gate.set_leverages(leverages),
            self.hyperliquid.set_leverages(leverages)
        )

        logger.info(f"[BOT] Set leverage for {len(leverages)} symbols")


    def _update_local_balances(self, gate_amount: Decimal, hl_amount: Decimal):
        """
        Обновляет локальные балансы после операций

        gate_amount: изменение баланса Gate (+ пополнение, - списание)
        hl_amount: изменение баланса Hyperliquid
        """
        if self.gate_balance:
            self.gate_balance.available += gate_amount

        if self.hyperliquid_balance:
            self.hyperliquid_balance.available += hl_amount

        logger.debug(
            f"[BOT] Updated balances | Gate: ${self.gate_balance.available} | "
            f"Hyperliquid: ${self.hyperliquid_balance.available}"
        )


    async def _refresh_balances(self):
        """Обновляет балансы с бирж (вызывается после закрытия позиций)"""
        self.gate_balance = await self.gate.get_balance()
        self.hyperliquid_balance = await self.hyperliquid.get_balance()

        logger.info(
            f"[BOT] Refreshed balances | Gate: ${self.gate_balance.available} | "
            f"Hyperliquid: ${self.hyperliquid_balance.available}"
        )


    async def _on_position_closed_callback(self):
        """Callback вызываемый после закрытия позиции для обновления балансов"""
        await self._refresh_balances()


    def _check_balance_available(self, size_usdt: float) -> bool:
        """
        Проверяет достаточно ли баланса на обеих биржах

        Учитывает, что нужно открыть позицию на каждой бирже
        """
        if not self.gate_balance or not self.hyperliquid_balance:
            return False

        size_dec = Decimal(str(size_usdt))

        # Нужен баланс на обеих биржах
        has_gate = self.gate_balance.available >= size_dec
        has_hl = self.hyperliquid_balance.available >= size_dec

        if not has_gate or not has_hl:
            logger.debug(
                f"[BOT] Insufficient balance | "
                f"Gate: ${self.gate_balance.available} (need ${size_usdt}) | "
                f"Hyperliquid: ${self.hyperliquid_balance.available} (need ${size_usdt})"
            )
            return False

        return True


    async def _handle_min_spread_mode(self, symbol: str):
        """
        Обработка режима MinSpread

        Проверяет условия открытия позиции и открывает если они выполнены
        """
        mode: MinSpread = self.mode

        # Получаем сырой спред для быстрой проверки
        raw_spread = self.finder.get_raw_spread(symbol)
        if not raw_spread:
            return

        # Проверяем минимальный порог
        if float(raw_spread.spread_pct) < mode.percentage:
            return

        # Проверяем баланс
        if not self._check_balance_available(mode.usd_size_per_pos):
            return

        # Вычисляем точный net spread с учетом комиссий
        net_spread = await self.finder.calculate_net_spread(
            symbol,
            mode.usd_size_per_pos
        )

        # Определяем лучшее направление
        if net_spread.best_direction == SpreadDirection.GATE_SHORT:
            spread_pct = float(net_spread.gate_short_pct)
        else:
            spread_pct = float(net_spread.hl_short_pct)

        # Проверяем что чистая прибыль все еще выше порога
        if spread_pct < mode.percentage:
            logger.debug(
                f"[BOT] {symbol} | Net spread {spread_pct:.4f}% < {mode.percentage}% (after fees)"
            )
            return

        logger.info(
            f"[BOT] {symbol} | Profitable spread detected | "
            f"Direction: {net_spread.best_direction.value} | "
            f"Spread: {spread_pct:.4f}% | Profit: ${net_spread.best_usd_profit}"
        )

        # Открываем позицию
        position = await self.position_manager.open_position(
            symbol=symbol,
            direction=net_spread.best_direction,
            size_usdt=mode.usd_size_per_pos,
            entry_spread_pct=spread_pct,
            mode=mode
        )

        if position:
            # Обновляем локальные балансы (списываем)
            size_dec = Decimal(str(mode.usd_size_per_pos))
            self._update_local_balances(-size_dec, -size_dec)


    async def run(self):
        """
        Основной цикл работы бота

        Постоянно проверяет спреды по всем символам и открывает позиции
        """
        self._running = True
        logger.info("[BOT] Starting main loop")

        check_interval = 0.1  # Проверка каждые 100мс

        while self._running:
            try:
                # Обрабатываем MinSpread mode
                if isinstance(self.mode, MinSpread):
                    # Проверяем все символы параллельно
                    tasks = [
                        self._handle_min_spread_mode(symbol)
                        for symbol in self.symbols
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True)

                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(f"[BOT] Error in main loop: {e}")
                await asyncio.sleep(1)

        logger.info("[BOT] Main loop stopped")


    async def update_balances_after_close(self):
        """
        Обновляет балансы после закрытия позиций

        Вызывается внешним кодом после закрытия позиции
        """
        await self._refresh_balances()
