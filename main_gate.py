# example_usage.py

import asyncio

from settings import GATE_API_KEY, GATE_API_SECRET
from src.exchanges.gate.client import GateClient


async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate:
    print('Connected to Gate.io')
    
    await asyncio.sleep(1)
    
    btc_price = gate.get_price('BTC_USDT')
    ena_price = gate.get_price('ENA_USDT')
    eth_price = gate.get_price('ETH_USDT')
    
    print(f'BTC: ${btc_price}')
    print(f'ENA: ${ena_price}')
    print(f'ETH: ${eth_price}')
    
    print(f'\nTotal contracts tracked: {len(gate.all_prices)}')
    
    for _ in range(10):
      await asyncio.sleep(1)
      new_btc = gate.get_price_unsafe('BTC_USDT')
      print(f'BTC: ${new_btc:,.2f}')


asyncio.run(main())