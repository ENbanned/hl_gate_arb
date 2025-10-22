import asyncio

from src.exchanges.common import ExchangeClient, Position
from src.exchanges.gate import GateClient
from src.exchanges.hyperliquid import HyperliquidClient

from settings import GATE_API_KEY, GATE_API_SECRET, HYPERLIQUID_ACCOUNT_ADDRESS, HYPERLIQUID_SECRET_KEY



async def main():
  async with GateClient(GATE_API_KEY, GATE_API_SECRET) as gate_client:
    async with HyperliquidClient(HYPERLIQUID_SECRET_KEY, HYPERLIQUID_ACCOUNT_ADDRESS) as hyperliquid_client:

      gate: ExchangeClient = gate_client
      hyperliquid: ExchangeClient = hyperliquid_client

      open_gate = await gate.buy_market('ENA', 100)
      print(open_gate)
      # gate_open_positions = await gate.get_positions()
      # hyperliquid_open_positions = await hyperliquid.get_positions()

      # print(f'Gate positions before: {gate_open_positions}')
      # print(f'Hyperliquid positions before: {hyperliquid_open_positions}')

      # open_gate = await gate.buy_market('ENA', 100)
      # print(f'GATE LONG 100 ENA: {open_gate}')

      # open_hyperliquid = await hyperliquid.buy_market('ENA', 100)
      # print(f'HYPERLIQUID LONG 100 ENA: {open_hyperliquid}')

      # gate_open_positions = await gate.get_positions()
      # hyperliquid_open_positions = await hyperliquid.get_positions()

      # print(f'Gate positions after: {gate_open_positions}')
      # print(f'Hyperliquid positions after: {hyperliquid_open_positions}')

      # gate_close = await gate.sell_market('ENA', 100)
      # print(f'GATE CLOSE LONG 100 ENA: {gate_close}')

      # hyperliquid_close = await hyperliquid.sell_market('ENA', 100)
      # print(f'HYPERLIQUID CLOSE LONG 100 ENA: {hyperliquid_close}')

      # gate_open_positions = await gate.get_positions()
      # hyperliquid_open_positions = await hyperliquid.get_positions()

      # print(f'Gate positions at the end: {gate_open_positions}')
      # print(f'Hyperliquid positions at the end: {hyperliquid_open_positions}')

  
"""

Gate positions before: []
Hyperliquid positions before: []

GATE LONG 100 ENA: 
order_id='61643020747359378' 
coin='ENA' size=Decimal('10') 
side=<PositionSide.LONG: 'long'> 
fill_price=Decimal('0.4314') 
status=<OrderStatus.FILLED: 'filled'> 
fee=Decimal('0.002070720')

HYPERLIQUID LONG 100 ENA: 
order_id='209446386207' 
coin='ENA' size=Decimal('100.0') 
side=<PositionSide.LONG: 'long'> 
fill_price=Decimal('0.43104') 
status=<OrderStatus.FILLED: 'filled'> 
fee=Decimal('0')

Gate positions after: 
[
  Position(
    coin='ENA', 
    size=Decimal('10'), 
    side=<PositionSide.LONG: 'long'>, 
    entry_price=Decimal('0.4314'), 
    mark_price=Decimal('0.4314'), 
    unrealized_pnl=Decimal('0'), 
    liquidation_price=None, 
    margin_used=Decimal('0'), 
    leverage=None
  )
]
Hyperliquid positions after: 
[
  Position(
    coin='ENA', 
    size=Decimal('100.0'), 
    side=<PositionSide.LONG: 'long'>, 
    entry_price=Decimal('0.43104'), 
    mark_price=Decimal('0.43104'), 
    unrealized_pnl=Decimal('0.002'), 
    liquidation_price=Decimal('0.3631852211'), 
    margin_used=Decimal('8.603404'), 
    leverage=5
  )
]

GATE CLOSE LONG 100 ENA: 
order_id='61643020747359438' 
coin='ENA' size=Decimal('10') 
side=<PositionSide.SHORT: 'short'> 
fill_price=Decimal('0.4314') 
status=<OrderStatus.FILLED: 'filled'> 
fee=Decimal('0.002070720')

HYPERLIQUID CLOSE LONG 100 ENA: 
order_id='209446401177' 
coin='ENA' 
size=Decimal('100.0') 
side=<PositionSide.SHORT: 'short'> 
fill_price=Decimal('0.431') 
status=<OrderStatus.FILLED: 'filled'> 
fee=Decimal('0')

Gate positions at the end: []
Hyperliquid positions at the end: []


"""






asyncio.run(main())