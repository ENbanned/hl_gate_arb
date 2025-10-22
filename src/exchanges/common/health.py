from typing import Protocol


class HealthCheck(Protocol):
  def is_healthy(self) -> bool: ...


class MonitorHealth:
  def __init__(self, price_monitor, orderbook_monitor, required_symbols: list[str]):
    self.price = price_monitor
    self.orderbook = orderbook_monitor
    self.symbols = required_symbols


  def is_healthy(self) -> bool:
    return all(
      self.price.has_price(s) and self.orderbook.has_orderbook(s)
      for s in self.symbols
    )


  def missing_prices(self) -> list[str]:
    return [s for s in self.symbols if not self.price.has_price(s)]


  def missing_orderbooks(self) -> list[str]:
    return [s for s in self.symbols if not self.orderbook.has_orderbook(s)]