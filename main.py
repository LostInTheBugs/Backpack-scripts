import argparse
import os
import traceback
import asyncio
from datetime import datetime, timezone
import asyncpg
import signal
import sys
import re

from utils.logger import log
from utils.public import check_table_and_fresh_data, get_last_timestamp, load_symbols_from_file
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from live.live_engine import handle_live_symbol
from backtest.backtest_engine2 import run_backtest_async
from config.settings import load_config, get_config
from utils.symbol_filter import filter_symbols_by_config
from utils.update_symbols_periodically import start_symbol_updater  # Import thread



# Charge la config au démarrage
config = load_config()

public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

auto_symbols = fetch_top_n_volatility_volume(n=config.strategy.auto_select_top_n)

# Vérifier si include et exclude existent dans la config
include_symbols = getattr(config.strategy, 'include', [])
exclude_symbols = getattr(config.strategy, 'exclude', [])

log(f"[DEBUG] Auto symbols: {auto_symbols}", level="DEBUG")
log(f"[DEBUG] Include symbols: {include_symbols}", level="DEBUG")
log(f"[DEBUG] Exclude symbols: {exclude_symbols}", level="DEBUG")

# On fusionne avec include (ajoute les symboles forcés)
all_symbols = list(set(auto_symbols + include_symbols))

# On applique le filtre exclude (retire les symboles interdits)
final_symbols = [s for s in all_symbols if s not in exclude_symbols]

log("[DEBUG] Final symbols: {final_symbols}", level="DEBUG")

symbols_container = {'list': final_symbols}

# Lance le thread de mise à jour périodique des symboles (thread daemon)
start_symbol_updater(symbols_container)


def parse_backtest(value):
    if ":" in value and re.match(r"^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$", value):
        start_str, end_str = value.split(":")
        from datetime import datetime
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d")
        if start_dt >= end_dt:
            raise argparse.ArgumentTypeError("La date de début doit être avant la date de fin.")
        return (start_dt, end_dt)

    match = re.match(r"^(\d+)([smhdw]?)$", value.lower())
    if not match:
        raise argparse.ArgumentTypeError(
            "Format invalide. Utilise par ex: 10m, 2h, 3d, 1w, juste un nombre (minutes), "
            "ou plage de dates YYYY-MM-DD:YYYY-MM-DD"
        )
    amount, unit = match.groups()
    amount = int(amount)
    multipliers_in_hours = {
        "": 1/60,  # minutes par défaut
        "s": 1/3600,
        "m": 1/60,
        "h": 1,
        "d": 24,
        "w": 168
    }
    return amount * multipliers_in_hours[unit]


async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False, symbols_container=None):
    while True:
        if auto_select and symbols_container:
            symbols = symbols_container.get('list', [])
            log(f"[DEBUG] Symbols list updated in main_loop: {symbols}")

        active_symbols = []
        ignored_symbols = []

        for symbol in symbols:
            if await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
                active_symbols.append(symbol)
                await handle_live_symbol(symbol, pool, real_run, dry_run, args=args)
            else:
                ignored_symbols.append(symbol)

        if active_symbols:
            log(f"Active symbols ({len(active_symbols)}): {active_symbols}")

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
                log(f"Ignored symbols ({len(ignored_details)}): {ignored_details}")

        if not active_symbols:
            log("No active symbols for this iteration")

        await asyncio.sleep(1)


async def watch_symbols_file(filepath: str = "symbol.lst", pool=None, real_run: bool = False, dry_run: bool = False):
    last_modified = None
    symbols = []

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                symbols = load_symbols_from_file(filepath)
                symbols = filter_symbols_by_config(symbols)
                log(f"Symbol file reloaded: {symbols}")
                last_modified = current_modified

            await main_loop(symbols, pool, real_run=real_run, dry_run=dry_run)
        except KeyboardInterrupt:
            log("Manual stop requested")
            break
        except Exception as e:
            log(f"Error in watcher: {e}")
            traceback.print_exc()

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
        initial_symbols = auto_symbols  # liste volatile auto récupérée en début main.py
    elif args.symbols:
        initial_symbols = args.symbols.split(",")
    else:
        initial_symbols = load_symbols_from_file()

    log(f"[DEBUG] Initial scan of symbols before main loop: {initial_symbols}", level="DEBUG")
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
            log("[DEBUG] Mode backtest activé", level="DEBUG")
            log(f"[DEBUG] Backtest demandé avec valeur: {args.backtest}", level="DEBUG")
            if args.symbols:
                symbols = args.symbols.split(",")
                log(f"[DEBUG] Symboles passés en argument: {symbols}", level="DEBUG")
            else:
                symbols = load_symbols_from_file()
                log(f"[DEBUG] Symboles chargés depuis fichier: {symbols}", level="DEBUG")

            if not symbols:
                log("[ERROR] Liste de symboles vide, backtest annulé", level="ERROR")
                return

            if isinstance(args.backtest, tuple):
                start_dt, end_dt = args.backtest
                for symbol in symbols:
                    log(f"[{symbol}] Starting backtest from {start_dt.date()} to {end_dt.date()} with {args.strategie} strategy")
                    log(f"[DEBUG] Lancement backtest {symbol} de {start_dt.date()} à {end_dt.date()}", level="DEBUG")
                    await run_backtest_async(symbol, (start_dt, end_dt), pg_dsn, args.strategie)
            else:
                for symbol in symbols:
                    log(f"[{symbol}] Starting {args.backtest}h backtest with {args.strategie} strategy")
                    log(f"[DEBUG] Lancement backtest {symbol} pendant {args.backtest} heures", level="DEBUG")
                    await run_backtest_async(symbol, args.backtest, pg_dsn, args.strategie)
        else:
            log("[DEBUG] Mode live (pas de backtest)", level="DEBUG")
            if args.auto_select:
                # Ne lance PAS update_symbols_periodically ici car thread déjà lancé
                task = asyncio.create_task(
                    main_loop([], pool, real_run=args.real_run, dry_run=args.dry_run, auto_select=True, symbols_container=symbols_container)
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

            stop_task = asyncio.create_task(stop_event.wait())
            await asyncio.wait([task, stop_task], return_when=asyncio.FIRST_COMPLETED)
    except Exception:
        traceback.print_exc()
    finally:
        await pool.close()
        print("Connection pool closed, program terminated")


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
    args = parser.parse_args()

    # Recharge config si chemin personnalisé
    if args.config != "config/settings.yaml":
        config = load_config(args.config)

    # Utilise la stratégie par défaut si non passée en CLI
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
