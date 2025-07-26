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

from WScriptDatabase.pgsql_ohlcv import get_ohlcv_1s_sync, fetch_ohlcv_1s
from signals.macd_rsi_breakout import get_combined_signal
from utils.logger import log
from utils.position_utils import position_already_open
from utils.ohlcv_utils import get_ohlcv_df
from utils.get_market import get_market
from utils.public import get_ohlcv
from utils.fetch_top_volume_symbols import fetch_top_n_perp
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backtest.backtest_engine import run_backtest

POSITION_AMOUNT_USDC = 25
INTERVAL = "1s"
public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

def format_table_name(symbol: str) -> str:
    parts = symbol.lower().split("_")
    return "ohlcv_" + "__".join(parts)

async def check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
    table_name = format_table_name(symbol)
    async with pool.acquire() as conn:
        try:
            recent_rows = await conn.fetch(
                f"""
                SELECT * FROM {table_name}
                WHERE timestamp >= $1
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds),
            )
            return bool(recent_rows)
        except asyncpg.exceptions.UndefinedTableError:
            print(f"❌ Table {table_name} n'existe pas.")
            return False
        except Exception as e:
            print(f"❌ Erreur lors de la vérification de la table {table_name}: {e}")
            return False

async def get_last_timestamp(pool, symbol):
    table_name = format_table_name(symbol)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                f"SELECT timestamp FROM {table_name} ORDER BY timestamp DESC LIMIT 1"
            )
            return row["timestamp"] if row else None
        except asyncpg.exceptions.UndefinedTableError:
            return None

async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool):
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")

        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
            log(f"[{symbol}] Ignoré : pas de données récentes")
            return

        if INTERVAL == "1s":
            end_ts = datetime.now(timezone.utc)
            start_ts = end_ts - timedelta(seconds=60)
            df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)
        else:
            data = get_ohlcv(symbol, INTERVAL)
            if not data:
                log(f"[{symbol}] ❌ Données OHLCV vides")
                return
            df = get_ohlcv_df(symbol, INTERVAL)

        if df.empty:
            log(f"[{symbol}] ❌ DataFrame OHLCV vide après conversion")
            return
        if len(df) < 2:
            log(f"[{symbol}] ⚠️ Pas assez de données (moins de 2 lignes) pour calculer le signal")
            return

        # Correction des timestamps
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)

        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        signal = get_combined_signal(df)
        log(f"[{symbol}] 🎯 Signal détecté : {signal}")

        if signal in ["BUY", "SELL"]:
            if position_already_open(symbol):
                log(f"[{symbol}] ⚠️ Position déjà ouverte — Ignorée")
                return
            direction = "long" if signal == "BUY" else "short"

            if dry_run:
                log(f"[{symbol}] 🧪 DRY-RUN: Simulation d'ouverture position {direction.upper()}")
            elif real_run:
                log(f"[{symbol}] ✅ OUVERTURE position réelle : {direction.upper()}")
                open_position(symbol, POSITION_AMOUNT_USDC, direction)
            else:
                log(f"[{symbol}] ❌ Ni --real-run ni --dry-run spécifié : aucune action")
    except Exception as e:
        log(f"[{symbol}] 💥 Erreur: {e}")
        traceback.print_exc()

async def backtest_symbol(symbol: str, interval: str):
    try:
        from backtest.backtest_engine import run_backtest_async
        log(f"[{symbol}] 🧪 Lancement du backtest en {interval}")
        dsn = os.environ.get("PG_DSN")
        await run_backtest_async(symbol, interval, dsn)
    except ModuleNotFoundError:
        log(f"[{symbol}] ❌ Module backtest non trouvé. Veuillez créer backtest/backtest_engine.py")
    except Exception as e:
        log(f"[{symbol}] 💥 Erreur durant le backtest: {e}")
        traceback.print_exc()

def load_symbols_from_file(filepath: str = "symbol.lst") -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]

async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False):
    if auto_select:
        log("🔍 Mode auto-select actif — sélection des symboles les plus volatils")
        try:
            symbols = fetch_top_n_perp(n=len(symbols))
            log(f"✅ Symboles sélectionnés automatiquement : {symbols}")
        except Exception as e:
            log(f"💥 Erreur sélection symboles auto: {e}")
            return

    while True:  # boucle infinie
        active_symbols = []
        ignored_symbols = []

        for symbol in symbols:
            if await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
                active_symbols.append(symbol)
                await handle_live_symbol(symbol, pool, real_run, dry_run)
            else:
                ignored_symbols.append(symbol)

        if active_symbols:
            log(f"✅ Symboles actifs ({len(active_symbols)}) : {active_symbols}")
        if ignored_symbols:
            ignored_details = []
            for sym in ignored_symbols:
                last_ts = await get_last_timestamp(pool, sym)
                if last_ts is None:
                    ignored_details.append(f"{sym} (table absente)")
                else:
                    ignored_details.append(f"{sym} (dernière donnée : {last_ts.isoformat()})")
            log(f"⛔ Symboles ignorés ({len(ignored_symbols)}) : {ignored_details}")
        if not active_symbols:
            log("⚠️ Aucun symbole actif pour cette itération.")

        await asyncio.sleep(1)  # pause 1 seconde avant prochaine itération

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
                await backtest_symbol(symbol, args.backtest)
        else:
            if args.symbols:
                symbols = args.symbols.split(",")
                task = asyncio.create_task(
                    main_loop(symbols, pool, real_run=args.real_run, dry_run=args.dry_run, auto_select=args.auto_select)
                )
                stop_task = asyncio.create_task(stop_event.wait())
                await asyncio.wait([task, stop_task], return_when=asyncio.FIRST_COMPLETED)
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
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", nargs="?", default="", help="Liste des symboles (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation sans exécuter de trade")
    parser.add_argument("--backtest", type=str, help="Exécuter un backtest (ex: 1h, 1d, 1w)")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symboles les plus volatils")

    args = parser.parse_args()

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("🛑 Arrêt manuel demandé via KeyboardInterrupt, fermeture propre...")
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
