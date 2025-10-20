from typing import Protocol

from core.models import Balance, FundingRate, Orderbook, PositionSnapshot


class ExchangeProtocol(Protocol):
  
  async def connect(self) -> None: ...
  
  
  async def disconnect(self) -> None: ...
  
  
  async def get_balance(self) -> Balance: ...
  
  
  async def get_orderbook(self, coin: str) -> Orderbook | None: ...
  
  
  async def get_funding_rate(self, coin: str) -> FundingRate | None: ...
  
  
  async def get_leverage_limits(self, coin: str) -> tuple[int, int]: ...
  
  
  async def open_position(
    self,
    coin: str,
    side: str,
    size_usd: float,
    leverage: int,
  ) -> str | None: ...
  
  
  async def close_position(self, coin: str) -> bool: ...
  
  
  async def get_position(self, coin: str) -> PositionSnapshot | None: ...
  
  
  async def get_all_positions(self) -> list[PositionSnapshot]: ...