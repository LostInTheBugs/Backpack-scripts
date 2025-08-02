import argparse
import os
import time
import traceback
import asyncio
from datetime import datetime, timezone
import asyncpg
import signal
import sys

from utils.logger import log
from utils.i18n import t, set_locale, get_available_locales  # Import i18n
from utils.public import check_table_and_fresh_data, get_last_timestamp, load_symbols_from_file
from utils.public import check_table_and_fresh_data, get_last_timestamp, load_symbols_from_file
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from live.live_engine import handle_live_symbol
from backtest.backtest_engine2 import run_backtest_async

public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")


async def update_symbols_periodically(symbols_container: dict, n: int = 10, interval_sec: int = 300):
    while True:
        try:
            new_symbols = fetch_top_n_volatility_volume(n=n)
            if new_symbols:
                symbols_container['list'] = new_symbols
                log(t("symbols.update_auto", new_symbols))  # Traduction
        except Exception as e:
            log(t("symbols.update_error", e))  # Traduction
        await asyncio.sleep(interval_sec)


async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False, symbols_container=None):
    while True:
        if auto_select and symbols_container:
            symbols = symbols_container.get('list', [])

        active_symbols = []
        ignored_symbols = []

        for symbol in symbols:
            if await check_table_and_fresh_data(pool, symbol, max_age_seconds=600):
                active_symbols.append(symbol)
                await handle_live_symbol(symbol, pool, real_run, dry_run, args=args)
            else:
                ignored_symbols.append(symbol)

        if active_symbols:
            log(t("symbols.active", len(active_symbols), active_symbols))

        ignored_details = []
        if ignored_symbols:
            for sym in ignored_symbols:
                last_ts = await get_last_timestamp(pool, sym)
                if last_ts is None:
                    ignored_details.append(t("symbols.table_missing", sym))
                else:
                    now = datetime.now(timezone.utc)
                    delay = now - last_ts
                    seconds = int(delay.total_seconds())
                    human_delay = t("time.seconds", seconds) if seconds < 120 else t("time.minutes", seconds // 60)
                    ignored_details.append(t("symbols.inactive_since", sym, human_delay))

            if ignored_details:
                log(t("symbols.ignored", len(ignored_details), ignored_details))

        if not active_symbols:
            log(t("symbols.no_active"))

        await asyncio.sleep(1)


async def watch_symbols_file(filepath: str = "symbol.lst", pool=None, real_run: bool = False, dry_run: bool = False):
    last_modified = None
    symbols = []

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                symbols = load_symbols_from_file(filepath)
                log(f"🔁 symbol.lst rechargé : {symbols}")
                last_modified = current_modified

            await main_loop(symbols, pool, real_run=real_run, dry_run=dry_run)
        except KeyboardInterrupt:
            log("🛑 Arrêt manuel demandé")
            break
        except Exception as e:
            log(f"💥 Erreur dans le watcher : {e}")
            traceback.print_exc()

        await asyncio.sleep(1)


async def async_main(args):
    pool = await asyncpg.create_pool(dsn=os.environ.get("PG_DSN"))

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown():
        print("🛑 Arrêt manuel demandé (Ctrl+C)")
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    try:
        if args.backtest:
            if args.symbols:
                symbols = args.symbols.split(",")
            else:
                symbols = load_symbols_from_file()
            for symbol in symbols:
                log(f"[{symbol}] 🧪 Lancement du backtest {args.backtest}h avec stratégie {args.strategie}")
                await run_backtest_async(symbol, args.backtest, os.environ.get("PG_DSN"), args.strategie)
        else:
            if args.auto_select:
                symbols_container = {'list': fetch_top_n_volatility_volume(n=10 if not args.no_limit else None)}
                updater_task = asyncio.create_task(update_symbols_periodically(symbols_container, n=10 if not args.no_limit else None))
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
        print("Pool de connexion fermé, fin du programme.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot for Backpack Exchange")
    parser.add_argument("symbols", nargs="?", default="", help="Liste des symboles")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation")
    parser.add_argument("--backtest", type=int, help="Durée du backtest en heures")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique")
    parser.add_argument('--strategie', type=str, default='Default', help='Nom de la stratégie')
    parser.add_argument("--no-limit", action="store_true", help="Désactive la limite")
    
    # Nouveau argument pour la langue
    parser.add_argument('--lang', '--locale', type=str, default='fr', 
                       choices=get_available_locales(),
                       help='Langue d\'interface (fr, en, es...)')
    
    args = parser.parse_args()
    
    # Configuration de la langue
    set_locale(args.lang)

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
        elif args.strategie in ["Auto", "AutoSoft", "Range"]:
            args.get_combined_signal = None
        else:
            from signals.macd_rsi_breakout import get_combined_signal
            args.get_combined_signal = get_combined_signal

        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("clean_shutdown")
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
