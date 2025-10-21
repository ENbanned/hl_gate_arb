import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import websockets


@dataclass
class PriceData:
  best_bid: float
  best_ask: float
  mid_price: float
  spread: float
  timestamp: float
  source: str
  sequence: int


@dataclass
class SourceStats:
  updates_count: int = 0
  last_update_time: float = 0
  update_intervals: deque = field(default_factory=lambda: deque(maxlen=50))
  price_changes: int = 0
  last_price: float = 0


async def subscribe_and_collect(uri: str, coin: str, source: str, queue: asyncio.Queue[PriceData]) -> None:
  sequence = 0
  try:
    async with websockets.connect(uri) as ws:
      await ws.send(json.dumps({
        "method": "subscribe",
        "subscription": {"type": "l2Book", "coin": coin}
      }))
      
      async for msg in ws:
        receive_time = time.time()
        data = json.loads(msg)
        
        if data.get("channel") == "l2Book":
          levels = data["data"]["levels"]
          
          if len(levels) >= 2 and levels[0] and levels[1]:
            sequence += 1
            best_bid = float(levels[0][0]["px"])
            best_ask = float(levels[1][0]["px"])
            mid_price = (best_bid + best_ask) / 2
            spread = best_ask - best_bid
            
            price_data = PriceData(
              best_bid=best_bid,
              best_ask=best_ask,
              mid_price=mid_price,
              spread=spread,
              timestamp=receive_time,
              source=source,
              sequence=sequence
            )
            
            await queue.put(price_data)
  except Exception as e:
    print(f"Error in {source}: {e}")


async def compare_prices(coin: str = "BTC") -> None:
  local_uri = "ws://localhost:8000/ws"
  public_uri = "wss://api.hyperliquid.xyz/ws"
  
  queue: asyncio.Queue[PriceData] = asyncio.Queue()
  
  local_task = asyncio.create_task(subscribe_and_collect(local_uri, coin, "LOCAL", queue))
  public_task = asyncio.create_task(subscribe_and_collect(public_uri, coin, "PUBLIC", queue))
  
  prices: dict[str, PriceData] = {}
  stats: dict[str, SourceStats] = {
    "LOCAL": SourceStats(),
    "PUBLIC": SourceStats()
  }
  
  start_time = time.time()
  last_stat_print = start_time
  
  try:
    while True:
      data = await queue.get()
      source_stats = stats[data.source]
      
      current_time = time.time()
      
      if source_stats.last_update_time > 0:
        interval = current_time - source_stats.last_update_time
        source_stats.update_intervals.append(interval)
      
      if source_stats.last_price != 0 and source_stats.last_price != data.mid_price:
        source_stats.price_changes += 1
      
      source_stats.updates_count += 1
      source_stats.last_update_time = current_time
      source_stats.last_price = data.mid_price
      
      prices[data.source] = data
      
      if "LOCAL" in prices and "PUBLIC" in prices:
        local = prices["LOCAL"]
        public = prices["PUBLIC"]
        
        price_diff = local.mid_price - public.mid_price
        price_diff_pct = (price_diff / public.mid_price) * 100
        
        print(f"L: ${local.mid_price:.2f} [{local.sequence:4d}] | "
              f"P: ${public.mid_price:.2f} [{public.sequence:4d}] | "
              f"Δ: ${price_diff:+.2f} ({price_diff_pct:+.4f}%)")
      
      if current_time - last_stat_print >= 10:
        print("\n" + "="*80)
        print("STATISTICS (last 10 seconds):")
        
        for source_name, source_stats in stats.items():
          if source_stats.update_intervals:
            avg_interval = sum(source_stats.update_intervals) / len(source_stats.update_intervals)
            updates_per_sec = 1 / avg_interval if avg_interval > 0 else 0
          else:
            updates_per_sec = 0
          
          elapsed = current_time - start_time
          total_rate = source_stats.updates_count / elapsed if elapsed > 0 else 0
          
          print(f"\n{source_name}:")
          print(f"  Total updates: {source_stats.updates_count}")
          print(f"  Updates/sec: {updates_per_sec:.2f} (recent) | {total_rate:.2f} (avg)")
          print(f"  Price changes: {source_stats.price_changes}")
          print(f"  Current sequence: {prices.get(source_name, PriceData(0,0,0,0,0,'',0)).sequence}")
        
        local_stats = stats["LOCAL"]
        public_stats = stats["PUBLIC"]
        
        if local_stats.updates_count > 0 and public_stats.updates_count > 0:
          local_rate = local_stats.updates_count / (current_time - start_time)
          public_rate = public_stats.updates_count / (current_time - start_time)
          
          faster = "LOCAL" if local_rate > public_rate else "PUBLIC"
          diff_pct = abs(local_rate - public_rate) / max(local_rate, public_rate) * 100
          
          print(f"\n🏆 FASTER SOURCE: {faster} (by {diff_pct:.1f}%)")
          
          more_responsive = "LOCAL" if local_stats.price_changes > public_stats.price_changes else "PUBLIC"
          print(f"📊 MORE PRICE CHANGES: {more_responsive}")
        
        print("="*80 + "\n")
        last_stat_print = current_time
        
  except KeyboardInterrupt:
    print("\nStopping...")
  finally:
    local_task.cancel()
    public_task.cancel()


if __name__ == "__main__":
  asyncio.run(compare_prices("BTC"))