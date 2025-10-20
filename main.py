import asyncio
import signal
import sys

from src.config.settings import settings
from src.exchanges.gate import GateExchange
from src.exchanges.hyperliquid import HyperliquidExchange
from src.strategy.arbitrage import ArbitrageStrategy
from src.utils.logging import get_logger, setup_logging
from src.utils.telegram import notifier


setup_logging(settings.log_level)
log = get_logger(__name__)


class Application:
  
  def __init__(self):
    self.gate = GateExchange()
    self.hyperliquid = HyperliquidExchange()
    self.strategy = ArbitrageStrategy(self.gate, self.hyperliquid)
    
    self.shutdown_event = asyncio.Event()
  
  
  async def start(self):
    log.info("application_starting")
    
    signal.signal(signal.SIGINT, self._signal_handler)
    signal.signal(signal.SIGTERM, self._signal_handler)
    
    try:
      await self.gate.connect()
      await self.hyperliquid.connect()
      
      log.info("application_started")
      
      await notifier.send("🚀 Arbitrage Bot Started")
      
      await asyncio.gather(
        self.strategy.start(),
        self._wait_for_shutdown(),
      )
    
    except Exception as e:
      log.error("application_error", error=str(e))
      await notifier.error_alert("Application Error", str(e))
      raise
    
    finally:
      await self._shutdown()
  
  
  async def _wait_for_shutdown(self):
    await self.shutdown_event.wait()
  
  
  def _signal_handler(self, signum, frame):
    log.info("shutdown_signal_received", signal=signum)
    self.shutdown_event.set()
  
  
  async def _shutdown(self):
    log.info("application_shutting_down")
    
    await self.strategy.stop()
    await self.gate.disconnect()
    await self.hyperliquid.disconnect()
    await notifier.close()
    
    log.info("application_shutdown_complete")


async def main():
  app = Application()
  
  try:
    await app.start()
  except KeyboardInterrupt:
    log.info("keyboard_interrupt_received")
  except Exception as e:
    log.critical("fatal_error", error=str(e))
    sys.exit(1)


if __name__ == "__main__":
  asyncio.run(main())