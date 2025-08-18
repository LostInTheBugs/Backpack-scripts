#main.py
import argparse
import os
import traceback
import asyncio
from datetime import datetime, timezone
import asyncpg
import signal
import sys
from tabulate import tabulate

from utils.logger import log
from utils.public import check_table_and_fresh_data, get_last_timestamp, load_symbols_from_file
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from live.live_engine import handle_live_symbol
from backtest.backtest_engine import run_backtest_async, parse_backtest
from config.settings import load_config
from utils.update_symbols_periodically import update_symbols_periodically
from utils.watch_symbols_file import watch_symbols_file
from utils.i18n import t, set_locale, get_available_locales

# Charge la config au démarrage
config = load_config()

public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

# Sécurise auto_symbols avec gestion d'erreur améliorée
try:
    auto_symbols_result = fetch_top_n_volatility_volume(n=getattr(config.strategy, "auto_select_top_n", 10))
    auto_symbols = auto_symbols_result if auto_symbols_result is not None else []
    log(f"Auto symbols récupérés avec succès: {auto_symbols}", level="DEBUG")
except Exception as e:
    log(f"Erreur lors de la récupération des auto_symbols: {e}", level="ERROR")
    auto_symbols = []

# Vérifier si include et exclude existent dans la config
include_symbols = getattr(config.strategy, 'include', []) or []
exclude_symbols = getattr(config.strategy, 'exclude', []) or []

log(f"Auto symbols: {auto_symbols}", level="DEBUG")
log(f" Include symbols: {include_symbols}", level="DEBUG")
log(f" Exclude symbols: {exclude_symbols}", level="DEBUG")

# On fusionne avec include (ajoute les symboles forcés)
all_symbols = list(set(auto_symbols + include_symbols))

# On applique le filtre exclude (retire les symboles interdits)
final_symbols = [s for s in all_symbols if s not in exclude_symbols]

log(f" Final symbols: {final_symbols}", level="DEBUG")

symbols_container = {'list': final_symbols}

# Lance le thread de mise à jour périodique des symboles (thread daemon)
update_symbols_periodically(symbols_container)

async def main_loop_textdashboard(symbols: list, pool, real_run: bool, dry_run: bool, symbols_container=None):
    """
    Boucle principale pour le dashboard texte en live.
    Affiche :
        - Symbols actifs
        - Trade events récents
        - Open positions
    """
    trade_events = []        # stockage des derniers trades
    open_positions = {}      # positions ouvertes par symbol

    if symbols_container is None:
        symbols_container = {"list": symbols}

    async def handle_symbol(symbol):
        """
        Gère les trades pour un symbol et met à jour trade_events / open_positions
        """
        while True:
            await asyncio.sleep(1)  # vérifie toutes les secondes

            try:
                # récupère le signal et l'état de la position depuis ton moteur live
                result = await handle_live_symbol(symbol, pool, real_run, dry_run, args=args)

                if result:
                    action = result.get("signal", "N/A")
                    price = result.get("price", 0.0)
                    pnl = result.get("pnl", 0.0)  # % ou valeur selon ton moteur
                    amount = result.get("amount", 0.0)
                    duration = result.get("duration", "0s")
                    trailing_stop = result.get("trailing_stop", 0.0)

                    # Ajoute le trade_event si un signal est présent
                    if action in ["BUY", "SELL"]:
                        trade_events.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "symbol": symbol,
                            "action": action,
                            "price": price
                        })

                    # Met à jour open_positions
                    open_positions[symbol] = {
                        "symbol": symbol,
                        "pnl": pnl,
                        "amount": amount,
                        "duration": duration,
                        "trailing_stop": trailing_stop
                    }
                else:
                    # supprime la position si fermée
                    if symbol in open_positions:
                        del open_positions[symbol]

            except Exception as e:
                log(f"[ERROR] Impossible de traiter {symbol}: {e}", level="ERROR")

    async def render_dashboard():
        """
        Redessine le dashboard toutes les secondes
        """
        while True:
            await asyncio.sleep(1)
            if symbols_container:
                symbols = symbols_container.get("list", [])

            active_symbols = []
            ignored_symbols = []

            # vérification symboles actifs
            for symbol in symbols:
                try:
                    if await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
                        active_symbols.append(symbol)
                    else:
                        ignored_symbols.append(symbol)
                except Exception as e:
                    ignored_symbols.append(symbol)
                    log(f"[ERROR] check_table_and_fresh_data {symbol}: {e}", level="ERROR")

            # clear terminal
            os.system("clear")

            # === SYMBOLS ===
            print("=== SYMBOLS ===")
            print(tabulate([
                ["Active", ", ".join(active_symbols)],
                ["Ignored", ", ".join(ignored_symbols)]
            ], headers=["Status", "Symbols"], tablefmt="fancy_grid"))

            # === TRADE EVENTS ===
            print("\n=== TRADE EVENTS ===")
            if trade_events:
                print(tabulate(trade_events[-10:], headers="keys", tablefmt="fancy_grid"))
            else:
                print("No trades yet.")

            # === OPEN POSITIONS ===
            print("\n=== OPEN POSITIONS ===")
            if open_positions:
                print(tabulate(
                    [[p["symbol"], f'{p["pnl"]:.2f}%', p["amount"], p["duration"], f'{p["trailing_stop"]}%']
                     for p in open_positions.values()],
                    headers=["Symbol", "PnL", "Amount", "Duration", "Trailing Stop"], tablefmt="fancy_grid"))
            else:
                print("No open positions yet.")

    # Crée une task pour chaque symbol
    tasks = [asyncio.create_task(handle_symbol(sym)) for sym in symbols_container.get("list", [])]
    tasks.append(asyncio.create_task(render_dashboard()))

    await asyncio.gather(*tasks)


