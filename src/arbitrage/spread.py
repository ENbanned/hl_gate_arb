from decimal import Decimal

from ..exchanges.common import ExchangeClient, PositionSide
from .models import RawSpread, SpreadDirection, NetSpread
from ..settings import GATE_TAKER_FEE, HYPERLIQUID_TAKER_FEE


class SpreadFinder:
    """Вычисляет спреды между биржами"""
    __slots__ = ('gate', 'hyperliquid', 'gate_fee', 'hl_fee', '_one', '_hundred')

    def __init__(
        self,
        gate: ExchangeClient,
        hyperliquid: ExchangeClient,
        gate_taker_fee: Decimal = GATE_TAKER_FEE,
        hyperliquid_taker_fee: Decimal = HYPERLIQUID_TAKER_FEE
        ):
        self.gate = gate
        self.hyperliquid = hyperliquid
        self.gate_fee = gate_taker_fee
        self.hl_fee = hyperliquid_taker_fee

        # Кэшируем константы для оптимизации
        self._one = Decimal('1')
        self._hundred = Decimal('100')


    def get_raw_spread(self, symbol: str) -> RawSpread | None:
        """Вычисляет сырой спред без учета комиссий (быстрый метод)"""
        gate_price = self.gate.price_monitor.get_price(symbol)
        hl_price = self.hyperliquid.price_monitor.get_price(symbol)

        if not gate_price or not hl_price:
            return None

        gate_dec = Decimal(str(gate_price))
        hl_dec = Decimal(str(hl_price))

        # Оптимизация: используем среднее значение только для расчета процента
        mid_price = (gate_dec + hl_dec) / Decimal('2')
        spread_pct = abs(gate_dec - hl_dec) / mid_price * self._hundred

        direction = SpreadDirection.GATE_SHORT if gate_dec > hl_dec else SpreadDirection.HL_SHORT

        return RawSpread(
            spread_pct=spread_pct,
            direction=direction,
            gate_price=gate_dec,
            hl_price=hl_dec
        )


    async def calculate_net_spread(
        self,
        symbol: str,
        size_usd: float
    ) -> NetSpread:
        """Вычисляет точный спред с учетом комиссий и ликвидности

        Args:
            symbol: Символ торговой пары
            size_usd: Размер позиции в USD
        """
        # Получаем текущие цены для конвертации USD в количество монет
        gate_price = self.gate.price_monitor.get_price(symbol)
        hl_price = self.hyperliquid.price_monitor.get_price(symbol)

        if not gate_price or not hl_price:
            # Возвращаем нулевой спред если нет цен
            return NetSpread(
                symbol=symbol,
                size=size_usd,
                gate_short_pct=Decimal('0'),
                hl_short_pct=Decimal('0'),
                profit_usd_gate_short=Decimal('0'),
                profit_usd_hl_short=Decimal('0'),
                best_direction=SpreadDirection.GATE_SHORT,
                best_usd_profit=Decimal('0')
            )

        # Конвертируем USD в количество монет
        avg_price = (float(gate_price) + float(hl_price)) / 2
        size_coins = size_usd / avg_price

        # Получаем информацию о символе для правильного округления
        gate_info = self.gate.get_symbol_info(symbol)
        hl_info = self.hyperliquid.get_symbol_info(symbol)

        if not gate_info or not hl_info:
            # Возвращаем нулевой спред если нет symbol info
            return NetSpread(
                symbol=symbol,
                size=size_usd,
                gate_short_pct=Decimal('0'),
                hl_short_pct=Decimal('0'),
                profit_usd_gate_short=Decimal('0'),
                profit_usd_hl_short=Decimal('0'),
                best_direction=SpreadDirection.GATE_SHORT,
                best_usd_profit=Decimal('0')
            )

        # Округляем размер согласно требованиям бирж
        gate_size = int(size_coins)  # Gate требует целые числа
        hl_size = round(size_coins, hl_info.sz_decimals)  # HL требует sz_decimals

        # Параллельный запрос цен с учетом ликвидности (передаем округленные размеры)
        gate_buy, gate_sell, hl_buy, hl_sell = await self._estimate_all_prices(
            symbol, gate_size, hl_size
        )

        # Применяем комиссии
        gate_buy_fee = gate_buy * (self._one + self.gate_fee)
        gate_sell_fee = gate_sell * (self._one - self.gate_fee)
        hl_buy_fee = hl_buy * (self._one + self.hl_fee)
        hl_sell_fee = hl_sell * (self._one - self.hl_fee)

        gate_size_dec = Decimal(str(gate_size))
        hl_size_dec = Decimal(str(hl_size))

        # Gate SHORT, HL LONG
        revenue_gate_short = gate_sell_fee * gate_size_dec
        cost_gate_short = hl_buy_fee * hl_size_dec
        profit_gate_short = revenue_gate_short - cost_gate_short
        spread_gate_short = profit_gate_short / cost_gate_short * self._hundred

        # HL SHORT, Gate LONG
        revenue_hl_short = hl_sell_fee * hl_size_dec
        cost_hl_short = gate_buy_fee * gate_size_dec
        profit_hl_short = revenue_hl_short - cost_hl_short
        spread_hl_short = profit_hl_short / cost_hl_short * self._hundred

        # Определяем лучшее направление
        if profit_gate_short > profit_hl_short:
            best_direction = SpreadDirection.GATE_SHORT
            best_profit = profit_gate_short
        else:
            best_direction = SpreadDirection.HL_SHORT
            best_profit = profit_hl_short

        return NetSpread(
            symbol=symbol,
            size=size_usd,
            gate_short_pct=spread_gate_short,
            hl_short_pct=spread_hl_short,
            profit_usd_gate_short=profit_gate_short,
            profit_usd_hl_short=profit_hl_short,
            best_direction=best_direction,
            best_usd_profit=best_profit
        )


    async def _estimate_all_prices(
        self, symbol: str, gate_size: float, hl_size: float
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Параллельно оценивает все 4 цены для ускорения

        Args:
            symbol: Символ торговой пары
            gate_size: Размер для Gate (целое число)
            hl_size: Размер для Hyperliquid (округленное до sz_decimals)
        """
        import asyncio

        tasks = [
            self.gate.estimate_fill_price(symbol, gate_size, PositionSide.LONG),
            self.gate.estimate_fill_price(symbol, gate_size, PositionSide.SHORT),
            self.hyperliquid.estimate_fill_price(symbol, hl_size, PositionSide.LONG),
            self.hyperliquid.estimate_fill_price(symbol, hl_size, PositionSide.SHORT)
        ]

        return await asyncio.gather(*tasks)
