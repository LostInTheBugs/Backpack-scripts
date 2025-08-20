# dashboard/textdashboard.py
import asyncio
import time
import os
from datetime import datetime
from tabulate import tabulate

from utils.public import check_table_and_fresh_data
from utils.logger import log
from utils.position_utils import get_real_positions, PositionTracker
from config.settings import load_config
from bpx.account import Account

config = load_config()
account = Account(api_key=config.bpx_bot_public_key, api_secret=config.bpx_bot_secret_key)

API_CALL_INTERVAL = 1  # secondes entre appels API pour chaque symbole
SYMBOLS_CHECK_INTERVAL = 10  # secondes entre vérifications des symboles
dashboard_refresh_interval = 2  # secondes entre rafraîchissements du dashboard

async def refresh_dashboard(dashboard: "OptimizedDashboard"):
    while True:
        try:
            await dashboard.check_symbols_status()
            tasks = [dashboard.process_symbol_with_throttling(sym) for sym in dashboard.active_symbols]
            await asyncio.gather(*tasks)
        except Exception as e:
            log(f"Erreur dans refresh_dashboard: {e}", level="ERROR")
        await asyncio.sleep(dashboard_refresh_interval)

class OptimizedDashboard:
    def __init__(self, symbols_container, pool, real_run=False, dry_run=False, args=None):
        self.symbols_container = symbols_container
        self.pool = pool
        self.real_run = real_run
        self.dry_run = dry_run
        self.args = args

        self.trade_events = []
        self.open_positions = {}
        self.position_trackers = {}  # <-- trackers par symbole
        self.active_symbols = []
        self.ignored_symbols = []

        self.last_api_call = {}
        self.last_symbols_check = 0
        self.processing_symbols = set()

        pool_size = getattr(config.database, "pool_max_size", 20)
        reserve_connections = 3
        calculated_limit = max(5, min(15, pool_size - reserve_connections))
        self.max_concurrent_symbols = getattr(config.performance, "max_concurrent_symbols", calculated_limit)
        self.symbol_semaphore = asyncio.Semaphore(self.max_concurrent_symbols)

        log(f"Max concurrent symbols set to: {self.max_concurrent_symbols} (pool_max_size: {pool_size})", level="INFO")
        self._handle_live_symbol = None

    async def load_initial_positions(self):
        try:
            positions = await get_real_positions(account)
            for pos in positions:
                self.open_positions[pos["symbol"]] = pos
            log(f"Loaded {len(self.open_positions)} open positions at startup", level="INFO")
        except Exception as e:
            log(f"Failed to load initial open positions: {e}", level="WARNING")

    async def check_symbols_status(self):
        current_time = time.time()
        if current_time - self.last_symbols_check < SYMBOLS_CHECK_INTERVAL:
            return

        self.last_symbols_check = current_time
        symbols = self.symbols_container.get("list", [])

        new_active = []
        new_ignored = []

        for symbol in symbols:
            try:
                if await check_table_and_fresh_data(self.pool, symbol, max_age_seconds=getattr(config.database, "max_age_seconds", 60)):
                    new_active.append(symbol)
                else:
                    new_ignored.append(symbol)
            except Exception as e:
                new_ignored.append(symbol)
                log(f"[ERROR] check_table_and_fresh_data {symbol}: {e}", level="ERROR")

        self.active_symbols = new_active
        self.ignored_symbols = new_ignored
        log(f"Symbols status updated: {len(new_active)} active, {len(new_ignored)} ignored", level="DEBUG")

    async def process_symbol_with_throttling(self, symbol):
        current_time = time.time()
        if symbol in self.last_api_call and current_time - self.last_api_call[symbol] < API_CALL_INTERVAL:
            return
        if symbol in self.processing_symbols:
            return

        async with self.symbol_semaphore:
            self.processing_symbols.add(symbol)
            try:
                self.last_api_call[symbol] = current_time
                if self._handle_live_symbol is None:
                    from live.live_engine import get_handle_live_symbol
                    self._handle_live_symbol = get_handle_live_symbol

                result = await self._handle_live_symbol(symbol, self.pool, self.real_run, self.dry_run, self.args)
                if result:
                    side = result.get("side", "N/A")
                    entry = result.get("entry_price", 0.0)
                    amount = result.get("amount", 0.0)
                    price = result.get("price", 0.0)
                    pnl_pct = result.get("pnl", 0.0)

                    if symbol not in self.position_trackers:
                        self.position_trackers[symbol] = PositionTracker(symbol)
                    tracker = self.position_trackers[symbol]

                    if side.lower() == "long" and not tracker.is_open():
                        tracker.open("BUY", entry, datetime.utcnow())
                    elif side.lower() == "short" and not tracker.is_open():
                        tracker.open("SELL", entry, datetime.utcnow())

                    tracker.update_trailing_stop(price, datetime.utcnow())

                    if entry > 0 and amount > 0 and price > 0:
                        if side.lower() == "long":
                            pnl_usdc = (price - entry) * amount
                            ret_pct = (price - entry) / entry * 100
                        elif side.lower() == "short":
                            pnl_usdc = (entry - price) * amount
                            ret_pct = (entry - price) / entry * 100
                        else:
                            pnl_usdc = ret_pct = 0.0
                    else:
                        pnl_usdc = ret_pct = 0.0

                    self.open_positions[symbol] = {
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry,
                        "pnl": pnl_pct,
                        "amount": amount,
                        "duration": result.get("duration", "0s"),
                        "trailing_stop": tracker.trailing_stop,
                        "pnl_usdc": pnl_usdc,
                        "ret_pct": ret_pct,
                    }

                    action = result.get("signal", None)
                    if action in ["BUY", "SELL"]:
                        self.trade_events.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "symbol": symbol,
                            "action": action,
                            "price": price
                        })
                        self.trade_events = self.trade_events[-20:]
                else:
                    self.open_positions.pop(symbol, None)
            except Exception as e:
                log(f"[ERROR] Impossible de traiter {symbol}: {e}", level="ERROR")
            finally:
                self.processing_symbols.discard(symbol)

    async def render_dashboard(self):
        while True:
            try:
                await asyncio.sleep(dashboard_refresh_interval)
                os.system("clear")
                print(f"=== DASHBOARD ({datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC) ===")
                print(f"Active symbols: {len(self.active_symbols)}, Ignored symbols: {len(self.ignored_symbols)}\n")

                if self.open_positions:
                    positions_data = []
                    for p in self.open_positions.values():
                        positions_data.append([
                            p.get("symbol", "N/A"),
                            p.get("side", "N/A"),
                            f'{p.get("entry_price", 0.0):.6f}',
                            f'{p.get("pnl", 0.0):.2f}%',
                            f'{p.get("pnl_usdc", 0.0):.2f}$',
                            f'{p.get("ret_pct", 0.0):.2f}%',
                            p.get("amount", 0.0),
                            p.get("duration", "0s"),
                            f'{p.get("trailing_stop", 0.0):.6f}'
                        ])
                    print(tabulate(
                        positions_data,
                        headers=["Symbol", "Side", "Entry", "PnL%", "PnL$", "ret%", "Amount", "Duration", "Trailing Stop"],
                        tablefmt="fancy_grid"
                    ))
                else:
                    print("No open positions yet.")
            except Exception as e:
                log(f"Erreur dans render_dashboard: {e}", level="ERROR")
                await asyncio.sleep(5)
