# dashboard/textdashboard.py
import asyncio
import time
import os
from datetime import datetime
from tabulate import tabulate

from utils.public import check_table_and_fresh_data
from live.live_engine import handle_live_symbol, trackers
from utils.logger import log
from config.settings import load_config
from utils.position_utils import get_real_positions
from utils.position_tracker import PositionTracker
from bpx.account import Account
from utils.get_market import get_market

# --- CONFIGURATION ---
config = load_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

dashboard_refresh_interval = getattr(config.performance, "dashboard_refresh_interval", 2)
API_CALL_INTERVAL = getattr(config.performance, "api_call_interval", 5)
SYMBOLS_CHECK_INTERVAL = getattr(config.performance, "symbols_check_interval", 30)

account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)


class OptimizedDashboard:
    def __init__(self, symbols_container, pool, real_run, dry_run, args):
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

    def _get_handle_live_symbol(self):
        if self._handle_live_symbol is None:
            self._handle_live_symbol = handle_live_symbol
        return self._handle_live_symbol

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
        if symbol in self.last_api_call:
            if current_time - self.last_api_call[symbol] < API_CALL_INTERVAL:
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
                    pnl_pct = result.get("pnl", 0.0)

                    # Création ou récupération du tracker
                    if symbol not in self.position_trackers:
                        self.position_trackers[symbol] = PositionTracker(symbol)
                    tracker = self.position_trackers[symbol]

                    # Ouvrir le tracker si position pas déjà ouverte
                    if side.lower() == "long" and not tracker.is_open():
                        tracker.open("BUY", entry, datetime.utcnow())
                    elif side.lower() == "short" and not tracker.is_open():
                        tracker.open("SELL", entry, datetime.utcnow())

                    # Mettre à jour le trailing stop
                    tracker.update_trailing_stop(price, datetime.utcnow())

                    # Calcul PnL USD
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

                    # Stocker dans open_positions pour affichage
                    self.open_positions[symbol] = {
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry,
                        "pnl": pnl_pct,
                        "amount": amount,
                        "duration": result.get("duration", "0s"),
                        "trailing_stop": tracker.trailing_stop,  # <-- prend la valeur du tracker
                        "pnl_usdc": pnl_usdc,
                        "ret_pct": ret_pct,
                    }

                    # Ajouter à trade events
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

    async def handle_live_symbol_with_pool(self, symbol):
        try:
            return await handle_live_symbol(symbol, self.pool, self.real_run, self.dry_run, args=self.args)
        except Exception as e:
            log(f"[ERROR] handle_live_symbol_with_pool: {e}", level="ERROR")
            await asyncio.sleep(API_CALL_INTERVAL)
            return None

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


async def refresh_dashboard():
    """
    Rafraîchit le dashboard toutes les X secondes.
    """
    dashboard = OptimizedDashboard({}, None, True, False, {})
    await dashboard.render_dashboard()


async def refresh_positions():
    """
    Récupère les positions réelles et met à jour les trackers.
    """
    positions = await get_real_positions()
    for pos in positions:
        symbol = pos['symbol']
        side = pos['side']
        entry_price = float(pos['entry_price'])
        amount = float(pos['amount'])
        current_price = float(pos['mark_price'])

        handle_live_symbol(symbol, current_price, side, entry_price, amount)

async def display_dashboard_loop():
    while True:
        await refresh_positions()
        table_data = []
        total_pnl = 0.0

        for symbol, tracker in trackers.items():
            # Utiliser le prix actuel pour PnL
            current_price = tracker.max_price if tracker.side == "long" else tracker.min_price
            pnl_usd, pnl_percent = tracker.get_unrealized_pnl(current_price)
            total_pnl += pnl_usd

            table_data.append([
                symbol,
                tracker.side,
                f"{tracker.entry_price:.2f}",
                f"{pnl_percent:.2f}%",
                f"${pnl_usd:.2f}",
                tracker.amount,
                f"${tracker.get_trailing_stop():.2f}" if tracker.get_trailing_stop() else "N/A"
            ])

        os.system('clear' if os.name == 'posix' else 'cls')
        print("="*110)
        print(f"🚀 POSITIONS OUVERTES - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"💰 PnL Total: ${total_pnl:.2f}")
        print("="*110)
        print(tabulate(table_data, headers=["Symbol", "Side", "Entry", "PnL%", "PnL$", "Amount", "Trailing Stop"]))
        print("="*110)
        await asyncio.sleep(1)  # rafraîchissement chaque seconde

def main():
    try:
        asyncio.run(display_dashboard_loop())
    except KeyboardInterrupt:
        log("Dashboard stopped by user.")

if __name__ == "__main__":
    main()
