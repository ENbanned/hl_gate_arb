import asyncio
import json
from datetime import datetime, timedelta

import gate_api
import websockets
from gate_api.exceptions import ApiException, GateApiException
from tenacity import retry, stop_after_attempt, wait_exponential

from config.constants import (
  GATE_API_URL,
  GATE_FEE_TAKER,
  GATE_WS_URL,
  MAX_RETRIES,
)
from config.settings import settings
from core.models import (
  Balance,
  ExchangeName,
  FundingRate,
  Orderbook,
  OrderbookLevel,
  PositionSnapshot,
)
from utils.logging import get_logger


log = get_logger(__name__)


class GateExchange:
  
  def __init__(self):
    self.name = ExchangeName.GATE
    
    config = gate_api.Configuration(
      host=GATE_API_URL,
      key=settings.gate_api_key,
      secret=settings.gate_api_secret,
    )
    self.api_client = gate_api.ApiClient(config)
    self.futures_api = gate_api.FuturesApi(self.api_client)
    
    self.ws: websockets.WebSocketClientProtocol | None = None
    self.orderbooks: dict[str, Orderbook] = {}
    self.funding_rates: dict[str, FundingRate] = {}
    self.contracts: dict[str, dict] = {}
    
    self.ws_task: asyncio.Task | None = None
    self.running = False
  
  
  async def connect(self):
    await self._load_contracts()
    await self._enable_dual_mode()
    self.running = True
    self.ws_task = asyncio.create_task(self._ws_handler())
    log.info("gate_connected", contracts=len(self.contracts))
  
  
  async def disconnect(self):
    self.running = False
    if self.ws:
      await self.ws.close()
    if self.ws_task:
      self.ws_task.cancel()
      try:
        await self.ws_task
      except asyncio.CancelledError:
        pass
    log.info("gate_disconnected")
  
  
  @retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
  )
  async def get_balance(self) -> Balance:
    try:
      loop = asyncio.get_event_loop()
      account = await loop.run_in_executor(
        None,
        lambda: self.futures_api.list_futures_accounts("usdt"),
      )
      
      total = float(account.total)
      available = float(account.available)
      in_positions = total - available
      
      return Balance(
        total=total,
        available=available,
        in_positions=in_positions,
      )
    except (ApiException, GateApiException) as e:
      log.error("gate_balance_error", error=str(e))
      raise
  
  
  async def get_orderbook(self, coin: str) -> Orderbook | None:
    contract = self._get_contract_name(coin)
    if not contract:
      return None
    return self.orderbooks.get(contract)
  
  
  async def get_funding_rate(self, coin: str) -> FundingRate | None:
    contract = self._get_contract_name(coin)
    if not contract:
      return None
    
    cached = self.funding_rates.get(contract)
    if cached and (datetime.now() - cached.timestamp).seconds < 300:
      return cached
    
    try:
      loop = asyncio.get_event_loop()
      ticker = await loop.run_in_executor(
        None,
        lambda: self.futures_api.list_futures_tickers("usdt", contract=contract),
      )
      
      if ticker:
        t = ticker[0]
        rate = float(t.funding_rate)
        next_time = datetime.fromtimestamp(t.funding_next_apply)
        
        funding = FundingRate(
          rate=rate,
          next_funding_time=next_time,
        )
        self.funding_rates[contract] = funding
        return funding
    except Exception as e:
      log.debug("gate_funding_error", coin=coin, error=str(e))
    
    return None
  
  
  async def get_leverage_limits(self, coin: str) -> tuple[int, int]:
    contract = self._get_contract_name(coin)
    if not contract or contract not in self.contracts:
      return (1, 1)
    
    c = self.contracts[contract]
    leverage_min = int(c.get("leverage_min", 1))
    leverage_max = int(c.get("leverage_max", 10))
    
    return (leverage_min, leverage_max)
  
  
  @retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
  )
  async def open_position(
    self,
    coin: str,
    side: str,
    size_usd: float,
    leverage: int,
  ) -> str | None:
    contract = self._get_contract_name(coin)
    if not contract:
      return None
    
    try:
      await self._set_leverage(contract, leverage)
      
      orderbook = await self.get_orderbook(coin)
      if not orderbook:
        return None
      
      if side == "long":
        price = orderbook.asks[0].price * 1.001
      else:
        price = orderbook.bids[0].price * 0.999
      
      size = int(size_usd / price)
      if size <= 0:
        return None
      
      order = gate_api.FuturesOrder(
        contract=contract,
        size=size if side == "long" else -size,
        price=str(price),
        tif="ioc",
      )
      
      loop = asyncio.get_event_loop()
      result = await loop.run_in_executor(
        None,
        lambda: self.futures_api.create_futures_order("usdt", order),
      )
      
      if result and result.id:
        log.info(
          "gate_order_placed",
          coin=coin,
          side=side,
          size=size,
          price=price,
          order_id=result.id,
        )
        return str(result.id)
    except (ApiException, GateApiException) as e:
      log.error("gate_order_error", coin=coin, error=str(e))
    
    return None
  
  
  @retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
  )
  async def close_position(self, coin: str) -> bool:
    contract = self._get_contract_name(coin)
    if not contract:
      return False
    
    try:
      position = await self.get_position(coin)
      if not position or position.size == 0:
        return True
      
      orderbook = await self.get_orderbook(coin)
      if not orderbook:
        return False
      
      if position.side == "long":
        price = orderbook.bids[0].price * 0.999
        size = -abs(int(position.size))
      else:
        price = orderbook.asks[0].price * 1.001
        size = abs(int(position.size))
      
      order = gate_api.FuturesOrder(
        contract=contract,
        size=size,
        price=str(price),
        tif="ioc",
        reduce_only=True,
      )
      
      loop = asyncio.get_event_loop()
      result = await loop.run_in_executor(
        None,
        lambda: self.futures_api.create_futures_order("usdt", order),
      )
      
      if result:
        log.info("gate_position_closed", coin=coin, order_id=result.id)
        return True
    except (ApiException, GateApiException) as e:
      log.error("gate_close_error", coin=coin, error=str(e))
    
    return False
  
  
  async def get_position(self, coin: str) -> PositionSnapshot | None:
    contract = self._get_contract_name(coin)
    if not contract:
      return None
    
    try:
      loop = asyncio.get_event_loop()
      position = await loop.run_in_executor(
        None,
        lambda: self.futures_api.get_position("usdt", contract),
      )
      
      if not position:
        return None
      
      size = float(position.size)
      if size == 0:
        return None
      
      side = "long" if size > 0 else "short"
      
      return PositionSnapshot(
        exchange=self.name,
        coin=coin,
        size=abs(size),
        side=side,
        entry_price=float(position.entry_price),
        mark_price=float(position.mark_price),
        unrealized_pnl=float(position.unrealised_pnl),
        margin_used=float(position.margin),
      )
    except (ApiException, GateApiException):
      return None
  
  
  async def get_all_positions(self) -> list[PositionSnapshot]:
    try:
      loop = asyncio.get_event_loop()
      positions = await loop.run_in_executor(
        None,
        lambda: self.futures_api.list_positions("usdt"),
      )
      
      result = []
      for p in positions:
        size = float(p.size)
        if size == 0:
          continue
        
        coin = self._contract_to_coin(p.contract)
        if not coin:
          continue
        
        side = "long" if size > 0 else "short"
        
        result.append(
          PositionSnapshot(
            exchange=self.name,
            coin=coin,
            size=abs(size),
            side=side,
            entry_price=float(p.entry_price),
            mark_price=float(p.mark_price),
            unrealized_pnl=float(p.unrealised_pnl),
            margin_used=float(p.margin),
          )
        )
      
      return result
    except (ApiException, GateApiException):
      return []
  
  
  async def _load_contracts(self):
    try:
      loop = asyncio.get_event_loop()
      contracts = await loop.run_in_executor(
        None,
        lambda: self.futures_api.list_futures_contracts("usdt"),
      )
      
      for c in contracts:
        self.contracts[c.name] = {
          "name": c.name,
          "leverage_min": c.leverage_min,
          "leverage_max": c.leverage_max,
          "order_size_min": c.order_size_min,
        }
      
      log.info("gate_contracts_loaded", count=len(self.contracts))
    except (ApiException, GateApiException) as e:
      log.error("gate_contracts_error", error=str(e))
      raise
  
  
  async def _enable_dual_mode(self):
    try:
      loop = asyncio.get_event_loop()
      await loop.run_in_executor(
        None,
        lambda: self.futures_api.update_dual_mode("usdt", True),
      )
      log.info("gate_dual_mode_enabled")
    except (ApiException, GateApiException) as e:
      if "already" not in str(e).lower():
        log.warning("gate_dual_mode_error", error=str(e))
  
  
  async def _set_leverage(self, contract: str, leverage: int):
    try:
      loop = asyncio.get_event_loop()
      await loop.run_in_executor(
        None,
        lambda: self.futures_api.update_position_leverage(
          "usdt",
          contract,
          leverage=str(leverage),
        ),
      )
    except (ApiException, GateApiException) as e:
      log.debug("gate_leverage_error", contract=contract, error=str(e))
  
  
  async def _ws_handler(self):
    while self.running:
      try:
        async with websockets.connect(GATE_WS_URL) as ws:
          self.ws = ws
          
          await self._subscribe_orderbooks(ws)
          
          async for msg in ws:
            await self._handle_ws_message(msg)
      except Exception as e:
        log.warning("gate_ws_error", error=str(e))
        await asyncio.sleep(5)
  
  
  async def _subscribe_orderbooks(self, ws: websockets.WebSocketClientProtocol):
    for contract in list(self.contracts.keys())[:100]:
      sub_msg = {
        "time": int(datetime.now().timestamp()),
        "channel": "futures.order_book_update",
        "event": "subscribe",
        "payload": [contract, "100ms", "5"],
      }
      await ws.send(json.dumps(sub_msg))
      await asyncio.sleep(0.01)
  
  
  async def _handle_ws_message(self, message: str):
    try:
      data = json.loads(message)
      
      if data.get("channel") == "futures.order_book_update":
        if data.get("event") == "update":
          await self._process_orderbook_update(data.get("result", {}))
    except Exception as e:
      log.debug("gate_ws_parse_error", error=str(e))
  
  
  async def _process_orderbook_update(self, result: dict):
    contract = result.get("c")
    if not contract:
      return
    
    asks_data = result.get("a", [])
    bids_data = result.get("b", [])
    
    asks = [
      OrderbookLevel(price=float(a["p"]), size=float(a["s"]))
      for a in asks_data[:5]
    ]
    bids = [
      OrderbookLevel(price=float(b["p"]), size=float(b["s"]))
      for b in bids_data[:5]
    ]
    
    if asks and bids:
      self.orderbooks[contract] = Orderbook(asks=asks, bids=bids)
  
  
  def _get_contract_name(self, coin: str) -> str | None:
    contract = f"{coin}_USDT"
    return contract if contract in self.contracts else None
  
  
  def _contract_to_coin(self, contract: str) -> str | None:
    if contract.endswith("_USDT"):
      return contract[:-5]
    return None