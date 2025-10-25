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
    """=D>@<0F8O >1 >B:@KB>9 0@18B@06=>9 ?>78F88"""
    position_id: str
    symbol: str
    gate_order: Order
    hl_order: Order
    direction: SpreadDirection
    entry_spread_pct: float
    open_time: float
    mode: MinSpread


class PositionManager:
    """
    #?@02;O5B >B:@KB85<, 70:@KB85< 8 <>=8B>@8=3>< 0@18B@06=KE ?>78F89
    """

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


    async def open_position(
        self,
        symbol: str,
        direction: SpreadDirection,
        size_usdt: float,
        entry_spread_pct: float,
        mode: MinSpread
    ) -> ArbitragePosition | None:
        """
        B:@K205B 0@18B@06=CN ?>78F8N =0 >158E 18@60E ?0@0;;5;L=>

        A;8 =0 >4=>9 18@65 ?@>87>H;0 >H81:0 - 70:@K205B >B:@KBCN ?>78F8N =0 4@C3>9
        >72@0I05B None 5A;8 >B:@KB85 =5 C40;>AL
        """
        position_id = str(uuid4())

        logger.info(
            f"[POSITION] Opening {position_id[:8]} | {symbol} | "
            f"Direction: {direction.value} | Size: ${size_usdt:.2f} | "
            f"Entry spread: {entry_spread_pct:.4f}%"
        )

        try:
            # B:@K205< ?>78F88 ?0@0;;5;L=> =0 >158E 18@60E
            if direction == SpreadDirection.GATE_SHORT:
                # Gate SHORT, Hyperliquid LONG
                gate_task = self.gate.sell_market(symbol, size_usdt)
                hl_task = self.hyperliquid.buy_market(symbol, size_usdt)
            else:
                # Gate LONG, Hyperliquid SHORT
                gate_task = self.gate.buy_market(symbol, size_usdt)
                hl_task = self.hyperliquid.sell_market(symbol, size_usdt)

            results = await asyncio.gather(gate_task, hl_task, return_exceptions=True)
            gate_result, hl_result = results

            # @>25@O5< @57C;LB0BK
            gate_order = None
            hl_order = None
            error_occurred = False

            if isinstance(gate_result, Exception):
                logger.error(f"[POSITION] Gate order failed: {gate_result}")
                error_occurred = True
            else:
                gate_order = gate_result
                logger.info(
                    f"[POSITION] Gate order filled | "
                    f"Price: {gate_order.fill_price} | Size: {gate_order.size} | "
                    f"Fee: {gate_order.fee}"
                )

            if isinstance(hl_result, Exception):
                logger.error(f"[POSITION] Hyperliquid order failed: {hl_result}")
                error_occurred = True
            else:
                hl_order = hl_result
                logger.info(
                    f"[POSITION] Hyperliquid order filled | "
                    f"Price: {hl_order.fill_price} | Size: {hl_order.size} | "
                    f"Fee: {hl_order.fee}"
                )

            # A;8 >4=0 87 ?>78F89 =5 >B:@K;0AL - 70:@K205< >B:@KBCN
            if error_occurred:
                if gate_order and not hl_order:
                    logger.warning("[POSITION] Closing Gate position due to Hyperliquid error")
                    await self._close_single_position(self.gate, symbol, gate_order)
                elif hl_order and not gate_order:
                    logger.warning("[POSITION] Closing Hyperliquid position due to Gate error")
                    await self._close_single_position(self.hyperliquid, symbol, hl_order)
                return None

            # !>7405< >1J5:B ?>78F88
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
                f"[POSITION] Opened {position_id[:8]} | {symbol} | "
                f"Gate fill: {gate_order.fill_price} | HL fill: {hl_order.fill_price}"
            )

            return position

        except Exception as e:
            logger.error(f"[POSITION] Unexpected error opening position: {e}")
            return None


    async def close_position(self, position_id: str) -> tuple[Order, Order] | None:
        """
        0:@K205B 0@18B@06=CN ?>78F8N =0 >158E 18@60E ?0@0;;5;L=>

        >72@0I05B tuple(gate_order, hl_order) 8;8 None 5A;8 =5 C40;>AL
        """
        position = self.positions.get(position_id)
        if not position:
            logger.warning(f"[POSITION] Position {position_id[:8]} not found")
            return None

        logger.info(f"[POSITION] Closing {position_id[:8]} | {position.symbol}")

        try:
            # 0:@K205< ?>78F88 ?0@0;;5;L=> (>1@0B=K5 >?5@0F88)
            if position.direction == SpreadDirection.GATE_SHORT:
                # 0:@K205<: Gate BUY, Hyperliquid SELL
                gate_size = float(position.gate_order.size)
                hl_size = float(position.hl_order.size)

                gate_task = self.gate.buy_market(position.symbol, gate_size)
                hl_task = self.hyperliquid.sell_market(position.symbol, hl_size)
            else:
                # 0:@K205<: Gate SELL, Hyperliquid BUY
                gate_size = float(position.gate_order.size)
                hl_size = float(position.hl_order.size)

                gate_task = self.gate.sell_market(position.symbol, gate_size)
                hl_task = self.hyperliquid.buy_market(position.symbol, hl_size)

            results = await asyncio.gather(gate_task, hl_task, return_exceptions=True)
            gate_result, hl_result = results

            # >38@C5< @57C;LB0BK
            if isinstance(gate_result, Exception):
                logger.error(f"[POSITION] Gate close failed: {gate_result}")
            else:
                logger.info(
                    f"[POSITION] Gate closed | "
                    f"Price: {gate_result.fill_price} | Size: {gate_result.size}"
                )

            if isinstance(hl_result, Exception):
                logger.error(f"[POSITION] Hyperliquid close failed: {hl_result}")
            else:
                logger.info(
                    f"[POSITION] Hyperliquid closed | "
                    f"Price: {hl_result.fill_price} | Size: {hl_result.size}"
                )

            # #40;O5< ?>78F8N 87 A?8A:0
            del self.positions[position_id]

            if isinstance(gate_result, Exception) or isinstance(hl_result, Exception):
                return None

            logger.info(f"[POSITION] Closed {position_id[:8]} | {position.symbol}")
            return (gate_result, hl_result)

        except Exception as e:
            logger.error(f"[POSITION] Unexpected error closing position: {e}")
            return None


    async def _close_single_position(
        self,
        exchange: ExchangeClient,
        symbol: str,
        order: Order
    ):
        """0:@K205B >4=C ?>78F8N (8A?>;L7C5BAO ?@8 >H81:5 >B:@KB8O)"""
        try:
            size = float(order.size)

            if order.side == PositionSide.LONG:
                await exchange.sell_market(symbol, size)
            else:
                await exchange.buy_market(symbol, size)

            logger.info(f"[POSITION] Closed single position | {symbol} | Side: {order.side}")

        except Exception as e:
            logger.error(f"[POSITION] Failed to close single position: {e}")


    def _get_current_spread(self, position: ArbitragePosition) -> float | None:
        """>;CG05B B5:CI89 A?@54 4;O ?>78F88 87 ;>:0;L=KE F5="""
        gate_price = self.gate.price_monitor.get_price(position.symbol)
        hl_price = self.hyperliquid.price_monitor.get_price(position.symbol)

        if not gate_price or not hl_price:
            return None

        # KG8A;O5< B5:CI89 A?@54
        gate_dec = Decimal(str(gate_price))
        hl_dec = Decimal(str(hl_price))
        mid_price = (gate_dec + hl_dec) / Decimal('2')
        spread_pct = abs(gate_dec - hl_dec) / mid_price * Decimal('100')

        return float(spread_pct)


    def _check_close_conditions(self, position: ArbitragePosition) -> tuple[bool, str]:
        """
        @>25@O5B CA;>28O 70:@KB8O ?>78F88

        >72@0I05B (should_close, reason)
        """
        current_spread = self._get_current_spread(position)
        if current_spread is None:
            return False, ""

        mode = position.mode
        elapsed_minutes = (time.time() - position.open_time) / 60

        # 1. Take Profit - A?@54 A>H5;AO 4> F5;52>3> 7=0G5=8O
        if current_spread <= mode.target_spread_pct:
            return True, f"Take Profit (spread {current_spread:.4f}% <= {mode.target_spread_pct}%)"

        # 2. Stop Loss - A?@54 @0AH8@8;AO 1>;LH5 4>?CAB8<>3>
        stop_loss_threshold = position.entry_spread_pct + mode.stop_loss_pct
        if current_spread >= stop_loss_threshold:
            return True, f"Stop Loss (spread {current_spread:.4f}% >= {stop_loss_threshold:.4f}%)"

        # 3. Timeout - 2@5<O 8AB5:;> 8 A?@54 =5 4>AB83 F5;8
        if elapsed_minutes >= mode.timeout_minutes:
            return True, f"Timeout ({elapsed_minutes:.1f}m >= {mode.timeout_minutes}m, spread {current_spread:.4f}%)"

        return False, ""


    async def monitor_positions(self):
        """
        $>=>20O 7040G0 4;O <>=8B>@8=30 >B:@KBKE ?>78F89

        @>25@O5B CA;>28O 70:@KB8O :064K5 0.5 A5:C=4
        """
        self._running = True
        logger.info("[POSITION] Monitor started")

        while self._running:
            try:
                # @>25@O5< 2A5 >B:@KBK5 ?>78F88
                positions_to_close = []

                for position_id, position in list(self.positions.items()):
                    should_close, reason = self._check_close_conditions(position)

                    if should_close:
                        positions_to_close.append((position_id, reason))

                # 0:@K205< ?>78F88
                for position_id, reason in positions_to_close:
                    logger.info(f"[POSITION] Closing {position_id[:8]} | Reason: {reason}")
                    result = await self.close_position(position_id)

                    # Вызываем callback для обновления балансов
                    if result and self._on_position_closed:
                        try:
                            if asyncio.iscoroutinefunction(self._on_position_closed):
                                await self._on_position_closed()
                            else:
                                self._on_position_closed()
                        except Exception as e:
                            logger.error(f"[POSITION] Error in on_position_closed callback: {e}")

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[POSITION] Monitor error: {e}")
                await asyncio.sleep(1)

        logger.info("[POSITION] Monitor stopped")


    def start_monitor(self):
        """0?CA:05B D>=>2K9 <>=8B>@8=3 ?>78F89"""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self.monitor_positions())


    def stop_monitor(self):
        """AB0=02;8205B D>=>2K9 <>=8B>@8=3"""
        self._running = False
