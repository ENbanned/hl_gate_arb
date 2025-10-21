import asyncio
from settings import GATE_API_KEY, GATE_API_SECRET
from src.exchanges.gate.client import GateClient


async def main():
  print('Starting...')
  
  try:
    print('Creating client...')
    client = GateClient(GATE_API_KEY, GATE_API_SECRET)
    print('Client created')
    
    print('Entering context...')
    async with client as gate:
      print('Context entered - 123')
      await asyncio.sleep(2)
      print('After sleep - 1234')
      
      print('BTC price:', gate.get_price('BTC_USDT'))
      print('ENA price:', gate.get_price('ENA_USDT'))
      print('All prices:', gate.all_prices)
      
      await asyncio.sleep(60)
  
  except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()


asyncio.run(main())