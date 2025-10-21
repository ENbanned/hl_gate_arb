import asyncio
from decimal import Decimal
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
    'dual_mode',
    'contracts_cache_interval',
    'config',
    'client',
    'futures_api',
    'contracts_meta',
    '_update_task',
    '_shutdown'
  )
  
  def __init__(
    self, 
    api_key: str, 
    api_secret: str,
    settle: str = 'usdt',
    dual_mode: bool = False,
    host: str = 'https://api.gateio.ws/api/v4',
    contracts_cache_interval: int = 300
  ):
    self.api_key = api_key
    self.api_secret = api_secret
    self.settle = settle
    self.dual_mode = dual_mode
    self.contracts_cache_interval = contracts_cache_interval
    
    self.config = Configuration(host=host, key=api_key, secret=api_secret)
    self.client = ApiClient(self.config)
    self.futures_api = FuturesApi(self.client)
    
    self.contracts_meta: dict[str, Decimal] = {}
    self._update_task = None
    self._shutdown = asyncio.Event()


  async def __aenter__(self):
    await self._init_setup()
    return self


  async def __aexit__(self, exc_type, exc_val, exc_tb):
    self._shutdown.set()
    if self._update_task:
      await self._update_task
    if self.client:
      self.client.close()


  async def _init_setup(self) -> None:
    await self._refresh_contracts()
    await self._set_position_mode()
    self._update_task = asyncio.create_task(self._contracts_updater())


  async def _refresh_contracts(self) -> None:
    contracts = await asyncio.to_thread(
      self.futures_api.list_futures_contracts,
      self.settle
    )
    
    cache = {}
    for contract in contracts:
      if hasattr(contract, 'quanto_multiplier') and contract.quanto_multiplier:
        cache[contract.name] = Decimal(contract.quanto_multiplier)
    
    self.contracts_meta = cache


  async def _set_position_mode(self) -> None:
    try:
      account = await asyncio.to_thread(
        self.futures_api.list_futures_accounts,
        self.settle
      )
      
      current_dual = getattr(account, 'in_dual_mode', False) or getattr(account, 'enable_new_dual_mode', False)
      
      if current_dual != self.dual_mode:
        positions = await asyncio.to_thread(
          self.futures_api.list_positions,
          self.settle
        )
        
        if positions and any(p.size != 0 for p in positions):
          raise RuntimeError(
            f"Cannot switch to {'dual' if self.dual_mode else 'single'} mode: close all positions first"
          )
        
        await asyncio.to_thread(
          self.futures_api.set_dual_mode,
          self.settle,
          self.dual_mode
        )
    except GateApiException as ex:
      if ex.label != "USER_NOT_FOUND":
        raise RuntimeError(f"Failed to set position mode: {ex.message}") from ex


  async def _contracts_updater(self) -> None:
    while not self._shutdown.is_set():
      try:
        await asyncio.wait_for(
          self._shutdown.wait(),
          timeout=self.contracts_cache_interval
        )
      except asyncio.TimeoutError:
        await self._refresh_contracts()


  def _tokens_to_contracts(self, contract: str, amount: float) -> int:
    multiplier = self.contracts_meta.get(contract)
    if not multiplier:
      raise ValueError(f"Contract {contract} not found in cache")
    return int(Decimal(str(amount)) / multiplier)


  def _contracts_to_tokens(self, contract: str, contracts: int) -> float:
    multiplier = self.contracts_meta.get(contract)
    if not multiplier:
      raise ValueError(f"Contract {contract} not found in cache")
    return float(Decimal(str(contracts)) * multiplier)


  async def buy_market(self, contract: str, amount: float) -> Any:
    size = self._tokens_to_contracts(contract, amount)
    
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


  async def sell_market(self, contract: str, amount: float) -> Any:
    size = self._tokens_to_contracts(contract, amount)
    
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


  async def get_positions(self) -> Any:
    try:
      return await asyncio.to_thread(
        self.futures_api.list_positions,
        self.settle
      )
    except GateApiException as ex:
      raise RuntimeError(f"Failed to get positions: {ex.message}") from ex


  def get_multiplier(self, contract: str) -> float:
    multiplier = self.contracts_meta.get(contract)
    if not multiplier:
      raise ValueError(f"Contract {contract} not found in cache")
    return float(multiplier)