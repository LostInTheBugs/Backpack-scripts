# dashboard/textdashboard.py
import asyncio
import time
import os

from tabulate import tabulate
from datetime import datetime
from utils.public import check_table_and_fresh_data
from live.live_engine import get_handle_live_symbol
from utils.logger import log
from config.settings import load_config
from utils.position_utils import get_real_positions

config = load_config()

# Configuration des intervalles (en secondes) - avec valeurs par défaut
API_CALL_INTERVAL = 5
DASHBOARD_REFRESH_INTERVAL = 2
SYMBOLS_CHECK_INTERVAL = 30


class OptimizedDashboard:
    def __init__(self, symbols_container, pool, real_run, dry_run, args):
        self.symbols_container = symbols_container
        self.pool = pool
        self.real_run = real_run
        self.dry_run = dry_run
        self.args = args

        # Cache des données
        self.trade_events = []
        self.open_positions = {}
        self.active_symbols = []
        self.ignored_symbols = []

        # Timestamps pour contrôler les intervalles
        self.last_api_call = {}
        self.last_symbols_check = 0

        # Verrous pour éviter les appels concurrents
        self.processing_symbols = set()

        # Limite de concurrence
        pool_size = getattr(config.database, 'pool_max_size', 20)
        reserve_connections = 3
        calculated_limit = max(5, min(15, pool_size - reserve_connections))
        if hasattr(config, 'performance') and hasattr(config.performance, 'max_concurrent_symbols'):
            self.max_concurrent_symbols = config.performance.max_concurrent_symbols
        else:
            self.max_concurrent_symbols = calculated_limit
        self.symbol_semaphore = asyncio.Semaphore(self.max_concurrent_symbols)

        log(f"Max concurrent symbols set to: {self.max_concurrent_symbols} (pool_max_size: {pool_size})", level="INFO")

        # Lazy-loaded handle_live_symbol function
        self._handle_live_symbol = None

    def _get_handle_live_symbol(self):
        if self._handle_live_symbol is None:
            self._handle_live_symbol = get_handle_live_symbol()
        return self._handle_live_symbol

    async def load_initial_positions(self):
        """
        Charge toutes les positions ouvertes existantes depuis Backpack Exchange
        au démarrage du dashboard.
        """
        try:
            positions = await get_real_positions()
            for pos in positions:
                self.open_positions[pos["symbol"]] = pos
            log(f"Loaded {len(self.open_positions)} open positions at startup", level="INFO")
        except Exception as e:
            log(f"Failed to load initial open positions: {e}", level="WARNING")

    # ---------------- SYMBOLS STATUS ----------------
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
                if await check_table_and_fresh_data(self.pool, symbol, max_age_seconds=config.database.max_age_seconds):
                    new_active.append(symbol)
                else:
                    new_ignored.append(symbol)
            except Exception as e:
                new_ignored.append(symbol)
                log(f"[ERROR] check_table_and_fresh_data {symbol}: {e}", level="ERROR")

        self.active_symbols = new_active
        self.ignored_symbols = new_ignored
        log(f"Symbols status updated: {len(new_active)} active, {len(new_ignored)} ignored", level="DEBUG")

    # ---------------- SYMBOL PROCESSING ----------------
    async def process_symbol_with_throttling(self, symbol):
        current_time = time.time()

        if symbol in self.last_api_call:
            time_since_last = current_time - self.last_api_call[symbol]
            if time_since_last < API_CALL_INTERVAL:
                return

        if symbol in self.processing_symbols:
            return

        async with self.symbol_semaphore:
            self.processing_symbols.add(symbol)
            try:
                self.last_api_call[symbol] = current_time
                result = await self.handle_live_symbol_with_pool(symbol)
                log(f"[DEBUG] handle_live_symbol({symbol}) returned: {result}")
                if result:
                    action = result.get("signal", "N/A")
                    price = result.get("price", 0.0)
                    pnl = result.get("pnl", 0.0)
                    amount = result.get("amount", 0.0)
                    duration = result.get("duration", "0s")
                    trailing_stop = result.get("trailing_stop", 0.0)

                    if action in ["BUY", "SELL"]:
                        self.trade_events.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "symbol": symbol,
                            "action": action,
                            "price": price
                        })
                        if len(self.trade_events) > 20:
                            self.trade_events = self.trade_events[-20:]

                    self.open_positions[symbol] = {
                        "symbol": symbol,
                        "pnl": pnl,
                        "amount": amount,
                        "duration": duration,
                        "trailing_stop": trailing_stop
                    }
                else:
                    if symbol in self.open_positions:
                        del self.open_positions[symbol]

            except Exception as e:
                log(f"[ERROR] Impossible de traiter {symbol}: {e}", level="ERROR")
                if "too many clients" in str(e).lower():
                    self.last_api_call[symbol] = current_time + API_CALL_INTERVAL * 2
            finally:
                self.processing_symbols.discard(symbol)

    async def handle_live_symbol_with_pool(self, symbol):
        try:
            handle_live_symbol = self._get_handle_live_symbol()
            result = await handle_live_symbol(symbol, self.pool, self.real_run, self.dry_run, args=self.args)
            return result
        except Exception as e:
            if "too many clients" in str(e).lower():
                log(f"[ERROR] Connection pool exhausted for {symbol}, will retry later", level="ERROR")
                await asyncio.sleep(API_CALL_INTERVAL)
            raise

    async def symbol_processor(self):
        while True:
            try:
                await self.check_symbols_status()
                active_symbols = self.active_symbols
                total_symbols = len(active_symbols)

                if total_symbols > self.max_concurrent_symbols:
                    current_batch = int(time.time() // (API_CALL_INTERVAL * 2)) % ((total_symbols // self.max_concurrent_symbols) + 1)
                    start_idx = current_batch * self.max_concurrent_symbols
                    end_idx = min(start_idx + self.max_concurrent_symbols, total_symbols)
                    active_symbols = active_symbols[start_idx:end_idx]
                    log(f"Processing batch {current_batch + 1}: symbols {start_idx+1}-{end_idx} of {total_symbols} total", level="INFO")
                else:
                    log(f"Processing all {total_symbols} active symbols", level="DEBUG")

                tasks = []
                for i, symbol in enumerate(active_symbols):
                    delay = (i * API_CALL_INTERVAL) / len(active_symbols) if active_symbols else 0
                    task = asyncio.create_task(self._process_symbol_delayed(symbol, delay))
                    tasks.append(task)

                if tasks:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*tasks, return_exceptions=True),
                            timeout=API_CALL_INTERVAL * 2
                        )
                    except asyncio.TimeoutError:
                        log("Some API calls timed out, continuing...", level="WARNING")

                await asyncio.sleep(max(1, API_CALL_INTERVAL // 2))
            except Exception as e:
                log(f"[ERROR] Erreur dans symbol_processor: {e}", level="ERROR")
                await asyncio.sleep(5)

    async def _process_symbol_delayed(self, symbol, delay):
        if delay > 0:
            await asyncio.sleep(delay)
        await self.process_symbol_with_throttling(symbol)

    # ---------------- DASHBOARD RENDER ----------------
    async def render_dashboard(self):
        while True:
            try:
                await asyncio.sleep(DASHBOARD_REFRESH_INTERVAL)
                os.system("clear")

                print(f"=== CONFIGURATION ===")
                print(f"API Call Interval: {API_CALL_INTERVAL}s")
                print(f"Dashboard Refresh: {DASHBOARD_REFRESH_INTERVAL}s")
                print(f"Symbols Check: {SYMBOLS_CHECK_INTERVAL}s\n")

                print("=== SYMBOLS ===")
                print(tabulate([
                    ["Active", f"{len(self.active_symbols)} symbols: {', '.join(self.active_symbols[:10])}{' ...' if len(self.active_symbols) > 10 else ''}"],
                    ["Ignored", f"{len(self.ignored_symbols)} symbols: {', '.join(self.ignored_symbols[:10])}{' ...' if len(self.ignored_symbols) > 10 else ''}"]
                ], headers=["Status", "Symbols"], tablefmt="fancy_grid"))

                print("\n=== API CALL STATUS ===")
                current_time = time.time()
                api_status = []
                max_symbols = config.performance.max_concurrent_symbols

                for symbol in self.active_symbols[:max_symbols]:
                    last_call = self.last_api_call.get(symbol, 0)
                    if last_call > 0:
                        seconds_ago = int(current_time - last_call)
                        status = "Processing" if symbol in self.processing_symbols else f"Last call: {seconds_ago}s ago"
                        api_status.append([symbol, status])
                    else:
                        api_status.append([symbol, "No calls yet"])

                if api_status:
                    print(tabulate(api_status, headers=["Symbol", "API Status"], tablefmt="fancy_grid"))
                else:
                    print("No API calls tracked yet.")

                print("\n=== TRADE EVENTS ===")
                if self.trade_events:
                    print(tabulate(self.trade_events[-10:], headers="keys", tablefmt="fancy_grid"))
                else:
                    print("No trades yet.")

                print("\n=== OPEN POSITIONS ===")
                if self.open_positions:
                    positions_data = []
                    for p in self.open_positions.values():
                        positions_data.append([
                            p["symbol"],
                            f'{p["pnl"]:.2f}%',
                            p["amount"],
                            p["duration"],
                            f'{p["trailing_stop"]}%'
                        ])
                    print(tabulate(
                        positions_data,
                        headers=["Symbol", "PnL", "Amount", "Duration", "Trailing Stop"],
                        tablefmt="fancy_grid"
                    ))
                else:
                    print("No open positions yet.")

                print(f"\n=== STATS ===")
                print(f"Total symbols: {len(self.active_symbols + self.ignored_symbols)}")
                print(f"Active symbols: {len(self.active_symbols)}")
                print(f"Ignored symbols: {len(self.ignored_symbols)}")
                print(f"Max concurrent processing: {self.max_concurrent_symbols}")
                print(f"Total API calls tracked: {len(self.last_api_call)}")
                print(f"Symbols currently processing: {len(self.processing_symbols)}")
                print(f"Pool size: {config.database.pool_min_size}-{config.database.pool_max_size}")
                print(f"Last symbols check: {int(current_time - self.last_symbols_check)}s ago")

                if len(self.active_symbols) > self.max_concurrent_symbols:
                    total_batches = (len(self.active_symbols) // self.max_concurrent_symbols) + 1
                    current_batch = int(current_time // (API_CALL_INTERVAL * 2)) % total_batches
                    print(f"Batch rotation: {current_batch + 1}/{total_batches} (changes every {API_CALL_INTERVAL * 2}s)")

            except Exception as e:
                log(f"Erreur dans render_dashboard: {e}", level="ERROR")
                await asyncio.sleep(5)


# ---------------- MAIN LOOP ----------------
async def main_loop_textdashboard(symbols: list, pool, real_run: bool, dry_run: bool, symbols_container=None, args=None):
    if symbols_container is None:
        symbols_container = {"list": symbols}

    dashboard = OptimizedDashboard(symbols_container, pool, real_run, dry_run, args)

    # Charger les positions ouvertes existantes avant de lancer les tâches
    await dashboard.load_initial_positions()

    # Créer les tâches
    processor_task = asyncio.create_task(dashboard.symbol_processor())
    render_task = asyncio.create_task(dashboard.render_dashboard())

    await asyncio.gather(processor_task, render_task)
