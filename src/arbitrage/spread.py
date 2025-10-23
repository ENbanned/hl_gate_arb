    from decimal import Decimal

    from ..exchanges.common import ExchangeClient, PositionSide
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


    def get_raw_spread(self, symbol: str) -> dict[str, Decimal] | None:
    gate_price = self.gate.price_monitor.get_price(symbol)
    hl_price = self.hyperliquid.price_monitor.get_price(symbol)

    if not gate_price or not hl_price:
    return None

    gate_dec = Decimal(str(gate_price))
    hl_dec = Decimal(str(hl_price))

    mid_price = (gate_dec + hl_dec) / Decimal('2')
    spread_pct = abs(gate_dec - hl_dec) / mid_price * Decimal('100')

    direction = 'gate_short' if gate_dec > hl_dec else 'hl_short'

    return {
    'spread_pct': spread_pct,
    'direction': direction,
    'gate_price': gate_dec,
    'hl_price': hl_dec
    }



    async def check_spread(self, symbol: str, size: float) -> list[dict]:

    gate_buy_price = await self.gate.estimate_fill_price(symbol, size, PositionSide.LONG)
    gate_sell_price = await self.gate.estimate_fill_price(symbol, size, PositionSide.SHORT)
    hyperliquid_buy_price = await self.hyperliquid.estimate_fill_price(symbol, size, PositionSide.LONG)
    hyperliquid_sell_price = await self.hyperliquid.estimate_fill_price(symbol, size, PositionSide.SHORT)

    # gate short -> hyperliquid long
    spread_1 = (gate_sell_price - hyperliquid_buy_price) / hyperliquid_buy_price

    # hyperliquid short -> gate long
    spread_2 = (hyperliquid_sell_price - gate_buy_price) / gate_buy_price

    total_fee = 2 * (GATE_TAKER_FEE + HYPERLIQUID_TAKER_FEE)

    net_spread_1 = spread_1 - total_fee
    net_spread_2 = spread_2 - total_fee