async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False, symbols_container=None):
    while True:
        if auto_select and symbols_container:
            symbols = symbols_container.get('list', [])
            log(f" Symbols list updated in main_loop: {symbols}")

        active_symbols = []
        ignored_symbols = []

        for symbol in symbols:
            if await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
                active_symbols.append(symbol)
                await handle_live_symbol(symbol, pool, real_run, dry_run, args=args)
            else:
                ignored_symbols.append(symbol)

        if active_symbols:
            log(f" Active symbols ({len(active_symbols)}): {active_symbols}", level="INFO")

        ignored_details = []
        if ignored_symbols:
            for sym in ignored_symbols:
                last_ts = await get_last_timestamp(pool, sym)
                if last_ts is None:
                    ignored_details.append(f"{sym} (table missing)")
                else:
                    now = datetime.now(timezone.utc)
                    delay = now - last_ts
                    seconds = int(delay.total_seconds())
                    human_delay = f"{seconds}s" if seconds < 120 else f"{seconds // 60}min"
                    ignored_details.append(f"{sym} (inactive for {human_delay})")

            if ignored_details:
                log(f" Ignored symbols ({len(ignored_details)}): {ignored_details}", level="INFO")

        if not active_symbols:
            log(f" No active symbols for this iteration", level="INFO")

        await asyncio.sleep(1)


