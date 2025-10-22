from decimal import Decimal
from typing import Any

from ..common.models import Balance, Order, OrderStatus, Position, PositionSide, SymbolInfo


def adapt_position(raw: dict[str, Any]) -> Position:
  pos = raw['position']
  szi = Decimal(pos['szi'])
  
  leverage_data = pos.get('leverage')
  leverage = None
  if leverage_data and isinstance(leverage_data, dict):
    leverage = int(leverage_data.get('value', 0))
  
  return Position(
    coin=pos['coin'],
    size=abs(szi),
    side=PositionSide.LONG if szi > 0 else PositionSide.SHORT,
    entry_price=Decimal(pos['entryPx']),
    mark_price=Decimal(pos['entryPx']),
    unrealized_pnl=Decimal(pos['unrealizedPnl']),
    liquidation_price=Decimal(pos['liquidationPx']) if pos.get('liquidationPx') else None,
    margin_used=Decimal(pos['marginUsed']),
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
  
  response = raw['response']
  if response.get('type') != 'order':
    return Order(
      order_id='0',
      coin=symbol,
      size=Decimal(str(size)),
      side=side,
      fill_price=Decimal('0'),
      status=OrderStatus.REJECTED,
    )
  
  data = response['data']
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
    order_id=str(filled['oid']),
    coin=symbol,
    size=Decimal(filled['totalSz']),
    side=side,
    fill_price=Decimal(filled['avgPx']),
    status=OrderStatus.FILLED,
  )


def adapt_balance(raw: dict[str, Any]) -> Balance:
  margin = raw.get('marginSummary', {})
  
  total = Decimal(margin.get('accountValue', '0'))
  available = Decimal(raw.get('withdrawable', '0'))
  
  return Balance(
    total=total,
    available=available,
    used=total - available,
  )


def adapt_symbol_info(raw: dict[str, Any]) -> SymbolInfo:
  return SymbolInfo(
    symbol=raw['name'],
    max_leverage=int(raw['max_leverage']),
    sz_decimals=int(raw['sz_decimals']),
  )