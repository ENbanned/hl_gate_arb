import asyncio
import json
from datetime import datetime

import httpx
import websockets
from eth_account import Account
from eth_account.signers.local import LocalAccount
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.constants import (
  HYPERLIQUID_API_URL,
  HYPERLIQUID_FEE_TAKER,
  HYPERLIQUID_WS_URL,
  MAX_RETRIES,
)
from src.config.settings import settings
from src.core.models import (
  Balance,
  ExchangeName,
  FundingRate,
  Orderbook,
  OrderbookLevel,
  PositionSnapshot,
)
from src.utils.logging import get_logger


log = get_logger(__name__)


class HyperliquidExchange:
  
  def __init__(self):
    self.name = ExchangeName.HYPERLIQUID
    
    self.wallet: LocalAccount = Account.from_key(
      settings.hyperliquid_private_key
    )
    self.agent_address = self.wallet.address
    self.address = settings.hyperliquid_account_address
    
    self.client = httpx.AsyncClient(timeout=30.0)
    
    self.ws: websockets.WebSocketClientProtocol | None = None
    self.orderbooks: dict[str, Orderbook] = {}
    self.funding_rates: dict[str, FundingRate] = {}
    self.universe: list[dict] = []
    self.coin_to_index: dict[str, int] = {}
    
    self.ws_task: asyncio.Task | None = None
    self.running = False
  
  
  async def connect(self):
    await self._load_universe()
    self.running = True
    self.ws_task = asyncio.create_task(self._ws_handler())
    log.info(
      "hyperliquid_connected",
      account_address=self.address,
      agent_address=self.agent_address,
      coins=len(self.coin_to_index),
    )
  
  
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
    await self.client.aclose()
    log.info("hyperliquid_disconnected")
  
  
  @retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
  )
  async def get_balance(self) -> Balance:
    try:
      response = await self._post(
        "/info",
        {"type": "clearinghouseState", "user": self.address},
      )
      
      if not response:
        raise Exception("no response")
      
      margin_summary = response.get("marginSummary", {})
      account_value = float(margin_summary.get("accountValue", 0))
      total_margin_used = float(margin_summary.get("totalMarginUsed", 0))
      available = account_value - total_margin_used
      
      return Balance(
        total=account_value,
        available=max(0, available),
        in_positions=total_margin_used,
      )
    except Exception as e:
      log.error("hyperliquid_balance_error", error=str(e))
      raise
  
  
  async def get_orderbook(self, coin: str) -> Orderbook | None:
    return self.orderbooks.get(coin)
  
  
  async def get_funding_rate(self, coin: str) -> FundingRate | None:
    cached = self.funding_rates.get(coin)
    if cached and (datetime.now() - cached.timestamp).seconds < 300:
      return cached
    
    try:
      response = await self._post(
        "/info",
        {"type": "metaAndAssetCtxs"},
      )
      
      if not response:
        return None
      
      for ctx in response[1]:
        if ctx.get("coin") == coin:
          funding = ctx.get("funding")
          if funding:
            rate = float(funding) / 100
            next_time = datetime.now().replace(
              minute=0, second=0, microsecond=0
            )
            
            fr = FundingRate(
              rate=rate,
              next_funding_time=next_time,
            )
            self.funding_rates[coin] = fr
            return fr
    except Exception as e:
      log.debug("hyperliquid_funding_error", coin=coin, error=str(e))
    
    return None
  
  
  async def get_leverage_limits(self, coin: str) -> tuple[int, int]:
    if coin not in self.coin_to_index:
      return (1, 1)
    
    try:
      response = await self._post(
        "/info",
        {"type": "metaAndAssetCtxs"},
      )
      
      if not response:
        return (1, 10)
      
      for meta in response[0]:
        if meta.get("name") == coin:
          max_lev = int(meta.get("maxLeverage", 10))
          return (1, max_lev)
    except Exception:
      pass
    
    return (1, 10)
  
  
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
    coin_index = self.coin_to_index.get(coin)
    if coin_index is None:
      return None
    
    try:
      await self._update_leverage(coin_index, leverage)
      
      orderbook = await self.get_orderbook(coin)
      if not orderbook:
        return None
      
      if side == "long":
        price = orderbook.asks[0].price * 1.002
      else:
        price = orderbook.bids[0].price * 0.998
      
      size = size_usd / price
      
      order = {
        "coin": coin_index,
        "is_buy": side == "long",
        "sz": size,
        "limit_px": price,
        "order_type": {"limit": {"tif": "Ioc"}},
        "reduce_only": False,
      }
      
      action = {
        "type": "order",
        "orders": [order],
        "grouping": "na",
      }
      
      response = await self._post_signed("/exchange", action)
      
      if response and response.get("status") == "ok":
        statuses = response.get("response", {}).get("data", {}).get("statuses", [])
        if statuses:
          status = statuses[0]
          if "resting" in status:
            order_id = status["resting"].get("oid")
            log.info(
              "hyperliquid_order_placed",
              coin=coin,
              side=side,
              size=size,
              price=price,
              order_id=order_id,
            )
            return str(order_id)
    except Exception as e:
      log.error("hyperliquid_order_error", coin=coin, error=str(e))
    
    return None
  
  
  @retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
  )
  async def close_position(self, coin: str) -> bool:
    coin_index = self.coin_to_index.get(coin)
    if coin_index is None:
      return False
    
    try:
      position = await self.get_position(coin)
      if not position or position.size == 0:
        return True
      
      orderbook = await self.get_orderbook(coin)
      if not orderbook:
        return False
      
      if position.side == "long":
        price = orderbook.bids[0].price * 0.998
        is_buy = False
      else:
        price = orderbook.asks[0].price * 1.002
        is_buy = True
      
      order = {
        "coin": coin_index,
        "is_buy": is_buy,
        "sz": position.size,
        "limit_px": price,
        "order_type": {"limit": {"tif": "Ioc"}},
        "reduce_only": True,
      }
      
      action = {
        "type": "order",
        "orders": [order],
        "grouping": "na",
      }
      
      response = await self._post_signed("/exchange", action)
      
      if response and response.get("status") == "ok":
        log.info("hyperliquid_position_closed", coin=coin)
        return True
    except Exception as e:
      log.error("hyperliquid_close_error", coin=coin, error=str(e))
    
    return False
  
  
  async def get_position(self, coin: str) -> PositionSnapshot | None:
    try:
      response = await self._post(
        "/info",
        {"type": "clearinghouseState", "user": self.address},
      )
      
      if not response:
        return None
      
      for asset_pos in response.get("assetPositions", []):
        position = asset_pos.get("position", {})
        if position.get("coin") == coin:
          szi = float(position.get("szi", 0))
          if szi == 0:
            return None
          
          side = "long" if szi > 0 else "short"
          
          return PositionSnapshot(
            exchange=self.name,
            coin=coin,
            size=abs(szi),
            side=side,
            entry_price=float(position.get("entryPx", 0)),
            mark_price=float(position.get("markPx", 0)),
            unrealized_pnl=float(position.get("unrealizedPnl", 0)),
            margin_used=float(position.get("marginUsed", 0)),
          )
    except Exception:
      return None
    
    return None
  
  
  async def get_all_positions(self) -> list[PositionSnapshot]:
    try:
      response = await self._post(
        "/info",
        {"type": "clearinghouseState", "user": self.address},
      )
      
      if not response:
        return []
      
      result = []
      for asset_pos in response.get("assetPositions", []):
        position = asset_pos.get("position", {})
        coin = position.get("coin")
        szi = float(position.get("szi", 0))
        
        if szi == 0 or not coin:
          continue
        
        side = "long" if szi > 0 else "short"
        
        result.append(
          PositionSnapshot(
            exchange=self.name,
            coin=coin,
            size=abs(szi),
            side=side,
            entry_price=float(position.get("entryPx", 0)),
            mark_price=float(position.get("markPx", 0)),
            unrealized_pnl=float(position.get("unrealizedPnl", 0)),
            margin_used=float(position.get("marginUsed", 0)),
          )
        )
      
      return result
    except Exception:
      return []
  
  
  async def _load_universe(self):
    try:
      response = await self._post("/info", {"type": "meta"})
      
      if not response:
        raise Exception("no universe data")
      
      self.universe = response.get("universe", [])
      
      for idx, asset in enumerate(self.universe):
        coin = asset.get("name")
        if coin:
          self.coin_to_index[coin] = idx
      
      log.info("hyperliquid_universe_loaded", coins=len(self.coin_to_index))
    except Exception as e:
      log.error("hyperliquid_universe_error", error=str(e))
      raise
  
  
  async def _update_leverage(self, coin_index: int, leverage: int):
    try:
      action = {
        "type": "updateLeverage",
        "asset": coin_index,
        "isCross": True,
        "leverage": leverage,
      }
      await self._post_signed("/exchange", action)
    except Exception as e:
      log.debug("hyperliquid_leverage_error", error=str(e))
  
  
  async def _ws_handler(self):
    while self.running:
      try:
        async with websockets.connect(HYPERLIQUID_WS_URL) as ws:
          self.ws = ws
          
          await self._subscribe_orderbooks(ws)
          
          async for msg in ws:
            await self._handle_ws_message(msg)
      except Exception as e:
        log.warning("hyperliquid_ws_error", error=str(e))
        await asyncio.sleep(5)
  
  
  async def _subscribe_orderbooks(
    self, ws: websockets.WebSocketClientProtocol
  ):
    for coin in list(self.coin_to_index.keys())[:100]:
      sub_msg = {
        "method": "subscribe",
        "subscription": {"type": "l2Book", "coin": coin},
      }
      await ws.send(json.dumps(sub_msg))
      await asyncio.sleep(0.01)
  
  
  async def _handle_ws_message(self, message: str):
    try:
      data = json.loads(message)
      
      if data.get("channel") == "l2Book":
        await self._process_orderbook(data.get("data", {}))
    except Exception as e:
      log.debug("hyperliquid_ws_parse_error", error=str(e))
  
  
  async def _process_orderbook(self, data: dict):
    coin = data.get("coin")
    if not coin:
      return
    
    levels = data.get("levels", [])
    if len(levels) < 2:
      return
    
    bids_data = levels[0]
    asks_data = levels[1]
    
    bids = [
      OrderbookLevel(price=float(b["px"]), size=float(b["sz"]))
      for b in bids_data[:5]
    ]
    asks = [
      OrderbookLevel(price=float(a["px"]), size=float(a["sz"]))
      for a in asks_data[:5]
    ]
    
    if bids and asks:
      self.orderbooks[coin] = Orderbook(bids=bids, asks=asks)
  
  
  async def _post(self, endpoint: str, payload: dict) -> dict | None:
    try:
      response = await self.client.post(
        f"{HYPERLIQUID_API_URL}{endpoint}",
        json=payload,
      )
      response.raise_for_status()
      return response.json()
    except httpx.TimeoutException as e:
      log.warning("hyperliquid_post_timeout", endpoint=endpoint, error=str(e))
      return None
    except httpx.HTTPStatusError as e:
      log.warning("hyperliquid_post_http_error", endpoint=endpoint, status=e.response.status_code, error=str(e))
      return None
    except Exception as e:
      log.warning("hyperliquid_post_error", endpoint=endpoint, error=str(e))
      return None
  
  
  async def _post_signed(self, endpoint: str, action: dict) -> dict | None:
    try:
      timestamp = int(datetime.now().timestamp() * 1000)
      
      vault_address = self.address if self.address.lower() != self.agent_address.lower() else None
      
      message = {
        "action": action,
        "nonce": timestamp,
        "vaultAddress": vault_address,
      }
      
      message_str = json.dumps(message, separators=(",", ":"))
      signature = self.wallet.sign_message(
        {"message": message_str}
      ).signature.hex()
      
      payload = {
        "action": action,
        "nonce": timestamp,
        "signature": signature,
        "vaultAddress": vault_address,
      }
      
      response = await self.client.post(
        f"{HYPERLIQUID_API_URL}{endpoint}",
        json=payload,
      )
      response.raise_for_status()
      return response.json()
    except httpx.TimeoutException as e:
      log.warning("hyperliquid_signed_post_timeout", endpoint=endpoint, error=str(e))
      return None
    except httpx.HTTPStatusError as e:
      log.warning("hyperliquid_signed_post_http_error", endpoint=endpoint, status=e.response.status_code, error=str(e))
      return None
    except Exception as e:
      log.warning("hyperliquid_signed_post_error", endpoint=endpoint, error=str(e))
      return None