import asyncio
from datetime import datetime

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from src.core.models import Balance, ExchangeName, OrderResult, PositionSide
from src.utils.logging import get_logger


log = get_logger(__name__)


class HyperliquidExchange:
  
  def __init__(
    self, 
    private_key: str, 
    account_address: str, 
    base_url: str = constants.MAINNET_API_URL
  ):
    self.name = ExchangeName.HYPERLIQUID
    self.base_url = base_url
    
    account: LocalAccount = eth_account.Account.from_key(private_key)
    self.wallet = account
    self.agent_address = account.address
    self.address = account_address
    
    self.info = Info(base_url, skip_ws=False)
    self.exchange = Exchange(account, base_url, account_address=account_address)
    
    self.orderbooks: dict[str, dict] = {}
    self._meta_cache: dict = {}
    self._asset_ctxs_cache: dict = {}
    self._update_task = None
    
    log.info(
      "hyperliquid_initialized",
      account_address=self.address,
      agent_address=self.agent_address
    )


  async def __aenter__(self):
    meta = await asyncio.to_thread(self.info.meta)
    self._meta_cache = {asset["name"]: asset for asset in meta["universe"]}
    
    for asset in meta["universe"]:
      coin = asset["name"]
      
      def callback(coin_name):
        def handler(msg):
          if msg["channel"] == "l2Book":
            self.orderbooks[coin_name] = {
              "levels": msg["data"]["levels"],
              "timestamp": datetime.utcnow()
            }
        return handler
      
      await asyncio.to_thread(
        self.info.subscribe,
        {"type": "l2Book", "coin": coin},
        callback(coin)
      )
    
    await self._update_asset_contexts()
    
    self._update_task = asyncio.create_task(self._keepalive_loop())
    log.info("hyperliquid_started", coins_count=len(self._meta_cache))
    return self


  async def __aexit__(self, exc_type, exc, tb):
    if self._update_task:
      self._update_task.cancel()
      try:
        await self._update_task
      except asyncio.CancelledError:
        pass
    
    await asyncio.to_thread(self.info.disconnect_websocket)


  async def _keepalive_loop(self):
    while True:
      await asyncio.sleep(60)
      await self._update_asset_contexts()


  async def _update_asset_contexts(self):
    try:
      all_mids = await asyncio.to_thread(self.info.all_mids)
      
      for coin, ctx in all_mids.items():
        if isinstance(ctx, dict):
          self._asset_ctxs_cache[coin] = ctx
    except Exception as e:
      log.debug("asset_contexts_update_failed", error=str(e))


  async def get_balance(self) -> Balance:
    state = await asyncio.to_thread(self.info.user_state, self.address)
    margin = state.get("marginSummary", {})
    
    return Balance(
      exchange=self.name,
      account_value=float(margin.get("accountValue", 0)),
      available=float(state.get("withdrawable", 0)),
      total_margin_used=float(margin.get("totalMarginUsed", 0)),
      unrealised_pnl=float(margin.get("totalRawUsd", 0)) - float(margin.get("accountValue", 0))
    )


  async def get_orderbook(self, coin: str) -> dict:
    return self.orderbooks.get(coin, {})


  async def get_leverage_limits(self, coin: str) -> tuple[int, int]:
    asset = self._meta_cache.get(coin)
    if asset:
      max_lev = int(asset.get("maxLeverage", 1))
      return (1, max_lev)
    return (1, 1)


  async def get_funding_rate(self, coin: str) -> float:
    ctx = self._asset_ctxs_cache.get(coin)
    if ctx and "funding" in ctx:
      return float(ctx["funding"])
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


  async def open_position(
    self, 
    coin: str, 
    side: PositionSide, 
    size_usd: float, 
    leverage: int
  ) -> OrderResult:
    try:
      await asyncio.to_thread(
        self.exchange.update_leverage,
        leverage,
        coin
      )
      
      asset = self._meta_cache.get(coin)
      if not asset:
        return OrderResult(
          exchange=self.name,
          coin=coin,
          side=side,
          size=0,
          executed_price=None,
          success=False,
          error="asset_not_found"
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
      sz_decimals = int(asset.get("szDecimals", 0))
      size_coins = round((size_usd * leverage) / price, sz_decimals)
      
      result = await asyncio.to_thread(
        self.exchange.market_open,
        coin,
        side == PositionSide.LONG,
        size_coins,
        slippage=0.01
      )
      
      log.debug(
        "hyperliquid_position_opened",
        coin=coin,
        side=side.value,
        size_coins=size_coins,
        leverage=leverage
      )
      
      return OrderResult(
        exchange=self.name,
        coin=coin,
        side=side,
        size=size_coins,
        executed_price=price,
        success=True,
        order_id=str(result)
      )
    
    except Exception as e:
      log.error("hyperliquid_open_position_failed", coin=coin, side=side.value, error=str(e))
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
      result = await asyncio.to_thread(
        self.exchange.market_close,
        coin,
        slippage=0.01
      )
      
      log.debug("hyperliquid_position_closed", coin=coin, side=side.value)
      
      return OrderResult(
        exchange=self.name,
        coin=coin,
        side=side,
        size=0,
        executed_price=None,
        success=True,
        order_id=str(result)
      )
    
    except Exception as e:
      log.error("hyperliquid_close_position_failed", coin=coin, side=side.value, error=str(e))
      return OrderResult(
        exchange=self.name,
        coin=coin,
        side=side,
        size=0,
        executed_price=None,
        success=False,
        error=str(e)
      )