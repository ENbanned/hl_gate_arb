import asyncio
import signal

from src.config.settings import settings
from src.exchanges.gate import GateExchange
from src.exchanges.hyperliquid import HyperliquidExchange
from src.strategy.arbitrage import ArbitrageStrategy
from src.utils.logging import get_logger, setup_logging


setup_logging(log_level="INFO", console_output=True)
log = get_logger(__name__)


class Application:
  
  def __init__(self):
    self.gate = None
    self.hyperliquid = None
    self.strategy = None
    self.shutdown_event = asyncio.Event()
  
  
  async def startup(self):
    log.info("application_starting")
    
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
    
    await asyncio.sleep(5)
    
    self.strategy = ArbitrageStrategy(self.gate, self.hyperliquid)
    
    log.info("application_started")
  
  
  async def run(self):
    try:
      await self.strategy.start()
    except asyncio.CancelledError:
      log.debug("application_cancelled")
    except Exception as e:
      log.error("application_error", error=str(e), exc_info=True)
  
  
  async def shutdown(self):
    log.info("application_shutting_down")
    
    if self.strategy:
      await self.strategy.shutdown()
    
    if self.gate:
      await self.gate.__aexit__(None, None, None)
    
    if self.hyperliquid:
      await self.hyperliquid.__aexit__(None, None, None)
    
    log.info("application_shutdown_complete")


async def main():
  app = Application()
  
  loop = asyncio.get_event_loop()
  
  def signal_handler():
    log.info("shutdown_signal_received")
    if app.strategy:
      app.strategy._shutdown_requested = True
  
  for sig in (signal.SIGTERM, signal.SIGINT):
    loop.add_signal_handler(sig, signal_handler)
  
  try:
    await app.startup()
    await app.run()
  except KeyboardInterrupt:
    log.info("keyboard_interrupt")
  finally:
    await app.shutdown()


if __name__ == "__main__":
  asyncio.run(main())