import asyncio
from typing import Any

import gate_api
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder
from gate_api.exceptions import GateApiException


__all__ = ['GateClient']


class GateClient:
  __slots__ = (
    'api_key',
    'api_secret',
    'settle',
    'config',
    'client',
    'futures_api',
    '_shutdown'
  )
  
  def __init__(
    self, 
    api_key: str, 
    api_secret: str,
    settle: str = 'usdt',
    host: str = 'https://api.gateio.ws/api/v4'
  ):
    self.api_key = api_key
    self.api_secret = api_secret
    self.settle = settle
    
    self.config = Configuration(
      host=host,
      key=api_key,
      secret=api_secret
    )
    self.client = ApiClient(self.config)
    self.futures_api = FuturesApi(self.client)
    self._shutdown = asyncio.Event()


  async def __aenter__(self):
    await self._ensure_single_mode()
    return self


  async def __aexit__(self, exc_type, exc_val, exc_tb):
    self._shutdown.set()
    if self.client:
      self.client.close()


  async def _ensure_single_mode(self) -> None:
    try:
      account = await asyncio.to_thread(
        self.futures_api.list_futures_accounts,
        self.settle
      )
      
      if hasattr(account, 'enable_dual_mode') and account.enable_dual_mode:
        positions = await asyncio.to_thread(
          self.futures_api.list_positions,
          self.settle
        )
        
        if positions and any(p.size != 0 for p in positions):
          raise RuntimeError(
            "Cannot switch to single mode: close all positions first"
          )
        
        await asyncio.to_thread(
          self.futures_api.set_dual_mode,
          self.settle,
          False
        )
    except GateApiException as ex:
      if ex.label != "USER_NOT_FOUND":
        raise RuntimeError(f"Failed to ensure single mode: {ex.message}") from ex


  async def get_contract_info(self, contract: str) -> Any:
    try:
      return await asyncio.to_thread(
        self.futures_api.get_futures_contract,
        self.settle,
        contract
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to get contract info: {ex.message}") from ex


  async def get_positions(self) -> Any:
    try:
      return await asyncio.to_thread(
        self.futures_api.list_positions,
        self.settle
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to get positions: {ex.message}") from ex


  async def buy_market(self, contract: str, size: int) -> Any:
    order = FuturesOrder(
      contract=contract,
      size=size,
      price='0',
      tif='ioc'
    )
    
    try:
      return await asyncio.to_thread(
        self.futures_api.create_futures_order,
        self.settle,
        order
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to buy market: {ex.message}") from ex


  async def sell_market(self, contract: str, size: int) -> Any:
    order = FuturesOrder(
      contract=contract,
      size=-abs(size),
      price='0',
      tif='ioc'
    )
    
    try:
      return await asyncio.to_thread(
        self.futures_api.create_futures_order,
        self.settle,
        order
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to sell market: {ex.message}") from ex