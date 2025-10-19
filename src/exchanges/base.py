from typing import Protocol

from src.core.models import Balance, ExchangeName, OrderResult, PositionSide


class ExchangeProtocol(Protocol):
  name: ExchangeName
  
  
  async def get_balance(self) -> Balance:
    ...
  
  
  async def get_orderbook(self, coin: str) -> dict:
    ...
  
  
  async def get_leverage_limits(self, coin: str) -> tuple[int, int]:
    ...
  
  
  async def open_position(self, coin: str, side: PositionSide, size_usd: float, leverage: int) -> OrderResult:
    ...
  
  
  async def close_position(self, coin: str, side: PositionSide) -> OrderResult:
    ...
  
  
  def calculate_slippage(self, coin: str, amount_usd: float, is_buy: bool) -> float:
    ...
  
  
  async def get_funding_rate(self, coin: str) -> float:
    ...