from .spread import SpreadFinder
from .models import BotMode
from ..exchanges.common import ExchangeClient


class Bot:
    __slots__ = ('mode', 'gate', 'hyperliquid', 'finder', 'symbols')
    
    def __init__(
        self,
        mode: BotMode,
        gate: ExchangeClient,
        hyperliquid: ExchangeClient
    ):
        self.mode = mode
        self.gate = gate
        self.hyperliquid = hyperliquid
        self.finder = SpreadFinder(gate, hyperliquid)
        self.symbols: list[str] = []
    
    
    async def __aenter__(self):
        common = self.gate.get_available_symbols() & self.hyperliquid.get_available_symbols()
        self.symbols = sorted(common)
        
        gate_contracts = [f'{s}_USDT' for s in self.symbols]
        
        print(f"[BOT] Starting monitors for {len(self.symbols)} symbols...")
        
        await self.gate.price_monitor.start(gate_contracts)
        await self.gate.orderbook_monitor.start(gate_contracts)
        await self.hyperliquid.price_monitor.start()
        await self.hyperliquid.orderbook_monitor.start(self.symbols)
        
        print(f"[BOT] Ready")
        return self
    
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


    async def _prepare_leverages(self):
        print(self.symbols)