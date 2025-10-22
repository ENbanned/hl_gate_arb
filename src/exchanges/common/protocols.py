from typing import Protocol, runtime_checkable

from .models import Balance, Order, Position


@runtime_checkable
class PriceProvider(Protocol):
  def get_price(self, symbol: str) -> float | None: ...
  
  def get_price_unsafe(self, symbol: str) -> float: ...
  
  def has_price(self, symbol: str) -> bool: ...
  
  @property
  def prices(self) -> dict[str, float]: ...


@runtime_checkable
class ExchangeClient(Protocol):
  price_monitor: PriceProvider
  
  async def buy_market(self, symbol: str, size: float) -> Order: ...
  
  async def sell_market(self, symbol: str, size: float) -> Order: ...
  
  async def get_positions(self) -> list[Position]: ...
  
  async def get_balance(self) -> Balance: ...