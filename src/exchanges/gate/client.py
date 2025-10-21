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
    return self


  async def __aexit__(self, exc_type, exc_val, exc_tb):
    self._shutdown.set()
    if self.client:
      self.client.close()


  async def open_long(
    self, 
    contract: str, 
    size: int, 
    price: str | None = None
  ) -> Any:
    order = FuturesOrder(
      contract=contract,
      size=size,
      price=price or '0',
      tif='ioc' if not price else 'gtc'
    )
    
    try:
      return await asyncio.to_thread(
        self.futures_api.create_futures_order,
        self.settle,
        order
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to open long: {ex.message}") from ex


  async def open_short(
    self, 
    contract: str, 
    size: int, 
    price: str | None = None
  ) -> Any:
    order = FuturesOrder(
      contract=contract,
      size=-abs(size),
      price=price or '0',
      tif='ioc' if not price else 'gtc'
    )
    
    try:
      return await asyncio.to_thread(
        self.futures_api.create_futures_order,
        self.settle,
        order
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to open short: {ex.message}") from ex


  async def close_position(
    self, 
    contract: str,
    size: int = 0
  ) -> Any:
    order = FuturesOrder(
      contract=contract,
      size=size,
      close=True if size == 0 else False,
      reduce_only=True if size != 0 else False
    )
    
    try:
      return await asyncio.to_thread(
        self.futures_api.create_futures_order,
        self.settle,
        order
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to close position: {ex.message}") from ex