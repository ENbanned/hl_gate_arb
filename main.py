import asyncio

from src.exchanges.common import setup_logging, get_logger, MonitorHealth
from src.exchanges.gate import GateClient
from src.exchanges.hyperliquid import HyperliquidClient

from settings import GATE_API_KEY, GATE_API_SECRET, HYPERLIQUID_ACCOUNT_ADDRESS, HYPERLIQUID_SECRET_KEY

logger = get_logger(__name__)


async def gate_example():
  setup_logging("INFO")
  
  async with GateClient(
    api_key=GATE_API_KEY,
    api_secret=GATE_API_SECRET,
    settle="usdt"
  ) as client:
    health = MonitorHealth(
      client.price_monitor,
      client.orderbook_monitor,
      required_symbols=["BTC", "ETH"]
    )
    
    await asyncio.sleep(2)
    
    if health.is_healthy():
      logger.info("gate_client_healthy")
    else:
      logger.warning("gate_client_unhealthy", 
                     missing_prices=health.missing_prices(),
                     missing_books=health.missing_orderbooks())
    
    balance = await client.get_balance()
    logger.info("balance", total=balance.total, available=balance.available)
    
    positions = await client.get_positions()
    logger.info("positions", count=len(positions))
    
    btc_price = client.price_monitor.get_price("BTC")
    logger.info("btc_price", price=btc_price)
    
    best_bid = client.orderbook_monitor.get_best_bid("BTC")
    best_ask = client.orderbook_monitor.get_best_ask("BTC")
    logger.info("btc_orderbook", bid=best_bid.price if best_bid else None, 
                ask=best_ask.price if best_ask else None)


async def hyperliquid_example():
  setup_logging("INFO")
  
  async with HyperliquidClient(
    secret_key=HYPERLIQUID_SECRET_KEY,
    account_address=HYPERLIQUID_ACCOUNT_ADDRESS
  ) as client:
    health = MonitorHealth(
      client.price_monitor,
      client.orderbook_monitor,
      required_symbols=["BTC", "ETH"]
    )
    
    await asyncio.sleep(2)
    
    if health.is_healthy():
      logger.info("hyperliquid_client_healthy")
    
    balance = await client.get_balance()
    logger.info("balance", total=balance.total)
    
    positions = await client.get_positions()
    logger.info("positions", count=len(positions))


if __name__ == "__main__":
  asyncio.run(gate_example())