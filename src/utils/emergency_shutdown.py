import asyncio
import sys
from datetime import datetime, UTC

from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from src.config.settings import settings
from src.core.models import PositionSide
from src.exchanges.gate import GateExchange
from src.exchanges.hyperliquid import HyperliquidExchange
from src.utils.logging import get_logger


log = get_logger(__name__)


class EmergencyShutdown:
  
  def __init__(self, gate: GateExchange = None, hyperliquid: HyperliquidExchange = None):
    self.gate = gate
    self.hyperliquid = hyperliquid
    self.own_exchanges = False
    self.failed_closes: list[dict] = []
  
  
  async def initialize_exchanges(self):
    if not self.gate or not self.hyperliquid:
      log.info("emergency_initializing_exchanges")
      
      self.gate = GateExchange(
        settings.gate_api_key,
        settings.gate_api_secret
      )
      
      self.hyperliquid = HyperliquidExchange(
        settings.hyperliquid_private_key,
        settings.hyperliquid_account_address
      )
      
      await self.gate.__aenter__()
      await self.hyperliquid.__aenter__()
      
      self.own_exchanges = True
      
      await asyncio.sleep(3)
  
  
  async def cleanup_exchanges(self):
    if self.own_exchanges:
      if self.gate:
        await self.gate.__aexit__(None, None, None)
      if self.hyperliquid:
        await self.hyperliquid.__aexit__(None, None, None)
  
  
  @retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True
  )
  async def _close_with_retry(self, exchange, coin: str, side: PositionSide, exchange_name: str):
    result = await exchange.close_position(coin, side)
    
    if not result.success:
      raise Exception(f"close_failed: {result.error}")
    
    return result
  
  
  async def close_all_positions(self) -> bool:
    log.critical("emergency_shutdown_started", timestamp=datetime.now(UTC).isoformat())
    
    all_closed = True
    
    try:
      gate_positions = await self.gate.get_open_positions()
      log.info("emergency_gate_positions_found", count=len(gate_positions))
    except Exception as e:
      log.error("emergency_failed_get_gate_positions", error=str(e))
      gate_positions = []
      all_closed = False
    
    try:
      hl_positions = await self.hyperliquid.get_open_positions()
      log.info("emergency_hl_positions_found", count=len(hl_positions))
    except Exception as e:
      log.error("emergency_failed_get_hl_positions", error=str(e))
      hl_positions = []
      all_closed = False
    
    close_tasks = []
    
    for pos in gate_positions:
      close_tasks.append(
        self._close_single_position(
          self.gate,
          pos["coin"],
          pos["side"],
          "GATE"
        )
      )
    
    for pos in hl_positions:
      close_tasks.append(
        self._close_single_position(
          self.hyperliquid,
          pos["coin"],
          pos["side"],
          "HYPERLIQUID"
        )
      )
    
    if close_tasks:
      results = await asyncio.gather(*close_tasks, return_exceptions=True)
      
      for i, result in enumerate(results):
        if isinstance(result, Exception) or result is False:
          all_closed = False
    
    if self.failed_closes:
      log.critical(
        "emergency_shutdown_incomplete",
        failed_count=len(self.failed_closes),
        failed_positions=self.failed_closes
      )
      all_closed = False
    else:
      log.info("emergency_shutdown_complete_all_closed")
    
    return all_closed
  
  
  async def _close_single_position(
    self,
    exchange,
    coin: str,
    side: PositionSide,
    exchange_name: str
  ) -> bool:
    
    log.info(
      "emergency_closing_position",
      exchange=exchange_name,
      coin=coin,
      side=side.value
    )
    
    try:
      result = await self._close_with_retry(exchange, coin, side, exchange_name)
      
      log.info(
        "emergency_position_closed",
        exchange=exchange_name,
        coin=coin,
        side=side.value
      )
      
      return True
    
    except RetryError as e:
      log.critical(
        "emergency_close_failed_max_retries",
        exchange=exchange_name,
        coin=coin,
        side=side.value,
        error=str(e)
      )
      
      self.failed_closes.append({
        "exchange": exchange_name,
        "coin": coin,
        "side": side.value,
        "error": str(e)
      })
      
      return False
    
    except Exception as e:
      log.critical(
        "emergency_close_failed_exception",
        exchange=exchange_name,
        coin=coin,
        side=side.value,
        error=str(e),
        exc_info=True
      )
      
      self.failed_closes.append({
        "exchange": exchange_name,
        "coin": coin,
        "side": side.value,
        "error": str(e)
      })
      
      return False
  
  
  async def run(self) -> bool:
    try:
      await self.initialize_exchanges()
      all_closed = await self.close_all_positions()
      return all_closed
    
    finally:
      await self.cleanup_exchanges()


async def emergency_close_all(gate: GateExchange = None, hyperliquid: HyperliquidExchange = None) -> bool:
  shutdown = EmergencyShutdown(gate, hyperliquid)
  return await shutdown.run()


async def main():
  print("=" * 60)
  print("EMERGENCY SHUTDOWN - CLOSING ALL POSITIONS")
  print("=" * 60)
  print()
  
  shutdown = EmergencyShutdown()
  all_closed = await shutdown.run()
  
  print()
  print("=" * 60)
  
  if all_closed:
    print("✅ ALL POSITIONS CLOSED SUCCESSFULLY")
    print("=" * 60)
    sys.exit(0)
  else:
    print("❌ SOME POSITIONS FAILED TO CLOSE")
    print("⚠️  CHECK LOGS AND CLOSE MANUALLY")
    print("=" * 60)
    sys.exit(1)


if __name__ == "__main__":
  asyncio.run(main())