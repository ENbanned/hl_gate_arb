from decimal import Decimal
from typing import Any
import time

from ..common.models import Balance, FundingRate, Order, Orderbook, OrderbookLevel, OrderStatus, Position, PositionSide, SymbolInfo, Volume24h
from ..common.utils import safe_decimal, safe_int


def adapt_position(raw: dict[str, Any]) -> Position:
  pos = raw.get('position', {})
  szi = safe_decimal(pos.get('szi'))
  
  leverage_data = pos.get('leverage')
  leverage = None
  if leverage_data and isinstance(leverage_data, dict):
    leverage = safe_int(leverage_data.get('value'))
  
  liq_price = safe_decimal(pos.get('liquidationPx'))
  
  return Position(
    coin=pos.get('coin', ''),
    size=abs(szi),
    side=PositionSide.LONG if szi > 0 else PositionSide.SHORT,
    entry_price=safe_decimal(pos.get('entryPx')),
    mark_price=safe_decimal(pos.get('entryPx')),
    unrealized_pnl=safe_decimal(pos.get('unrealizedPnl')),
    liquidation_price=liq_price if liq_price != 0 else None,
    margin_used=safe_decimal(pos.get('marginUsed')),
    leverage=leverage,
  )


def adapt_order(raw: dict[str, Any], symbol: str, size: float, side: PositionSide) -> Order:
  if raw.get('status') != 'ok':
    return Order(
      order_id='0',
      coin=symbol,
      size=Decimal(str(size)),
      side=side,
      fill_price=Decimal('0'),
      status=OrderStatus.REJECTED,
    )
  
  response = raw.get('response', {})
  if response.get('type') != 'order':
    return Order(
      order_id='0',
      coin=symbol,
      size=Decimal(str(size)),
      side=side,
      fill_price=Decimal('0'),
      status=OrderStatus.REJECTED,
    )
  
  data = response.get('data', {})
  statuses = data.get('statuses', [])
  
  if not statuses:
    return Order(
      order_id='0',
      coin=symbol,
      size=Decimal(str(size)),
      side=side,
      fill_price=Decimal('0'),
      status=OrderStatus.REJECTED,
    )
  
  first_status = statuses[0]
  filled = first_status.get('filled')
  
  if not filled:
    return Order(
      order_id='0',
      coin=symbol,
      size=Decimal(str(size)),
      side=side,
      fill_price=Decimal('0'),
      status=OrderStatus.PARTIAL,
    )
  
  return Order(
    order_id=str(filled.get('oid', '0')),
    coin=symbol,
    size=safe_decimal(filled.get('totalSz')),
    side=side,
    fill_price=safe_decimal(filled.get('avgPx')),
    status=OrderStatus.FILLED,
  )


def adapt_balance(raw: dict[str, Any]) -> Balance:
  margin = raw.get('marginSummary', {})
  
  total = safe_decimal(margin.get('accountValue'))
  available = safe_decimal(raw.get('withdrawable'))
  
  return Balance(
    total=total,
    available=available,
    used=total - available,
  )


def adapt_symbol_info(raw: dict[str, Any]) -> SymbolInfo:
  return SymbolInfo(
    symbol=raw.get('name', ''),
    max_leverage=safe_int(raw.get('max_leverage'), 1),
    sz_decimals=safe_int(raw.get('sz_decimals')),
  )


def adapt_funding_rate(raw: dict[str, Any], symbol: str) -> FundingRate:
  current_time = int(time.time())
  next_hour = ((current_time // 3600) + 1) * 3600
  
  return FundingRate(
    symbol=symbol,
    rate=safe_decimal(raw.get('funding')),
    timestamp=next_hour
  )


def adapt_orderbook(raw: dict[str, Any]) -> Orderbook:
  levels = raw.get('levels', [[], []])
  bids_raw = levels[0]
  asks_raw = levels[1]
  
  bids = [
    OrderbookLevel(price=safe_decimal(level['px']), size=safe_decimal(level['sz']))
    for level in bids_raw
  ]
  asks = [
    OrderbookLevel(price=safe_decimal(level['px']), size=safe_decimal(level['sz']))
    for level in asks_raw
  ]
  
  return Orderbook(
    symbol=raw.get('coin', ''),
    bids=bids,
    asks=asks,
    timestamp=raw.get('time', 0)
  )


def adapt_volume_24h(raw: dict[str, Any], symbol: str) -> Volume24h:
  return Volume24h(
    symbol=symbol,
    base_volume=safe_decimal(raw.get('dayBaseVlm')),
    quote_volume=safe_decimal(raw.get('dayNtlVlm'))
  )