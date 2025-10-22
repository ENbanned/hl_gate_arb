from src.exchanges.common import ExchangeClient, Position
from src.exchanges.gate import GateClient
from src.exchanges.hyperliquid import HyperliquidClient

from settings import GATE_API_KEY, GATE_API_SECRET, HYPERLIQUID_ACCOUNT_ADDRESS, HYPERLIQUID_SECRET_KEY



async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate:
    async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hl:
      clients: list[ExchangeClient] = [gate, hl]
      
      for client in clients:
        positions = await client.get_positions()
        for pos in positions:
          print(f"{pos.coin}: {pos.side} {pos.size} @ {pos.entry_price}")
        
        order = await client.buy_market('ENA', 100)
        print(f"Order {order.order_id}: {order.status}")