from decimal import Decimal


def calculate_deviation(price_a: Decimal, price_b: Decimal) -> Decimal:
  avg = (price_a + price_b) / 2
  if avg == 0:
    return Decimal('0')
  return ((price_a - price_b) / avg) * 100


def calculate_spread_profit(
  entry_price_a: Decimal,
  entry_price_b: Decimal, 
  exit_price_a: Decimal,
  exit_price_b: Decimal,
  size: Decimal,
  direction_long_a: bool
) -> Decimal:
  if direction_long_a:
    pnl_a = (exit_price_a - entry_price_a) * size
    pnl_b = (entry_price_b - exit_price_b) * size
  else:
    pnl_a = (entry_price_a - exit_price_a) * size
    pnl_b = (exit_price_b - entry_price_b) * size
  
  return pnl_a + pnl_b


def calculate_total_fees(
  size: Decimal, 
  entry_price_a: Decimal,
  entry_price_b: Decimal,
  exit_price_a: Decimal,
  exit_price_b: Decimal,
  fee_rate: Decimal = Decimal('0.0006')
) -> Decimal:
  entry_fees = (size * entry_price_a + size * entry_price_b) * fee_rate
  exit_fees = (size * exit_price_a + size * exit_price_b) * fee_rate
  return entry_fees + exit_fees


def calculate_max_position_size(
  balance_a: Decimal,
  balance_b: Decimal,
  price_a: Decimal,
  price_b: Decimal,
  leverage_a: int,
  leverage_b: int,
  margin_buffer: Decimal = Decimal('0.9')
) -> Decimal:
  max_a = (balance_a * Decimal(str(leverage_a)) * margin_buffer) / price_a
  max_b = (balance_b * Decimal(str(leverage_b)) * margin_buffer) / price_b
  return min(max_a, max_b)


def calculate_roi_daily(
  estimated_profit: Decimal,
  margin_used: Decimal,
  funding_cost_daily: Decimal
) -> Decimal:
  if margin_used == 0:
    return Decimal('0')
  net_profit = estimated_profit - funding_cost_daily
  return (net_profit / margin_used) * 100


def calculate_funding_cost_daily(
  size: Decimal,
  price: Decimal,
  funding_rate: Decimal,
  periods_per_day: int = 3
) -> Decimal:
  notional = size * price
  return notional * abs(funding_rate) * Decimal(str(periods_per_day))


def calculate_breakeven_time(
  spread_pct: Decimal,
  funding_rate_daily: Decimal,
  fee_rate: Decimal = Decimal('0.0006')
) -> Decimal:
  if spread_pct <= 0:
    return Decimal('999999')
  
  total_fees_pct = fee_rate * 4 * 100
  net_spread = spread_pct - total_fees_pct
  
  if net_spread <= 0:
    return Decimal('999999')
  
  if funding_rate_daily == 0:
    return Decimal('0')
  
  return net_spread / abs(funding_rate_daily * 100)