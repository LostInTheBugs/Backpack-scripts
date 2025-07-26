import argparse
import os
import time
import traceback
import asyncio
from datetime import datetime, timedelta, timezone
import pandas as pd
import asyncpg
import signal
import pytz

from With_PGSQL.pgsql_ohlcv import get_ohlcv_1s_sync, fetch_ohlcv_1s
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.get_market import get_market
from utils.position_utils import position_already_open
from utils.ohlcv_utils import get_ohlcv_df
from fetch_top_volume_symbols import fetch_top_n_perp
from backpack_public.public import get_ohlcv
from backtest.backtest_engine import run_backtest, backtest_symbol

POSITION_AMOUNT_USDC = 25
INTERVAL = "1s"
public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

# ... toutes tes fonctions existantes (format_table_name, check_table_and_fresh_data, etc.) ...

async def async_main(args):
    pool = await asyncpg.create_pool(dsn=os.environ.get("PG_DSN"))

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown():
        log("🛑 Arrêt manuel demandé (Ctrl+C)")
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
                await backtest_symbol(symbol, args.backtest)
        else:
            if args.symbols:
                symbols = args.symbols.split(",")
                task = asyncio.create_task(main_loop(symbols, pool, real_run=args.real_run, dry_run=args.dry_run, auto_select=args.auto_select))
                await asyncio.wait([task, stop_event.wait()], return_when=asyncio.FIRST_COMPLETED)
            else:
                task = asyncio.create_task(watch_symbols_file(pool=pool, real_run=args.real_run, dry_run=args.dry_run))
                await asyncio.wait([task, stop_event.wait()], return_when=asyncio.FIRST_COMPLETED)

            # Si stop_event est déclenché, annuler la tâche si toujours active
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    log("Tâche annulée proprement après arrêt manuel")
    finally:
        await pool.close()
        log("Pool de connexion fermé, fin du programme.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", nargs="?", default="", help="Liste des symboles (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation sans exécuter de trade")
    parser.add_argument("--backtest", type=str, help="Exécuter un backtest (ex: 1h, 1d, 1w)")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symboles les plus volatils")

    args = parser.parse_args()

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(async_main(args))
    except KeyboardInterrupt:
        log("🛑 Arrêt manuel détecté dans main")
    except RuntimeError as e:
        log(f"Erreur RuntimeLoop: {e}")
    finally:
        if not loop.is_closed():
            loop.close()
