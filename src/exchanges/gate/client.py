import asyncio
from typing import Any
from decimal import Decimal

import gate_api
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder
from gate_api.exceptions import GateApiException

from ..common.exceptions import OrderError
from ..common.models import Balance, FundingRate, Order, Orderbook, Position, PositionSide, SymbolInfo, Volume24h
from .adapters import adapt_balance, adapt_funding_rate, adapt_order, adapt_orderbook, adapt_position, adapt_symbol_info, adapt_volume_24h
from .price_monitor import GatePriceMonitor
from .orderbook_monitor import GateOrderbookMonitor


__all__ = ['GateClient']


class GateClient:
    __slots__ = (
        'api_key',
        'api_secret',
        'settle',
        'dual_mode',
        'contracts_cache_interval',
        'config',
        'client',
        'futures_api',
        'price_monitor',
        'orderbook_monitor',
        'contracts_meta',
        '_leverage_cache',
        '_update_task',
        '_shutdown'
    )
  
    def __init__(
        self, 
        api_key: str, 
        api_secret: str,
        settle: str = 'usdt',
        dual_mode: bool = False,
        host: str = 'https://api.gateio.ws/api/v4',
        contracts_cache_interval: int = 300
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.settle = settle
        self.dual_mode = dual_mode
        self.contracts_cache_interval = contracts_cache_interval
        
        self.config = Configuration(host=host, key=api_key, secret=api_secret)
        self.client = ApiClient(self.config)
        self.futures_api = FuturesApi(self.client)
        
        self.price_monitor = GatePriceMonitor(settle)
        self.orderbook_monitor = GateOrderbookMonitor(settle, self.futures_api)
        self.contracts_meta: dict[str, Any] = {}
        self._leverage_cache: dict[str, int] = {}
        self._update_task = None
        self._shutdown = asyncio.Event()


    async def __aenter__(self):
        await self._init_setup()
        contracts = list(self.contracts_meta.keys())
        await self.price_monitor.start(contracts)
        await self.orderbook_monitor.start(contracts)
        return self


    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._shutdown.set()
        if self._update_task:
            await self._update_task

        await self.price_monitor.stop()
        await self.orderbook_monitor.stop()

        if self.client:
            self.client.close()


    async def _init_setup(self) -> None:
        await self._refresh_contracts()
        await self._set_position_mode()
        self._update_task = asyncio.create_task(self._contracts_updater())


    async def _refresh_contracts(self) -> None:
        contracts = await asyncio.to_thread(
        self.futures_api.list_futures_contracts,
        self.settle
        )
        
        cache = {}
        for contract in contracts:
            cache[contract.name] = contract.to_dict()
        
        self.contracts_meta = cache


    async def _set_position_mode(self) -> None:
        try:
            account = await asyncio.to_thread(
                self.futures_api.list_futures_accounts,
                self.settle
            )
            
            current_dual = getattr(account, 'in_dual_mode', False) or getattr(account, 'enable_new_dual_mode', False)
            
            if current_dual != self.dual_mode:
                positions = await asyncio.to_thread(
                self.futures_api.list_positions,
                self.settle
                )
                
                if positions and any(p.size != 0 for p in positions):
                    raise RuntimeError(
                        f"Cannot switch to {'dual' if self.dual_mode else 'single'} mode: close all positions first"
                    )
                
                await asyncio.to_thread(
                self.futures_api.set_dual_mode,
                self.settle,
                self.dual_mode
                )
        except GateApiException as ex:
            if ex.label != "USER_NOT_FOUND":
                raise RuntimeError(f"Failed to set position mode: {ex.message}") from ex


    async def _contracts_updater(self) -> None:
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(
                self._shutdown.wait(),
                timeout=self.contracts_cache_interval
                )
            except asyncio.TimeoutError:
                await self._refresh_contracts()


    def _symbol_to_contract(self, symbol: str) -> str:
        return f'{symbol}_USDT'


    async def set_leverage(self, symbol: str, leverage: int) -> None:
        contract = self._symbol_to_contract(symbol)
        
        if self._leverage_cache.get(contract) == leverage:
            return
        
        try:
            await asyncio.to_thread(
                self.futures_api.update_position_leverage,
                self.settle,
                contract,
                str(leverage)
            )
            self._leverage_cache[contract] = leverage
        except GateApiException as ex:
            raise OrderError(f"Failed to set leverage for {symbol}: {ex.message}") from ex


    async def set_leverages(self, leverages: dict[str, int]) -> None:
        tasks = [self.set_leverage(symbol, lev) for symbol, lev in leverages.items()]
        await asyncio.gather(*tasks)


    def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        contract = self._symbol_to_contract(symbol)
        raw = self.contracts_meta.get(contract)
        if not raw:
            return None
        return adapt_symbol_info(raw, symbol)


    async def buy_market(self, symbol: str, size: float) -> Order:
        contract = self._symbol_to_contract(symbol)
        
        order = FuturesOrder(
        contract=contract,
        size=int(size),
        price='0',
        tif='ioc'
        )
        
        try:
            raw = await asyncio.to_thread(
                self.futures_api.create_futures_order,
                self.settle,
                order
            )
            return adapt_order(raw.to_dict())
        except GateApiException as ex:
            raise OrderError(f"Failed to buy market: {ex.message}") from ex


    async def sell_market(self, symbol: str, size: float) -> Order:
        contract = self._symbol_to_contract(symbol)
        
        order = FuturesOrder(
        contract=contract,
        size=-abs(int(size)),
        price='0',
        tif='ioc'
        )
        
        try:
            raw = await asyncio.to_thread(
                self.futures_api.create_futures_order,
                self.settle,
                order
            )
            return adapt_order(raw.to_dict())
        except GateApiException as ex:
            raise OrderError(f"Failed to sell market: {ex.message}") from ex


    async def get_positions(self) -> list[Position]:
        try:
            raw_positions = await asyncio.to_thread(
                self.futures_api.list_positions,
                self.settle
            )
            
            positions = []
            for raw in raw_positions:
                pos = adapt_position(raw.to_dict())
                if pos:
                    positions.append(pos)
            
            return positions
        except GateApiException as ex:
            raise OrderError(f"Failed to get positions: {ex.message}") from ex


    async def get_balance(self) -> Balance:
        try:
            account = await asyncio.to_thread(
                self.futures_api.list_futures_accounts,
                self.settle
            )
            return adapt_balance(account.to_dict())
        except GateApiException as ex:
            raise OrderError(f"Failed to get balance: {ex.message}") from ex


    async def get_funding_rate(self, symbol: str) -> FundingRate:
        contract = self._symbol_to_contract(symbol)
        
        try:
            raw = await asyncio.to_thread(
                self.futures_api.list_futures_funding_rate_history,
                self.settle,
                contract,
                limit=1
            )
            
            if not raw:
                raise OrderError(f"No funding rate data for {symbol}")
            
            return adapt_funding_rate(raw[0].to_dict(), symbol)
        except GateApiException as ex:
            raise OrderError(f"Failed to get funding rate for {symbol}: {ex.message}") from ex


    async def get_orderbook(self, symbol: str, depth: int = 20) -> Orderbook:
        contract = self._symbol_to_contract(symbol)
        
        try:
            raw = await asyncio.to_thread(
                self.futures_api.list_futures_order_book,
                self.settle,
                contract,
                limit=depth
            )
            return adapt_orderbook(raw.to_dict(), symbol)
        except GateApiException as ex:
            raise OrderError(f"Failed to get orderbook for {symbol}: {ex.message}") from ex


    async def get_24h_volume(self, symbol: str) -> Volume24h:
        contract = self._symbol_to_contract(symbol)
        
        try:
            raw = await asyncio.to_thread(
                self.futures_api.list_futures_tickers,
                self.settle,
                contract=contract
            )
            
            if not raw:
                raise OrderError(f"No ticker data for {symbol}")
            
            return adapt_volume_24h(raw[0].to_dict(), symbol)
        except GateApiException as ex:
            raise OrderError(f"Failed to get 24h volume for {symbol}: {ex.message}") from ex

    async def estimate_fill_price(self, symbol: str, size: float, side: PositionSide, depth: int = 100) -> Decimal:
        book = self.orderbook_monitor.get_orderbook(symbol)
        
        if not book:
            book = await self.get_orderbook(symbol, depth=min(depth, 50))
        
        levels = book.asks if side == PositionSide.LONG else book.bids
        
        if not levels:
            raise OrderError(f"No orderbook data for {symbol}")
        
        remaining = Decimal(str(abs(size)))
        total_cost = Decimal('0')
        filled = Decimal('0')
        
        for level in levels:
            if remaining <= 0:
                break
        
            fill = min(remaining, level.size)
            total_cost += fill * level.price
            filled += fill
            remaining -= fill
        
        if remaining > 0:
            last_level = levels[-1]
            slippage_factor = Decimal('1.005') if side == PositionSide.LONG else Decimal('0.995')
            extrapolated_price = last_level.price * slippage_factor
            
            total_cost += remaining * extrapolated_price
            filled += remaining
        
        return total_cost / filled
