from decimal import Decimal

from ..exchanges.common import ExchangeClient, PositionSide
from .models import RawSpread, SpreadDirection
from ..settings import GATE_TAKER_FEE, HYPERLIQUID_TAKER_FEE


class SpreadFinder:
    __slots__ = ('gate', 'hyperliquid', 'gate_taker_fee', 'hyperliquid_taker_fee')

    def __init__(
        self,
        gate: ExchangeClient,
        hyperliquid: ExchangeClient,
        gate_taker_fee: Decimal = GATE_TAKER_FEE,
        hyperliquid_taker_fee: Decimal = HYPERLIQUID_TAKER_FEE
        ):
        self.gate = gate
        self.hyperliquid = hyperliquid
        self.gate_taker_fee = gate_taker_fee
        self.hyperliquid_taker_fee = hyperliquid_taker_fee


    def get_raw_spread(self, symbol: str) -> RawSpread | None:
        gate_price = self.gate.price_monitor.get_price(symbol)
        hl_price = self.hyperliquid.price_monitor.get_price(symbol)

        if not gate_price or not hl_price:
            return None

        gate_dec = Decimal(str(gate_price))
        hl_dec = Decimal(str(hl_price))

        mid_price = (gate_dec + hl_dec) / Decimal('2')
        spread_pct = abs(gate_dec - hl_dec) / mid_price * Decimal('100')

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
        size: float
    ) -> NetSpread:
        gate_buy = await self.gate.estimate_fill_price(symbol, size, PositionSide.LONG)
        gate_sell = await self.gate.estimate_fill_price(symbol, size, PositionSide.SHORT)
        hl_buy = await self.hyperliquid.estimate_fill_price(symbol, size, PositionSide.LONG)
        hl_sell = await self.hyperliquid.estimate_fill_price(symbol, size, PositionSide.SHORT)
        
        gate_buy_with_fee = gate_buy * (Decimal('1') + self.gate_taker_fee)
        gate_sell_with_fee = gate_sell * (Decimal('1') - self.gate_taker_fee)
        hl_buy_with_fee = hl_buy * (Decimal('1') + self.hyperliquid_taker_fee)
        hl_sell_with_fee = hl_sell * (Decimal('1') - self.hyperliquid_taker_fee)
        
        size_dec = Decimal(str(size))
        
        revenue_gate_short = gate_sell_with_fee * size_dec
        cost_gate_short = hl_buy_with_fee * size_dec
        profit_gate_short = revenue_gate_short - cost_gate_short
        spread_gate_short = profit_gate_short / cost_gate_short * Decimal('100')
        
        revenue_hl_short = hl_sell_with_fee * size_dec
        cost_hl_short = gate_buy_with_fee * size_dec
        profit_hl_short = revenue_hl_short - cost_hl_short
        spread_hl_short = profit_hl_short / cost_hl_short * Decimal('100')
        
        if profit_gate_short > profit_hl_short:
            best_direction = SpreadDirection.GATE_SHORT
            best_profit = profit_gate_short
        else:
            best_direction = SpreadDirection.HL_SHORT
            best_profit = profit_hl_short
        
        return NetSpread(
            symbol=symbol,
            size=size,
            gate_short_pct=spread_gate_short,
            hl_short_pct=spread_hl_short,
            profit_gate_short=profit_gate_short,
            profit_hl_short=profit_hl_short,
            best_direction=best_direction,
            best_profit=best_profit
        )

    async def scan_opportunities(
        self, 
        symbols: list[str], 
        min_spread_pct: Decimal
    ) -> list[tuple[str, RawSpread]]:
        opportunities = []
        
        for symbol in symbols:
            raw = self.get_raw_spread(symbol)
            if raw and raw.spread_pct >= min_spread_pct:
                opportunities.append((symbol, raw))
        
        return opportunities





