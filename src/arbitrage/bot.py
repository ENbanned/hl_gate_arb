import asyncio
from decimal import Decimal

from .spread import SpreadFinder
from .models import BotMode, MinSpread, SpreadDirection
from .position_manager import PositionManager
from ..exchanges.common import ExchangeClient, Balance
from ..logger import logger


class Bot:
    """Основной класс бота для арбитража между Gate.io и Hyperliquid"""
    __slots__ = (
        'mode', 'gate', 'hyperliquid', 'finder', 'position_manager',
        'symbols', 'gate_balance', 'hyperliquid_balance', '_running',
        '_volume_cache', '_volume_update_task', '_position_semaphore'
    )

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
        self.gate_balance: Balance | None = None
        self.hyperliquid_balance: Balance | None = None
        self._running = False

        # Кэш 24h объемов для фильтрации
        self._volume_cache: dict[str, float] = {}
        self._volume_update_task: asyncio.Task | None = None

        # Семафор для открытия только 1 позиции одновременно
        self._position_semaphore = asyncio.Semaphore(1)


    async def __aenter__(self):
        """Инициализация бота при старте"""
        # Получаем общие символы
        common = self.gate.get_available_symbols() & self.hyperliquid.get_available_symbols()
        self.symbols = sorted(common)

        gate_contracts = [f'{s}_USDT' for s in self.symbols]

        logger.info(f"[BOT] Starting monitors for {len(self.symbols)} symbols")

        # Запускаем мониторы
        await asyncio.gather(
            self.gate.price_monitor.start(gate_contracts),
            self.gate.orderbook_monitor.start(gate_contracts),
            self.hyperliquid.price_monitor.start(),
            self.hyperliquid.orderbook_monitor.start(self.symbols)
        )

        # Получаем балансы
        self.gate_balance, self.hyperliquid_balance = await asyncio.gather(
            self.gate.get_balance(),
            self.hyperliquid.get_balance()
        )

        logger.info(
            f"[BOT] Balances | Gate: ${self.gate_balance.available} | "
            f"HL: ${self.hyperliquid_balance.available}"
        )

        # Устанавливаем плечи
        await self._prepare_leverages()

        # Фильтруем по объему если необходимо
        if isinstance(self.mode, MinSpread) and self.mode.min_24h_volume_usd > 0:
            await self._filter_by_volume()
            # Запускаем фоновое обновление объемов
            self._volume_update_task = asyncio.create_task(self._volume_updater())

        # Запускаем мониторинг позиций
        self.position_manager.start_monitor()

        logger.info(f"[BOT] Ready | Mode: {type(self.mode).__name__} | Symbols: {len(self.symbols)}")
        return self


    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Очистка при завершении"""
        self._running = False
        self.position_manager.stop_monitor()

        if self._volume_update_task:
            self._volume_update_task.cancel()
            try:
                await self._volume_update_task
            except asyncio.CancelledError:
                pass


    async def _prepare_leverages(self):
        """Устанавливает плечи на обеих биржах"""
        leverages = {}

        for symbol in self.symbols:
            gate_info = self.gate.get_symbol_info(symbol)
            hl_info = self.hyperliquid.get_symbol_info(symbol)
            leverages[symbol] = min(gate_info.max_leverage, hl_info.max_leverage)

        if leverages:
            await asyncio.gather(
                self.gate.set_leverages(leverages),
                self.hyperliquid.set_leverages(leverages)
            )
            logger.info(f"[BOT] Leverage set for {len(leverages)} symbols")


    async def _filter_by_volume(self):
        """Фильтрует символы по минимальному 24h объему"""
        mode: MinSpread = self.mode
        min_volume = mode.min_24h_volume_usd

        logger.info(f"[BOT] Filtering symbols by 24h volume >= ${min_volume:,.0f}")

        # Параллельно получаем объемы для всех символов
        tasks = [self.gate.get_24h_volume(symbol) for symbol in self.symbols]
        volumes = await asyncio.gather(*tasks, return_exceptions=True)

        # Фильтруем символы
        filtered_symbols = []
        for symbol, volume_result in zip(self.symbols, volumes):
            if isinstance(volume_result, Exception):
                continue

            volume_usd = float(volume_result.quote_volume)
            self._volume_cache[symbol] = volume_usd

            if volume_usd >= min_volume:
                filtered_symbols.append(symbol)

        removed = len(self.symbols) - len(filtered_symbols)
        self.symbols = filtered_symbols

        logger.info(f"[BOT] Filtered: {len(self.symbols)} symbols (removed {removed})")


    async def _volume_updater(self):
        """Фоновое обновление кэша объемов (каждые 5 минут)"""
        while self._running:
            try:
                await asyncio.sleep(300)  # 5 минут

                tasks = [self.gate.get_24h_volume(symbol) for symbol in self.symbols]
                volumes = await asyncio.gather(*tasks, return_exceptions=True)

                for symbol, volume_result in zip(self.symbols, volumes):
                    if not isinstance(volume_result, Exception):
                        self._volume_cache[symbol] = float(volume_result.quote_volume)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BOT] Volume update error: {e}")


    def _update_local_balances(self, gate_amount: Decimal, hl_amount: Decimal):
        """Обновляет локальные балансы после операций"""
        if self.gate_balance:
            self.gate_balance.available += gate_amount
        if self.hyperliquid_balance:
            self.hyperliquid_balance.available += hl_amount


    async def _refresh_balances(self):
        """Обновляет балансы с бирж"""
        self.gate_balance, self.hyperliquid_balance = await asyncio.gather(
            self.gate.get_balance(),
            self.hyperliquid.get_balance()
        )

        logger.info(
            f"[BOT] Balances refreshed | Gate: ${self.gate_balance.available} | "
            f"HL: ${self.hyperliquid_balance.available}"
        )


    async def _on_position_closed_callback(self):
        """Callback после закрытия позиции"""
        await self._refresh_balances()


    def _check_balance_available(self, size_usdt: float) -> bool:
        """Проверяет достаточно ли баланса"""
        if not self.gate_balance or not self.hyperliquid_balance:
            return False

        size_dec = Decimal(str(size_usdt))
        return (self.gate_balance.available >= size_dec and
                self.hyperliquid_balance.available >= size_dec)


    async def _handle_min_spread_mode(self, symbol: str):
        """Обработка режима MinSpread"""
        mode: MinSpread = self.mode

        # Быстрая проверка raw spread
        raw_spread = self.finder.get_raw_spread(symbol)
        if not raw_spread or float(raw_spread.spread_pct) < mode.percentage:
            return

        # Семафор: только 1 позиция открывается одновременно
        async with self._position_semaphore:
            # Проверяем, нет ли уже открытой позиции по этому символу
            if self.position_manager.has_position(symbol):
                return

            # Повторная проверка баланса внутри критической секции
            if not self._check_balance_available(mode.usd_size_per_pos):
                return

            # Вычисляем точный net spread
            net_spread = await self.finder.calculate_net_spread(symbol, mode.usd_size_per_pos)

            # Определяем лучшее направление и проверяем порог
            spread_pct = (float(net_spread.gate_short_pct) if net_spread.best_direction == SpreadDirection.GATE_SHORT
                          else float(net_spread.hl_short_pct))

            if spread_pct < mode.percentage:
                return

            logger.info(
                f"[BOT] {symbol} | Dir: {net_spread.best_direction.value} | "
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

            # Обновляем локальные балансы используя РЕАЛЬНЫЙ размер позиции
            if position:
                # Вычисляем реальный размер в USD
                gate_size_usd = float(position.gate_order.size) * float(position.gate_order.fill_price)
                hl_size_usd = float(position.hl_order.size) * float(position.hl_order.fill_price)

                # Вычитаем реальный размер + комиссии
                gate_total = Decimal(str(gate_size_usd)) + position.gate_order.fee
                hl_total = Decimal(str(hl_size_usd)) + position.hl_order.fee

                self._update_local_balances(-gate_total, -hl_total)
            else:
                # Позиция не открылась - обновляем с бирж для точности
                await self._refresh_balances()


    async def run(self):
        """Основной цикл работы бота (максимально оптимизирован)"""
        self._running = True
        logger.info("[BOT] Main loop started")

        while self._running:
            try:
                # Обрабатываем MinSpread mode
                if isinstance(self.mode, MinSpread):
                    # Проверяем все символы параллельно БЕЗ ИСКУССТВЕННОЙ ЗАДЕРЖКИ
                    tasks = [self._handle_min_spread_mode(symbol) for symbol in self.symbols]
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Минимальная задержка для предотвращения 100% CPU
                # В продакшене можно убрать или уменьшить до 0.001
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"[BOT] Main loop error: {e}")
                await asyncio.sleep(0.1)
