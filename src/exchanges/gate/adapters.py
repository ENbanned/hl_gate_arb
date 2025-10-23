from decimal import Decimal
from typing import Any

from ..common.models import Balance, Order, OrderStatus, Position, PositionSide, SymbolInfo, FundingRate, Orderbook, Volume24h, PositionSide, OrderbookLevel


def adapt_position(raw: dict[str, Any]) -> Position | None:
size = raw.get('size', 0)
if size == 0:
return None

margin_used = Decimal(raw.get('initial_margin', '0'))
if margin_used == 0:
value = Decimal(raw.get('value', '0'))
leverage_str = raw.get('leverage', '0')
if leverage_str and leverage_str != '0':
    leverage_val = Decimal(leverage_str)
    if leverage_val > 0:
    margin_used = value / leverage_val

leverage_str = raw.get('leverage', '0')
leverage = int(leverage_str) if leverage_str and leverage_str != '0' else None

liq_price_str = raw.get('liq_price', '0')
liq_price = None
if liq_price_str and liq_price_str != '0':
liq_price = Decimal(liq_price_str)

return Position(
coin=raw['contract'].replace('_USDT', ''),
size=Decimal(str(abs(size))),
side=PositionSide.LONG if size > 0 else PositionSide.SHORT,
entry_price=Decimal(raw.get('entry_price', '0')),
mark_price=Decimal(raw.get('mark_price', '0')),
unrealized_pnl=Decimal(raw.get('unrealised_pnl', '0')),
liquidation_price=liq_price,
margin_used=margin_used,
leverage=leverage,
)


def adapt_order(raw: dict[str, Any]) -> Order:
size = raw['size']

fee_rate = Decimal(raw.get('tkfr', '0'))
fill_price = Decimal(raw['fill_price'])
fee = abs(Decimal(str(size)) * fill_price * fee_rate)

status_map = {
'finished': OrderStatus.FILLED,
'open': OrderStatus.PARTIAL,
}

return Order(
order_id=str(raw['id']),
coin=raw['contract'].replace('_USDT', ''),
size=Decimal(str(abs(size))),
side=PositionSide.LONG if size > 0 else PositionSide.SHORT,
fill_price=fill_price,
status=status_map.get(raw.get('status', 'finished'), OrderStatus.FILLED),
fee=fee,
)


def adapt_balance(raw: dict[str, Any]) -> Balance:
total = Decimal(raw.get('total', '0'))
available = Decimal(raw.get('available', '0'))

return Balance(
total=total,
available=available,
used=total - available,
)


def adapt_symbol_info(raw: dict[str, Any], symbol: str) -> SymbolInfo:
return SymbolInfo(
symbol=symbol,
max_leverage=int(raw.get('leverage_max', 1)),
sz_decimals=0,
)

def adapt_funding_rate(raw: dict[str, Any], symbol: str) -> FundingRate:
return FundingRate(
symbol=symbol,
rate=Decimal(raw['r']),
timestamp=raw['t']
)


def adapt_orderbook(raw: dict[str, Any], symbol: str) -> Orderbook:
bids = [
OrderbookLevel(price=Decimal(level['p']), size=Decimal(str(level['s'])))
for level in raw['bids']
]
asks = [
OrderbookLevel(price=Decimal(level['p']), size=Decimal(str(level['s'])))
for level in raw['asks']
]

return Orderbook(
symbol=symbol,
bids=bids,
asks=asks,
timestamp=int(raw['current'] * 1000)
)


def adapt_volume_24h(raw: dict[str, Any], symbol: str) -> Volume24h:
return Volume24h(
symbol=symbol,
base_volume=Decimal(raw['volume_24h_base']),
quote_volume=Decimal(raw['volume_24h_settle'])
)