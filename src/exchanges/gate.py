import asyncio
from datetime import datetime, UTC

import gate_api
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.models import Balance, ExchangeName, OrderResult, PositionSide
from src.utils.logging import get_logger


log = get_logger(__name__)


class GateExchange:
  
  def __init__(self, api_key: str, api_secret: str, settle: str = "usdt"):
    self.name = ExchangeName.GATE
    self.settle = settle
    
    config = Configuration(
      host="https://api.gateio.ws/api/v4",
      key=api_key,
      secret=api_secret
    )
    
    client = ApiClient(config)
    self.api = FuturesApi(client)
    
    self.orderbooks: dict[str, dict] = {}
    self._coins: list[str] = []
    self._contracts_cache: dict[str, any] = {}
    self._dual_mode_enabled = False


  async def __aenter__(self):
    contracts = await asyncio.to_thread(self.api.list_futures_contracts, self.settle)
    
    for c in contracts:
      if c.name.endswith("_USDT"):
        coin = c.name.replace("_USDT", "")
        self._coins.append(coin)
        self._contracts_cache[coin] = c
    
    await self._enable_dual_mode()
    
    asyncio.create_task(self._update_orderbooks_loop())
    log.info("gate_started", coins_count=len(self._coins))
    return self


  async def __aexit__(self, exc_type, exc, tb):
    pass


  async def _enable_dual_mode(self):
    try:
      account = await asyncio.to_thread(self.api.list_futures_accounts, self.settle)
      
      if not account.in_dual_mode:
        positions = await asyncio.to_thread(self.api.list_positions, self.settle)
        
        if any(float(p.size) != 0 for p in positions):
          log.error("dual_mode_enable_failed_has_positions")
          raise RuntimeError("Cannot enable dual mode - close all positions first")
        
        await asyncio.to_thread(self.api.set_dual_mode, self.settle, True)
        self._dual_mode_enabled = True
        log.info("gate_dual_mode_enabled")
      else:
        self._dual_mode_enabled = True
        log.info("gate_dual_mode_already_enabled")
    
    except Exception as e:
      log.error("dual_mode_enable_error", error=str(e), exc_info=True)
      raise


  async def _update_orderbooks_loop(self):
    while True:
      for coin in self._coins:
        try:
          contract = f"{coin}_USDT"
          book = await self._fetch_orderbook(contract)
          self.orderbooks[coin] = book
        except Exception as e:
          log.debug("gate_orderbook_fetch_failed", coin=coin, error=str(e))
          continue
      
      await asyncio.sleep(0.5)


  async def _fetch_orderbook(self, contract: str) -> dict:
    book = await asyncio.to_thread(
      self.api.list_futures_order_book,
      self.settle,
      contract,
      limit=50
    )
    
    bids = [{"px": item.p, "sz": item.s} for item in book.bids]
    asks = [{"px": item.p, "sz": item.s} for item in book.asks]
    
    return {
      "levels": [bids, asks],
      "timestamp": datetime.now(UTC)
    }


  async def get_balance(self) -> Balance:
    account = await asyncio.to_thread(
      self.api.list_futures_accounts,
      self.settle
    )
    
    return Balance(
      exchange=self.name,
      account_value=float(account.total or 0),
      available=float(account.available or 0),
      total_margin_used=float(account.position_margin or 0) + float(account.order_margin or 0),
      unrealised_pnl=float(account.unrealised_pnl or 0)
    )


  async def get_orderbook(self, coin: str) -> dict:
    return self.orderbooks.get(coin, {})


  async def get_leverage_limits(self, coin: str) -> tuple[int, int]:
    contract = self._contracts_cache.get(coin)
    if contract:
      return (int(contract.leverage_min), int(contract.leverage_max))
    return (1, 1)


  async def get_funding_rate(self, coin: str) -> float:
    try:
      contract = f"{coin}_USDT"
      tickers = await asyncio.to_thread(self.api.list_futures_tickers, self.settle, contract=contract)
      if tickers and len(tickers) > 0:
        return float(tickers[0].funding_rate or 0.0)
    except Exception as e:
      log.debug("gate_funding_rate_error", coin=coin, error=str(e))
    return 0.0


  def calculate_slippage(self, coin: str, amount_usd: float, is_buy: bool) -> float:
    if coin not in self.orderbooks or not self.orderbooks[coin]:
      return 0.0
    
    book = self.orderbooks[coin]
    levels = book["levels"][1 if is_buy else 0]
    
    if not levels:
      return 0.0
    
    best_price = float(levels[0]["px"])
    remaining = amount_usd
    total_cost = 0.0
    total_size = 0.0
    
    for level in levels:
      price = float(level["px"])
      size = float(level["sz"])
      
      level_usd = price * size
      if remaining >= level_usd:
        total_cost += level_usd
        total_size += size
        remaining -= level_usd
      else:
        partial_size = remaining / price
        total_cost += remaining
        total_size += partial_size
        remaining = 0
      
      if remaining <= 0:
        break
    
    if total_size == 0:
      return 0.0
    
    avg_price = total_cost / total_size
    slippage_pct = abs((avg_price - best_price) / best_price) * 100
    
    return slippage_pct

  @retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
  )
  async def open_position(
    self, 
    coin: str, 
    side: PositionSide, 
    size_usd: float, 
    leverage: int
  ) -> OrderResult:
    try:
      contract = f"{coin}_USDT"
      
      await asyncio.to_thread(
        self.api.update_dual_mode_position_leverage,
        self.settle,
        contract,
        str(leverage)
      )
      
      book = self.orderbooks.get(coin)
      if not book:
        return OrderResult(
          exchange=self.name,
          coin=coin,
          side=side,
          size=0,
          executed_price=None,
          success=False,
          error="orderbook_not_available"
        )
      
      price = float(book["levels"][1 if side == PositionSide.LONG else 0][0]["px"])
      size_contracts = int((size_usd * leverage) / price)
      
      if size_contracts < 1:
        size_contracts = 1
      
      order = FuturesOrder(
        contract=contract,
        size=size_contracts if side == PositionSide.LONG else -size_contracts,
        price="0",
        tif="ioc"
      )
      
      result = await asyncio.to_thread(
        self.api.create_futures_order,
        self.settle,
        order
      )
      
      log.debug(
        "gate_position_opened",
        coin=coin,
        side=side.value,
        size_contracts=size_contracts,
        leverage=leverage
      )
      
      return OrderResult(
        exchange=self.name,
        coin=coin,
        side=side,
        size=size_contracts,
        executed_price=float(result.fill_price) if hasattr(result, "fill_price") and result.fill_price else price,
        success=True,
        order_id=str(result.id)
      )
    
    except Exception as e:
      log.error("gate_open_position_failed", coin=coin, side=side.value, error=str(e))
      return OrderResult(
        exchange=self.name,
        coin=coin,
        side=side,
        size=0,
        executed_price=None,
        success=False,
        error=str(e)
      )


  async def close_position(self, coin: str, side: PositionSide) -> OrderResult:
    try:
      contract = f"{coin}_USDT"
      
      auto_size_value = "close_long" if side == PositionSide.LONG else "close_short"
      
      order = FuturesOrder(
        contract=contract,
        size=0,
        auto_size=auto_size_value,
        price="0",
        tif="ioc"
      )
      
      result = await asyncio.to_thread(
        self.api.create_futures_order,
        self.settle,
        order
      )
      
      log.debug("gate_position_closed", coin=coin, side=side.value)
      
      return OrderResult(
        exchange=self.name,
        coin=coin,
        side=side,
        size=0,
        executed_price=float(result.fill_price) if hasattr(result, "fill_price") and result.fill_price else None,
        success=True,
        order_id=str(result.id)
      )
    
    except Exception as e:
      log.error("gate_close_position_failed", coin=coin, side=side.value, error=str(e))
      return OrderResult(
        exchange=self.name,
        coin=coin,
        side=side,
        size=0,
        executed_price=None,
        success=False,
        error=str(e)
      )