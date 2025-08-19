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
from bpx.account import Account
from utils.get_market import get_market

config = load_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)

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

        # Cache
        self.trade_events = []
        self.open_positions = {}
        self.active_symbols = []
        self.ignored_symbols = []

        # Timing
        self.last_api_call = {}
        self.last_symbols_check = 0
        self.processing_symbols = set()

        # Concurrence
        pool_size = getattr(config.database, 'pool_max_size', 20)
        reserve_connections = 3
        calculated_limit = max(5, min(15, pool_size - reserve_connections))
        self.max_concurrent_symbols = getattr(getattr(config, 'performance', {}), 'max_concurrent_symbols', calculated_limit)
        self.symbol_semaphore = asyncio.Semaphore(self.max_concurrent_symbols)

        log(f"Max concurrent symbols: {self.max_concurrent_symbols}", level="INFO")
        self._handle_live_symbol = None

    def _get_handle_live_symbol(self):
        if self._handle_live_symbol is None:
            self._handle_live_symbol = get_handle_live_symbol()
        return self._handle_live_symbol

    async def load_initial_positions(self):
        try:
            positions = await get_real_positions(account)
            for pos in positions:
                self.open_positions[pos["symbol"]] = pos
            log(f"Loaded {len(self.open_positions)} open positions at startup", level="INFO")
        except Exception as e:
            log(f"Failed to load initial positions: {e}", level="WARNING")

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
        log(f"Symbols updated: {len(new_active)} active, {len(new_ignored)} ignored", level="DEBUG")

    # ---------------- SYMBOL PROCESSING ----------------
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
                result = await self.handle_live_symbol_with_pool(symbol)
                if result:
                    side = result.get("side", "N/A")
                    entry = result.get("entry_price", 0.0)
                    amount = result.get("amount", 0.0)
                    price = result.get("price", 0.0)
                    duration = result.get("duration", "0s")
                    trailing_stop = result.get("trailing_stop", 0.0)

                    # Calcul PnL% et PnL$
                    if entry > 0 and amount > 0 and price > 0:
                        if side.lower() == "long":
                            pnl_usdc = (price - entry) * amount
                            pnl_pct = (price - entry) / entry * 100
                        elif side.lower() == "short":
                            pnl_usdc = (entry - price) * amount
                            pnl_pct = (entry - price) / entry * 100
                        else:
                            pnl_usdc = 0.0
                            pnl_pct = 0.0
                    else:
                        pnl_usdc = 0.0
                        pnl_pct = 0.0

                    self.open_positions[symbol] = {
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry,
                        "pnl": pnl_pct,
                        "amount": amount,
                        "duration": duration,
                        "trailing_stop": trailing_stop,
                        "pnl_usdc": pnl_usdc,
                        "ret_pct": pnl_pct
                    }

                    action = result.get("signal", None)
                    if action in ["BUY", "SELL"]:
                        self.trade_events.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "symbol": symbol,
                            "action": action,
                            "price": price
                        })
                        if len(self.trade_events) > 20:
                            self.trade_events = self.trade_events[-20:]
                else:
                    self.open_positions.pop(symbol, None)
            except Exception as e:
                log(f"[ERROR] Cannot process {symbol}: {e}", level="ERROR")
            finally:
                self.processing_symbols.discard(symbol)

    async def handle_live_symbol_with_pool(self, symbol):
        try:
            handle_live_symbol = self._get_handle_live_symbol()
            return await handle_live_symbol(symbol, self.pool, self.real_run, self.dry_run, args=self.args)
        except Exception as e:
            if "too many clients" in str(e).lower():
                log(f"[ERROR] Connection pool exhausted for {symbol}, retry later", level="ERROR")
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

                tasks = []
                for i, symbol in enumerate(active_symbols):
                    delay = (i * API_CALL_INTERVAL) / len(active_symbols) if active_symbols else 0
                    tasks.append(asyncio.create_task(self._process_symbol_delayed(symbol, delay)))

                if tasks:
                    try:
                        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=API_CALL_INTERVAL * 2)
                    except asyncio.TimeoutError:
                        log("Some API calls timed out", level="WARNING")

                await asyncio.sleep(max(1, API_CALL_INTERVAL // 2))
            except Exception as e:
                log(f"[ERROR] symbol_processor: {e}", level="ERROR")
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

                print("\n=== OPEN POSITIONS ===")
                if self.open_positions:
                    positions_data = []
                    for p in self.open_positions.values():
                        positions_data.append([
                            p.get("symbol", "N/A"),
                            p.get("side", "N/A"),
                            f'{p.get("entry_price", 0.0):.6f}',
                            f'{p.get("pnl", 0.0):.2f}%',
                            f'{p.get("pnl_usdc", 0.0):.2f}$',
                            f'({p.get("ret_pct", 0.0):.2f}%)',
                            p.get("amount", 0.0),
                            p.get("duration", "0s"),
                            f'{p.get("trailing_stop", 0.0):.2f}%'
                        ])
                    print(tabulate(positions_data, headers=["Symbol", "Side", "Entry", "PnL%", "PnL$", "ret%", "Amount", "Duration", "Trailing Stop"], tablefmt="fancy_grid"))
                else:
                    print("No open positions yet.")

                print("\n=== TRADE EVENTS ===")
                if self.trade_events:
                    print(tabulate(self.trade_events[-10:], headers="keys", tablefmt="fancy_grid"))
                else:
                    print("No trades yet.")

            except Exception as e:
                log(f"Erreur render_dashboard: {e}", level="ERROR")
                await asyncio.sleep(5)

async def refresh_dashboard(latest_positions: dict):
    """
    Affiche les positions ouvertes avec PnL mis à jour en temps réel.
    latest_positions : dict[symbol -> dict] contenant entry_price, side, amount, trailing_stop, pnl, current_price
    """
    from tabulate import tabulate
    import os

    # Efface l'écran pour un affichage "dashboard"
    os.system("cls" if os.name == "nt" else "clear")
    print("\n=== OPEN POSITIONS ===")

    if not latest_positions:
        print("No open positions yet.")
        return

    positions_data = []
    for p in latest_positions.values():
        symbol = p.get("symbol", "N/A")
        side = p.get("side", "N/A")
        entry_price = p.get("entry_price", 0.0)
        pnl_pct = p.get("pnl", 0.0)        # PnL %
        pnl_usdc = p.get("pnl_usdc", 0.0)  # PnL en USDC
        ret_pct = p.get("ret_pct", 0.0)    # Retour réel %
        amount = p.get("amount", 0.0)
        duration = p.get("duration", "0s")
        trailing_stop = p.get("trailing_stop", 0.0)

        positions_data.append([
            symbol,
            side,
            f"{entry_price:.6f}",
            f"{pnl_pct:.2f}%",
            f"{pnl_usdc:.2f}$",
            f"{ret_pct:.2f}%",
            amount,
            duration,
            f"{trailing_stop:.2f}%"
        ])

    table = tabulate(
        positions_data,
        headers=["Symbol", "Side", "Entry", "PnL%", "PnL$", "ret%", "Amount", "Duration", "Trailing Stop"],
        tablefmt="fancy_grid"
    )
    print(table)