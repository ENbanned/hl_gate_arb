from decimal import Decimal
from typing import Any

from ..common.models import Balance, Order, OrderStatus, Position, PositionSide, SymbolInfo, FundingRate, Orderbook, OrderbookLevel, Volume24h
from ..common.utils import safe_decimal, safe_int


def adapt_position(raw: dict[str, Any]) -> Position | None:
  size = raw.get('size', 0)
  if size == 0:
    return None
  
  margin_used = safe_decimal(raw.get('initial_margin'))
  if margin_used == 0:
    value = safe_decimal(raw.get('value'))
    leverage_val = safe_decimal(raw.get('leverage'))
    if leverage_val > 0:
      margin_used = value / leverage_val
  
  leverage = safe_int(raw.get('leverage'))
  liq_price = safe_decimal(raw.get('liq_price'))
  
  return Position(
    coin=raw['contract'].replace('_USDT', ''),
    size=Decimal(str(abs(size))),
    side=PositionSide.LONG if size > 0 else PositionSide.SHORT,
    entry_price=safe_decimal(raw.get('entry_price')),
    mark_price=safe_decimal(raw.get('mark_price')),
    unrealized_pnl=safe_decimal(raw.get('unrealised_pnl')),
    liquidation_price=liq_price if liq_price != 0 else None,
    margin_used=margin_used,
    leverage=leverage,
  )


def adapt_order(raw: dict[str, Any]) -> Order:
  size = raw['size']
  
  fee_rate = safe_decimal(raw.get('tkfr'))
  fill_price = safe_decimal(raw['fill_price'])
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
  total = safe_decimal(raw.get('total'))
  available = safe_decimal(raw.get('available'))
  
  return Balance(
    total=total,
    available=available,
    used=total - available,
  )


def adapt_symbol_info(raw: dict[str, Any], symbol: str) -> SymbolInfo:
  return SymbolInfo(
    symbol=symbol,
    max_leverage=safe_int(raw.get('leverage_max'), 1),
    sz_decimals=0,
  )


def adapt_funding_rate(raw: dict[str, Any], symbol: str) -> FundingRate:
  return FundingRate(
    symbol=symbol,
    rate=safe_decimal(raw['r']),
    timestamp=raw['t']
  )


def adapt_orderbook(raw: dict[str, Any], symbol: str) -> Orderbook:
  bids = [
    OrderbookLevel(price=safe_decimal(level['p']), size=safe_decimal(level['s']))
    for level in raw['bids']
  ]
  asks = [
    OrderbookLevel(price=safe_decimal(level['p']), size=safe_decimal(level['s']))
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
    base_volume=safe_decimal(raw['volume_24h_base']),
    quote_volume=safe_decimal(raw['volume_24h_settle'])
  )