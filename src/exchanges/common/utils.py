from decimal import Decimal
from typing import Any


def safe_decimal(value: Any, default: str = '0') -> Decimal:
  if value is None or value == '':
    return Decimal(default)
  return Decimal(str(value))


def safe_int(value: Any, default: int = 0) -> int:
  if value is None or value == '' or value == '0':
    return default
  try:
    return int(value)
  except (ValueError, TypeError):
    return default