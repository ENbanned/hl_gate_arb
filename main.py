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

      hl_meta = await asyncio.to_thread(
        hyperliquid_client.info.meta_and_asset_ctxs
      )
      meta, asset_ctxs = hl_meta
      for i, asset in enumerate(meta["universe"]):
          if asset["name"] == "BTC":
              ctx = asset_ctxs[i]

      try:
        gate_stats = await asyncio.to_thread(
          gate_client.futures_api.list_futures_tickers,
          gate_client.settle,
          contract='BTC_USDT'
        )
        print("\nGATE 24H STATS:")
        print(gate_stats[0].to_dict() if gate_stats else "Empty")
      except Exception as e:
        print(f"Gate stats error: {e}")
      
      # Hyperliquid 24h volume (из asset_ctxs который уже есть)
      print("\nHYPERLIQUID 24H VOLUME (из ctx выше):")
      print(f"dayNtlVlm: {ctx.get('dayNtlVlm')}")
      print(f"dayBaseVlm: {ctx.get('dayBaseVlm')}")

asyncio.run(main())