async def async_main(args):
    db_config = config.database
    pg_dsn = config.pg_dsn or os.environ.get("PG_DSN")

    pool = await asyncpg.create_pool(
        dsn=pg_dsn,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size
    )

    from utils.scan_all_symbols import scan_all_symbols  # Ajuste chemin si besoin

    # Choix des symbols à scanner
    if args.auto_select:
        initial_symbols = auto_symbols
    elif args.symbols:
        initial_symbols = args.symbols.split(",")
    else:
        initial_symbols = load_symbols_from_file()

    log(f" Initial scan of symbols before main loop: {initial_symbols}", level="DEBUG")
    await scan_all_symbols(pool, initial_symbols)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown():
        print("Manual stop requested (Ctrl+C)")
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    try:
        if args.backtest:
            # -------------------------
            # Mode backtest
            # -------------------------
            log(" Mode backtest activé", level="DEBUG")
            log(f" Backtest demandé avec valeur: {args.backtest}", level="DEBUG")
            if args.symbols:
                symbols = args.symbols.split(",")
                log(f" Symboles passés en argument: {symbols}", level="DEBUG")
            else:
                symbols = load_symbols_from_file()
                log(f" Symboles chargés depuis fichier: {symbols}", level="DEBUG")

            if not symbols:
                log(" Liste de symboles vide, backtest annulé", level="ERROR")
                return

            if isinstance(args.backtest, tuple):
                start_dt, end_dt = args.backtest
                for symbol in symbols:
                    log(f" [{symbol}] Starting backtest from {start_dt.date()} to {end_dt.date()} with {args.strategie} strategy", level="DEBUG")
                    await run_backtest_async(symbol, (start_dt, end_dt), pg_dsn, args.strategie)
            else:
                for symbol in symbols:
                    log(f" [{symbol}] Starting {args.backtest}h backtest with {args.strategie} strategy", level="DEBUG")
                    await run_backtest_async(symbol, args.backtest, pg_dsn, args.strategie)
        else:
            # -------------------------
            # Mode live
            # -------------------------
            log(" Mode live (pas de backtest)", level="DEBUG")

            # Choix du mode textdashboard ou mode classique
            if getattr(args, "mode", None) == "textdashboard":
                # Mode textdashboard
                if args.auto_select:
                    task = asyncio.create_task(
                        main_loop_textdashboard(
                            [], pool, real_run=args.real_run, dry_run=args.dry_run, symbols_container=symbols_container
                        )
                    )
                elif args.symbols:
                    symbols = args.symbols.split(",")
                    task = asyncio.create_task(
                        main_loop_textdashboard(
                            symbols, pool, real_run=args.real_run, dry_run=args.dry_run
                        )
                    )
                else:
                    task = asyncio.create_task(
                        watch_symbols_file(pool=pool, real_run=args.real_run, dry_run=args.dry_run)
                    )
            else:
                # Mode classique (main_loop normal)
                if args.auto_select:
                    task = asyncio.create_task(
                        main_loop(
                            [], pool, real_run=args.real_run, dry_run=args.dry_run, auto_select=True, symbols_container=symbols_container
                        )
                    )
                elif args.symbols:
                    symbols = args.symbols.split(",")
                    task = asyncio.create_task(
                        main_loop(symbols, pool, real_run=args.real_run, dry_run=args.dry_run)
                    )
                else:
                    task = asyncio.create_task(
                        watch_symbols_file(pool=pool, real_run=args.real_run, dry_run=args.dry_run)
                    )

            # Attente Ctrl+C ou fin de tâche
            stop_task = asyncio.create_task(stop_event.wait())
            await asyncio.wait([task, stop_task], return_when=asyncio.FIRST_COMPLETED)

    except Exception:
        traceback.print_exc()
    finally:
        await pool.close()
        log(f" Connection pool closed, program terminated", level="ERROR")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot for Backpack Exchange")
    parser.add_argument("symbols", nargs="?", default="", help="Symbol list (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Enable real execution")
    parser.add_argument("--dry-run", action="store_true", help="Simulation mode without executing trades")
    parser.add_argument("--backtest", type=parse_backtest, help="Backtest duration (ex: 10m, 2h, 3d, 1w, or just a number = minutes)")
    parser.add_argument("--auto-select", action="store_true", help="Automatic selection of most volatile symbols")
    parser.add_argument('--strategie', type=str, default=None, help='Strategy name (Default, Trix, Combo, Auto, Range, RangeSoft, ThreeOutOfFour, TwoOutOfFourScalp and DynamicThreeTwo.)')
    parser.add_argument("--no-limit", action="store_true", help="Disable symbol count limit")
    parser.add_argument("--config", type=str, default="config/settings.yaml", help="Configuration file path")
    parser.add_argument("--mode", type=str, default="text", choices=["text", "textdashboard", "webdashboard"], help="Mode d'affichage")
    args = parser.parse_args()

    if args.config != "config/settings.yaml":
        config = load_config(args.config)

    if args.strategie is None:
        args.strategie = config.strategy.default_strategy

    try:
        if args.strategie == "Trix":
            from signals.trix_only_signal import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "Combo":
            from signals.macd_rsi_bo_trix import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "RangeSoft":
            from signals.range_soft_signal import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "ThreeOutOfFour":
            from signals.three_out_of_four_conditions import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "TwoOutOfFourScalp":
            from signals.two_out_of_four_scalp import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "DynamicThreeTwo":
            from signals.dynamic_three_two_selector import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie in ["Auto", "AutoSoft", "Range"]:
            args.get_combined_signal = None
        else:
            from signals.macd_rsi_breakout import get_combined_signal
            args.get_combined_signal = get_combined_signal

        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("Manual stop requested via KeyboardInterrupt, clean shutdown...")
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)