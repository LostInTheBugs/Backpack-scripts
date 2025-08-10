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

# Load configuration at startup
config = load_config()

public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")


def parse_backtest(value):
    """
    Parse le format du backtest:
    - Durée: 10m, 2h, 3d, 1w, ou juste un nombre (minutes par défaut) → retourne nombre d'heures (float)
    - Plage de dates: YYYY-MM-DD:YYYY-MM-DD → retourne tuple (datetime_start, datetime_end)
    """
    # Test si c'est une plage de dates
    if ":" in value and re.match(r"^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$", value):
        start_str, end_str = value.split(":")
        from datetime import datetime
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d")
        if start_dt >= end_dt:
            raise argparse.ArgumentTypeError("La date de début doit être avant la date de fin.")
        return (start_dt, end_dt)

    # Sinon, on considère que c'est une durée
    match = re.match(r"^(\d+)([smhdw]?)$", value.lower())
    if not match:
        raise argparse.ArgumentTypeError(
            "Format invalide. Utilise par ex: 10m, 2h, 3d, 1w, juste un nombre (minutes), "
            "ou plage de dates YYYY-MM-DD:YYYY-MM-DD"
        )
    amount, unit = match.groups()
    amount = int(amount)
    multipliers_in_hours = {
        "": 1/60,     # nombre seul → minutes
        "s": 1/3600,  # secondes
        "m": 1/60,    # minutes
        "h": 1,       # heures
        "d": 24,      # jours
        "w": 168      # semaines
    }
    return amount * multipliers_in_hours[unit]



async def update_symbols_periodically(symbols_container: dict, n: int = None, interval_sec: int = None):
    """Update symbols automatically based on volatility and volume"""
    if n is None:
        n = config.strategy.auto_select_top_n
    if interval_sec is None:
        interval_sec = config.strategy.auto_select_update_interval
        
    while True:
        try:
            new_symbols = fetch_top_n_volatility_volume(n=n)
            if new_symbols:
                symbols_container['list'] = new_symbols
                log(f"Symbol auto-update: {new_symbols}")
        except Exception as e:
            log(f"Error updating symbols automatically: {e}")
        await asyncio.sleep(interval_sec)


async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False, symbols_container=None):
    """Main trading loop"""
    while True:
        if auto_select and symbols_container:
            symbols = symbols_container.get('list', [])

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
    """Watch symbol file for changes and reload automatically"""
    last_modified = None
    symbols = []

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                symbols = load_symbols_from_file(filepath)
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
    """Main async function"""
    db_config = config.database
    pg_dsn = config.pg_dsn or os.environ.get("PG_DSN")
    
    pool = await asyncpg.create_pool(
        dsn=pg_dsn,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size
    )

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
                # Plage de dates
                start_dt, end_dt = args.backtest
                for symbol in symbols:
                    log(f"[{symbol}] Starting backtest from {start_dt.date()} to {end_dt.date()} with {args.strategie} strategy")
                    log(f"[DEBUG] Lancement backtest {symbol} de {start_dt.date()} à {end_dt.date()}", level="DEBUG")
                    await run_backtest_async(symbol, (start_dt, end_dt), pg_dsn, args.strategie)
            else:
                # Durée en heures
                for symbol in symbols:
                    log(f"[{symbol}] Starting {args.backtest}h backtest with {args.strategie} strategy")
                    log(f"[DEBUG] Lancement backtest {symbol} pendant {args.backtest} heures", level="DEBUG")
                    await run_backtest_async(symbol, args.backtest, pg_dsn, args.strategie)
        else:
            log("[DEBUG] Mode live (pas de backtest)", level="DEBUG")
            if args.auto_select:
                top_n = config.strategy.auto_select_top_n if not args.no_limit else None
                symbols_container = {'list': fetch_top_n_volatility_volume(n=top_n)}
                updater_task = asyncio.create_task(update_symbols_periodically(symbols_container, n=top_n))
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

    # Load config with custom path if provided
    if args.config != "config/settings.yaml":
        config = load_config(args.config)

    # Use strategy from config if not provided via CLI
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
