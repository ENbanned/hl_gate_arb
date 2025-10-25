import asyncio
import time
from decimal import Decimal
from dataclasses import dataclass
from uuid import uuid4

from ..exchanges.common import ExchangeClient, Order, PositionSide
from .models import SpreadDirection, MinSpread
from ..logger import logger


@dataclass
class ArbitragePosition:
    """Информация об открытой арбитражной позиции"""
    position_id: str
    symbol: str
    gate_order: Order
    hl_order: Order
    direction: SpreadDirection
    entry_spread_pct: float
    open_time: float
    mode: MinSpread


class PositionManager:
    """Управляет открытием, закрытием и мониторингом арбитражных позиций"""
    __slots__ = (
        'gate', 'hyperliquid', 'positions', '_monitor_task',
        '_running', '_on_position_closed', '_check_event'
    )

    def __init__(
        self,
        gate: ExchangeClient,
        hyperliquid: ExchangeClient,
        on_position_closed: callable = None
    ):
        self.gate = gate
        self.hyperliquid = hyperliquid
        self.positions: dict[str, ArbitragePosition] = {}
        self._monitor_task: asyncio.Task | None = None
        self._running = False
        self._on_position_closed = on_position_closed
        self._check_event = asyncio.Event()


    async def open_position(
        self,
        symbol: str,
        direction: SpreadDirection,
        size_usdt: float,
        entry_spread_pct: float,
        mode: MinSpread
    ) -> ArbitragePosition | None:
        """
        Открывает арбитражную позицию на обеих биржах параллельно

        Если на одной бирже произошла ошибка - закрывает открытую позицию на другой
        """
        position_id = str(uuid4())

        logger.info(
            f"[POS OPEN] {symbol} | ID: {position_id[:8]} | Dir: {direction.value} | "
            f"Size: ${size_usdt:.2f} | Entry: {entry_spread_pct:.4f}%"
        )

        try:
            # Открываем позиции параллельно
            if direction == SpreadDirection.GATE_SHORT:
                gate_task = self.gate.sell_market(symbol, size_usdt)
                hl_task = self.hyperliquid.buy_market(symbol, size_usdt)
            else:
                gate_task = self.gate.buy_market(symbol, size_usdt)
                hl_task = self.hyperliquid.sell_market(symbol, size_usdt)

            results = await asyncio.gather(gate_task, hl_task, return_exceptions=True)
            gate_result, hl_result = results

            gate_order = None
            hl_order = None
            error_occurred = False

            if isinstance(gate_result, Exception):
                logger.error(f"[POS OPEN] Gate failed: {gate_result}")
                error_occurred = True
            else:
                gate_order = gate_result
                logger.info(
                    f"[POS OPEN] Gate filled | Price: {gate_order.fill_price} | "
                    f"Size: {gate_order.size} | Fee: {gate_order.fee}"
                )

            if isinstance(hl_result, Exception):
                logger.error(f"[POS OPEN] HL failed: {hl_result}")
                error_occurred = True
            else:
                hl_order = hl_result
                logger.info(
                    f"[POS OPEN] HL filled | Price: {hl_order.fill_price} | "
                    f"Size: {hl_order.size} | Fee: {hl_order.fee}"
                )

            # Если одна позиция не открылась - закрываем другую
            if error_occurred:
                if gate_order and not hl_order:
                    logger.warning("[POS OPEN] Closing Gate position due to HL error")
                    await self._close_single_position(self.gate, symbol, gate_order)
                elif hl_order and not gate_order:
                    logger.warning("[POS OPEN] Closing HL position due to Gate error")
                    await self._close_single_position(self.hyperliquid, symbol, hl_order)
                return None

            # Создаем объект позиции
            position = ArbitragePosition(
                position_id=position_id,
                symbol=symbol,
                gate_order=gate_order,
                hl_order=hl_order,
                direction=direction,
                entry_spread_pct=entry_spread_pct,
                open_time=time.time(),
                mode=mode
            )

            self.positions[position_id] = position

            logger.info(
                f"[POS OPEN] Success {symbol} | ID: {position_id[:8]} | "
                f"Gate: {gate_order.fill_price} | HL: {hl_order.fill_price}"
            )

            # Сигнализируем монитору о необходимости проверки
            self._check_event.set()

            return position

        except Exception as e:
            logger.error(f"[POS OPEN] Unexpected error: {e}")
            return None


    async def close_position(self, position_id: str) -> tuple[Order, Order] | None:
        """Закрывает арбитражную позицию на обеих биржах параллельно"""
        position = self.positions.get(position_id)
        if not position:
            return None

        logger.info(f"[POS CLOSE] {position.symbol} | ID: {position_id[:8]}")

        try:
            # Закрываем позиции параллельно (обратные операции)
            if position.direction == SpreadDirection.GATE_SHORT:
                gate_size = float(position.gate_order.size)
                hl_size = float(position.hl_order.size)
                gate_task = self.gate.buy_market(position.symbol, gate_size)
                hl_task = self.hyperliquid.sell_market(position.symbol, hl_size)
            else:
                gate_size = float(position.gate_order.size)
                hl_size = float(position.hl_order.size)
                gate_task = self.gate.sell_market(position.symbol, gate_size)
                hl_task = self.hyperliquid.buy_market(position.symbol, hl_size)

            results = await asyncio.gather(gate_task, hl_task, return_exceptions=True)
            gate_result, hl_result = results

            # Логируем результаты
            if isinstance(gate_result, Exception):
                logger.error(f"[POS CLOSE] Gate failed: {gate_result}")
            else:
                logger.info(
                    f"[POS CLOSE] Gate closed | Price: {gate_result.fill_price} | "
                    f"Size: {gate_result.size}"
                )

            if isinstance(hl_result, Exception):
                logger.error(f"[POS CLOSE] HL failed: {hl_result}")
            else:
                logger.info(
                    f"[POS CLOSE] HL closed | Price: {hl_result.fill_price} | "
                    f"Size: {hl_result.size}"
                )

            # Удаляем позицию из списка
            del self.positions[position_id]

            if isinstance(gate_result, Exception) or isinstance(hl_result, Exception):
                return None

            # Вычисляем PNL
            open_time_minutes = (time.time() - position.open_time) / 60
            self._log_pnl(position, gate_result, hl_result, open_time_minutes)

            return (gate_result, hl_result)

        except Exception as e:
            logger.error(f"[POS CLOSE] Unexpected error: {e}")
            return None


    def _log_pnl(
        self,
        position: ArbitragePosition,
        gate_close: Order,
        hl_close: Order,
        duration_minutes: float
    ):
        """Логирует детальную информацию о PNL позиции"""
        try:
            # Открытие
            gate_open_price = float(position.gate_order.fill_price)
            hl_open_price = float(position.hl_order.fill_price)
            gate_open_size = float(position.gate_order.size)
            hl_open_size = float(position.hl_order.size)

            # Закрытие
            gate_close_price = float(gate_close.fill_price)
            hl_close_price = float(hl_close.fill_price)
            gate_close_size = float(gate_close.size)
            hl_close_size = float(hl_close.size)

            # PNL для каждой биржи
            if position.direction == SpreadDirection.GATE_SHORT:
                # Gate: SHORT открытие, LONG закрытие
                gate_pnl = (gate_open_price - gate_close_price) * gate_open_size
                # HL: LONG открытие, SHORT закрытие
                hl_pnl = (hl_close_price - hl_open_price) * hl_open_size
            else:
                # Gate: LONG открытие, SHORT закрытие
                gate_pnl = (gate_close_price - gate_open_price) * gate_open_size
                # HL: SHORT открытие, LONG закрытие
                hl_pnl = (hl_open_price - hl_close_price) * hl_open_size

            # Комиссии
            gate_fees = float(position.gate_order.fee) + float(gate_close.fee)
            hl_fees = float(position.hl_order.fee) + float(hl_close.fee)
            total_fees = gate_fees + hl_fees

            # Итоговый PNL
            total_pnl = gate_pnl + hl_pnl - total_fees

            logger.info(
                f"[POS PNL] {position.symbol} | ID: {position.position_id[:8]} | "
                f"Duration: {duration_minutes:.1f}m | "
                f"Gate PNL: ${gate_pnl:.2f} | HL PNL: ${hl_pnl:.2f} | "
                f"Fees: ${total_fees:.2f} | Net PNL: ${total_pnl:.2f}"
            )

        except Exception as e:
            logger.error(f"[POS PNL] Failed to calculate PNL: {e}")


    async def _close_single_position(
        self,
        exchange: ExchangeClient,
        symbol: str,
        order: Order
    ):
        """Закрывает одну позицию (используется при ошибке открытия)"""
        try:
            size = float(order.size)

            if order.side == PositionSide.LONG:
                await exchange.sell_market(symbol, size)
            else:
                await exchange.buy_market(symbol, size)

        except Exception as e:
            logger.error(f"[POS CLOSE] Failed to close single position: {e}")


    def _get_current_spread(self, position: ArbitragePosition) -> float | None:
        """Получает текущий спред для позиции из локальных цен"""
        gate_price = self.gate.price_monitor.get_price(position.symbol)
        hl_price = self.hyperliquid.price_monitor.get_price(position.symbol)

        if not gate_price or not hl_price:
            return None

        # Вычисляем текущий спред
        gate_dec = Decimal(str(gate_price))
        hl_dec = Decimal(str(hl_price))
        mid_price = (gate_dec + hl_dec) / Decimal('2')
        spread_pct = abs(gate_dec - hl_dec) / mid_price * Decimal('100')

        return float(spread_pct)


    def _check_close_conditions(self, position: ArbitragePosition) -> tuple[bool, str]:
        """Проверяет условия закрытия позиции"""
        current_spread = self._get_current_spread(position)
        if current_spread is None:
            return False, ""

        mode = position.mode
        elapsed_minutes = (time.time() - position.open_time) / 60

        # Take Profit - спред сошелся до целевого значения
        if current_spread <= mode.target_spread_pct:
            return True, f"TP (spread {current_spread:.4f}% <= {mode.target_spread_pct}%)"

        # Stop Loss - спред расширился больше допустимого
        stop_loss_threshold = position.entry_spread_pct + mode.stop_loss_pct
        if current_spread >= stop_loss_threshold:
            return True, f"SL (spread {current_spread:.4f}% >= {stop_loss_threshold:.4f}%)"

        # Timeout - время истекло и спред не достиг цели
        if elapsed_minutes >= mode.timeout_minutes:
            return True, f"Timeout ({elapsed_minutes:.1f}m >= {mode.timeout_minutes}m, {current_spread:.4f}%)"

        return False, ""


    async def monitor_positions(self):
        """Фоновая задача для мониторинга открытых позиций"""
        self._running = True

        while self._running:
            try:
                # Ждем события или таймаута
                try:
                    await asyncio.wait_for(self._check_event.wait(), timeout=0.1)
                    self._check_event.clear()
                except asyncio.TimeoutError:
                    pass

                if not self.positions:
                    continue

                # Проверяем все открытые позиции
                positions_to_close = []

                for position_id, position in list(self.positions.items()):
                    should_close, reason = self._check_close_conditions(position)
                    if should_close:
                        positions_to_close.append((position_id, reason))

                # Закрываем позиции
                for position_id, reason in positions_to_close:
                    logger.info(f"[POS CLOSE] Reason: {reason}")
                    result = await self.close_position(position_id)

                    # Вызываем callback для обновления балансов
                    if result and self._on_position_closed:
                        try:
                            if asyncio.iscoroutinefunction(self._on_position_closed):
                                await self._on_position_closed()
                            else:
                                self._on_position_closed()
                        except Exception as e:
                            logger.error(f"[POS CLOSE] Callback error: {e}")

            except Exception as e:
                logger.error(f"[POS MONITOR] Error: {e}")
                await asyncio.sleep(0.1)


    def start_monitor(self):
        """Запускает фоновый мониторинг позиций"""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self.monitor_positions())


    def stop_monitor(self):
        """Останавливает фоновый мониторинг"""
        self._running = False


    def trigger_check(self):
        """Сигнализирует монитору о необходимости проверки позиций"""
        if self._check_event:
            self._check_event.set()
